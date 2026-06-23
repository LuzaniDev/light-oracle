import streamlit as st
import sys, os, json, time, random, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle.utils.config import OracleConfig
from oracle.engine import OracleEngine
from oracle.pipeline.live import LivePipeline
from oracle.pipeline.persistent import PersistentPipeline

st.set_page_config(
    page_title="Oraculo RAG",
    page_icon=chr(10052),
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Inter:wght@300;400;600;700&display=swap');
    * { font-family: 'Inter', sans-serif; }
    .stApp { background: linear-gradient(135deg, #0a0a1a 0%, #1a0a2e 30%, #0a1a2e 60%, #0a0a1a 100%); background-attachment: fixed; }
    .main-title { font-family: 'Orbitron', monospace; font-size: 3.5rem; font-weight: 900; background: linear-gradient(135deg, #00d4ff, #7b2ff7, #ff2d95); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; margin-bottom: 0; animation: glow 3s ease-in-out infinite alternate; }
    @keyframes glow { from { filter: drop-shadow(0 0 10px rgba(0,212,255,0.3)); } to { filter: drop-shadow(0 0 25px rgba(123,47,247,0.6)); } }
    .subtitle { text-align: center; color: #8888aa; font-size: 1.1rem; margin-top: -10px; margin-bottom: 30px; letter-spacing: 3px; text-transform: uppercase; }
    .particles { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 0; overflow: hidden; }
    .particle { position: absolute; width: 3px; height: 3px; background: rgba(0,212,255,0.6); border-radius: 50%; animation: float linear infinite; }
    @keyframes float { 0% { transform: translateY(100vh) scale(0); opacity: 0; } 10% { opacity: 1; } 90% { opacity: 1; } 100% { transform: translateY(-10vh) scale(1); opacity: 0; } }
    .chat-container { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 20px; margin-bottom: 20px; backdrop-filter: blur(10px); }
    .msg-user { background: linear-gradient(135deg, rgba(123,47,247,0.15), rgba(0,212,255,0.1)); border: 1px solid rgba(123,47,247,0.2); border-radius: 12px; padding: 12px 18px; margin-bottom: 12px; animation: slideIn 0.3s ease-out; }
    .msg-oracle { background: linear-gradient(135deg, rgba(0,212,255,0.08), rgba(123,47,247,0.08)); border: 1px solid rgba(0,212,255,0.15); border-radius: 12px; padding: 12px 18px; margin-bottom: 12px; animation: slideIn 0.4s ease-out; position: relative; overflow: hidden; }
    .msg-oracle::before { content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%; background: radial-gradient(circle, rgba(0,212,255,0.03) 0%, transparent 70%); animation: pulse 4s ease-in-out infinite; }
    @keyframes slideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    @keyframes pulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.1); } }
    .badge { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; margin-right: 6px; }
    .badge-ok { background: rgba(0,200,100,0.2); color: #00c864; border: 1px solid rgba(0,200,100,0.3); }
    .badge-warn { background: rgba(255,200,0,0.2); color: #ffc800; border: 1px solid rgba(255,200,0,0.3); }
    .badge-err { background: rgba(255,50,50,0.2); color: #ff3232; border: 1px solid rgba(255,50,50,0.3); }
    .stTextInput>div>div { background: rgba(255,255,255,0.05) !important; border: 1px solid rgba(0,212,255,0.2) !important; border-radius: 12px !important; color: white !important; }
    .stTextInput>div>div:focus-within { border-color: rgba(0,212,255,0.6) !important; box-shadow: 0 0 20px rgba(0,212,255,0.1) !important; }
    .stButton>button { background: linear-gradient(135deg, #7b2ff7, #00d4ff) !important; border: none !important; border-radius: 12px !important; color: white !important; font-weight: 600 !important; padding: 10px 28px !important; transition: all 0.3s ease !important; text-transform: uppercase; letter-spacing: 1px; }
    .stButton>button:hover { transform: translateY(-2px) scale(1.02); box-shadow: 0 0 30px rgba(123,47,247,0.4); }
    .stFileUploader>div { background: rgba(255,255,255,0.03) !important; border: 2px dashed rgba(0,212,255,0.2) !important; border-radius: 12px !important; }
    .stFileUploader>div:hover { border-color: rgba(0,212,255,0.5) !important; }
    .metric-card { text-align: center; padding: 15px; background: rgba(255,255,255,0.03); border-radius: 12px; border: 1px solid rgba(255,255,255,0.06); }
    .metric-value { font-family: 'Orbitron', monospace; font-size: 2rem; font-weight: 700; background: linear-gradient(135deg, #00d4ff, #7b2ff7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .metric-label { color: #8888aa; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; }
    .typing-dots { display: inline-block; padding: 12px 18px; background: rgba(255,255,255,0.03); border-radius: 12px; border: 1px solid rgba(0,212,255,0.1); margin-bottom: 12px; }
    .typing-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #00d4ff; margin: 0 3px; animation: tb 1.4s ease-in-out infinite; }
    .typing-dot:nth-child(2) { animation-delay:0.2s; } .typing-dot:nth-child(3) { animation-delay:0.4s; }
    @keyframes tb { 0%,60%,100% { transform:translateY(0); } 30% { transform:translateY(-8px); } }
    ::-webkit-scrollbar { width:6px; } ::-webkit-scrollbar-track { background:transparent; } ::-webkit-scrollbar-thumb { background:rgba(0,212,255,0.3); border-radius:10px; }
    .sb-section { margin-bottom:20px; padding:10px; background:rgba(255,255,255,0.02); border-radius:8px; border:1px solid rgba(255,255,255,0.05); }
    .sb-title { font-size:0.7rem; text-transform:uppercase; letter-spacing:2px; color:#666688; margin-bottom:10px; }
    .dot-online { display:inline-block; width:8px; height:8px; border-radius:50%; background:#00c864; animation: blink 2s ease-in-out infinite; margin-right:6px; }
    @keyframes blink { 0%,100% { opacity:1; } 50% { opacity:0.3; } }
    h1,h2,h3,h4,h5,h6,p,span,div,label { color:#ddd !important; }
    .footer { text-align:center; color:#444466; font-size:0.75rem; padding:20px 0; border-top:1px solid rgba(255,255,255,0.03); margin-top:30px; }
    .fa-icon { margin-right: 6px; }
</style>
""", unsafe_allow_html=True)

def ic(name):
    return f'<i class="fas fa-{name} fa-icon"></i>'

ICONS = {
    "oracle": ic("crystal-ball"),
    "bolt": ic("bolt"),
    "doc": ic("file-alt"),
    "trash": ic("trash-alt"),
    "chart": ic("chart-bar"),
    "bulb": ic("lightbulb"),
    "user": ic("user"),
    "globe": ic("globe-americas"),
    "check": ic("check-circle"),
    "x": ic("times-circle"),
    "alert": ic("exclamation-circle"),
    "send": ic("paper-plane"),
    "file": ic("file-upload"),
    "cpu": ic("microchip"),
    "layers": ic("layer-group"),
    "db": ic("database"),
    "search": ic("search"),
    "info": ic("info-circle"),
}

particles = '<div class="particles">'
for i in range(25):
    particles += f'<div class="particle" style="left:{random.randint(0,100)}%;animation-delay:{random.uniform(0,15)}s;animation-duration:{random.uniform(10,25)}s;width:{random.uniform(2,5)}px;height:{random.uniform(2,5)}px;background:{random.choice(["rgba(0,212,255,0.6)","rgba(123,47,247,0.6)","rgba(255,45,149,0.4)"])}"></div>'
particles += "</div>"
st.markdown(particles, unsafe_allow_html=True)

st.markdown(f'<p class="main-title">{ICONS["oracle"]} ORACULO RAG</p>', unsafe_allow_html=True)
st.markdown(f'<p class="subtitle">{ICONS["bolt"]} Consulta Inteligente com Self-RAG {ICONS["bolt"]}</p>', unsafe_allow_html=True)

def init():
    if "oracle" not in st.session_state:
        config = OracleConfig()
        st.session_state.engine = OracleEngine(config)
        st.session_state.live = LivePipeline(st.session_state.engine)
        st.session_state.persistent = PersistentPipeline(st.session_state.engine)
        st.session_state.msgs = []
        st.session_state.current_file = None
init()

with st.sidebar:
    st.markdown('<div class="sb-section"><div class="sb-title">Status do Sistema</div></div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1: st.markdown(f'<div class="metric-card"><span class="dot-online"></span><div class="metric-label">Online</div></div>', unsafe_allow_html=True)
    with c2:
        d = st.session_state.persistent.stats()["documentos_indexados"]
        st.markdown(f'<div class="metric-card"><div class="metric-value">{d}</div><div class="metric-label">Chunks</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="sb-section"><div class="sb-title">Upload de Arquivo</div></div>', unsafe_allow_html=True)
    uf = st.file_uploader("Upload", type=["txt","md","csv","pdf","html","htm"], label_visibility="collapsed")
    if uf:
        ext = os.path.splitext(uf.name)[1].lower()
        tmp = os.path.join(tempfile.gettempdir(), uf.name)
        if ext == ".pdf":
            with open(tmp, "wb") as f: f.write(uf.getbuffer())
        else:
            with open(tmp, "w", encoding="utf-8") as f: f.write(uf.read().decode("utf-8", errors="replace"))
        st.session_state.current_file = tmp

    if st.session_state.current_file:
        st.markdown(f'<div class="sb-section"><div style="color:#8888aa;font-size:0.8rem">{ICONS["doc"]} Arquivo:</div><div style="color:#00d4ff;font-size:0.9rem">{os.path.basename(st.session_state.current_file)}</div></div>', unsafe_allow_html=True)
        if st.button(f'{ICONS["trash"]} Limpar', use_container_width=True):
            st.session_state.current_file = None; st.rerun()

    st.markdown('<div class="sb-section"><div class="sb-title">Acoes</div></div>', unsafe_allow_html=True)
    if st.button(f'{ICONS["chart"]} Estatisticas', use_container_width=True):
        s = st.session_state.persistent.stats(); st.info(f"Chunks indexados: {s['documentos_indexados']}")
    if st.button(f'{ICONS["trash"]} Limpar Conversa', use_container_width=True):
        st.session_state.msgs = []; st.rerun()

    st.markdown('<div class="sb-section"><div class="sb-title">Exemplos</div></div>', unsafe_allow_html=True)
    for ex in ["Qual o faturamento total?","Liste os produtos vendidos","Explique as regras tributarias"]:
        if st.button(f'{ICONS["bulb"]} {ex}', use_container_width=True, type="secondary"):
            st.session_state.suggested = ex

    st.markdown(f'<div class="footer">{ICONS["cpu"]} Oraculo RAG v0.1<br>CPU {ICONS["bolt"]} Self-RAG</div>', unsafe_allow_html=True)

with st.container():
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    for msg in st.session_state.msgs:
        if msg["role"] == "user":
            st.markdown(f'<div class="msg-user"><strong>{ICONS["user"]} Voce</strong><br>{msg["content"]}</div>', unsafe_allow_html=True)
        else:
            conf = msg.get("confidence", 0)
            bcls = "badge-ok" if conf >= 0.60 else ("badge-warn" if conf >= 0.40 else "badge-err")
            bic = ICONS["check"] if conf >= 0.60 else (ICONS["alert"] if conf >= 0.40 else ICONS["x"])
            blbl = {"[Supported]":"Suportado","[Partially]":"Parcial","[No Support]":"Nao encontrado"}.get(msg.get("decision",""),"")
            src = ""
            if msg.get("chunks"):
                src = '<div style="margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.05)"><small style="color:#666">Fontes:</small><br>'
                for c in msg["chunks"][:3]: src += f'<small style="color:#888">{ICONS["doc"]} {c["source"]} ({c["score"]:.0%})</small><br>'
                src += '</div>'
            st.markdown(f'<div class="msg-oracle"><strong>{ICONS["oracle"]} Oraculo</strong> <span class="badge {bcls}">{bic} {blbl}</span> <span style="color:#888;font-size:0.8rem">Confianca: {conf:.0%}</span><br>{msg["content"]}{src}</div>', unsafe_allow_html=True)
    if st.session_state.get("typing"):
        st.markdown('<div class="typing-dots"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

suggested = st.session_state.pop("suggested", None)
q_input = st.text_input("Pergunta", key="q", placeholder="Ex: Qual o valor do pedido #456?", label_visibility="collapsed")
query = suggested if suggested else q_input

c1, c2, c3 = st.columns([6, 1, 1])
with c2: send = st.button(f'{ICONS["send"]} Perguntar', use_container_width=True)
with c3: web = st.checkbox(f'{ICONS["globe"]} Web', help="Busca na web como fallback")

if send and query:
    st.session_state.msgs.append({"role": "user", "content": query})
    st.session_state.typing = True
    with st.spinner("Consultando..."):
        t0 = time.time()
        if st.session_state.current_file:
            r = st.session_state.live.ask(st.session_state.current_file, query)
        else:
            r = st.session_state.persistent.ask(query)
            if (r["decision"] == "[No Support]" or r["confidence"] < 0.4) and web:
                wr = st.session_state.engine._web_fallback(query)
                if wr["decision"] != "[No Support]" and wr.get("answer"): r = wr
        dt = time.time() - t0
    st.session_state.typing = False
    ans = r.get("answer", "") or "Nao encontrei informacao suficiente."
    st.session_state.msgs.append({"role": "oracle", "content": ans[:500], "decision": r.get("decision","[No Support]"), "confidence": r.get("confidence",0), "time": f"{dt:.1f}s", "chunks": r.get("chunks",[])})
    st.session_state.current_file = None
    st.rerun()

if not st.session_state.msgs:
    st.markdown(f"""
    <div style="text-align:center;padding:60px 20px">
        <div style="margin-bottom:20px">{ICONS["search"]}</div>
        <h3 style="color:#8888aa;font-weight:300">Faca uma pergunta para comecar</h3>
        <p style="color:#666688;font-size:0.9rem">Envie um arquivo ou use documentos indexados<br>O Oraculo usa Self-RAG para decidir como responder</p>
        <div style="display:flex;gap:10px;justify-content:center;margin-top:20px">
            <span style="padding:5px 12px;background:rgba(0,212,255,0.1);border:1px solid rgba(0,212,255,0.2);border-radius:8px;font-size:0.8rem;color:#00d4ff">{ICONS["doc"]} PDF</span>
            <span style="padding:5px 12px;background:rgba(123,47,247,0.1);border:1px solid rgba(123,47,247,0.2);border-radius:8px;font-size:0.8rem;color:#7b2ff7">{ICONS["file"]} TXT</span>
            <span style="padding:5px 12px;background:rgba(255,45,149,0.1);border:1px solid rgba(255,45,149,0.2);border-radius:8px;font-size:0.8rem;color:#ff2d95">{ICONS["layers"]} CSV</span>
            <span style="padding:5px 12px;background:rgba(0,200,100,0.1);border:1px solid rgba(0,200,100,0.2);border-radius:8px;font-size:0.8rem;color:#00c864">{ICONS["db"]} SQL</span>
            <span style="padding:5px 12px;background:rgba(255,200,0,0.1);border:1px solid rgba(255,200,0,0.2);border-radius:8px;font-size:0.8rem;color:#ffc800">{ICONS["globe"]} Web</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
