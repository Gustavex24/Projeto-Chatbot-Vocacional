
import os
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="Analisar PDF", layout="centered")
st.title("📄 Analisar PDF")

uploaded_pdf = st.file_uploader("Envie um PDF textual (não escaneado):", type=["pdf"])

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("📤 Enviar PDF"):
        if uploaded_pdf is None:
            st.warning("Selecione um arquivo PDF.")
        else:
            try:
                files = {"file": (uploaded_pdf.name, uploaded_pdf.read(), "application/pdf")}
                res = requests.post(f"{API_URL}/api/upload_pdf", files=files, timeout=300)
                res.raise_for_status()  # Lança exceção para 4xx/5xx

                # Tente decodificar JSON; se falhar, mostre o texto de resposta para depuração
                try:
                    data = res.json()
                except ValueError:
                    st.error(f"Resposta não-JSON da API (até 500 chars):\n\n{res.text[:500]}")
                    raise

                # Backend retorna ok/filename/docs_count. Pode não ter 'message'.
                msg = data.get("message") or f"Enviado! Arquivo: {data.get('filename', 'desconhecido')}"
                st.success(msg)

            except requests.exceptions.HTTPError as e:
                st.error(f"Erro HTTP: {e}\n\nCorpo: {res.text[:500] if 'res' in locals() else ''}")
            except Exception as e:
                st.error(f"Erro ao enviar: {e}")

with col2:
    if st.button("🧹 Limpar PDFs do RAG"):
        try:
            data = requests.post(f"{API_URL}/api/limpar_docs", timeout=60).json()
            st.info(f"Removidos: {data.get('removed', 0)}")
        except Exception as e:
            st.error(f"Erro: {e}")

with col3:
    if st.button("📊 Status do RAG"):
        try:
            data = requests.get(f"{API_URL}/api/rag_status", timeout=30).json()
            st.json(data)
        except Exception as e:
            st.error(f"Erro: {e}")

