import streamlit as st
import sys, os, json, time, random, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle.utils.config import OracleConfig
from oracle.engine import OracleEngine
from oracle.pipeline.live import LivePipeline
from oracle.pipeline.persistent import PersistentPipeline

st.set_page_config(
    page_title="Oráculo RAG",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Inter:wght@300;400;600;700&display=swap');

    * { font-family: 'Inter', sans-serif; }

    .stApp {
        background: linear-gradient(135deg, #0a0a1a 0%, #1a0a2e 30%, #0a1a2e 60%, #0a0a1a 100%);
        background-attachment: fixed;
    }

    .main-title {
        font-family: 'Orbitron', monospace;
        font-size: 3.5rem;
        font-weight: 900;
        background: linear-gradient(135deg, #00d4ff, #7b2ff7, #ff2d95);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0;
        animation: glow 3s ease-in-out infinite alternate;
    }

    @keyframes glow {
        from { filter: drop-shadow(0 0 10px rgba(0,212,255,0.3)); }
        to { filter: drop-shadow(0 0 25px rgba(123,47,247,0.6)); }
    }

    .subtitle {
        text-align: center;
        color: #8888aa;
        font-size: 1.1rem;
        margin-top: -10px;
        margin-bottom: 30px;
        letter-spacing: 3px;
        text-transform: uppercase;
    }

    .particles {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        z-index: 0;
        overflow: hidden;
    }

    .particle {
        position: absolute;
        width: 3px;
        height: 3px;
        background: rgba(0, 212, 255, 0.6);
        border-radius: 50%;
        animation: float linear infinite;
    }

    @keyframes float {
        0% { transform: translateY(100vh) scale(0); opacity: 0; }
        10% { opacity: 1; }
        90% { opacity: 1; }
        100% { transform: translateY(-10vh) scale(1); opacity: 0; }
    }

    .chat-container {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 20px;
        backdrop-filter: blur(10px);
    }

    .message-user {
        background: linear-gradient(135deg, rgba(123, 47, 247, 0.15), rgba(0, 212, 255, 0.1));
        border: 1px solid rgba(123, 47, 247, 0.2);
        border-radius: 12px;
        padding: 12px 18px;
        margin-bottom: 12px;
        animation: slideIn 0.3s ease-out;
    }

    .message-oracle {
        background: linear-gradient(135deg, rgba(0, 212, 255, 0.08), rgba(123, 47, 247, 0.08));
        border: 1px solid rgba(0, 212, 255, 0.15);
        border-radius: 12px;
        padding: 12px 18px;
        margin-bottom: 12px;
        animation: slideIn 0.4s ease-out;
        position: relative;
        overflow: hidden;
    }

    .message-oracle::before {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle, rgba(0,212,255,0.03) 0%, transparent 70%);
        animation: pulse 4s ease-in-out infinite;
    }

    @keyframes slideIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }

    @keyframes pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.1); }
    }

    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 6px;
    }

    .badge-supported { background: rgba(0, 200, 100, 0.2); color: #00c864; border: 1px solid rgba(0, 200, 100, 0.3); }
    .badge-partial { background: rgba(255, 200, 0, 0.2); color: #ffc800; border: 1px solid rgba(255, 200, 0, 0.3); }
    .badge-nosupport { background: rgba(255, 50, 50, 0.2); color: #ff3232; border: 1px solid rgba(255, 50, 50, 0.3); }

    .cyber-card {
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(0, 212, 255, 0.1);
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        transition: all 0.3s ease;
    }

    .cyber-card:hover {
        border-color: rgba(0, 212, 255, 0.3);
        box-shadow: 0 0 20px rgba(0, 212, 255, 0.05);
        transform: translateY(-2px);
    }

    .stTextInput > div > div {
        background: rgba(255, 255, 255, 0.05) !important;
        border: 1px solid rgba(0, 212, 255, 0.2) !important;
        border-radius: 12px !important;
        color: white !important;
    }

    .stTextInput > div > div:focus-within {
        border-color: rgba(0, 212, 255, 0.6) !important;
        box-shadow: 0 0 20px rgba(0, 212, 255, 0.1) !important;
    }

    .stButton > button {
        background: linear-gradient(135deg, #7b2ff7, #00d4ff) !important;
        border: none !important;
        border-radius: 12px !important;
        color: white !important;
        font-weight: 600 !important;
        padding: 10px 28px !important;
        transition: all 0.3s ease !important;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .stButton > button:hover {
        transform: translateY(-2px) scale(1.02);
        box-shadow: 0 0 30px rgba(123, 47, 247, 0.4);
    }

    .stFileUploader > div {
        background: rgba(255, 255, 255, 0.03) !important;
        border: 2px dashed rgba(0, 212, 255, 0.2) !important;
        border-radius: 12px !important;
    }

    .stFileUploader > div:hover {
        border-color: rgba(0, 212, 255, 0.5) !important;
    }

    .metric-card {
        text-align: center;
        padding: 15px;
        background: rgba(255, 255, 255, 0.03);
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.06);
    }

    .metric-value {
        font-family: 'Orbitron', monospace;
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #00d4ff, #7b2ff7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    .metric-label {
        color: #8888aa;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .typing-indicator {
        display: inline-block;
        padding: 12px 18px;
        background: rgba(255, 255, 255, 0.03);
        border-radius: 12px;
        border: 1px solid rgba(0, 212, 255, 0.1);
        margin-bottom: 12px;
    }

    .typing-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #00d4ff;
        margin: 0 3px;
        animation: typingBounce 1.4s ease-in-out infinite;
    }

    .typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-dot:nth-child(3) { animation-delay: 0.4s; }

    @keyframes typingBounce {
        0%, 60%, 100% { transform: translateY(0); }
        30% { transform: translateY(-8px); }
    }

    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(0, 212, 255, 0.3); border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(0, 212, 255, 0.5); }

    .sidebar-section {
        margin-bottom: 20px;
        padding: 10px;
        background: rgba(255, 255, 255, 0.02);
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.05);
    }

    .sidebar-section-title {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 2px;
        color: #666688;
        margin-bottom: 10px;
    }

    .status-online {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #00c864;
        animation: blink 2s ease-in-out infinite;
        margin-right: 6px;
    }

    @keyframes blink {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.3; }
    }

    h1, h2, h3, h4, h5, h6, p, span, div, label {
        color: #ddd !important;
    }

    .footer {
        text-align: center;
        color: #444466;
        font-size: 0.75rem;
        padding: 20px 0;
        border-top: 1px solid rgba(255, 255, 255, 0.03);
        margin-top: 30px;
    }
</style>
""", unsafe_allow_html=True)

particles_html = """
<div class="particles">
"""
for i in range(30):
    x = random.randint(0, 100)
    delay = random.uniform(0, 15)
    duration = random.uniform(10, 25)
    size = random.uniform(2, 5)
    colors = ["rgba(0, 212, 255, 0.6)", "rgba(123, 47, 247, 0.6)", "rgba(255, 45, 149, 0.4)"]
    color = random.choice(colors)
    particles_html += f'<div class="particle" style="left:{x}%;animation-delay:{delay}s;animation-duration:{duration}s;width:{size}px;height:{size}px;background:{color}"></div>'
particles_html += "</div>"

st.markdown(particles_html, unsafe_allow_html=True)

st.markdown('<p class="main-title">🔮 ORÁCULO RAG</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">⚡ Consulta Inteligente com Self-RAG ⚡</p>', unsafe_allow_html=True)

if "oracle" not in st.session_state:
    with st.spinner("Inicializando Oráculo..."):
        config = OracleConfig()
        st.session_state.engine = OracleEngine(config)
        st.session_state.live = LivePipeline(st.session_state.engine)
        st.session_state.persistent = PersistentPipeline(st.session_state.engine)
        st.session_state.messages = []
        st.session_state.current_file = None
        st.session_state.model_loaded = True

with st.sidebar:
    st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-section-title">Status do Sistema</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f'<div class="metric-card"><span class="status-online"></span><div class="metric-label">Online</div></div>', unsafe_allow_html=True)
    with col2:
        docs = st.session_state.persistent.stats()["documentos_indexados"]
        st.markdown(f'<div class="metric-card"><div class="metric-value">{docs}</div><div class="metric-label">Chunks</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-section-title">Upload de Arquivo</div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("", type=["txt", "md", "csv", "pdf", "html", "htm"], label_visibility="collapsed")
    if uploaded_file is not None:
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext in [".txt", ".md", ".csv", ".html", ".htm"]:
            text = uploaded_file.read().decode("utf-8", errors="replace")
            tmp_path = os.path.join(tempfile.gettempdir(), uploaded_file.name)
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(text)
            st.session_state.current_file = tmp_path
            st.success(f"📄 {uploaded_file.name} carregado")
        elif ext == ".pdf":
            tmp_path = os.path.join(tempfile.gettempdir(), uploaded_file.name)
            with open(tmp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.session_state.current_file = tmp_path
            st.success(f"📄 {uploaded_file.name} carregado")
    st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.current_file:
        st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
        st.markdown(f'<div style="color:#8888aa;font-size:0.8rem">📎 Arquivo ativo:</div><div style="color:#00d4ff">{os.path.basename(st.session_state.current_file)}</div>', unsafe_allow_html=True)
        if st.button("🧹 Limpar arquivo", use_container_width=True):
            st.session_state.current_file = None
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-section-title">Ações Rápidas</div>', unsafe_allow_html=True)
    if st.button("📊 Estatísticas", use_container_width=True):
        stats = st.session_state.persistent.stats()
        st.info(f"Documentos indexados: {stats['documentos_indexados']}")
    if st.button("🗑️ Limpar Conversa", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-section-title">Exemplos</div>', unsafe_allow_html=True)
    examples = [
        "Qual o faturamento total?",
        "Liste os produtos vendidos",
        "Explique as regras tributarias",
    ]
    for ex in examples:
        if st.button(f"💡 {ex}", use_container_width=True, type="secondary"):
            st.session_state.suggested_query = ex
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(f'<div class="footer">Oráculo RAG v0.1<br>CPU Inference • Self-RAG</div>', unsafe_allow_html=True)

chat_container = st.container()

with chat_container:
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)

    for msg in st.session_state.messages:
        role = msg["role"]
        css = "message-user" if role == "user" else "message-oracle"
        prefix = "🧑 Você" if role == "user" else "🔮 Oráculo"

        with st.container():
            if role == "user":
                st.markdown(f'<div class="{css}"><strong>{prefix}</strong><br>{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                decision = msg.get("decision", "")
                conf = msg.get("confidence", 0)
                badge_class = "badge-supported" if conf >= 0.60 else ("badge-partial" if conf >= 0.40 else "badge-nosupport")
                badge_label = {"[Supported]": "Suportado", "[Partially]": "Parcial", "[No Support]": "Não encontrado"}.get(decision, decision)

                sources_html = ""
                if msg.get("chunks"):
                    sources_html = '<div style="margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,0.05)"><small style="color:#666">Fontes:</small><br>'
                    for c in msg["chunks"][:3]:
                        sources_html += f'<small style="color:#888">📄 {c["source"]} ({c["score"]:.0%})</small><br>'
                    sources_html += '</div>'

                st.markdown(f'''
                <div class="{css}">
                    <strong>{prefix}</strong>
                    <span class="badge {badge_class}">{badge_label}</span>
                    <span style="color:#888;font-size:0.8rem">Confiança: {conf:.0%}</span>
                    <br>{msg["content"]}
                    {sources_html}
                </div>
                ''', unsafe_allow_html=True)

    if st.session_state.get("show_typing", False):
        st.markdown('<div class="typing-indicator"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

query = st.session_state.pop("suggested_query", st.text_input(
    "Faça sua pergunta...",
    key="query_input",
    placeholder="Ex: Qual o valor do pedido #456?",
    label_visibility="collapsed",
))

col1, col2, col3 = st.columns([6, 1, 1])
with col2:
    send = st.button("🔮 Perguntar", use_container_width=True)
with col3:
    web_mode = st.checkbox("🌐 Web", help="Ativar busca na web como fallback")

if send and query:
    st.session_state.messages.append({"role": "user", "content": query})
    st.session_state.show_typing = True

    with st.spinner("Consultando o Oráculo..."):
        start = time.time()

        if st.session_state.current_file:
            result = st.session_state.live.ask(st.session_state.current_file, query)
        else:
            result = st.session_state.persistent.ask(query)

            if (result["decision"] == "[No Support]" or result["confidence"] < 0.4) and web_mode:
                web_result = st.session_state.engine._web_fallback(query)
                if web_result["decision"] != "[No Support]" and web_result.get("answer"):
                    result = web_result

        elapsed = time.time() - start

    st.session_state.show_typing = False
    answer = result.get("answer", "") or ""
    if not answer:
        answer = "Não encontrei informação suficiente."

    msg = {
        "role": "oracle",
        "content": answer[:500],
        "decision": result.get("decision", "[No Support]"),
        "confidence": result.get("confidence", 0),
        "time": f"{elapsed:.1f}s",
        "chunks": result.get("chunks", []),
    }
    st.session_state.messages.append(msg)

    if st.session_state.current_file:
        st.session_state.current_file = None

    st.rerun()

if not st.session_state.messages:
    st.markdown("""
    <div style="text-align:center;padding:60px 20px">
        <div style="font-size:3rem;margin-bottom:20px">🔮</div>
        <h3 style="color:#8888aa;font-weight:300">Faça uma pergunta para começar</h3>
        <p style="color:#666688;font-size:0.9rem">
            Envie um arquivo ou use documentos indexados<br>
            O Oráculo usa Self-RAG para decidir como responder
        </p>
        <div style="display:flex;gap:10px;justify-content:center;margin-top:20px">
            <span style="padding:5px 12px;background:rgba(0,212,255,0.1);border-radius:8px;border:1px solid rgba(0,212,255,0.2);font-size:0.8rem;color:#00d4ff">PDF</span>
            <span style="padding:5px 12px;background:rgba(123,47,247,0.1);border-radius:8px;border:1px solid rgba(123,47,247,0.2);font-size:0.8rem;color:#7b2ff7">TXT</span>
            <span style="padding:5px 12px;background:rgba(255,45,149,0.1);border-radius:8px;border:1px solid rgba(255,45,149,0.2);font-size:0.8rem;color:#ff2d95">CSV</span>
            <span style="padding:5px 12px;background:rgba(0,200,100,0.1);border-radius:8px;border:1px solid rgba(0,200,100,0.2);font-size:0.8rem;color:#00c864">SQL</span>
            <span style="padding:5px 12px;background:rgba(255,200,0,0.1);border-radius:8px;border:1px solid rgba(255,200,0,0.2);font-size:0.8rem;color:#ffc800">HTML</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
