import sys, os, json, time, asyncio
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from oracle.utils.config import OracleConfig
from oracle.engine import OracleEngine
from oracle.pipeline.live import LivePipeline
from oracle.pipeline.persistent import PersistentPipeline

app = FastAPI(title="Oraculo RAG", version="0.1.0")

_engine = None
_live = None
_persistent = None


def get_engine():
    global _engine, _live, _persistent
    if _engine is None:
        config = OracleConfig()
        _engine = OracleEngine(config)
        _live = LivePipeline(_engine)
        _persistent = PersistentPipeline(_engine)
    return _engine, _live, _persistent


class AskRequest(BaseModel):
    query: str
    file: Optional[str] = None
    web: bool = False


class AskResponse(BaseModel):
    query: str
    answer: str
    confidence: float
    decision: str
    source: str
    chunks: list
    time_ms: int


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    engine, live, persistent = get_engine()
    t0 = time.time()

    if req.file and os.path.exists(req.file):
        result = live.ask(req.file, req.query)
    else:
        result = persistent.ask(req.query)
        if (result["decision"] == "[No Support]" or result["confidence"] < 0.4) and req.web:
            wr = engine._web_fallback(req.query)
            if wr["decision"] != "[No Support]" and wr.get("answer"):
                result = wr

    elapsed = int((time.time() - t0) * 1000)
    answer = result.get("answer", "") or "Nao encontrei informacao suficiente."

    return AskResponse(
        query=req.query,
        answer=answer[:500],
        confidence=round(result.get("confidence", 0), 3),
        decision=result.get("decision", "[No Support]"),
        source=result.get("source", ""),
        chunks=result.get("chunks", []),
        time_ms=elapsed,
    )


@app.get("/api/ask/stream")
async def ask_stream(query: str, file: Optional[str] = None, web: bool = False):
    async def event_stream():
        engine, live, persistent = get_engine()
        t0 = time.time()

        yield f"data: {json.dumps({'type': 'status', 'message': 'Analisando pergunta...'})}\n\n"
        await asyncio.sleep(0.1)

        if file and os.path.exists(file):
            yield f"data: {json.dumps({'type': 'status', 'message': 'Processando arquivo...'})}\n\n"
            await asyncio.sleep(0.1)
            result = live.ask(file, query)
        else:
            yield f"data: {json.dumps({'type': 'status', 'message': 'Buscando informacoes...'})}\n\n"
            await asyncio.sleep(0.1)
            result = persistent.ask(query)
            if (result["decision"] == "[No Support]" or result["confidence"] < 0.4) and web:
                yield f"data: {json.dumps({'type': 'status', 'message': 'Buscando na web...'})}\n\n"
                await asyncio.sleep(0.1)
                wr = engine._web_fallback(query)
                if wr["decision"] != "[No Support]" and wr.get("answer"):
                    result = wr

        elapsed = int((time.time() - t0) * 1000)
        answer = result.get("answer", "") or "Nao encontrei informacao suficiente."

        yield f"data: {json.dumps({'type': 'result', 'answer': answer[:500], 'confidence': round(result.get('confidence', 0), 3), 'decision': result.get('decision', '[No Support]'), 'source': result.get('source', ''), 'chunks': result.get('chunks', []), 'time_ms': elapsed})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    engine, live, persistent = get_engine()
    tmp_dir = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, file.filename)

    content = await file.read()
    ext = os.path.splitext(file.filename)[1].lower()
    if ext == ".pdf":
        with open(tmp_path, "wb") as f:
            f.write(content)
    else:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content.decode("utf-8", errors="replace"))

    from oracle.pipeline.parser import DocumentParser
    parser = DocumentParser()
    text = parser.parse(tmp_path)
    if not text:
        raise HTTPException(400, "Nao foi possivel extrair texto do arquivo.")

    chunks = engine.index_document(text, source=file.filename)
    return {"filename": file.filename, "path": tmp_path, "chunks": chunks}


@app.get("/api/stats")
async def stats():
    engine, live, persistent = get_engine()
    return persistent.stats()


@app.get("/api/sql")
async def sql_query(db: str, query: str):
    engine, live, persistent = get_engine()
    conn_name = engine.connect_sqlite(db)
    text = engine.query_sql(conn_name, query)
    return {"result": text}


static_dir = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
else:
    @app.get("/")
    async def root():
        return HTMLResponse("<h1>Oraculo RAG - Build o frontend primeiro: cd web/frontend && npm install && npm run build</h1>")
