"""SQLite 数据层：会话、消息、文档、片段、模型配置。

设计说明
--------
- 用 Python 标准库 sqlite3，零安装依赖
- 所有写操作走事务，读操作加索引
- 向量单独存 .npy 文件：numpy 矩阵乘法比反序列化快得多
- 保留旧 JSON 的只读兼容，迁移后不再写 JSON

用法
----
    from db import get_db
    db = get_db()
    db.list_sessions()
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "agent.db"

# 旧数据目录（仅用于一次性迁移）
LEGACY_SESSION_DIR = BASE_DIR / "session_store"
LEGACY_RAG_DIR = BASE_DIR / "rag_store"
LEGACY_MODELS = BASE_DIR / "models.json"

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sessions (
    id       TEXT PRIMARY KEY,
    title    TEXT NOT NULL DEFAULT '新对话',
    created  REAL NOT NULL,
    updated  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated DESC);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created     REAL NOT NULL,
    reasoning   TEXT,
    thinking_ms INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS documents (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    size    INTEGER DEFAULT 0,
    chunks  INTEGER DEFAULT 0,
    chars   INTEGER DEFAULT 0,
    created REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id   TEXT NOT NULL,
    doc_name TEXT NOT NULL,
    text     TEXT NOT NULL,
    ord      INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id, ord);

CREATE TABLE IF NOT EXISTS models (
    id        TEXT PRIMARY KEY,
    label     TEXT,
    tag       TEXT,
    desc      TEXT,
    provider  TEXT,
    base_url  TEXT,
    model     TEXT,
    api_key   TEXT,
    vision    INTEGER DEFAULT 0,
    reasoning INTEGER DEFAULT 0,
    enabled   INTEGER DEFAULT 1,
    created   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class Database:
    """线程安全的 SQLite 封装。"""

    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(path), check_same_thread=False, timeout=15
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._migrate_columns()
            self._conn.commit()

    def _migrate_columns(self) -> None:
        """给老数据库补上新增的列（幂等）。"""
        try:
            cols = {
                r["name"]
                for r in self._conn.execute("PRAGMA table_info(messages)").fetchall()
            }
            if "reasoning" not in cols:
                self._conn.execute("ALTER TABLE messages ADD COLUMN reasoning TEXT")
            if "thinking_ms" not in cols:
                self._conn.execute(
                    "ALTER TABLE messages ADD COLUMN thinking_ms INTEGER"
                )
        except Exception:
            pass

    # ---------- 底层 ----------

    @contextmanager
    def tx(self):
        """写事务。"""
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        """查询。"""
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    def q1(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        rows = self.q(sql, args)
        return rows[0] if rows else None

    # ---------- 会话 ----------

    def list_sessions(self, limit: int = 200) -> list[dict]:
        rows = self.q(
            "SELECT id, title, created, updated FROM sessions "
            "ORDER BY updated DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    def get_session(self, sid: str) -> dict | None:
        row = self.q1("SELECT * FROM sessions WHERE id = ?", (sid,))
        if not row:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "created": row["created"],
            "updated": row["updated"],
            "messages": self.get_messages(sid),
        }

    def ensure_session(self, sid: str, title: str = "新对话") -> str:
        now = time.time()
        with self.tx() as c:
            c.execute(
                "INSERT OR IGNORE INTO sessions(id, title, created, updated) "
                "VALUES (?,?,?,?)",
                (sid, title, now, now),
            )
        return sid

    def touch_session(self, sid: str, title: str | None = None) -> None:
        now = time.time()
        with self.tx() as c:
            if title:
                c.execute(
                    "UPDATE sessions SET updated = ?, title = ? WHERE id = ?",
                    (now, title, sid),
                )
            else:
                c.execute("UPDATE sessions SET updated = ? WHERE id = ?", (now, sid))

    def rename_session(self, sid: str, title: str) -> bool:
        with self.tx() as c:
            cur = c.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, sid))
            return cur.rowcount > 0

    def delete_session(self, sid: str) -> bool:
        with self.tx() as c:
            cur = c.execute("DELETE FROM sessions WHERE id = ?", (sid,))
            return cur.rowcount > 0

    # ---------- 消息 ----------

    def get_messages(self, sid: str) -> list[dict]:
        rows = self.q(
            "SELECT role, content, created, reasoning, thinking_ms "
            "FROM messages WHERE session_id = ? ORDER BY id",
            (sid,),
        )
        return [
            {
                "role": r["role"],
                "content": r["content"],
                "created": r["created"],
                "reasoning": r["reasoning"] or "",
                "thinking_ms": r["thinking_ms"] or 0,
            }
            for r in rows
        ]

    def add_message(self, sid: str, role: str, content: str) -> None:
        now = time.time()
        with self.tx() as c:
            c.execute(
                "INSERT INTO messages(session_id, role, content, created) VALUES (?,?,?,?)",
                (sid, role, content, now),
            )
            c.execute("UPDATE sessions SET updated = ? WHERE id = ?", (now, sid))

    def replace_messages(self, sid: str, messages: list[dict]) -> None:
        """整体替换某会话的消息（用于保存完整历史）。"""
        now = time.time()
        with self.tx() as c:
            c.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
            for m in messages:
                if m.get("role") == "system":
                    continue
                c.execute(
                    "INSERT INTO messages"
                    "(session_id, role, content, created, reasoning, thinking_ms) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        sid,
                        m.get("role", "user"),
                        m.get("content", ""),
                        m.get("created") or now,
                        m.get("reasoning") or "",
                        int(m.get("thinking_ms") or 0),
                    ),
                )
            c.execute("UPDATE sessions SET updated = ? WHERE id = ?", (now, sid))

    def count_messages(self, sid: str) -> int:
        row = self.q1("SELECT COUNT(*) n FROM messages WHERE session_id = ?", (sid,))
        return row["n"] if row else 0

    # ---------- 文档 ----------

    def list_documents(self) -> list[dict]:
        rows = self.q("SELECT * FROM documents ORDER BY created")
        return [dict(r) for r in rows]

    def add_document(self, doc_id: str, name: str, size: int, chunks: int, chars: int) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO documents(id,name,size,chunks,chars,created) "
                "VALUES (?,?,?,?,?,?)",
                (doc_id, name, size, chunks, chars, time.time()),
            )

    def delete_document(self, doc_id: str) -> bool:
        with self.tx() as c:
            cur = c.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            return cur.rowcount > 0

    def get_document_by_name(self, name: str) -> dict | None:
        row = self.q1("SELECT * FROM documents WHERE name = ?", (name,))
        return dict(row) if row else None

    # ---------- 片段 ----------

    def add_chunks(self, doc_id: str, doc_name: str, texts: list[str]) -> None:
        with self.tx() as c:
            c.executemany(
                "INSERT INTO chunks(doc_id, doc_name, text, ord) VALUES (?,?,?,?)",
                [(doc_id, doc_name, t, i) for i, t in enumerate(texts)],
            )

    def list_chunks(self) -> list[dict]:
        rows = self.q("SELECT id, doc_id, doc_name, text, ord FROM chunks ORDER BY id")
        return [dict(r) for r in rows]

    def delete_chunks_of(self, doc_id: str) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))

    def clear_chunks(self) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM chunks")

    # ---------- 模型 ----------

    def list_models(self, only_enabled: bool = True) -> list[dict]:
        sql = "SELECT * FROM models"
        if only_enabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY created"
        return [dict(r) for r in self.q(sql)]

    def get_model(self, mid: str) -> dict | None:
        row = self.q1("SELECT * FROM models WHERE id = ?", (mid,))
        return dict(row) if row else None

    def add_model(self, m: dict) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO models(id,label,tag,desc,provider,base_url,model,"
                "api_key,vision,reasoning,enabled,created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    m["id"], m.get("label"), m.get("tag"), m.get("desc"),
                    m.get("provider"), m.get("base_url"), m.get("model"),
                    m.get("api_key"), int(bool(m.get("vision"))),
                    int(bool(m.get("reasoning"))), int(bool(m.get("enabled", 1))),
                    m.get("created") or time.time(),
                ),
            )

    def update_model(self, mid: str, m: dict) -> None:
        fields = []
        args: list[Any] = []
        for k in ("label", "tag", "desc", "provider", "base_url", "model", "api_key"):
            if k in m and m[k] is not None:
                fields.append(f"{k} = ?")
                args.append(m[k])
        if "vision" in m:
            fields.append("vision = ?")
            args.append(int(bool(m["vision"])))
        if "reasoning" in m:
            fields.append("reasoning = ?")
            args.append(int(bool(m["reasoning"])))
        if "enabled" in m:
            fields.append("enabled = ?")
            args.append(int(bool(m["enabled"])))
        if not fields:
            return
        args.append(mid)
        with self.tx() as c:
            c.execute(f"UPDATE models SET {', '.join(fields)} WHERE id = ?", tuple(args))

    def delete_model(self, mid: str) -> bool:
        with self.tx() as c:
            cur = c.execute("DELETE FROM models WHERE id = ?", (mid,))
            return cur.rowcount > 0

    # ---------- meta ----------

    def get_meta(self, key: str) -> str | None:
        row = self.q1("SELECT value FROM meta WHERE key = ?", (key,))
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES (?,?)", (key, value))

    # ---------- 统计 ----------

    def stats(self) -> dict:
        return {
            "sessions": (self.q1("SELECT COUNT(*) n FROM sessions") or {"n": 0})["n"],
            "messages": (self.q1("SELECT COUNT(*) n FROM messages") or {"n": 0})["n"],
            "documents": (self.q1("SELECT COUNT(*) n FROM documents") or {"n": 0})["n"],
            "chunks": (self.q1("SELECT COUNT(*) n FROM chunks") or {"n": 0})["n"],
            "models": (self.q1("SELECT COUNT(*) n FROM models") or {"n": 0})["n"],
        }


# ============ 单例 ============

_db: Database | None = None
_db_lock = threading.Lock()


def get_db() -> Database:
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = Database()
    return _db


# ============ 一次性迁移 ============

def migrate_from_legacy(db: Database | None = None, verbose: bool = True) -> dict:
    """把旧的 JSON / npy 数据导入数据库。

    幂等：重复运行不会重复插入。
    """
    db = db or get_db()
    report = {"sessions": 0, "messages": 0, "documents": 0, "chunks": 0, "models": 0}

    if db.get_meta("migrated_v1") == "done":
        if verbose:
            print("[db] 已完成过迁移，跳过")
        return report

    # ---- 1. 会话 ----
    if LEGACY_SESSION_DIR.exists():
        for fp in LEGACY_SESSION_DIR.glob("*.json"):
            try:
                d = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
            sid = d.get("session_id") or fp.stem
            msgs = d.get("messages") or []
            if db.get_session(sid):
                continue
            db.ensure_session(sid, d.get("title") or "新对话")
            body = [m for m in msgs if m.get("role") != "system"]
            if body:
                db.replace_messages(sid, body)
                report["messages"] += len(body)
            report["sessions"] += 1

    # ---- 2. 知识库 ----
    meta_fp = LEGACY_RAG_DIR / "meta.json"
    if meta_fp.exists() and db.stats()["chunks"] == 0:
        try:
            meta = json.loads(meta_fp.read_text(encoding="utf-8"))
            docs = meta.get("documents", {})
            chunks = meta.get("chunks", [])

            for doc_id, d in docs.items():
                db.add_document(
                    doc_id,
                    d.get("name", ""),
                    d.get("size", 0),
                    d.get("chunks", 0),
                    d.get("chars", 0),
                )
                report["documents"] += 1

            # 按 doc_name 把 chunk 归到 doc
            name2id = {d.get("name"): k for k, d in docs.items()}
            buckets: dict[str, list[tuple[int, str]]] = {}
            for c in chunks:
                dn = c.get("doc_name", "")
                buckets.setdefault(dn, []).append((c.get("id", 0), c.get("text", "")))

            for dn, items in buckets.items():
                did = name2id.get(dn, dn)
                items.sort(key=lambda x: x[0])
                db.add_chunks(did, dn, [t for _, t in items])
                report["chunks"] += len(items)
        except Exception as e:
            if verbose:
                print(f"[db] 知识库迁移失败：{e}")

    # ---- 3. 模型 ----
    if LEGACY_MODELS.exists():
        try:
            mdata = json.loads(LEGACY_MODELS.read_text(encoding="utf-8"))
            for m in mdata.get("custom", []):
                if db.get_model(m.get("id", "")):
                    continue
                db.add_model(m)
                report["models"] += 1
        except Exception as e:
            if verbose:
                print(f"[db] 模型迁移失败：{e}")

    db.set_meta("migrated_v1", "done")
    db.set_meta("migrated_at", time.strftime("%Y-%m-%d %H:%M:%S"))

    if verbose:
        print(
            f"[db] 迁移完成：{report['sessions']} 会话 / "
            f"{report['messages']} 消息 / {report['documents']} 文档 / "
            f"{report['chunks']} 片段 / {report['models']} 模型"
        )
    return report


if __name__ == "__main__":
    import sys

    d = get_db()
    print("数据库:", d.path)
    print("当前统计:", d.stats())
    if "--migrate" in sys.argv:
        migrate_from_legacy(d)
        print("迁移后统计:", d.stats())
