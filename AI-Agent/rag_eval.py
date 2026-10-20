"""RAG 评估：量化检索和回答的质量。

为什么必须做评估：
    没有评估，你只能凭感觉说"感觉好多了"。
    面试官问"你的 RAG 召回率多少"，你答不上来，说明你没真做过。

三个核心指标（参考 RAGAS）：
    1. Recall@K     —— 检索到正确片段的比例（检索质量）
    2. MRR          —— 正确片段排在第几位的倒数均值（排序质量）
    3. Answer Acc   —— 回答是否包含关键事实（生成质量）

评估集格式（JSONL，每行一条）：
    {"question": "...", "answer": "标准答案", "keywords": ["关键事实1", "关键事实2"]}

keywords 用于判断回答是否命中要点，比字符串全等更鲁棒。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
EVAL_DIR = BASE_DIR / "eval_data"
EVAL_DIR.mkdir(exist_ok=True)


@dataclass
class EvalCase:
    question: str
    answer: str
    keywords: list[str] = field(default_factory=list)
    doc: str = ""


@dataclass
class CaseResult:
    question: str
    retrieved: int
    recall_hit: bool
    mrr: float
    answer: str
    answer_hit: bool
    hit_keywords: list[str]
    elapsed: float


@dataclass
class EvalReport:
    total: int
    recall_at_k: float
    mrr: float
    answer_accuracy: float
    avg_elapsed: float
    results: list[CaseResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "recall_at_k": round(self.recall_at_k, 4),
            "mrr": round(self.mrr, 4),
            "answer_accuracy": round(self.answer_accuracy, 4),
            "avg_elapsed": round(self.avg_elapsed, 3),
            "results": [
                {
                    "question": r.question,
                    "recall_hit": r.recall_hit,
                    "mrr": round(r.mrr, 3),
                    "answer_hit": r.answer_hit,
                    "hit_keywords": r.hit_keywords,
                    "answer": r.answer[:400],
                }
                for r in self.results
            ],
        }


def load_cases(path: Path | None = None) -> list[EvalCase]:
    """从 JSONL 读取评估集。"""
    path = path or (EVAL_DIR / "cases.jsonl")
    if not path.exists():
        return []
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            d = json.loads(line)
            cases.append(
                EvalCase(
                    question=d["question"],
                    answer=d.get("answer", ""),
                    keywords=d.get("keywords", []),
                    doc=d.get("doc", ""),
                )
            )
        except (json.JSONDecodeError, KeyError):
            continue
    return cases


def save_cases(cases: list[EvalCase]) -> None:
    lines = []
    for c in cases:
        lines.append(
            json.dumps(
                {
                    "question": c.question,
                    "answer": c.answer,
                    "keywords": c.keywords,
                    "doc": c.doc,
                },
                ensure_ascii=False,
            )
        )
    (EVAL_DIR / "cases.jsonl").write_text("\n".join(lines), encoding="utf-8")


def _keyword_hit(answer: str, keywords: list[str]) -> tuple[bool, list[str]]:
    """判断回答命中了哪些关键词。

    宽松匹配：只要回答里出现关键词的核心部分就算命中。
    数字类做特殊处理（"200ms" 匹配 "200"）。
    """
    if not answer:
        return False, []

    hit = []
    ans_lower = answer.lower()
    for kw in keywords:
        kw = str(kw).strip()
        if not kw:
            continue
        if kw.lower() in ans_lower:
            hit.append(kw)
            continue

        # 数字提取：200ms / 0.5% / 85%
        nums = re.findall(r"\d+(?:\.\d+)?", kw)
        if nums and all(n in ans_lower for n in nums):
            hit.append(kw)
            continue

        # 中文关键词：取前 4 个字匹配
        if len(kw) >= 4 and kw[:4] in ans_lower:
            hit.append(kw)

    return len(hit) > 0, hit


def evaluate(
    kb,
    cases: list[EvalCase],
    *,
    answer_fn=None,
    top_k: int = 4,
    use_rewrite: bool = True,
    use_rerank: bool = True,
    rewrite_client=None,
    rewrite_model: str = "",
) -> EvalReport:
    """跑完整评估。

    Args:
        kb: KnowledgeBase 实例
        cases: 评估用例
        answer_fn: 生成回答的函数 (question) -> str；为 None 则只评检索
        top_k: 检索返回几条
        use_rewrite: 是否启用查询改写
        use_rerank: 是否启用重排
    """
    if not cases:
        return EvalReport(0, 0, 0, 0, 0)

    results: list[CaseResult] = []

    for case in cases:
        t0 = time.perf_counter()

        # 检索：完整流程交给 kb.search（改写 + 粗排 + 重排都在里面）
        # 注意：不要在外部再做一次规则改写，那会覆盖掉 LLM 的改写结果
        try:
            hits = kb.search(
                case.question,
                top_k=top_k,
                use_rerank=use_rerank,
                use_rewrite=use_rewrite,
                rewrite_client=rewrite_client,
                rewrite_model=rewrite_model,
            )
        except TypeError:
            hits = kb.search(case.question, top_k=top_k)
        except Exception:
            hits = []

        # 判断召回：检索片段是否包含关键词
        recall_hit = False
        first_hit_rank = 0
        for rank, (chunk, _score) in enumerate(hits, 1):
            ok, _ = _keyword_hit(chunk.text, case.keywords)
            if not case.keywords:
                ok = True
            if ok:
                recall_hit = True
                if first_hit_rank == 0:
                    first_hit_rank = rank
                break

        mrr = (1.0 / first_hit_rank) if first_hit_rank else 0.0

        # 生成回答并判断
        answer = ""
        answer_hit = False
        hit_kws: list[str] = []
        if answer_fn is not None:
            try:
                answer = answer_fn(case.question) or ""
            except Exception as e:  # noqa: BLE001
                answer = f"[生成失败: {e}]"
            answer_hit, hit_kws = _keyword_hit(answer, case.keywords)

        results.append(
            CaseResult(
                question=case.question,
                retrieved=len(hits),
                recall_hit=recall_hit,
                mrr=mrr,
                answer=answer,
                answer_hit=answer_hit,
                hit_keywords=hit_kws,
                elapsed=time.perf_counter() - t0,
            )
        )

    n = len(results)
    report = EvalReport(
        total=n,
        recall_at_k=sum(1 for r in results if r.recall_hit) / n,
        mrr=sum(r.mrr for r in results) / n,
        answer_accuracy=(
            sum(1 for r in results if r.answer_hit) / n if answer_fn else 0.0
        ),
        avg_elapsed=sum(r.elapsed for r in results) / n,
        results=results,
    )
    return report


def format_report(report: EvalReport) -> str:
    """把报告格式化成可读文本。"""
    lines = [
        "=" * 56,
        "RAG 评估报告",
        "=" * 56,
        f"用例数：      {report.total}",
        f"Recall@{4}：     {report.recall_at_k:.1%}",
        f"MRR：         {report.mrr:.3f}",
    ]
    if report.answer_accuracy:
        lines.append(f"回答准确率：    {report.answer_accuracy:.1%}")
    lines.append(f"平均耗时：     {report.avg_elapsed:.2f}s")
    lines.append("-" * 56)
    lines.append("逐条结果：")

    for i, r in enumerate(report.results, 1):
        mark = "✓" if r.recall_hit else "✗"
        amark = "✓" if r.answer_hit else "✗"
        lines.append(f"  {i}. {mark} {r.question[:38]}")
        if report.answer_accuracy:
            lines.append(f"     MRR={r.mrr:.2f}  回答={amark}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    cases = load_cases()
    print(f"评估集：{len(cases)} 条")
    for c in cases[:5]:
        print(f"  Q: {c.question}")
        print(f"     关键词: {c.keywords}")