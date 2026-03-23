import os
import html
import re
import requests
import streamlit as st

# ================= CONFIG =================
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
TIMEOUT = (10, 120)
MAX_COURSES = 6
LOGO_PATH = "assets/logo.png"

# ================= PAGE =================
st.set_page_config(page_title="Chatbot Vocacional", layout="wide", page_icon="🎓")

# ================= CSS =================
st.markdown(
    """
    <style>
    body { background:#f4f6fb; }
    .block-container { max-width:1100px; }
    .chat-card {
        background:#fff;border-radius:14px;padding:1rem;
        border:1px solid #e5e7eb;margin-bottom:.6rem;
    }
    .intro-box {
        background:#fff;border-radius:16px;padding:1.6rem;
        border:1px solid #e5e7eb;margin-bottom:2rem;
        box-shadow:0 8px 20px rgba(0,0,0,.05);
    }
    .course-card {
        background:#fff;border-radius:14px;padding:1rem;
        margin-bottom:1rem;border-left:6px solid #2563eb;
        box-shadow:0 6px 16px rgba(0,0,0,.07);
    }
    .score-badge {
        background:#16a34a;color:#fff;padding:.3rem .6rem;
        border-radius:999px;font-size:.75rem;font-weight:600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ================= HELPERS =================
def sanitize(text: str) -> str:
    if text is None:
        return ""
    text = html.unescape(text)
    # remove tags HTML após o unescape
    text = re.sub(r"<.*?>", "", text)
    return text

def esc(text: str) -> str:
    return html.escape(str(text)) if text is not None else ""

def post_api(path, payload=None):
    try:
        r = requests.post(f"{API_URL}{path}", json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        st.error("⚠️ Erro ao comunicar com a API.")
        return None

def append(role, content):
    st.session_state.messages.append({"role": role, "content": sanitize(content)})

def card_html(c: dict) -> str:
    return f"""
    <div class="course-card">
        <h4>{esc(c.get('nome'))}</h4>
        <span class="score-badge">Compatibilidade {esc(c.get('score'))}</span>
        <p><strong>Graduação:</strong> {esc(c.get('nivel'))}</p>
        <p><strong>Duração:</strong> {esc(c.get('duracao'))}</p>
        <p><strong>Custo:</strong> {esc(c.get('custo'))}</p>
        <p style="color:#6b7280"><strong>Tags:</strong> {esc(', '.join(c.get('tags', [])))}</p>
    </div>
    """

# ================= STATE =================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "scores" not in st.session_state:
    st.session_state.scores = None
if "recommendations" not in st.session_state:
    st.session_state.recommendations = []
if "perfil_texto" not in st.session_state:
    st.session_state.perfil_texto = None

# ================= HEADER =================
col_logo, col_title = st.columns([0.12, 0.88])
with col_logo:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=80)
with col_title:
    st.title("🎓 Chatbot Vocacional")
    st.caption("Descubra cursos e caminhos profissionais alinhados ao seu perfil")

# ================= SIDEBAR =================
with st.sidebar:
    st.header("⚙️ Controles")

    api_ok = st.session_state.get("_api_ok", None)
    if api_ok is None:
        try:
            r = requests.post(f"{API_URL}/api/reset", timeout=(5, 10))
            st.session_state._api_ok = (r.status_code == 200)
        except Exception:
            st.session_state._api_ok = False
        api_ok = st.session_state._api_ok

    if api_ok:
        st.success("API conectada", icon="✅")
    else:
        st.warning("API indisponível", icon="⚠️")

    if st.button("🗑️ Apagar conversa", use_container_width=True):
        st.session_state.messages = []
        st.session_state.scores = None
        st.session_state.recommendations = []
        st.session_state.perfil_texto = None
        append("assistant", "Conversa limpa. Digite /questionario para começar.")
        st.rerun()

    if st.button("🔄 Resetar bot", use_container_width=True):
        try:
            requests.post(f"{API_URL}/api/reset", timeout=(5, 10))
        except Exception:
            pass
        st.session_state.messages = []
        st.session_state.scores = None
        st.session_state.recommendations = []
        st.session_state.perfil_texto = None
        st.session_state._api_ok = None
        st.rerun()

    st.markdown("---")
    st.caption("💡 Dica: digite **/questionario** no chat para iniciar o teste.")
    with st.expander("Ajuda rápida"):
        st.markdown(
            "- Use *números de 1 a 5* nas respostas do questionário.\n"
            "- Ao finalizar, veja as recomendações ao final da página.\n"
            "- Você pode conversar sobre carreiras e cursos depois."
        )

# ================= INTRO =================
st.markdown(
    """
    <div class="intro-box">
        <h3>👋 Bem-vindo!</h3>
        <p>Este chatbot ajuda você a identificar <strong>cursos e áreas profissionais</strong> compatíveis com seus interesses.</p>
        <h4>🧭 Como funciona</h4>
        <ul>
            <li>Responda um questionário rápido</li>
            <li>Analisamos seu perfil vocacional (RIASEC)</li>
            <li>Você recebe cursos recomendados</li>
        </ul>
        <h4>✅ Como usar</h4>
        <ol>
            <li>Digite <strong>/questionario</strong> no chat</li>
            <li>Responda cada pergunta de <strong>1 a 5</strong></li>
            <li>Veja suas recomendações</li>
        </ol>
    </div>
    """,
    unsafe_allow_html=True,
)

# ================= CHAT =================
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(
            f"<div class='chat-card'>{esc(m['content'])}</div>",
            unsafe_allow_html=True,
        )

user_input = st.chat_input("Digite sua mensagem…")
if user_input:
    append("user", user_input)
    res = post_api("/api/chat", {"message": user_input})
    if res and res.get("text"):
        append("assistant", res["text"])
        if res.get("scores"):
            st.session_state.scores = res["scores"]
            st.session_state.recommendations = res.get("recommendations", [])
            st.session_state.perfil_texto = res.get("perfil_texto")
    st.rerun()

# ================= RESULTADOS =================
if st.session_state.scores:
    st.divider()
    if st.session_state.perfil_texto:
        st.markdown(f"**Resumo do perfil:** {esc(st.session_state.perfil_texto)}")

    st.subheader("🎓 Cursos Recomendados")
    recs = st.session_state.recommendations or []
    for i in range(0, len(recs), 2):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(card_html(recs[i]), unsafe_allow_html=True)
        if i + 1 < len(recs):
            with c2:
                st.markdown(card_html(recs[i + 1]), unsafe_allow_html=True)