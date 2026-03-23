# src/api.py
import os
import logging
from io import BytesIO
from typing import Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError

try:
    # Quando rodar com: uvicorn api:app --app-dir src
    from bot import BetterChatbot
except ModuleNotFoundError:
    # Fallback quando rodar com: uvicorn src.api:app (src como pacote)
    from src.bot import BetterChatbot

# ======================================================
# LOGGING
# ======================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("chatbot")

# ======================================================
# ENV
# ======================================================

load_dotenv()

# ======================================================
# FASTAPI
# ======================================================

app = FastAPI(title="API Chatbot Vocacional")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================================================
# BOT
# ======================================================

ASSETS_DIR = "assets"  # ajuste se necessário (deve conter cursos.json)

bot = BetterChatbot(
    azure_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
    azure_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01"),
    deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT", ""),
    course_text="",
    catalog_path=os.path.join(ASSETS_DIR, "cursos.json"),
    temperature=0.2,
    max_context_chars=5000,
)

logger.info("✅ BetterChatbot inicializado")

# ======================================================
# ROOT
# ======================================================

@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "message": "API do Chatbot Vocacional ativa.",
        "endpoints": [
            "/api/chat",
            "/api/reset",
            "/api/catalogo",
            "/api/upload_pdf",
            "/api/resumir_pdf",
            "/api/limpar_docs",
            "/api/rag_status",
        ],
    }

# ======================================================
# CHAT
# ======================================================

@app.post("/api/chat")
def api_chat(payload: Dict[str, Any]) -> Dict[str, Any]:
    message = payload.get("message", "")
    return bot.chat(message)

@app.post("/api/reset")
def api_reset() -> Dict[str, Any]:
    return bot.reset()

@app.get("/api/catalogo")
def api_catalogo() -> Dict[str, Any]:
    return {"total": len(bot.cursos)}

# ======================================================
# UPLOAD PDF
# ======================================================

@app.post("/api/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)) -> Dict[str, Any]:
    try:
        if file.content_type not in ("application/pdf", "application/octet-stream"):
            raise HTTPException(status_code=415, detail="Envie um PDF válido (content-type PDF).")

        content = await file.read()
        size_bytes = len(content) if content else 0
        logger.info("📥 Recebido PDF: name=%s content_type=%s size=%dB",
                    file.filename, file.content_type, size_bytes)

        if size_bytes == 0:
            raise HTTPException(status_code=400, detail="Arquivo vazio.")

        # Abrir PDF
        try:
            reader = PdfReader(BytesIO(content))
        except PdfReadError as e:
            logger.exception("Erro do PyPDF2 ao abrir o PDF")
            raise HTTPException(status_code=400, detail=f"PDF inválido ou corrompido: {e}")

        # Criptografia
        if getattr(reader, "is_encrypted", False):
            try:
                result = reader.decrypt("")  # algumas versões retornam 0 quando falha
                if result == 0:
                    raise HTTPException(status_code=400, detail="PDF criptografado (senha requerida).")
            except Exception:
                raise HTTPException(status_code=400, detail="PDF criptografado (não foi possível descriptografar).")

        # Páginas
        try:
            num_pages = len(reader.pages)
        except Exception as e:
            logger.exception("Falha ao ler páginas do PDF")
            raise HTTPException(status_code=400, detail=f"Não foi possível ler as páginas do PDF: {e}")

        if num_pages == 0:
            raise HTTPException(status_code=400, detail="PDF sem páginas.")

        # Extrair texto
        text_parts = []
        for idx, page in enumerate(reader.pages):
            try:
                text = page.extract_text()
            except Exception as e:
                logger.exception("Falha ao extrair texto da página %d", idx)
                raise HTTPException(status_code=400, detail=f"Falha ao extrair texto da página {idx+1}: {e}")
            if text and text.strip():
                text_parts.append(text.strip())

        full_text = "\n\n".join(text_parts)
        if not full_text.strip():
            raise HTTPException(
                status_code=400,
                detail="PDF não contém texto extraível (possivelmente escaneado)."
            )

        # RAG
        bot.add_custom_document(
            full_text,
            metadata={
                "filename": file.filename,
                "pages": num_pages,
                "source": "upload_pdf"
            }
        )

        docs_count = bot.count_custom_documents()
        logger.info("📄 PDF adicionado com sucesso: %s | pages=%d | docs=%d",
                    file.filename, num_pages, docs_count)

        return {
            "ok": True,
            "filename": file.filename,
            "docs_count": docs_count,
            "message": f"PDF '{file.filename}' enviado com sucesso."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erro inesperado em /api/upload_pdf")
        raise HTTPException(status_code=500, detail=f"Erro interno ao processar o PDF: {e}")

# ======================================================
# RESUMO DO PDF
# ======================================================

@app.post("/api/resumir_pdf")
def resumir_pdf() -> Dict[str, Any]:
    if bot.count_custom_documents() == 0:
        return {"ok": False, "text": "Nenhum PDF foi enviado ainda."}

    prompt = (
        "Faça um resumo claro e objetivo do documento carregado.\n"
        "- Principais ideias\n"
        "- Pontos importantes\n"
        "- Insights práticos\n"
        "Use apenas o conteúdo do contexto."
    )
    resp = bot.chat(prompt)
    return {"ok": True, "docs_count": bot.count_custom_documents(), "text": resp.get("text")}

# ======================================================
# LIMPAR DOCS
# ======================================================

@app.post("/api/limpar_docs")
def limpar_docs() -> Dict[str, Any]:
    removed = bot.clear_custom_documents()
    logger.info("🧹 Documentos removidos: %d", removed)
    return {"ok": True, "removed": removed}

# ======================================================
# STATUS RAG
# ======================================================

@app.get("/api/rag_status")
def rag_status() -> Dict[str, Any]:
    return {"custom_documents": bot.count_custom_documents()}