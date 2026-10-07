"""FastAPI 后端：暴露检索/问答接口 + 托管前端 + 笔记浏览。
启动: python server.py  → 浏览器打开 http://127.0.0.1:8777
"""
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from query import retrieve, build_context, answer
from config import (VAULT_PATH, DATA_DIR, COLLECTION, EMBED_MODEL,
                    LOCAL_FALLBACK, CLOUD_CHAIN, CLOUD_MODELS)
import chromadb
import threading
import time
from datetime import datetime

app = FastAPI(title="Obsidian RAG")
STATIC_DIR = Path(__file__).parent / "static"

# 重建索引状态（供 /reindex 一键更新 + 前端轮询）
_reindex_state = {"running": False, "done": 0, "error": None, "finished_at": None, "last_chunks": None}


@app.post("/reindex")
def reindex(force: bool = False):
    """后台重建索引（一键更新数据库）。force=true 清空旧索引全量重建。"""
    if _reindex_state["running"]:
        return {"status": "already_running"}

    def _run():
        try:
            from index import build_index
            _reindex_state["running"] = True
            _reindex_state["error"] = None
            t0 = time.time()
            done = build_index(force=force)
            _reindex_state.update(
                running=False, done=done, last_chunks=done,
                finished_at=time.time(), elapsed=round(time.time() - t0, 1),
            )
        except Exception as e:
            _reindex_state.update(running=False, error=str(e)[:200])

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started", "force": force}


@app.get("/reindex/status")
def reindex_status():
    return _reindex_state


class AskBody(BaseModel):
    question: str
    local: bool = False
    model: str | None = None   # None=auto, "auto"=自动降级, 云端模型名=直接用, 本地模型名=本地
    history: list | None = None   # 最近几轮对话，用于结合上下文回答


class SearchBody(BaseModel):
    query: str
    top_k: int = 5


class NoteBody(BaseModel):
    source: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def stats():
    """知识库概况 + 可用模型列表（供前端模型选择器）。"""
    col = chromadb.PersistentClient(path=str(DATA_DIR)).get_collection(COLLECTION)
    all_metas = col.get(include=["metadatas"])
    notes = {}
    for m in all_metas["metadatas"]:
        notes[m["source"]] = notes.get(m["source"], 0) + 1

    # --- 最近更新时间：各数据源文件 mtime 的最大值 ---
    src_files = {
        "qq_channel": Path(__file__).parent / "crawled_pdqq.json",
        "school_ee": Path(__file__).parent / "crawled_ee.json",
    }
    src_details, last_ts = {}, 0
    for k, p in src_files.items():
        ts = p.stat().st_mtime if p.exists() else 0
        src_details[k] = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else None
        last_ts = max(last_ts, ts)
    # vault 里最新笔记的 mtime（QQ频道 目录，导入后更新）
    latest_note_ts = 0
    qq_dir = VAULT_PATH / "QQ频道"
    if qq_dir.exists():
        try:
            for f in qq_dir.rglob("*.md"):
                latest_note_ts = max(latest_note_ts, f.stat().st_mtime)
        except Exception:
            pass
    src_details["vault_notes"] = (datetime.fromtimestamp(latest_note_ts).strftime("%Y-%m-%d %H:%M")
                                  if latest_note_ts else None)
    last_ts = max(last_ts, latest_note_ts)

    return {
        "notes": len(notes),
        "notes_list": sorted(notes.keys()),
        "chunks": col.count(),
        "embed_model": EMBED_MODEL,
        "gen_model": CLOUD_CHAIN[0],
        "fallback": LOCAL_FALLBACK,
        "chain": CLOUD_CHAIN + [LOCAL_FALLBACK],
        "models": CLOUD_MODELS,   # 前端模型选择器用
        "last_update": {
            "ts": last_ts,
            "time": datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M") if last_ts else None,
            "sources": src_details,
        },
    }


@app.post("/search")
def search(body: SearchBody):
    """只检索不生成，返回命中分块+来源+相似度。"""
    hits = retrieve(body.query, top_k=body.top_k)
    if not hits["documents"]:
        return {"hits": [], "message": "知识库为空，请先添加笔记并重建索引。"}
    return {
        "query": body.query,
        "hits": [
            {"source": m["source"], "doc": d, "score": round(1 - dist, 3)}
            for d, m, dist in zip(hits["documents"], hits["metadatas"], hits["distances"])
        ],
    }


@app.post("/ask")
def ask(body: AskBody):
    """检索 + 生成。
    body.model 可指定模型（None/auto=自动降级, 云端名=直接用, 本地名=本地）。
    body.history 携带最近对话用于结合上下文；若问题含计算意图，先做数据计算再生成。
    """
    # --- 计算意图检测：从知识库相关笔记提取数据精确计算 ---
    calc_block = ""
    try:
        from calculator import detect_calc_intent, calc, format_result
        calc_type = detect_calc_intent(body.question)
        if calc_type:
            # 检索相关笔记（优先个人信息）
            hits = retrieve(body.question, top_k=10)
            # 拼所有命中笔记原文
            notes_text = ""
            for m in hits["metadatas"]:
                src_path = VAULT_PATH / m["source"]
                if src_path.exists():
                    notes_text += f"\n===== {m['source']} =====\n" + src_path.read_text(encoding="utf-8")[:4000]
            result = calc(calc_type, body.question, notes_text)
            if result.get("found"):
                calc_block = "\n\n[自动数据计算] " + format_result(result)
    except Exception as e:
        print(f"[计算引擎] 异常: {e}")

    # --- 普通检索 ---
    hits = retrieve(body.question)
    if not hits["documents"]:
        return {"answer": "知识库为空，请先在 vault 添加笔记后运行 index.py 重建索引。", "sources": []}
    ctx = build_context(hits) + calc_block
    srcs = [m["source"] for m in hits["metadatas"]]
    ans, provider = answer(body.question, ctx, force_local=body.local,
                           force_model=body.model, history=body.history)
    return {"answer": ans, "sources": srcs, "provider": provider, "calc": bool(calc_block)}


@app.get("/note")
def note(body: NoteBody):
    """按来源路径返回单篇笔记原文。"""
    p = VAULT_PATH / body.source
    if not p.exists():
        raise HTTPException(404, f"笔记不存在：{body.source}")
    return {"source": body.source, "content": p.read_text(encoding="utf-8")}


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=500, content={"detail": f"Internal Server Error: {str(exc)[:200]}"})


# 中间件：所有响应强制 no-cache（否则 sw.js/style.css 被 304 缓存死锁，PWA 永远更新不了）
@app.middleware("http")
async def no_cache_middleware(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    print("启动 Obsidian RAG 服务...")
    print("浏览器访问: http://127.0.0.1:8777")
    uvicorn.run(app, host="127.0.0.1", port=8777)
