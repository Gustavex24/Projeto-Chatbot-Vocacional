
import os
import logging
from io import BytesIO
from typing import Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PyPDF2 import PdfReader

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

ASSETS_DIR = "assets"

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

    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail="Envie um PDF válido.")

    content = await file.read()
    reader = PdfReader(BytesIO(content))

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception:
            raise HTTPException(status_code=400, detail="PDF criptografado.")

    text_parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text.strip())

    full_text = "\n\n".join(text_parts)

    if not full_text.strip():
        raise HTTPException(
            status_code=400,
            detail="PDF não contém texto extraível (possivelmente escaneado)."
        )

    bot.add_custom_document(
        full_text,
        metadata={
            "filename": file.filename,
            "pages": len(reader.pages),
            "source": "upload_pdf"
        }
    )

    logger.info(
        "📄 PDF adicionado: %s | docs=%d",
        file.filename,
        bot.count_custom_documents()
    )

    return {
        "ok": True,
        "filename": file.filename,
        "docs_count": bot.count_custom_documents()
    }

# ======================================================
# RESUMO DO PDF
# ======================================================

@app.post("/api/resumir_pdf")
def resumir_pdf() -> Dict[str, Any]:

    if bot.count_custom_documents() == 0:
        return {
            "ok": False,
            "text": "Nenhum PDF foi enviado ainda."
        }

    prompt = (
        "Faça um resumo claro e objetivo do documento carregado.\n"
        "- Principais ideias\n"
        "- Pontos importantes\n"
        "- Insights práticos\n"
        "Use apenas o conteúdo do contexto."
    )

    resp = bot.chat(prompt)

    return {
        "ok": True,
        "docs_count": bot.count_custom_documents(),
        "text": resp.get("text")
    }

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
    return {
        "custom_documents": bot.count_custom_documents()
    }
