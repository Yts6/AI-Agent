"""RAG 引擎：文档解析 → 切分 → 向量化 → 检索 → 重排。

设计说明：
- 不依赖 ChromaDB/FAISS，用 numpy 做暴力检索。
  原因：单机文档量小（几百页），暴力检索在毫秒级，且零外部依赖、可解释。
  如果文档上万页再换向量库。
- embedding 用本地 bge-small-zh（512 维），已下载到 models/ 目录，离线可用。
- 检索用「向量 + 关键词」混合打分，缓解纯语义检索对专有名词不敏感的问题。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models" / "bge-small-zh"
STORE_DIR = BASE_DIR / "rag_store"
RERANK_DIR = BASE_DIR / "models" / "bge-reranker-base"

# 检索参数
RECALL_K = 8       # 粗排召回数量（给重排的候选池，越小越快）
RERANK_TOP = 4     # 精排后返回数量
MIN_SCORE = 0.10   # 重排后绝对下限（低于此值认为与问题无关，不再硬塞进上下文）
REL_SCORE = 0.15   # 相对阈值：低于 top1 分数的这个比例则丢弃
DEDUP_SIM = 0.92   # 片段相似度超过此值视为重复

# embedding 维度（阿里云百炼 text-embedding-v4 输出 1024 维）
# 知识库载入时用它校验：维度不符说明换了 embedding 方案，旧向量作废
EMBED_DIM = 1024

# 让 transformers 完全离线，避免每次启动尝试联网
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_embed_lock = threading.Lock()
_embedder = None


def _get_embedder():
    """懒加载 embedding 模型（首次约 1 秒，之后常驻内存）。"""
    global _embedder
    if _embedder is not None:
        return _embedder
    with _embed_lock:
        if _embedder is not None:
            return _embedder
        import torch
        from transformers import AutoModel, AutoTokenizer

        if not MODEL_DIR.exists():
            raise RuntimeError(
                f"找不到 embedding 模型：{MODEL_DIR}\n"
                "请确认 models/bge-small-zh 目录完整（包含 pytorch_model.bin）"
            )
        tok = AutoTokenizer.from_pretrained(str(MODEL_DIR))
        model = AutoModel.from_pretrained(str(MODEL_DIR))
        model.eval()
        _embedder = (tok, model, torch)
        return _embedder


def _embed_via_api(texts: list[str]) -> np.ndarray | None:
    """用阿里云百炼 text-embedding-v4 计算向量。

    返回 None 表示 API 不可用，调用方报错。

    批处理：百炼 API 对单次请求的输入总量有限制，
    长文档切出的块数多（几十块），一次性发送会超限报错。
    所以按 20 条一批切分。
    """
    import json
    import urllib.request

    key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not key:
        return None

    BATCH = 10  # 百炼限制：单次 batch size 不能超过 10 条
    all_vecs: list[np.ndarray] = []

    for i in range(0, len(texts), BATCH):
        batch = texts[i : i + BATCH]
        try:
            body = json.dumps({"model": "text-embedding-v4", "input": batch}).encode()
            req = urllib.request.Request(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
                data=body,
                headers={
                    "Authorization": "Bearer " + key,
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read())
            vecs = np.array(
                [item["embedding"] for item in d["data"]], dtype=np.float32
            )
            all_vecs.append(vecs)
        except Exception:
            return None

    if not all_vecs:
        return None

    result = np.vstack(all_vecs)
    # 归一化（与本地模型行为一致）
    norms = np.linalg.norm(result, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return (result / norms).astype(np.float32)


def embed_texts(texts: list[str]) -> np.ndarray:
    """把文本列表转成归一化向量矩阵（1024 维）。

    统一使用阿里云百炼 text-embedding-v4 API。
    API 不可用时抛异常，不做本地降级——
    混用两种维度的向量会导致检索点积崩溃，不如直接报错让用户知道。
    """
    if not texts:
        return np.zeros((0, EMBED_DIM), dtype=np.float32)

    v = _embed_via_api(texts)
    if v is None:
        raise RuntimeError(
            "百炼 embedding API 调用失败。请检查：\n"
            "  1. .env 里 DASHSCOPE_API_KEY 是否有效\n"
            "  2. 网络是否可达 dashscope.aliyuncs.com\n"
            "  3. 账号是否还有免费额度",
        )
    return v



# ============ 重排（Reranker） ============

_rerank_lock = threading.Lock()
_reranker = None


def _get_reranker():
    """懒加载 bge-reranker-base。

    这是一个交叉编码器（cross-encoder）：把 query 和 passage 拼一起送进模型，
    直接输出相关性分数。比 bi-encoder 的向量点积准得多，但慢，
    所以只对粗排召回的 top-12 做精排。
    """
    global _reranker
    if _reranker is not None:
        return _reranker
    with _rerank_lock:
        if _reranker is not None:
            return _reranker
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        if not RERANK_DIR.exists():
            raise RuntimeError(f"找不到重排模型：{RERANK_DIR}")

        tok = AutoTokenizer.from_pretrained(str(RERANK_DIR))
        model = AutoModelForSequenceClassification.from_pretrained(str(RERANK_DIR))
        model.eval()
        _reranker = (tok, model, torch)
        return _reranker


def rerank_scores_batch(queries: list[str], passages: list[str]) -> list[list[float]]:
    """批量重排：一次前向算完所有 (query, passage) 组合。

    之前是循环每个 query 调一次，25 条评估 × 3 个改写 × 12 候选 = 900 次前向，
    耗时 178 秒。合并成一个 batch 后能快 5-10 倍。
    """
    if not queries or not passages:
        return [[0.0] * len(passages) for _ in queries]

    try:
        tok, model, torch = _get_reranker()
    except Exception:
        return [[0.5] * len(passages) for _ in queries]

    pairs: list[list[str]] = []
    for q in queries:
        if not q.strip():
            q = queries[0]
        for p in passages:
            pairs.append([q, p])

    out: list[float] = []
    batch = 32
    with torch.no_grad():
        for i in range(0, len(pairs), batch):
            chunk = pairs[i : i + batch]
            enc = tok(
                chunk, padding=True, truncation=True,
                max_length=512, return_tensors="pt",
            )
            logits = model(**enc).logits.view(-1)
            out.extend(float(x) for x in torch.sigmoid(logits))

    n = len(passages)
    return [out[i * n : (i + 1) * n] for i in range(len(queries))]


def rerank_scores(query: str, passages: list[str]) -> list[float]:
    """单查询重排（兼容接口）。"""
    return rerank_scores_batch([query], passages)[0]

# ============ 文档解析 ============

def _read_txt(path: Path) -> str:
    for enc in ("utf-8", "gbk", "utf-16", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return path.read_bytes().decode("utf-8", errors="ignore")


def _read_pdf(path: Path) -> str:
    try:
        import pypdf
    except ImportError:
        raise RuntimeError("解析 PDF 需要 pypdf，请运行 pip install pypdf")
    reader = pypdf.PdfReader(str(path))
    parts = []
    for i, page in enumerate(reader.pages):
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    return "\n".join(parts)


def _read_docx(path: Path) -> str:
    try:
        import docx
    except ImportError:
        raise RuntimeError("解析 Word 需要 python-docx，请运行 pip install python-docx")
    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells))
    return "\n".join(parts)


def read_document(path: Path) -> str:
    """按扩展名解析文档为纯文本。"""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix == ".docx":
        return _read_docx(path)
    if suffix in {".txt", ".md", ".markdown", ".csv", ".log", ".py", ".json"}:
        return _read_txt(path)
    raise ValueError(f"不支持的文件类型：{suffix}（支持 pdf/docx/txt/md/csv）")


# ============ 切分 ============

# 句子边界：中文句号/问号/叹号/分号，或换行
_SENT_END = re.compile(r"(?<=[。！？；!?])")
# 标题行（Markdown 或编号），要粘在后面的正文前面，不能单独成块
_HEADING = re.compile(r"^\s*(#{1,6}\s+.+|\d+[.、]\s*.+|第[一二三四五六七八九十]+[章节].*)$")


def split_text(text: str, chunk_size: int = 500, overlap: int = 80) -> list[str]:
    """按「标题 + 句子」切分，保证每块从完整句子开始。

    关键设计：
    1. 标题与其后正文绑定（标题不能单独成块）
    2. 重叠按【完整句子】取，不是按字符硬切
       —— 否则下一块会从句子中间开始，检索和重排都会变差
    3. 块内句子合并到接近 chunk_size
    """
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []

    # 第一遍：拆成「标题单元」和「句子单元」
    units: list[str] = []
    buf = ""

    def flush_buf() -> None:
        nonlocal buf
        if buf.strip():
            # 段落内按句子再切
            for s in _SENT_END.split(buf):
                s = s.strip()
                if s:
                    units.append(s)
            buf = ""

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            flush_buf()
            continue
        if _HEADING.match(line):
            flush_buf()
            # 标题单独作为一个 unit，后面合并时优先与正文同块
            units.append("\x00H" + line)
        else:
            buf += line
            if len(buf) >= chunk_size:
                flush_buf()
    flush_buf()

    if not units:
        return []

    # 第二遍：贪心合并
    chunks: list[str] = []
    cur_parts: list[str] = []
    cur_len = 0

    def close_chunk() -> list[str]:
        """收尾当前块，返回用于重叠的尾部句子。"""
        nonlocal cur_parts, cur_len
        if not cur_parts:
            return []
        body = "".join(p.lstrip("\x00H") if p.startswith("\x00H") else p for p in cur_parts)
        if len(body.strip()) > 20:
            chunks.append(body.strip())
        # 取尾部若干完整句子做重叠
        tail: list[str] = []
        tail_len = 0
        for p in reversed(cur_parts):
            p_clean = p.lstrip("\x00H")
            if tail_len + len(p_clean) > overlap:
                break
            tail.insert(0, p_clean)
            tail_len += len(p_clean)
        cur_parts = []
        cur_len = 0
        return tail

    for u in units:
        is_heading = u.startswith("\x00H")
        raw = u.lstrip("\x00H")

        # 超长单元硬切
        if len(raw) > chunk_size:
            tail = close_chunk()
            for i in range(0, len(raw), chunk_size):
                piece = raw[i : i + chunk_size]
                if piece.strip():
                    chunks.append(piece.strip())
            continue

        need = len(raw) + (1 if cur_parts else 0)
        if cur_len + need > chunk_size and cur_parts:
            tail = close_chunk()
            cur_parts = list(tail)
            cur_len = sum(len(t) for t in tail)
            # 标题不要和前面的尾巴混在一起，单独起头
            if is_heading:
                cur_parts = []
                cur_len = 0

        cur_parts.append(u)
        cur_len += len(raw) + (1 if len(cur_parts) > 1 else 0)

    close_chunk()
    return [c for c in chunks if len(c) > 20]


# ============ 关键词打分（辅助混合检索） ============

def _bigrams(text: str) -> set[str]:
    """中文按二元组切，英文按单词切，用于关键词重合度打分。"""
    text = text.lower()
    chars = re.sub(r"[^\u4e00-\u9fff a-z0-9]", " ", text)
    tokens: set[str] = set()
    for word in re.findall(r"[a-z0-9]{2,}", chars):
        tokens.add(word)
    Han = re.findall(r"[\u4e00-\u9fff]", chars)
    for i in range(len(Han) - 1):
        tokens.add(Han[i] + Han[i + 1])
    return tokens


def keyword_score(query: str, chunk: str) -> float:
    """查询与块的字面重合度，0~1。"""
    q = _bigrams(query)
    if not q:
        return 0.0
    c = _bigrams(chunk)
    if not c:
        return 0.0
    return len(q & c) / len(q)


# ============ 数据模型 ============

@dataclass
class Chunk:
    id: int
    text: str
    doc_name: str
    page: int = 0


@dataclass
class Document:
    doc_id: str
    name: str
    size: int
    chunks: int
    chars: int


@dataclass
class KnowledgeBase:
    """一个知识库：文档 + 向量 + 元数据。"""

    chunks: list[Chunk] = field(default_factory=list)
    vectors: np.ndarray = field(default_factory=lambda: np.zeros((0, 512), dtype=np.float32))
    documents: dict[str, Document] = field(default_factory=dict)

    def add(self, path: Path, text: str, chunk_size: int, overlap: int) -> Document:
        doc_id = hashlib.md5(str(path).encode()).hexdigest()[:12]
        pieces = split_text(text, chunk_size, overlap)
        base = len(self.chunks)
        new_chunks = [
            Chunk(id=base + i, text=p, doc_name=path.name) for i, p in enumerate(pieces)
        ]
        vecs = embed_texts([c.text for c in new_chunks])

        self.chunks.extend(new_chunks)
        self.vectors = (
            np.vstack([self.vectors, vecs]) if len(self.vectors) else vecs
        )
        doc = Document(
            doc_id=doc_id,
            name=path.name,
            size=path.stat().st_size,
            chunks=len(pieces),
            chars=len(text),
        )
        self.documents[doc_id] = doc
        return doc

    def remove(self, doc_id: str) -> bool:
        doc = self.documents.get(doc_id)
        if not doc:
            return False
        keep = [c for c in self.chunks if c.doc_name != doc.name]
        if keep:
            self.vectors = self.vectors[[c.id for c in keep]]
            for i, c in enumerate(keep):
                c.id = i
        else:
            self.vectors = np.zeros((0, 512), dtype=np.float32)
        self.chunks = keep
        del self.documents[doc_id]
        return True

    def _recall(
        self, queries: list[str], limit: int, alpha: float = 0.7
    ) -> list[tuple[int, float]]:
        """粗排：多查询混合打分，返回 (索引, 分数)。

        向量相似度 + 关键词重合度的加权和。多个改写查询取最高分。
        """
        if not self.chunks:
            return []

        best: dict[int, float] = {}
        for q in queries:
            if not q.strip():
                continue
            qv = embed_texts([q])[0]
            vec = self.vectors @ qv
            kw = np.array([keyword_score(q, c.text) for c in self.chunks])
            combined = alpha * vec + (1 - alpha) * kw
            for i, s in enumerate(combined):
                if s > best.get(int(i), -1.0):
                    best[int(i)] = float(s)

        order = sorted(best.items(), key=lambda kv: -kv[1])[:limit]
        return order

    def search(
        self,
        query: str,
        top_k: int = RERANK_TOP,
        alpha: float = 0.7,
        *,
        use_rerank: bool = True,
        use_rewrite: bool = True,
        recall_k: int = RECALL_K,
        min_score: float = MIN_SCORE,
        rewrite_client=None,
        rewrite_model: str = "",
    ) -> list[tuple[Chunk, float]]:
        """完整检索流程：改写 → 粗排召回 → 精排 → 去重 → 阈值过滤。

        Args:
            query: 用户问题
            top_k: 最终返回几条
            alpha: 粗排时向量权重（1-alpha 给关键词）
            use_rerank: 是否用交叉编码器精排
            use_rewrite: 是否做查询改写
            recall_k: 粗排召回多少条给精排
            min_score: 低于此分数视为未命中

        Returns:
            [(Chunk, score), ...]；score 是最终相关度（重排后为 0~1）
        """
        if not self.chunks:
            return []

        # 1. 查询改写（智能模式：只在口语化/指代时调 LLM）
        queries = [query]
        if use_rewrite:
            try:
                import query_rewrite

                if rewrite_client and rewrite_model:
                    queries = query_rewrite.smart_rewrite(
                        query, rewrite_client, rewrite_model
                    )
                else:
                    queries = query_rewrite.rewrite(query)
            except Exception:
                queries = [query]

        # 2. 粗排召回
        candidates = self._recall(queries, limit=max(recall_k, top_k), alpha=alpha)
        if not candidates:
            return []

        # 3. 精排（多查询取最大分）
        #
        # 为什么要对每个改写查询分别重排？
        # 实测：用户问"数据库怎么保证读性能"，直接把原句喂给 reranker，
        # 正确片段（含"主从架构、从库只读"）只有 0.005 分；
        # 换成"数据库主从架构 读写分离"后，同一片段升到 0.608。
        # 所以让每个改写查询都投一次票，取最高分。
        if use_rerank and len(candidates) > 1:
            try:
                passages = [self.chunks[i].text for i, _ in candidates]
                valid = [q for q in queries if q.strip()] or [query]
                all_scores = rerank_scores_batch(valid, passages)
                best_scores = [0.0] * len(candidates)
                for row in all_scores:
                    for k, sc in enumerate(row):
                        if sc > best_scores[k]:
                            best_scores[k] = sc
                ranked = sorted(
                    zip([i for i, _ in candidates], best_scores),
                    key=lambda x: -x[1],
                )
            except Exception:
                ranked = candidates
        else:
            ranked = candidates

        # 4. 去重 + 阈值 + 截断
        #
        # 阈值采用「相对 + 绝对」双条件：
        #   - 相对：分数低于 top1 的 REL_SCORE 倍，说明明显无关
        #   - 绝对：低于 MIN_SCORE 视为完全无关
        # 只用绝对阈值会有问题——bge-reranker 对"短查询 vs 长片段"的
        # 打分普遍偏低（正确片段可能只有 0.1~0.2），一刀切 0.3 会误杀。
        top_score = ranked[0][1] if ranked else 0.0
        rel_floor = top_score * REL_SCORE
        floor = max(min_score, rel_floor) if use_rerank else min_score

        picked: list[tuple[int, float]] = []
        picked_idx: list[int] = []
        for idx, score in ranked:
            if len(picked) >= top_k:
                break
            if score < floor:
                continue
            if picked_idx:
                sims = self.vectors[picked_idx] @ self.vectors[idx]
                if float(np.max(sims)) > DEDUP_SIM:
                    continue
            picked.append((idx, score))
            picked_idx.append(idx)

        # 兜底：一个都没选出来但确实有候选，至少给最相关的 1 条
        if not picked and ranked and ranked[0][1] > 0.001:
            picked = [ranked[0]]

        return [(self.chunks[i], float(s)) for i, s in picked]

        return [(self.chunks[i], float(s)) for i, s in picked]

    def search_debug(self, query: str, top_k: int = 5, *, rewrite_client=None,
                     rewrite_model: str = "") -> dict:
        """返回检索的中间过程，用于前端调试。

        必须和 search() 走完全相同的流程，否则调试结果会误导人
        （之前这里只用规则改写，导致调试看到的结果和实际检索不一致）。
        """
        try:
            import query_rewrite

            if rewrite_client and rewrite_model:
                queries = query_rewrite.smart_rewrite(query, rewrite_client, rewrite_model)
            else:
                queries = query_rewrite.rewrite(query)
        except Exception:
            queries = [query]

        candidates = self._recall(queries, limit=RECALL_K)
        passages = [self.chunks[i].text for i, _ in candidates]

        # 与 search() 一致：每个改写查询都重排，取最大分
        best = [0.0] * len(candidates)
        if candidates:
            try:
                for q in queries:
                    if not q.strip():
                        continue
                    s = rerank_scores(q, passages)
                    for k, sc in enumerate(s):
                        if sc > best[k]:
                            best[k] = sc
            except Exception:
                best = [0.0] * len(candidates)

        recall_view = [
            {
                "rank": rank,
                "score": round(s, 3),
                "doc": self.chunks[i].doc_name,
                "preview": self.chunks[i].text[:80].replace("\n", " "),
                "rerank": round(rs, 3),
            }
            for rank, ((i, s), rs) in enumerate(zip(candidates, best), 1)
        ]

        recall_view.sort(key=lambda x: -x["rerank"])

        # 直接用上面算好的结果，不再调一次 search（重排慢，重复调用很浪费）
        ranked_all = sorted(
            zip([ci for ci, _ in candidates], best or [0.0] * len(candidates)),
            key=lambda x: -x[1],
        )
        top_rr = ranked_all[0][1] if ranked_all else 0.0
        floor = max(MIN_SCORE, top_rr * REL_SCORE)

        picked: list[tuple[int, float]] = []
        picked_idx: list[int] = []
        for idx, sc in ranked_all:
            if len(picked) >= top_k:
                break
            if sc < floor:
                continue
            if picked_idx:
                sims = self.vectors[picked_idx] @ self.vectors[idx]
                if float(np.max(sims)) > DEDUP_SIM:
                    continue
            picked.append((idx, sc))
            picked_idx.append(idx)
        if not picked and ranked_all and ranked_all[0][1] > 0.001:
            picked = [ranked_all[0]]

        final = [(self.chunks[ci], sc) for ci, sc in picked]
        return {
            "query": query,
            "rewritten": queries,
            "recall_k": len(candidates),
            "candidates": recall_view[:10],
            "final": [
                {"doc": c.doc_name, "score": round(s, 3), "text": c.text[:200]}
                for c, s in final
            ],
        }

    def save(self) -> None:
        """保存知识库：元信息和文本入库，向量存 npy。

        向量不存库的原因：numpy 矩阵乘法做检索比反序列化 BLOB 快得多。
        chunks 的 id 顺序和 npy 的行号一一对应。
        """
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            import db as db_mod

            d = db_mod.get_db()
            d.clear_chunks()
            with d.tx() as c:
                c.execute("DELETE FROM documents")
            for doc in self.documents.values():
                d.add_document(doc.doc_id, doc.name, doc.size, doc.chunks, doc.chars)
            # 按 id 顺序写入，保证与向量行号一致
            ordered = sorted(self.chunks, key=lambda x: x.id)
            if ordered:
                with d.tx() as c:
                    c.executemany(
                        "INSERT INTO chunks(doc_id, doc_name, text, ord) VALUES (?,?,?,?)",
                        [
                            (
                                next(
                                    (k for k, v in self.documents.items() if v.name == ch.doc_name),
                                    ch.doc_name,
                                ),
                                ch.doc_name,
                                ch.text,
                                i,
                            )
                            for i, ch in enumerate(ordered)
                        ],
                    )
        except Exception as e:
            print(f"[RAG] 入库失败，回退到文件：{e}")

        np.save(STORE_DIR / "vectors.npy", self.vectors)

    @classmethod
    def load(cls) -> "KnowledgeBase":
        """从数据库加载知识库，向量从 npy 读。"""
        kb = cls()
        vec_path = STORE_DIR / "vectors.npy"

        # 1. 从数据库读元信息和文本
        try:
            import db as db_mod

            d = db_mod.get_db()
            docs = d.list_documents()
            chunks = d.list_chunks()
            if docs and chunks:
                for row in docs:
                    kb.documents[row["id"]] = Document(
                        doc_id=row["id"],
                        name=row["name"],
                        size=row["size"],
                        chunks=row["chunks"],
                        chars=row["chars"],
                    )
                kb.chunks = [
                    Chunk(id=i, text=r["text"], doc_name=r["doc_name"])
                    for i, r in enumerate(chunks)
                ]
        except Exception as e:
            print(f"[RAG] 从库加载失败：{e}")

        # 2. 读向量
        if vec_path.exists():
            try:
                vecs = np.load(vec_path)
                if vecs.ndim == 2 and vecs.shape[1] != EMBED_DIM:
                    print(
                        f"[RAG] 向量维度 {vecs.shape[1]} != {EMBED_DIM}，需要重建知识库"
                    )
                    return cls()
                # 数量和 chunk 对不上说明数据不一致
                if len(kb.chunks) and vecs.shape[0] != len(kb.chunks):
                    print(
                        f"[RAG] 向量数 {vecs.shape[0]} != 片段数 {len(kb.chunks)}，以较小者为准"
                    )
                    n = min(vecs.shape[0], len(kb.chunks))
                    kb.chunks = kb.chunks[:n]
                    vecs = vecs[:n]
                kb.vectors = vecs
            except Exception as e:
                print(f"[RAG] 向量加载失败：{e}")

        return kb

# 全局单例
_kb: KnowledgeBase | None = None
_kb_lock = threading.Lock()


def get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        with _kb_lock:
            if _kb is None:
                _kb = KnowledgeBase.load()
    return _kb


# ============ 历史消息语义搜索 ============
# 把历史对话也做成向量索引，支持"我记得之前聊过 XX"式的模糊查找。
# 向量存 msg_vectors.npy，元信息存 SQLite 的 msg_vectors 表。

MSG_VEC_PATH = STORE_DIR / "msg_vectors.npy"

_msg_vecs: np.ndarray | None = None
_msg_meta: list[dict] | None = None
_msg_lock = threading.Lock()


def msg_index_available() -> bool:
    """消息向量索引是否可用（表和文件都存在）。"""
    return MSG_VEC_PATH.exists() and MSG_VEC_PATH.stat().st_size > 0


def rebuild_msg_index(batch_limit: int = 2000) -> dict:
    """重建历史消息向量索引。

    Returns:
        {"ok": bool, "count": int, "error": str}
    """
    global _msg_vecs, _msg_meta

    try:
        import db as db_mod

        d = db_mod.get_db()
        if not d.ensure_msg_vectors_table():
            return {"ok": False, "count": 0, "error": "数据库只读，无法创建向量表"}

        rows = d.q(
            "SELECT id, session_id, role, content, created FROM messages "
            "WHERE role IN ('user', 'assistant') "
            "ORDER BY id DESC LIMIT ?",
            (batch_limit,),
        )
        if not rows:
            return {"ok": True, "count": 0, "error": ""}

        items = []
        for r in rows:
            content = (r["content"] or "").strip()
            if not content:
                continue
            # 只索引摘要（前 500 字），长回答没必要全存
            snippet = content[:500]
            items.append(
                {
                    "msg_id": r["id"],
                    "session_id": r["session_id"],
                    "role": r["role"],
                    "snippet": snippet,
                    "created": r["created"],
                }
            )

        if not items:
            return {"ok": True, "count": 0, "error": ""}

        texts = [f"{it['role']}: {it['snippet']}" for it in items]
        vecs = embed_texts(texts)  # 可能抛异常（API 不可用）

        STORE_DIR.mkdir(parents=True, exist_ok=True)
        np.save(MSG_VEC_PATH, vecs)

        with d.tx() as c:
            c.execute("DELETE FROM msg_vectors")
        for it in items:
            d.add_msg_vector(
                it["msg_id"], it["session_id"], it["role"],
                it["snippet"], it["created"],
            )

        with _msg_lock:
            _msg_vecs = vecs
            _msg_meta = items

        return {"ok": True, "count": len(items), "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "count": 0, "error": f"{type(e).__name__}: {e}"}


def _load_msg_index() -> bool:
    """加载消息向量索引（懒加载）。"""
    global _msg_vecs, _msg_meta

    if _msg_vecs is not None and _msg_meta is not None:
        return True

    if not msg_index_available():
        return False

    try:
        import db as db_mod

        d = db_mod.get_db()
        meta = d.list_msg_vectors()
        if not meta:
            return False

        vecs = np.load(MSG_VEC_PATH)
        if vecs.ndim != 2 or vecs.shape[1] != EMBED_DIM:
            return False
        if vecs.shape[0] != len(meta):
            n = min(vecs.shape[0], len(meta))
            vecs = vecs[:n]
            meta = meta[:n]

        with _msg_lock:
            _msg_vecs = vecs
            _msg_meta = meta
        return True
    except Exception:
        return False


def search_messages(query: str, top_k: int = 8) -> list[dict]:
    """在历史消息里做语义搜索。

    Returns:
        [{session_id, role, snippet, score, created}, ...]
    """
    if not query or not query.strip():
        return []

    if not _load_msg_index():
        return []

    try:
        qv = embed_texts([query])[0]
    except Exception:
        return []

    with _msg_lock:
        vecs = _msg_vecs
        meta = _msg_meta

    if vecs is None or not len(meta or []):
        return []

    scores = vecs @ qv
    order = np.argsort(-scores)[:top_k]

    out = []
    for idx in order:
        if scores[idx] < 0.25:  # 太低的不要
            continue
        m = meta[int(idx)]
        out.append(
            {
                "session_id": m["session_id"],
                "role": m["role"],
                "snippet": m["snippet"],
                "score": round(float(scores[idx]), 3),
                "created": m["created"],
            }
        )
    return out


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        kb = KnowledgeBase()
        text = (
            "RAG 是检索增强生成，先检索再生成，可以减少幻觉。"
            "Python 用 open() 读文件，with 语法能自动关闭。"
            "FastAPI 支持异步和自动文档。"
        )
        p = Path("_test.txt")
        p.write_text(text * 5, encoding="utf-8")
        d = kb.add(p, text * 5, 200, 40)
        print("added:", d)
        for q in ["怎么减少幻觉", "Python读文件"]:
            print(f"\n查询: {q}")
            for c, s in kb.search(q, 2):
                print(f"  [{s:.3f}] {c.text[:50]}")