"""Web 服务：FastAPI + SSE 流式对话。

启动：
    python server.py
    # 或指定端口
    python server.py --port 8080

访问：
    http://127.0.0.1:8000

接口：
    GET  /                 前端页面
    POST /api/chat         对话（SSE 流式）
    POST /api/reset        清空会话
    GET  /api/health       健康检查
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import (
    Body,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from agent import ChatState, stream_answer
from config import get_client
import rag as rag_mod

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="AI Agent Demo", version="1.0.0")

# ===== 访问控制 =====
# 在 .env 里设置 ACCESS_PASSWORD 后，所有 API 都需要在请求头带 X-Password。
# 不设置则完全开放（仅适合本机或可信局域网）。
_ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD", "").strip()


def check_auth(x_password: str = Header(default="")) -> None:
    """简单的口令校验。为空时不校验。"""
    if _ACCESS_PASSWORD and x_password != _ACCESS_PASSWORD:
        raise HTTPException(status_code=401, detail="访问密码错误")

# 隧道进程 ID（用于退出时清理）
_TUNNEL_PID = 0

# 是否隐藏 cpolar 控制台窗口（由 --hide-cpolar 控制）
_HIDE_CPOLAR = False

# 会话存储：SQLite 持久化 + 内存缓存（缓存只为了省重复查询）
_sessions: dict[str, ChatState] = {}
_MAX_SESSIONS = 200

import db as db_mod

_DB = db_mod.get_db()


def _save_session(sid: str, state: ChatState) -> None:
    """把会话写入数据库。标题取第一条用户消息前 30 字。"""
    try:
        existing = _DB.get_session(sid)
        title = existing["title"] if existing else "新对话"

        # 没有标题时，从消息里提取
        if not title or title == "新对话":
            for m in state.messages:
                if m["role"] == "user" and m["content"].strip():
                    title = m["content"].strip()[:30]
                    break

        _DB.ensure_session(sid, title)
        # 消息整体替换（简单可靠，会话轮数不多）
        body = [m for m in state.messages if m["role"] != "system"]
        _DB.replace_messages(sid, body)
        _DB.touch_session(sid, title)
    except Exception as _e:
        print(f"[WARN] 会话入库失败 {sid}: {type(_e).__name__} {_e}")


def _restore_session(sid: str) -> ChatState | None:
    """从数据库恢复某个会话的完整消息。"""
    try:
        d = _DB.get_session(sid)
        if not d:
            return None
        st = ChatState()
        msgs = [{"role": "system", "content": st.messages[0]["content"]}]
        msgs.extend(d.get("messages") or [])
        st.messages = msgs
        return st
    except Exception:
        return None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str = ""
    force_search: bool = False
    model_id: str = ""
    attachments: list[dict] = []
    search_enabled: bool = True


class ResetRequest(BaseModel):
    session_id: str


def _get_session(sid: str) -> tuple[str, ChatState]:
    """取会话，返回 (session_id, ChatState)。

    优先内存，其次数据库，最后新建。
    """
    if sid and sid in _sessions:
        return sid, _sessions[sid]

    # 缓存淘汰
    if len(_sessions) >= _MAX_SESSIONS:
        for k in list(_sessions.keys())[: _MAX_SESSIONS // 2]:
            _sessions.pop(k, None)

    if sid:
        restored = _restore_session(sid)
        if restored:
            _sessions[sid] = restored
            return sid, restored
        st = ChatState()
        _safe_ensure_session(sid, "新对话")
        _sessions[sid] = st
        return sid, st

    new_sid = uuid.uuid4().hex
    state = ChatState()
    _safe_ensure_session(new_sid, "新对话")
    _sessions[new_sid] = state
    return new_sid, state


# 数据库是否可写（首次写失败后置为 False，后续直接跳过写盘）
_DB_WRITABLE: bool | None = None


def _db_writable() -> bool:
    """探测数据库是否可写（结果缓存）。"""
    global _DB_WRITABLE
    if _DB_WRITABLE is None:
        try:
            with _DB.tx() as c:
                c.execute(
                    "CREATE TABLE IF NOT EXISTS _wprobe (a TEXT)"
                )
                c.execute("DROP TABLE IF EXISTS _wprobe")
            _DB_WRITABLE = True
        except Exception:
            _DB_WRITABLE = False
            print(
                "[WARN] 数据库为只读，本次运行的数据不会持久化（会话在内存中保留）"
            )
    return _DB_WRITABLE


def _safe_ensure_session(sid: str, title: str = "新对话") -> None:
    """创建会话；只读时静默跳过。"""
    if not _db_writable():
        return
    try:
        _DB.ensure_session(sid, title)
    except Exception:
        global _DB_WRITABLE
        _DB_WRITABLE = False


def _safe_save_session(sid: str, state: ChatState) -> None:
    """保存会话；只读时静默跳过。"""
    if not _db_writable():
        return
    _save_session(sid, state)


def _sse(payload: dict) -> str:
    """包装成 SSE 格式。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/models")
async def get_models(_: None = Depends(check_auth)) -> dict:
    """返回可用模型列表，供前端下拉选择。"""
    try:
        import config as cfg_mod

        models = cfg_mod.list_models()
    except Exception:
        models = []
    default = models[0]["id"] if models else "qwen-flash"
    return {"models": models, "default": default}


# ============ 模型管理（网页端配置） ============


@app.get("/api/models/providers")
async def get_providers(_: None = Depends(check_auth)) -> dict:
    """返回常见服务商预设，前端用来一键填 base_url。"""
    import model_store

    return {"providers": model_store.PROVIDER_PRESETS}


@app.get("/api/models/custom")
async def list_custom_models(_: None = Depends(check_auth)) -> dict:
    """列出所有自定义模型（Key 脱敏）。"""
    import model_store

    return {"models": model_store.list_custom_public()}


@app.post("/api/models/custom")
async def create_custom_model(
    req: dict = Body(...), _: None = Depends(check_auth)
) -> dict:
    """新增自定义模型。"""
    import model_store

    try:
        entry = model_store.add_custom(req)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"保存失败：{e}")

    return {
        "status": "ok",
        "model": {"id": entry["id"], "label": entry["label"]},
    }


@app.patch("/api/models/custom/{model_id}")
async def update_custom_model(
    model_id: str, req: dict = Body(...), _: None = Depends(check_auth)
) -> dict:
    """更新自定义模型（api_key 留空表示不改）。"""
    import model_store

    try:
        entry = model_store.update_custom(model_id, req)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"更新失败：{e}")
    return {"status": "ok", "model": {"id": entry["id"]}}


@app.delete("/api/models/custom/{model_id}")
async def delete_custom_model(model_id: str, _: None = Depends(check_auth)) -> dict:
    """删除自定义模型。"""
    import model_store

    ok = model_store.remove_custom(model_id)
    if not ok:
        raise HTTPException(404, "模型不存在")
    return {"status": "ok"}


@app.post("/api/models/test")
async def test_model(req: dict = Body(...), _: None = Depends(check_auth)) -> dict:
    """测试模型连通性。

    body 支持两种：
      {"model_id": "xxx"}                     —— 测试已保存的模型
      {"base_url","api_key","model"}          —— 测试未保存的配置
    """
    import model_store

    # 方式一：测试已存在的模型
    if req.get("model_id"):
        mid = req["model_id"]
        try:
            import config as cfg_mod

            cfg = cfg_mod.get_model_by_id(mid)
            if not cfg:
                return {"ok": False, "message": f"模型 {mid} 不存在"}
            return model_store.test_connection(cfg.base_url, cfg.api_key, cfg.model)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)[:120]}

    # 方式二：测试临时配置
    return model_store.test_connection(
        req.get("base_url", ""), req.get("api_key", ""), req.get("model", "")
    )


@app.get("/api/models/detail")
async def model_detail(model_id: str, _: None = Depends(check_auth)) -> dict:
    """取单个自定义模型的完整信息（用于编辑，Key 脱敏）。"""
    import model_store

    m = model_store.get_custom(model_id)
    if not m:
        raise HTTPException(404, "不是自定义模型")
    item = dict(m)
    key = item.get("api_key", "")
    item["api_key"] = "****" + key[-4:] if len(key) > 8 else "****"
    item["has_key"] = bool(key)
    return item


@app.post("/api/attach")
async def parse_attachment(
    file: UploadFile = File(...), _: None = Depends(check_auth)
) -> dict:
    """解析对话中上传的文件，返回纯文本供模型阅读（不入知识库）。"""
    name = file.filename or "unknown"
    suffix = Path(name).suffix.lower()

    if suffix not in ALLOWED_EXT and suffix not in {
        ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif",
    }:
        raise HTTPException(400, f"不支持的文件类型 {suffix}")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix, dir=str(UPLOAD_DIR)
        ) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = Path(tmp.name)

        size_mb = tmp_path.stat().st_size / 1024 / 1024
        if size_mb > MAX_FILE_MB:
            raise HTTPException(400, f"文件过大（{size_mb:.1f}MB）")

        # 图片：转成 base64 返回，前端在支持视觉的模型下直接传给模型
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
            import base64

            raw = tmp_path.read_bytes()
            size_kb = len(raw) / 1024
            if size_kb > 4096:
                raise HTTPException(400, f"图片过大（{size_kb:.0f}KB），上限 4MB")

            # 统一转成 png/jpeg，避免 bmp 等格式模型不支持
            mime = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".gif": "image/gif",
                ".bmp": "image/bmp",
            }.get(suffix, "image/png")

            b64 = base64.b64encode(raw).decode()
            data_url = f"data:{mime};base64,{b64}"

            # 同时尝试 OCR，作为不支持视觉时的兜底
            ocr_text = _ocr_image(tmp_path)

            return {
                "status": "ok",
                "name": name,
                "type": "image",
                "text": ocr_text[:5000] if ocr_text.strip() else "",
                "data_url": data_url,
                "chars": len(ocr_text),
                "truncated": False,
                "note": "视觉模型可直接识别图片；其他模型只能用 OCR 文字",
            }

        text = rag_mod.read_document(tmp_path)
        if not text.strip():
            raise HTTPException(400, "文件内容为空或无法提取文字")

        return {
            "status": "ok",
            "name": name,
            "type": "doc",
            "text": text[:20000],
            "chars": len(text),
            "truncated": len(text) > 20000,
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"解析失败：{e}")
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _ocr_image(path: Path) -> str:
    """对图片做 OCR。没有 pytesseract 时返回空串。"""
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(path)
        return pytesseract.image_to_string(img, lang="chi_sim+eng")
    except Exception:
        return ""


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "sessions": len(_sessions),
        "auth_required": bool(_ACCESS_PASSWORD),
        "search_engines": ["360", "bing", "sogou"],
    }


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request, _: None = Depends(check_auth)) -> StreamingResponse:
    sid, state = _get_session(req.session_id)
    state.search_enabled = req.search_enabled

    async def event_stream():
        # 先告诉前端会话 id，后续请求带上它才能延续上下文
        yield _sse({"type": "session", "session_id": sid})
        finished = False
        reasoning_buf: list[str] = []
        try:
            for event in stream_answer(
                state,
                req.message,
                force_search=req.force_search,
                model_id=req.model_id,
                attachments=req.attachments,
            ):
                if await request.is_disconnected():
                    break
                # 收集思考过程，稍后随消息一起入库
                if event.get("type") == "reasoning":
                    reasoning_buf.append(event.get("text") or "")
                yield _sse(event)
                if event.get("type") == "done":
                    # 把思考过程挂到最后一条助手消息上，历史里能回看
                    if reasoning_buf and state.messages:
                        for m in reversed(state.messages):
                            if m.get("role") == "assistant":
                                m["reasoning"] = "".join(reasoning_buf)
                                thinking = event.get("thinking") or 0
                                if thinking:
                                    m["thinking_ms"] = int(thinking * 1000)
                                break
                    # 立即落盘，不要等 finally（客户端读完就断开，finally 可能不执行）
                    _safe_save_session(sid, state)
                    finished = True
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(e)})
        finally:
            # 兜底：异常或中途断开也保存已生成的部分
            if not finished:
                _safe_save_session(sid, state)
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # 让 nginx 不缓冲，否则流式失效
            "Connection": "keep-alive",
        },
    )


@app.post("/api/reset")
async def reset(req: ResetRequest, _: None = Depends(check_auth)) -> dict:
    if req.session_id in _sessions:
        _sessions[req.session_id].reset()
    return {"status": "ok"}


# ============ 会话历史 ============


@app.get("/api/sessions")
async def list_sessions(
    limit: int = 100, _: None = Depends(check_auth)
) -> dict:
    """列出所有历史会话：置顶优先，其余按更新时间倒序。"""
    items = _DB.list_sessions(limit=limit)
    return {
        "sessions": [
            {
                "session_id": s["id"],
                "title": s["title"],
                "created": s["created"],
                "updated": s["updated"],
                "group": s.get("grp") or "",
                "pinned": bool(s.get("pinned")),
            }
            for s in items
        ],
        "groups": _DB.list_groups(),
    }


@app.get("/api/sessions/{sid}")
async def get_session_detail(sid: str, _: None = Depends(check_auth)) -> dict:
    """读取某个会话的完整消息。"""
    d = _DB.get_session(sid)
    if not d:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "session_id": d["id"],
        "title": d["title"],
        "created": d["created"],
        "updated": d["updated"],
        "messages": [{"role": "system", "content": ""}] + d["messages"],
    }


@app.delete("/api/sessions/{sid}")
async def delete_session(sid: str, _: None = Depends(check_auth)) -> dict:
    """删除会话（消息级联删除）。"""
    _sessions.pop(sid, None)
    ok = _DB.delete_session(sid)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "ok"}


@app.patch("/api/sessions/{sid}")
async def rename_session(
    sid: str, req: dict = Body(...), _: None = Depends(check_auth)
) -> dict:
    """重命名会话。"""
    title = (req.get("title") or "").strip()[:60]
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    ok = _DB.rename_session(sid, title)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "ok", "title": title}

@app.patch("/api/sessions/{sid}/group")
async def set_session_group(
    sid: str, req: dict = Body(...), _: None = Depends(check_auth)
) -> dict:
    """调整会话所属分组 / 置顶状态。

    body: {"group": "工作"} 或 {"pinned": true}
    """
    changed = False

    if "group" in req:
        grp = (req.get("group") or "").strip()[:30]
        if _DB.set_session_group(sid, grp):
            changed = True

    if "pinned" in req:
        if _DB.set_session_pinned(sid, bool(req["pinned"])):
            changed = True

    if not changed:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "ok"}


@app.get("/api/groups")
async def get_groups(_: None = Depends(check_auth)) -> dict:
    """列出所有分组。"""
    return {"groups": _DB.list_groups()}


@app.post("/api/groups/rename")
async def rename_group_endpoint(
    req: dict = Body(...), _: None = Depends(check_auth)
) -> dict:
    """重命名分组（批量移动该组下所有会话）。"""
    old = (req.get("old") or "").strip()
    new = (req.get("new") or "").strip()[:30]
    if not old or not new:
        raise HTTPException(status_code=400, detail="新旧名称都不能为空")
    n = _DB.rename_group(old, new)
    return {"status": "ok", "moved": n}


@app.post("/api/groups/delete")
async def delete_group_endpoint(
    req: dict = Body(...), _: None = Depends(check_auth)
) -> dict:
    """删除分组，组内会话回到「未分组」。"""
    grp = (req.get("group") or "").strip()
    if not grp:
        raise HTTPException(status_code=400, detail="分组名不能为空")
    n = _DB.delete_group(grp)
    return {"status": "ok", "moved": n}


@app.post("/api/sessions/batch-delete")
async def batch_delete_sessions(
    req: dict = Body(...), _: None = Depends(check_auth)
) -> dict:
    """批量删除会话。"""
    ids = req.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    n = 0
    for sid in ids:
        _sessions.pop(sid, None)
        if _DB.delete_session(str(sid)):
            n += 1
    return {"status": "ok", "deleted": n}



@app.get("/api/sessions/search/{keyword}")
async def search_sessions(keyword: str, _: None = Depends(check_auth)) -> dict:
    """全文搜索会话消息（SQLite LIKE，支持中文）。"""
    kw = f"%{keyword}%"
    rows = _DB.q(
        "SELECT DISTINCT s.id, s.title, s.updated, m.content "
        "FROM sessions s JOIN messages m ON m.session_id = s.id "
        "WHERE m.content LIKE ? ORDER BY s.updated DESC LIMIT 30",
        (kw,),
    )
    return {
        "keyword": keyword,
        "results": [
            {
                "session_id": r["id"],
                "title": r["title"],
                "updated": r["updated"],
                "snippet": r["content"][:120],
            }
            for r in rows
        ],
    }


@app.get("/api/semantic-search")
async def semantic_search(
    q: str, top_k: int = 8, _: None = Depends(check_auth)
) -> dict:
    """语义搜索历史消息（基于向量相似度）。

    需要先构建消息向量索引，否则返回空结果并提示。
    """
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="搜索词不能为空")

    if not rag_mod.msg_index_available():
        return {
            "query": q,
            "results": [],
            "available": False,
            "hint": "消息向量索引未构建，可在设置 → 工具里点「重建索引」",
        }

    try:
        hits = rag_mod.search_messages(q, top_k=min(max(top_k, 1), 30))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"语义搜索失败：{e}")

    # 补上会话标题
    titles = {s["id"]: s["title"] for s in _DB.list_sessions(limit=500)}
    for h in hits:
        h["title"] = titles.get(h["session_id"], "（已删除会话）")

    return {"query": q, "results": hits, "available": True}


@app.post("/api/msg-index/rebuild")
async def rebuild_msg_index(_: None = Depends(check_auth)) -> dict:
    """重建历史消息向量索引。"""
    try:
        r = rag_mod.rebuild_msg_index()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"重建失败：{e}")
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error") or "重建失败")
    return r


@app.get("/api/msg-index/status")
async def msg_index_status(_: None = Depends(check_auth)) -> dict:
    """查看消息向量索引状态。"""
    available = rag_mod.msg_index_available()
    count = 0
    if available:
        try:
            count = len(_DB.list_msg_vectors())
        except Exception:
            count = 0
    return {"available": available, "count": count}


@app.get("/api/stats")
async def get_stats(_: None = Depends(check_auth)) -> dict:
    """数据库统计信息。"""
    return {**_DB.stats(), "db_path": str(_DB.path)}


# ============ 文档导出 ============


class ExportRequest(BaseModel):
    """导出请求。"""
    content: str = Field(..., min_length=1)
    title: str = ""
    format: str = "docx"
    meta: dict = {}


@app.post("/api/export")
async def export_document(
    req: ExportRequest, _: None = Depends(check_auth)
):
    """把一段 Markdown 导出成文件，直接下载。

    支持 docx / pdf / html / md / txt。
    """
    import urllib.parse

    import docgen

    title = (req.title or "AI 回答").strip()
    try:
        data, mime, ext = docgen.build(req.format, title, req.content, req.meta)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"生成失败：{e}")

    fname = docgen.safe_filename(title, ext)
    # 中文文件名需要 RFC 5987 编码
    quoted = urllib.parse.quote(fname)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quoted}",
        "Content-Length": str(len(data)),
    }
    return Response(content=data, media_type=mime, headers=headers)


@app.get("/api/export/formats")
async def export_formats(_: None = Depends(check_auth)) -> dict:
    """返回支持的导出格式。"""
    return {
        "formats": [
            {"id": "docx", "name": "Word 文档", "ext": ".docx", "icon": "📝"},
            {"id": "pdf", "name": "PDF 文件", "ext": ".pdf", "icon": "📕"},
            {"id": "html", "name": "网页 HTML", "ext": ".html", "icon": "🌐"},
            {"id": "md", "name": "Markdown", "ext": ".md", "icon": "📋"},
            {"id": "txt", "name": "纯文本", "ext": ".txt", "icon": "📄"},
        ]
    }


# ============ 评估 ============


@app.get("/api/eval/cases")
async def list_eval_cases(_: None = Depends(check_auth)) -> dict:
    """列出评估集。"""
    import rag_eval

    cases = rag_eval.load_cases()
    return {
        "total": len(cases),
        "cases": [
            {"question": c.question, "answer": c.answer, "keywords": c.keywords}
            for c in cases
        ],
    }


@app.post("/api/eval/run")
async def run_eval(req: dict = Body(...), _: None = Depends(check_auth)) -> dict:
    """跑评估，返回指标。

    body:
        rewrite: bool  —— 是否启用查询改写（默认 true）
        rerank: bool   —— 是否启用重排（默认 true）
        with_answer: bool —— 是否同时生成回答并评准确率（慢，默认 false）
    """
    import rag_eval

    cases = rag_eval.load_cases()
    if not cases:
        raise HTTPException(
            status_code=400,
            detail="评估集为空，请在 AI-Agent/eval_data/cases.jsonl 中添加用例",
        )

    kb = rag_mod.get_kb()
    if not kb.chunks:
        raise HTTPException(status_code=400, detail="知识库为空，请先上传文档")

    try:
        client, model, _ = get_client()
    except Exception:
        client, model = None, ""

    answer_fn = None
    if req.get("with_answer") and client:

        def _answer(q: str) -> str:
            from agent import ChatState, stream_answer

            st = ChatState()
            parts = []
            for ev in stream_answer(st, q):
                if ev.get("type") == "delta":
                    parts.append(ev["text"])
            return "".join(parts)

        answer_fn = _answer

    report = rag_eval.evaluate(
        kb,
        cases,
        answer_fn=answer_fn,
        top_k=4,
        use_rewrite=bool(req.get("rewrite", True)),
        use_rerank=bool(req.get("rerank", True)),
        rewrite_client=client,
        rewrite_model=model,
    )
    return report.to_dict()



@app.post("/api/kb/debug")
async def kb_debug(req: dict = Body(...), _: None = Depends(check_auth)) -> dict:
    """检索过程调试：看改写、粗排、重排的中间结果。"""
    query = (req.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query 不能为空")
    kb = rag_mod.get_kb()
    try:
        client, model, _ = get_client()
    except Exception:
        client, model = None, ""
    return kb.search_debug(
        query, top_k=int(req.get("top_k", 4)),
        rewrite_client=client, rewrite_model=model,
    )


# ============ 知识库管理 ============

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_FILE_MB = 20
ALLOWED_EXT = {".pdf", ".docx", ".txt", ".md", ".markdown", ".csv"}


@app.get("/api/kb/documents")
async def list_documents(_: None = Depends(check_auth)) -> dict:
    """列出知识库里的所有文档。"""
    kb = rag_mod.get_kb()
    return {
        "documents": [
            {
                "doc_id": d.doc_id,
                "name": d.name,
                "size": d.size,
                "chunks": d.chunks,
                "chars": d.chars,
            }
            for d in kb.documents.values()
        ],
        "total_chunks": len(kb.chunks),
    }


@app.post("/api/kb/upload")
async def upload_document(
    file: UploadFile = File(...), _: None = Depends(check_auth)
) -> dict:
    """上传文档，解析、切分、向量化后加入知识库。"""
    name = file.filename or "unknown"
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 {suffix}，支持：{', '.join(sorted(ALLOWED_EXT))}",
        )

    # 存到临时文件，避免大文件占内存
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix, dir=str(UPLOAD_DIR)
        ) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = Path(tmp.name)

        size_mb = tmp_path.stat().st_size / 1024 / 1024
        if size_mb > MAX_FILE_MB:
            raise HTTPException(
                status_code=400, detail=f"文件过大（{size_mb:.1f}MB），上限 {MAX_FILE_MB}MB"
            )

        # 解析
        text = rag_mod.read_document(tmp_path)
        if len(text.strip()) < 20:
            raise HTTPException(
                status_code=400,
                detail="文档内容为空或无法提取文字（扫描版 PDF 需要先做 OCR）",
            )

        # 重命名为原始文件名再入库（保证 doc_name 正确）
        target = UPLOAD_DIR / name
        shutil.move(str(tmp_path), str(target))
        tmp_path = None

        kb = rag_mod.get_kb()
        doc = kb.add(target, text, chunk_size=300, overlap=60)
        kb.save()

        return {
            "status": "ok",
            "doc_id": doc.doc_id,
            "name": doc.name,
            "chunks": doc.chunks,
            "chars": doc.chars,
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"处理失败：{e}")
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


@app.delete("/api/kb/documents/{doc_id}")
async def delete_document(doc_id: str, _: None = Depends(check_auth)) -> dict:
    """从知识库删除文档。"""
    kb = rag_mod.get_kb()
    doc = kb.documents.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    file_path = UPLOAD_DIR / doc.name
    if file_path.exists():
        file_path.unlink(missing_ok=True)

    kb.remove(doc_id)
    kb.save()
    return {"status": "ok"}


@app.post("/api/kb/search")
async def kb_search(
    req: dict = Body(...), _: None = Depends(check_auth)
) -> dict:
    """调试用：直接看检索结果，不经过模型。"""
    query = (req.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query 不能为空")
    kb = rag_mod.get_kb()
    try:
        client, model, _ = get_client()
    except Exception:
        client, model = None, ""
    hits = kb.search(
        query, top_k=int(req.get("top_k", 5)),
        rewrite_client=client, rewrite_model=model,
    )
    return {
        "query": query,
        "hits": [
            {
                "doc": c.doc_name,
                "score": round(s, 3),
                "text": c.text[:400],
            }
            for c, s in hits
        ],
    }


def _get_lan_ip() -> str:
    """获取本机局域网 IP（优先 WLAN/以太网，排除虚拟网卡）。"""
    import socket

    best = ""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.6)
        # 连一个外部地址，看内核选了哪个网卡（不会真的发包）
        s.connect(("223.5.5.5", 80))
        best = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    if best and not best.startswith("127."):
        return best

    # 兜底：枚举主机名解析
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except Exception:
        pass
    return "127.0.0.1"


def _find_cpolar() -> str:
    """找 cpolar.exe 的路径。"""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    candidates = [
        root / "tools" / "cpolar" / "cpolar.exe",
        Path(r"D:\Download\APP\cpolar\cpolar.exe"),
        Path.home() / "AppData" / "Local" / "cpolar" / "cpolar.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return ""


def _port_in_use(port: int) -> bool:
    """检查端口是否已被监听。"""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _find_free_port(start: int, max_try: int = 20) -> int:
    """从 start 开始找一个空闲端口。"""
    for p in range(start, start + max_try):
        if not _port_in_use(p):
            return p
    return start


def _find_existing_tunnel() -> str:
    """从已有 cpolar 日志里找仍在工作的隧道地址。"""
    import glob
    import os
    import urllib.request

    if os.name == "nt":
        log_dir = os.environ.get("TEMP", "")
    else:
        log_dir = "/tmp"

    candidates: list[str] = []
    for lf in glob.glob(os.path.join(log_dir, "cpolar_*")):
        try:
            with open(lf, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except Exception:
            continue
        for m in re.finditer(r"Tunnel established at (https://[^\s" + chr(34) + r"]+)", content):
            candidates.append(m.group(1))

    # 从新到旧验证
    for url in reversed(candidates):
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=5) as resp:
                if resp.status == 200:
                    return url
        except Exception:
            continue
    return ""


def _check_cpolar_conflicts() -> dict:
    """检查 cpolar 冲突：服务 + 残留进程。"""
    import subprocess

    info = {"service": "", "service_status": "", "processes": [], "has_conflict": False}

    # 1. 检查 cpolar 服务
    try:
        r = subprocess.run(
            ["sc", "query", "cpolar"],
            capture_output=True, text=True, timeout=5,
        )
        out = r.stdout or ""
        if "RUNNING" in out:
            info["service"] = "cpolar"
            info["service_status"] = "RUNNING"
            info["has_conflict"] = True
        elif "STOPPED" in out:
            info["service"] = "cpolar"
            info["service_status"] = "STOPPED"
    except Exception:
        pass

    # 2. 列出运行中的 cpolar 进程
    try:
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq cpolar.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=8,
        )
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if not line or "cpolar.exe" not in line.lower():
                continue
            parts = [p.strip(chr(34)) for p in line.split(",")]
            if len(parts) >= 2:
                info["processes"].append(parts[1])
    except Exception:
        pass

    # 有服务在跑，或有多个进程，都算冲突
    if info["service_status"] == "RUNNING" or len(info["processes"]) > 1:
        info["has_conflict"] = True

    return info


def _cleanup_cpolar_conflicts(verbose: bool = True) -> bool:
    """清理 cpolar 服务与残留进程。需要管理员权限才能停服务。

    Returns:
        True 表示清理干净，False 表示还有残留（通常是权限不足）。
    """
    import subprocess
    import time

    def _run(args, timeout=10):
        try:
            return subprocess.run(
                args, capture_output=True, text=True, timeout=timeout
            )
        except Exception:
            return None

    # 1. 尝试停止服务（需要管理员）
    _run(["sc", "stop", "cpolar"])
    time.sleep(1)

    # 2. 杀掉所有 cpolar 进程
    _run(["taskkill", "/F", "/IM", "cpolar.exe"])
    time.sleep(2)

    # 3. 再杀一次（有些进程需要两次）
    _run(["taskkill", "/F", "/IM", "cpolar.exe"])
    time.sleep(1)

    # 4. 检查结果
    remain = _check_cpolar_conflicts()
    clean = len(remain["processes"]) == 0

    if verbose and not clean:
        print()
        print("  ⚠️  检测到 cpolar 冲突，自动清理失败（需要管理员权限）")
        print()
        print("     原因：cpolar 被注册成了 Windows 服务，普通权限无法停止")
        print("     影响：可能连到已失效的旧地址，出现 404")
        print()
        print("     解决方法（任选其一）：")
        print("       1. 右键开始菜单 → 终端(管理员)，运行：")
        print("          sc stop cpolar & sc config cpolar start= demand")
        print("       2. 或运行项目根目录的 run.ps1 -FixCpolar")
        print()

    return clean


def _start_tunnel(port: int, cpolar_path: str) -> dict:
    """启动 cpolar 并解析出公网地址。返回 {url, pid} 或 {error}。"""
    import glob
    import os
    import re
    import subprocess
    import tempfile
    import time

    # 1. 先检测冲突，再清理
    conflicts = _check_cpolar_conflicts()
    if conflicts["has_conflict"]:
        parts = []
        if conflicts["service_status"] == "RUNNING":
            parts.append("服务正在运行")
        if len(conflicts["processes"]) > 1:
            parts.append(str(len(conflicts["processes"])) + " 个进程")
        print()
        print("  检测到 cpolar 冲突：" + "、".join(parts) + "，正在清理…")
        _cleanup_cpolar_conflicts(verbose=True)
    else:
        # 无冲突也要杀残留单进程
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "cpolar.exe"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8,
            )
        except Exception:
            pass
        time.sleep(1.5)

    # 2. 清空旧日志
    log_base = os.path.join(tempfile.gettempdir(), "cpolar_auto")
    for f in glob.glob(log_base + "*"):
        try:
            os.remove(f)
        except Exception:
            pass

    # 3. 启动
    # cpolar 是 TUI 程序，需要真实控制台才能稳定运行。
    # 实测：带 CREATE_NO_WINDOW 会变成孤儿后退出；DETACHED_PROCESS 会启动即退。
    # 唯一稳定的方式是用 start 开一个最小化窗口。
    try:
        if os.name == "nt":
            # cpolar 是 TUI 程序，必须有真实控制台才不会退出。
            # CREATE_NEW_CONSOLE (0x10) 给它开一个独立控制台窗口。
            # 默认开独立控制台（cpolar 需要真实终端才稳定）
            # --hide-cpolar 时改用 CREATE_NO_WINDOW（可能不稳定，仅调试用）
            flags = 0x00000008 if _HIDE_CPOLAR else 0x00000010
            proc = subprocess.Popen(
                [cpolar_path, "http", str(port), "-log", log_base, "-log-level", "info"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
        else:
            proc = subprocess.Popen(
                [cpolar_path, "http", str(port), "-log", log_base, "-log-level", "info"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except Exception as e:
        return {"error": "启动失败：" + str(e)[:50]}

    # 4. 轮询日志（最多 75 秒，cpolar 可能要换服务器重试）
    url = ""
    for _ in range(150):
        time.sleep(0.5)
        if proc is not None and proc.poll() is not None:
            return {"error": "cpolar 启动后立即退出，请检查 authtoken"}

        for f in glob.glob(log_base + "*"):
            try:
                with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
            except Exception:
                continue
            m = re.search(r"Tunnel established at (https://[^\s" + chr(34) + r"]+)", content)
            if m:
                url = m.group(1)
                break
        if url:
            break

    if not url:
        return {
            "error": "等待地址超时",
            "pid": proc.pid if proc is not None else 0,
        }

    # 5. 验证地址真的能访问（避免拿到失效的旧地址）
    import urllib.request

    verified = False
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url + "/api/health",
                headers={"User-Agent": "cpolar-verify"},
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status == 200:
                    verified = True
                    break
        except Exception:
            if attempt < 2:
                time.sleep(2)

    # 反查 cpolar 的 PID（start 方式拿不到）
    real_pid = proc.pid if proc is not None else 0
    if real_pid == 0 and os.name == "nt":
        try:
            r = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq cpolar.exe", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            for line in (r.stdout or "").splitlines():
                if "cpolar.exe" in line.lower():
                    parts = [p.strip(chr(34)) for p in line.split(",")]
                    if len(parts) >= 2:
                        real_pid = int(parts[1])
                        break
        except Exception:
            pass

    return {
        "url": url,
        "pid": real_pid,
        "verified": verified,
        "error": None if verified else "地址不可达（可能是旧隧道残留）",
    }


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--no-tunnel", action="store_true", help="不自动启动 cpolar")
    parser.add_argument(
        "--kill-tunnel-on-exit",
        action="store_true",
        help="退出时关闭隧道（默认保留，因为免费版域名 24 小时才变）",
    )
    parser.add_argument(
        "--new-tunnel",
        action="store_true",
        help="强制新建隧道（默认复用已有的，避免地址变化）",
    )
    parser.add_argument(
        "--hide-cpolar",
        action="store_true",
        help="隐藏 cpolar 控制台窗口（可能不稳定）",
    )
    args = parser.parse_args()

    global _HIDE_CPOLAR
    _HIDE_CPOLAR = args.hide_cpolar

    port = args.port

    # 端口被占用时自动换一个，避免 PyCharm 里重复运行直接退出
    if _port_in_use(port):
        old_port = port
        port = _find_free_port(port + 1)
        print()
        print(f"  ⚠️  端口 {old_port} 已被占用（可能上次没关干净）")
        print(f"     自动改用端口 {port}")

    lan_ip = _get_lan_ip()

    # ===== 启动公网隧道 =====
    tunnel = {}
    if not args.no_tunnel:
        cpolar = _find_cpolar()
        if cpolar and not args.new_tunnel:
            # 复用：从现有日志里找已建立的地址
            import glob as _glob
            import re as _re

            existing = ""
            if os.name == "nt":
                log_dir = os.environ.get("TEMP", "")
            else:
                log_dir = "/tmp"
            for lf in _glob.glob(os.path.join(log_dir, "cpolar_*")):
                try:
                    with open(lf, "r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read()
                except Exception:
                    continue
                m = _re.search(
                    r"Tunnel established at (https://[^\s" + chr(34) + r"]+)", content
                )
                if m:
                    existing = m.group(1)

            if existing:
                # 验证地址还活着
                alive = False
                try:
                    import urllib.request

                    with urllib.request.urlopen(
                        existing + "/api/health", timeout=8
                    ) as resp:
                        alive = resp.status == 200
                except Exception:
                    alive = False

                if alive:
                    tunnel = {"url": existing, "pid": 0, "verified": True, "reused": True}
                    print()
                    print(f"  复用已有隧道：{existing}")

        if cpolar and not tunnel:
            print()
            print("  ⏳ 正在申请公网地址（最多等 75 秒，网络差时会重试）…")
            import sys as _s2

            _s2.stdout.flush()
            tunnel = _start_tunnel(port, cpolar)
            if tunnel.get("pid"):
                _TUNNEL_PID = tunnel["pid"]

                # 默认不自动杀隧道：cpolar 免费版域名 24 小时才换一次，
                # 保留隧道可以让别人手上的链接继续有效。
                # 需要退出时清理的，加 --kill-tunnel-on-exit 参数。
                if args.kill_tunnel_on_exit:
                    import atexit

                    def _cleanup_tunnel():
                        try:
                            import subprocess as _sp

                            _sp.run(
                                ["taskkill", "/F", "/PID", str(_TUNNEL_PID)],
                                stdout=_sp.DEVNULL,
                                stderr=_sp.DEVNULL,
                                timeout=5,
                            )
                        except Exception:
                            pass

                    atexit.register(_cleanup_tunnel)

    # ===== 打印访问地址 =====
    W = 60
    print()
    print("  " + "=" * W)
    print("   AI Agent 已启动")
    print("  " + "-" * W)
    print()
    print(f"   🖥  本机访问     http://127.0.0.1:{port}")
    if args.host == "0.0.0.0":
        print(f"   📡 局域网访问   http://{lan_ip}:{port}")

    if tunnel.get("url") and tunnel.get("verified"):
        print()
        print(f"   🌍 公网访问     {tunnel['url']}")
        print(f"      发这个链接给别人，他在任何网络都能访问")
    elif tunnel.get("url") and not tunnel.get("verified"):
        print()
        print(f"   🌍 公网地址     {tunnel['url']}")
        print("      ⚠️  该地址暂时不可达，可能需要等待 10-30 秒生效")
    elif tunnel.get("error"):
        print()
        print(f"   ⚠️  公网隧道失败：{tunnel['error']}")
        print("      cpolar 服务器可能暂时不可达，本机和局域网仍可正常使用")
    elif not args.no_tunnel:
        print()
        print("   ⚠️  未找到 cpolar，只有本机和局域网可访问")
        print("      如需公网访问，把 cpolar.exe 放到 tools/cpolar/ 下")

    print()
    print("  " + "-" * W)
    print("   按 Ctrl+C 停止服务")
    print("  " + "=" * W)
    print()
    import sys as _sys

    _sys.stdout.flush()

    # 自定义日志配置：保留日志内容，但去掉 ANSI 颜色码。
    # uvicorn 默认的彩色日志在 PyCharm / 重定向输出里会显示成 [32mINFO[0m 乱码。
    log_cfg = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            # 键名必须是 default：uvicorn 会写 log_config["formatters"]["default"]["use_colors"]
            "default": {
                "format": "%(levelname)s:     %(message)s",
                "use_colors": False,
            },
            "access": {
                "format": "%(levelname)s:     %(message)s",
                "use_colors": False,
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }

    uvicorn.run(
        "server:app" if args.reload else app,
        host=args.host,
        port=port,
        reload=args.reload,
        log_level="info",
        log_config=log_cfg,
        use_colors=False,
    )


if __name__ == "__main__":
    main()