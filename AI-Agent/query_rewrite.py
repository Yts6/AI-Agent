"""查询改写：把用户口语化的问题改写成更适合检索的形式。

为什么需要：
    用户问"这东西咋弄"、"上次说的那个"，直接拿去向量检索效果很差。
    改写成多个具体、含关键词的查询，能显著提升召回。

两种策略：
    1. 规则：口语词替换（零成本，快速）
    2. LLM：让模型生成 2-3 个不同角度的检索查询（有成本，效果好）

这里两种都保留，默认用规则，可在配置里切换。
"""

from __future__ import annotations

import time
import re

# 口语 → 书面（按长度降序替换，避免短词先匹配）
_COLLOQUIAL = {
    "咋样": "如何", "咋办": "怎么解决", "咋弄": "怎么做",
    "啥": "什么", "咋": "怎么", "咋回事": "是什么原因",
    "能不能": "是否可以", "可不可以": "是否可以",
    "东西": "内容", "那个": "", "这个": "",
    "搞": "做", "弄": "做", "整": "做",
    "老是": "经常", "老是出": "经常出现",
    "为啥": "为什么", "咱": "我们",
    "牛逼": "优秀", "厉害": "优秀",
    "多少钱": "价格多少", "贵不贵": "价格如何",
}

# 需要保留的技术词（避免被误改）
_KEEP_PATTERN = re.compile(
    r"[A-Za-z][A-Za-z0-9_\-.]*|\d+[A-Za-z]*|[\u4e00-\u9fff]{2,6}(?=的|是|有|在)"
)

_STRIP_PATTERN = re.compile(r"[？?！!。,，、；;：:\s]+$")


def rule_rewrite(query: str) -> str:
    """规则改写：口语词归一 + 清理标点。

    零成本，适合高频调用。但不能理解语义。
    """
    q = (query or "").strip()
    if not q:
        return ""

    # 按长度降序替换，避免 "咋" 先于 "咋样" 被替换
    for old in sorted(_COLLOQUIAL, key=len, reverse=True):
        if old in q:
            q = q.replace(old, _COLLOQUIAL[old])

    q = _STRIP_PATTERN.sub("", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q or query.strip()


LLM_REWRITE_PROMPT = """你是检索查询改写助手。把用户问题改写成 3 个适合技术文档检索的查询。

核心要求：**必须使用具体的技术术语，而不是口语描述**。

为什么重要：用户问"数据库怎么保证读性能"，文档里写的是"主从架构、从库只读"，
两者字面完全不同。只有把问题改写成"数据库主从架构 读写分离"，才能检索到。

改写规则：
1. 第一个查询保留原问题（防止改写丢失原意）
2. 第二、三个查询要用【技术文档里可能出现的术语】
3. 思考：这个问题在技术文档里通常怎么表述？对应的专业名词是什么？
4. 直接输出 JSON 数组，不要解释

示例：
用户：数据库怎么保证读性能
输出：["数据库怎么保证读性能", "数据库主从架构 读写分离", "从库只读 主库写入"]

用户：内存老是不够用是啥原因
输出：["内存老是不够用是啥原因", "内存泄漏 排查", "堆内存 OOM 原因"]

用户：缓存咋就崩了呢，上次那个事故
输出：["缓存咋就崩了呢，上次那个事故", "缓存雪崩 原因", "Redis 主节点宕机 缓存失效"]

用户：接口响应太慢了怎么优化
输出：["接口响应太慢了怎么优化", "接口性能优化 慢查询 索引", "P99 延迟 优化"]
"""


def llm_rewrite(query: str, client, model: str, n: int = 3) -> list[str]:
    """用 LLM 生成多个检索查询。失败时回退到规则改写。"""
    import json

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": LLM_REWRITE_PROMPT},
                {"role": "user", "content": f"用户问题：{query}"},
            ],
            temperature=0.3,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)

        # 兼容 {"queries": [...]} 和 [...] 两种返回
        if isinstance(data, list):
            queries = data
        else:
            queries = (
                data.get("queries")
                or data.get("输出")
                or next((v for v in data.values() if isinstance(v, list)), [])
            )

        # 去重，并剔除与原问题重复的项（原问题最后统一拼回去）
        seen: set[str] = set()
        extra: list[str] = []
        for q in queries:
            q = str(q).strip()
            if not q or q in seen or q == query:
                continue
            seen.add(q)
            extra.append(q)

        if extra:
            # 原问题放第一位，后面是改写结果，最多 n 条
            return ([query] + extra)[:n]
    except Exception:
        pass

    return [query, rule_rewrite(query)]


def needs_llm_rewrite(query: str) -> bool:
    """判断是否值得花 LLM 调用做改写。

    触发条件（满足任一）：
    1. 含口语词/指代词 —— 字面完全没法检索
    2. 问句但缺少文档可能使用的关键词 —— 口语描述 vs 术语描述
       例如用户问"怎么保证读性能"，文档写的是"主从架构、从库只读"，
       字面和语义都对不上，必须改写成"数据库主从架构"才能召回。
    3. 极短且无技术词
    """
    q = (query or "").strip()
    if len(q) < 4:
        return False

    # 1. 口语词 / 指代词
    colloquial = (
        "咋", "啥", "老是", "东西", "整", "搞", "弄", "能不能",
        "这个", "那个", "上次", "之前", "刚才",
    )
    if any(m in q for m in colloquial):
        return True

    # 2. 极短且无技术词
    if len(q) <= 8 and not re.search(r"[A-Za-z0-9]", q):
        return True

    # 3. 「怎么/如何/为什么 + 动词短语」型问题，缺具体名词
    #    这类问题往往需要术语化改写才能匹配文档
    if re.search(r"(怎么|如何|怎样|为什么|为啥)(保证|实现|做到|避免|解决|优化|提升)", q):
        return True

    return False


# 改写结果缓存：相同问题 1 小时内不重复调 LLM
_cache: dict[str, tuple[list[str], float]] = {}
_CACHE_TTL = 3600


def smart_rewrite(
    query: str, client=None, model: str = "", force_llm: bool = False
) -> list[str]:
    """智能改写：只在必要时调用 LLM，兼顾效果与成本。

    实测：规则改写 < 1ms，LLM 改写 2-4s。
    加了一层内存缓存，相同问题在 TTL 内直接复用。
    """
    q = (query or "").strip()
    if not q:
        return []

    now = time.time()
    cached = _cache.get(q)
    if cached and now - cached[1] < _CACHE_TTL:
        return list(cached[0])

    result: list[str]
    if force_llm or (client and model and needs_llm_rewrite(q)):
        if client and model:
            result = llm_rewrite(q, client, model)
        else:
            rw = rule_rewrite(q)
            result = [q] if rw == q else [q, rw]
    else:
        rw = rule_rewrite(q)
        result = [q] if rw == q else [q, rw]

    # 只缓存真正走了 LLM 的结果（规则改写本身极快，没必要缓存）
    if client and model and needs_llm_rewrite(q):
        _cache[q] = (list(result), now)
        if len(_cache) > 500:
            oldest = min(_cache.items(), key=lambda kv: kv[1][1])
            _cache.pop(oldest[0], None)

    return result


def rewrite(query: str, client=None, model: str = "", use_llm: bool = False) -> list[str]:
    """统一入口。

    Args:
        query: 用户原始问题
        client: OpenAI 客户端（use_llm=True 时必需）
        model: 模型名
        use_llm: 是否用 LLM 改写（更准但更慢更贵）

    Returns:
        查询列表，第一个通常是原始问题
    """
    q = (query or "").strip()
    if not q:
        return []

    if use_llm and client and model:
        return llm_rewrite(q, client, model)

    rw = rule_rewrite(q)
    return [q] if rw == q else [q, rw]


if __name__ == "__main__":
    tests = [
        "这东西咋弄啊，老是出问题",
        "RAG 咋减少幻觉的？",
        "多少钱",
        "what is RAG?",
    ]
    for t in tests:
        print(f"{t!r:40} -> {rewrite(t)}")