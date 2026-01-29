from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import uuid
import time
import json
from threading import Thread
from typing import Any, Iterator
from fastapi.encoders import jsonable_encoder
from agent.agent_core import Agent
from services.pdf_parser import parse_financial_pdf
from services.excel_parser import parse_financial_excel
from agent.memory import AgentMemory
from config import ENABLE_PERSIST_RAW_PDF_TEXT
from agent.models import ChatRequest, ChatResponse, PdfParseResult, ExcelParseResult, AgentStep
from services.akshare_tools import (
    get_indices_snapshot,
    get_cached_cn_code_name_list,
    get_cached_hk_code_name_list,
    get_cached_us_code_name_list,
    get_cn_stock_history,
    get_hk_stock_history,
    get_us_stock_history,
)
from services.summarizer import analyze_index_snapshot

app = FastAPI(title="Finance Data & News Agent")

origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = Agent()
memory = AgentMemory()

def _serialize_step(step: AgentStep) -> Dict[str, Any]:
    """Make AgentStep JSON-safe (datetime -> iso string)."""
    try:
        data = step.model_dump()
    except Exception:
        data = dict(step)

    ts = data.get("timestamp")
    if hasattr(ts, "isoformat"):
        data["timestamp"] = ts.isoformat()
    return data

def _sse(payload: Any) -> str:
    """Safely encode SSE payload as JSON (handles datetime, etc.)."""
    safe = jsonable_encoder(payload)
    return f"data: {json.dumps(safe, ensure_ascii=False)}\n\n"

HISTORY_CACHE: dict = {}
CACHE_TTL_SECONDS = 6 * 3600  # 6 小时

_LOCAL_CN_CACHE = None
_LOCAL_HK_CACHE = None
_LOCAL_US_CACHE = None


def _cache_get(key: str):
    item = HISTORY_CACHE.get(key)
    if not item:
        return None
    ts, value = item
    if time.time() - ts > CACHE_TTL_SECONDS or not value["points"]:
        HISTORY_CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value):
    HISTORY_CACHE[key] = (time.time(), value)


def _ensure_local_search_cache():
    """懒加载本地代码-名称缓存，避免每次搜索都访问外网。"""
    global _LOCAL_CN_CACHE, _LOCAL_HK_CACHE, _LOCAL_US_CACHE
    if _LOCAL_CN_CACHE is None:
        _LOCAL_CN_CACHE = get_cached_cn_code_name_list()
    if _LOCAL_HK_CACHE is None:
        _LOCAL_HK_CACHE = get_cached_hk_code_name_list()
    if _LOCAL_US_CACHE is None:
        _LOCAL_US_CACHE = get_cached_us_code_name_list()


def _local_filter(items: List[dict], q: str, limit: int) -> List[dict]:
    q_lower = q.lower()
    results: List[dict] = []
    for it in items:
        code = str(it.get("code", ""))
        name = str(it.get("name", ""))
        if (q_lower in code.lower()) or (q_lower in name.lower()):
            results.append(it)
        if len(results) >= limit:
            break
    return results


def _sse_json(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.on_event("startup")
def warmup_background():
    """后端启动时的后台预热：
    - 预加载本地代码-名称缓存
    """
    def _preload():
        try:
            _ensure_local_search_cache()
        except Exception:
            pass

    Thread(target=_preload, daemon=True).start()


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    核心对话接口：智能规划 + 调工具 + 返回结构化结果。
    """
    return agent.handle_chat(req)


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    SSE 流式接口，返回 text/event-stream。
    """
    return StreamingResponse(agent.stream_chat(req), media_type="text/event-stream")


# ------------------------
# Upload: Non-stream (兼容 AgentView 旧写法)
# ------------------------
@app.post("/api/upload/pdf", response_model=PdfParseResult)
async def upload_pdf(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    store: bool = Form(True),  # ✅ 新增：隐私模式下 store=false
):
    content = await file.read()
    parsed = parse_financial_pdf(content, file.filename, include_preview=store)

    # ✅ 隐私模式：不写入 memory，不返回 raw_preview
    raw_preview = parsed["raw_preview"] if store else ""

    steps: List[AgentStep] = []
    step = AgentStep(
        id=f"pdf-{uuid.uuid4().hex}",
        type="tool",
        title="解析 PDF 财报",
        detail=(
            f"已解析 PDF 报表 {file.filename}，抽取全文后生成结构化指标、图表，并给出 LLM 解读。"
            if store
            else "已解析 PDF 报表（隐私模式：不保存文件概要/不保留原文预览）。"
        ),
    )
    steps.append(step)

    if store:
        info = {
            "type": "pdf",
            "filename": file.filename,
            "metrics": parsed["metrics"],
        }
        # 只有在“允许存储”且开启了该开关时，才会把 preview 写入 memory
        if ENABLE_PERSIST_RAW_PDF_TEXT:
            info["raw_preview"] = raw_preview
        memory.add_file_summary(session_id, info)
        memory.add_step(session_id, step)

    return PdfParseResult(
        session_id=session_id,
        filename=file.filename,
        metrics=parsed["metrics"],
        raw_preview=raw_preview,
        steps=steps,
    )


@app.post("/api/upload/excel", response_model=ExcelParseResult)
async def upload_excel(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    store: bool = Form(True),  # ✅ 新增
):
    """
    上传 Excel 财报，统一解析数据与指标。
    """
    content = await file.read()
    parsed = parse_financial_excel(content, file.filename, include_preview=store)
    raw_preview = parsed["raw_preview"] if store else ""

    steps: List[AgentStep] = []
    step = AgentStep(
        id=f"excel-{uuid.uuid4().hex}",
        type="tool",
        title="解析 Excel 财报",
        detail=(
            f"已解析 Excel 报表 {file.filename}，抽取表格后生成结构化指标、图表，并给出 LLM 解读。"
            if store
            else "已解析 Excel 报表（隐私模式：不保存文件概要/不保留预览）。"
        ),
    )
    steps.append(step)

    if store:
        info = {
            "type": "excel",
            "filename": file.filename,
            "metrics": parsed["metrics"],
        }
        memory.add_file_summary(session_id, info)
        memory.add_step(session_id, step)

    return ExcelParseResult(
        session_id=session_id,
        filename=parsed["filename"],
        metrics=parsed["metrics"],
        steps=steps,
    )


@app.post("/api/upload/pdf/stream")
async def upload_pdf_stream(
    session_id: str = Form(...),
    file: UploadFile = File(...),
):
    """SSE 版本：上传 PDF 并流式返回步骤/结果。

    关键点：必须在返回 StreamingResponse 前把 UploadFile 读成 bytes，
    否则请求生命周期结束时底层文件会被关闭，导致后续解析时报
    "I/O operation on closed file"。
    """
    content = await file.read()
    filename = file.filename

    step = AgentStep(
        id=f"pdf-{uuid.uuid4().hex}",
        type="tool",
        title="解析 PDF 财报",
        detail=f"已收到 PDF 文件 {filename}，开始抽取文本与表格…",
    )
    memory.add_step(session_id, step)

    def event_iter() -> Iterator[str]:
        yield _sse({"type": "step", "step": _serialize_step(step)})
        try:
            parsed = parse_financial_pdf(content, filename)

            info = {"type": "pdf", "filename": filename, "metrics": parsed["metrics"]}
            if ENABLE_PERSIST_RAW_PDF_TEXT:
                info["raw_preview"] = parsed.get("raw_preview", "")
            memory.add_file_summary(session_id, info)

            payload = {
                "type": "done",
                "session_id": session_id,
                "filename": filename,
                "metrics": parsed["metrics"],
                "raw_preview": parsed.get("raw_preview", ""),
                "steps": [_serialize_step(step)],
            }
            yield _sse(payload)
        except Exception as e:
            yield _sse({"type": "error", "message": str(e)})

    return StreamingResponse(event_iter(), media_type="text/event-stream")


@app.post("/api/upload/excel/stream")
async def upload_excel_stream(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    store: bool = Form(True),
):
    """SSE 版本：上传 Excel 并流式返回步骤/结果。"""
    content = await file.read()
    filename = file.filename

    step = AgentStep(
        id=f"excel-{uuid.uuid4().hex}",
        type="tool",
        title="解析 Excel 财报",
        detail=f"已收到 Excel 文件 {filename}，开始抽取表格并生成指标/图表…",
    )

    if store:
        memory.add_step(session_id, step)

    def event_iter() -> Iterator[str]:
        yield _sse({"type": "step", "step": _serialize_step(step)})
        try:
            parsed = parse_financial_excel(content, filename, include_preview=store)

            info = {
                "type": "excel",
                "filename": parsed.get("filename") or filename,
                "metrics": parsed["metrics"],
            }
            if store:
                memory.add_file_summary(session_id, info)

            payload = {
                "type": "done",
                "session_id": session_id,
                "filename": info["filename"],
                "metrics": parsed["metrics"],
                "raw_preview": parsed.get("raw_preview", "") if store else "",
                "steps": [_serialize_step(step)],
            }
            yield _sse(payload)
        except Exception as e:
            yield _sse({"type": "error", "message": str(e)})

    return StreamingResponse(event_iter(), media_type="text/event-stream")






# ------------------------
# Upload: Stream (兼容 frontend/src/api/upload.js 的 /stream)
# ------------------------
@app.post("/api/upload/pdf/stream")
async def upload_pdf_stream(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    store: bool = Form(True),
):
    # ✅ 关键：在 generator 之前就把 bytes 读出来，避免文件被关闭
    filename = file.filename
    content = await file.read()

    async def gen():
        try:
            yield _sse_json({"type": "step", "step": {"type": "tool", "title": "接收文件", "detail": "已接收 PDF 上传文件，开始解析..."}})

            parsed = parse_financial_pdf(content, filename, include_preview=store)
            raw_preview = parsed["raw_preview"] if store else ""

            step = AgentStep(
                id=f"pdf-{uuid.uuid4().hex}",
                type="tool",
                title="解析 PDF 财报",
                detail=(
                    f"已解析 PDF 报表 {filename}，抽取全文后生成结构化指标、图表，并给出 LLM 解读。"
                    if store
                    else "已解析 PDF 报表（隐私模式：不保存文件概要/不保留原文预览）。"
                ),
            )

            if store:
                info = {"type": "pdf", "filename": filename, "metrics": parsed["metrics"]}
                if ENABLE_PERSIST_RAW_PDF_TEXT:
                    info["raw_preview"] = raw_preview
                memory.add_file_summary(session_id, info)
                memory.add_step(session_id, step)

            yield _sse_json({"type": "step", "step": step.dict()})
            yield _sse_json({
                "type": "done",
                "session_id": session_id,
                "filename": filename,
                "metrics": parsed["metrics"],
                "raw_preview": raw_preview,
                "steps": [step.dict()],
            })
        except Exception as e:
            yield _sse_json({"type": "error", "message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream")




@app.post("/api/upload/excel/stream")
async def upload_excel_stream(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    store: bool = Form(True),
):
    filename = file.filename
    content = await file.read()

    async def gen():
        try:
            yield _sse_json({"type": "step", "step": {"type": "tool", "title": "接收文件", "detail": "已接收 Excel 上传文件，开始解析..."}})

            parsed = parse_financial_excel(content, filename, include_preview=store)
            raw_preview = parsed["raw_preview"] if store else ""

            step = AgentStep(
                id=f"excel-{uuid.uuid4().hex}",
                type="tool",
                title="解析 Excel 财报",
                detail=(
                    f"已解析 Excel 报表 {filename}，抽取表格后生成结构化指标、图表，并给出 LLM 解读。"
                    if store
                    else "已解析 Excel 报表（隐私模式：不保存文件概要/不保留预览）。"
                ),
            )

            if store:
                info = {"type": "excel", "filename": filename, "metrics": parsed["metrics"]}
                memory.add_file_summary(session_id, info)
                memory.add_step(session_id, step)

            yield _sse_json({"type": "step", "step": step.dict()})
            yield _sse_json({
                "type": "done",
                "session_id": session_id,
                "filename": parsed["filename"],
                "metrics": parsed["metrics"],
                "raw_preview": raw_preview,
                "steps": [step.dict()],
            })
        except Exception as e:
            yield _sse_json({"type": "error", "message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream")




@app.get("/api/akshare/index_snapshot")
def akshare_index_snapshot():
    """
    一键获取 AkShare 指数快照，供首页或 Agent 页面调用。
    """
    return get_indices_snapshot()


@app.get("/api/akshare/analyze")
def akshare_analyze(language: str = "zh"):
    """
    一键分析 AkShare 指数行情，返回分析文本和原始数据。
    """
    snapshot = get_indices_snapshot()
    analysis = analyze_index_snapshot(snapshot, language=language)
    return {"snapshot": snapshot, "analysis": analysis}


@app.get("/api/stocks/search")
def stocks_search(q: str, limit: int = 10):
    """
    股票搜索，展示代码与名称匹配结果，优先使用本地缓存。
    """
    _ensure_local_search_cache()

    items: List[dict] = []
    seen: dict = {}

    # 先匹配 A 股缓存
    if _LOCAL_CN_CACHE:
        for it in _local_filter(_LOCAL_CN_CACHE, q, limit):
            sym = it.get("symbol")
            if sym and not seen.get(sym):
                items.append(it)
                seen[sym] = True
            if len(items) >= limit:
                break

    # 再匹配美股缓存
    if len(items) < limit and _LOCAL_US_CACHE:
        for it in _local_filter(_LOCAL_US_CACHE, q, limit):
            sym = it.get("symbol")
            if sym and not seen.get(sym):
                items.append(it)
                seen[sym] = True
            if len(items) >= limit:
                break

    # 最后匹配港股缓存
    if len(items) < limit and _LOCAL_HK_CACHE:
        for it in _local_filter(_LOCAL_HK_CACHE, q, limit):
            sym = it.get("symbol")
            if sym and not seen.get(sym):
                items.append(it)
                seen[sym] = True
            if len(items) >= limit:
                break

    return {"items": items[:limit]}


@app.get("/api/stocks/history")
def stocks_history(symbol: str, days: int = 90):
    """
    股票历史行情，使用 AkShare 获取 A 股、港股、美股，返回 points:[{date, close}]
    """
    sym = symbol.strip()
    lower = sym.lower()
    is_cn = (lower.startswith(("sh", "sz"))) or (len(sym) == 6 and sym.isdigit())
    is_hk_numeric = (len(sym) in (4, 5)) and sym.isdigit()
    is_hk_yf = lower.endswith(".hk")

    cache_key = f"{sym}|{days}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    if is_cn:
        result = get_cn_stock_history(sym, days=days)
        _cache_set(cache_key, result)
        return result

    if is_hk_numeric or is_hk_yf:
        result = get_hk_stock_history(sym, days=days)
        _cache_set(cache_key, result)
        return result

    result = get_us_stock_history(sym, days=days)
    _cache_set(cache_key, result)
    return result


@app.get("/api/session/{session_id}/steps")
async def get_session_steps(session_id: str):
    """
    查看 Agent 在某个会话中的任务规划与中间步骤。
    """
    return {"steps": memory.get_session_steps(session_id)}


@app.get("/api/session/{session_id}/files")
async def get_session_files(session_id: str):
    """
    查看已解析的文件概要（多份 PDF/Excel 汇总）。
    """
    return {"files": memory.get_session_files(session_id)}
