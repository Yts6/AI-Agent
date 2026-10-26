"""Agent 核心：带联网能力的对话引擎。

流程：
    用户提问
      → 判断是否需要联网（关键词 + 显式开关）
      → 需要则搜索，把结果塞进 system 提示
      → 流式生成回答
      → 通过 SSE 推给前端

设计取舍：
- 不用 LangChain/Agent 框架，裸写一遍，方便你看清"Agent 到底在干什么"
- 意图判断用规则而非第二次模型调用，省 token、更快
- 工具结果注入 system，而不是伪造 user 消息，避免污染对话历史
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

import rag as rag_mod
from config import get_client
import search as search_mod

SYSTEM_BASE = """你是一个乐于助人的 AI 助手，运行在一个自建的 Web 演示程序里。

回答要求：
- 用中文回答，简洁准确，避免空洞的套话
- 涉及代码时给出可直接运行的示例
- 如果不确定，明确说"我不确定"，不要编造
{extra}"""

SYSTEM_WITH_SEARCH = """
本轮对话附带了实时搜索资料，请遵守：
- 优先基于【搜索结果】作答，用 [1][2] 标注引用的来源编号
- 搜索结果没覆盖到的内容，可以用你自己的知识补充，但要说明这是通用知识
- 如果搜索结果和问题无关，直接说明没搜到有用信息，然后按常识回答
- 不要照抄搜索结果，要综合概括"""


SYSTEM_WITH_KB = """

本轮附带了【知识库检索结果】，来自用户上传的文档。回答规则：

1. 文档里**有**答案：直接用它回答，用 [1][2] 标注引用编号
2. 文档里**只有部分**相关：先用文档的部分，缺失的用你自己的知识补全，
   并明确区分（例如"文档中提到 X[1]；补充说明 Y"）
3. 文档里**完全没有**相关内容：正常用你的通用知识回答，开头用一句话说明
   "文档未涉及此问题，以下基于通用知识"，不要拒绝回答
4. 涉及文档里的数字、人名、配置项时，严格照原文，不要改动
5. 引用时带上文档名，方便核对"""

# 触发联网的关键词（命中任一即搜索）
_SEARCH_HINTS = (
    "最新", "今天", "现在", "最近", "今年", "实时", "当前",
    "新闻", "价格", "股价", "汇率", "天气", "发布", "上线",
    "多少", "谁是", "排名", "对比", "怎么样", "值得",
)

# 明显不需要联网的（闲聊、写作类）
_NO_SEARCH_HINTS = (
    "你好", "谢谢", "再见", "写一首", "讲个笑话", "翻译一下",
)


def should_search(question: str, force: bool = False, enabled: bool = True) -> bool:
    """判断这个问题要不要联网。"""
    if force:
        return True
    if not enabled:
        return False
    q = question.strip()
    if len(q) < 4:
        return False
    if any(h in q for h in _NO_SEARCH_HINTS):
        return False
    return any(h in q for h in _SEARCH_HINTS)


@dataclass
class ChatState:
    """一次对话的状态。"""

    messages: list[dict] = field(default_factory=list)
    search_enabled: bool = True

    def __post_init__(self) -> None:
        if not self.messages:
            self.messages.append(
                {"role": "system", "content": SYSTEM_BASE.format(extra="")}
            )

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": SYSTEM_BASE.format(extra="")}]

    def trim(self, max_rounds: int = 12) -> None:
        """保留 system + 最近 N 轮。"""
        limit = 1 + max_rounds * 2
        if len(self.messages) > limit:
            self.messages = [self.messages[0]] + self.messages[-max_rounds * 2 :]


def _build_messages(
    state: ChatState,
    question: str,
    search_results: list | None,
    kb_hits: list | None = None,
    attachments: list[dict] | None = None,
    model_id: str = "",
) -> list[dict]:
    """组装本次请求的 messages，不修改 state 里的历史。

    优先级：知识库 > 联网搜索 > 纯对话。
    用户上传了文档时，以文档为准，不再让模型自由发挥。
    """
    msgs = list(state.messages)

    kb_block = ""
    if kb_hits:
        parts = []
        for i, (chunk, score) in enumerate(kb_hits, 1):
            parts.append(
                f"[{i}] 来源：{chunk.doc_name}（相关度 {score:.2f}）\n{chunk.text}"
            )
        kb_block = (
            "\n\n【知识库检索结果】\n"
            + "\n\n".join(parts)
            + "\n【知识库结束】\n")

    search_block = ""
    if search_results and not kb_hits:
        search_block = (
            "\n\n【本轮搜索结果】\n"
            + search_mod.format_for_prompt(search_results)
            + "\n【搜索结果结束】\n"
        )

    if kb_block:
        extra = SYSTEM_WITH_KB + kb_block
    elif search_block:
        extra = SYSTEM_WITH_SEARCH + search_block
    else:
        extra = ""

    msgs[0] = {"role": "system", "content": SYSTEM_BASE.format(extra=extra)}
    # ===== 附件处理 =====
    # 分两类：
    #   - 图片且模型支持视觉 → 多模态消息，把图片直接给模型看
    #   - 其他（文档 / 不支持视觉时的 OCR 文本）→ 拼成文本
    image_parts: list[dict] = []
    text_parts: list[str] = []

    if attachments:
        vision_ok = False
        try:
            import config as cfg_mod

            vision_ok = cfg_mod.supports_vision(model_id)
        except Exception:
            vision_ok = False

        for a in attachments:
            name = a.get("name", "文件")
            a_type = a.get("type", "doc")
            data_url = a.get("data_url") or ""
            content = (a.get("text") or "").strip()

            # 图片 + 支持视觉 → 走多模态
            if a_type == "image" and data_url and vision_ok:
                image_parts.append(
                    {"type": "image_url", "image_url": {"url": data_url}}
                )
                if content:
                    text_parts.append(
                        f"【图片 {name} 的 OCR 文字参考】\n{content[:2000]}"
                    )
                continue

            # 其他情况：走文本
            if not content:
                if a_type == "image":
                    text_parts.append(
                        f"【图片：{name}】当前模型不支持视觉识别，无法查看图片内容。"
                        "如需识图，请切换到 qwen3-vl-plus 模型。"
                    )
                continue

            if len(content) > 8000:
                content = content[:8000] + "\n...(内容过长，已截断)"
            text_parts.append(f"【附件：{name}】\n{content}")

    # 组装最终用户消息
    if image_parts:
        content_list: list[dict] = []
        header = "\n\n".join(text_parts) + ("\n\n" if text_parts else "")
        content_list.append({"type": "text", "text": header + question})
        content_list.extend(image_parts)
        msgs.append({"role": "user", "content": content_list})
    elif text_parts:
        attach_text = (
            "\n\n=== 用户本轮上传的附件 ===\n"
            + "\n\n".join(text_parts)
            + "\n=== 附件结束 ===\n"
            "请优先基于上述附件内容回答。"
        )
        msgs.append({"role": "user", "content": attach_text})
        msgs.append({"role": "user", "content": question})
    else:
        msgs.append({"role": "user", "content": question})
    return msgs


def stream_answer(
    state: ChatState,
    question: str,
    *,
    force_search: bool = False,
    use_kb: bool = True,
    model_id: str = "",
    attachments: list[dict] | None = None,
) -> Iterator[dict]:
    """生成回答，逐个事件 yield 给上层。

    事件类型：
        {"type": "kb_start"}
        {"type": "kb_done", "hits": [...]}
        {"type": "search_start", "query": str}
        {"type": "search_done", "results": [...]}
        {"type": "delta", "text": str}
        {"type": "done", "sources": [...], "kb_sources": [...]}
        {"type": "error", "message": str}
    """
    question = (question or "").strip()
    if not question:
        yield {"type": "error", "message": "问题不能为空"}
        return

    # 先拿到模型客户端（查询改写和生成都要用）
    try:
        client, model, _ = get_client(model_id)
    except Exception as e:  # noqa: BLE001
        yield {"type": "error", "message": f"模型不可用：{e}"}
        return

    # 有附件时优先看附件，跳过知识库检索（避免两套上下文打架）
    has_attachments = bool(attachments)

    # ===== 第 1 步：知识库检索（有文档时优先） =====
    kb_hits: list = []
    if use_kb and not has_attachments:
        try:
            kb = rag_mod.get_kb()
            if kb.chunks:
                yield {"type": "kb_start"}
                kb_hits = kb.search(question, top_k=4, rewrite_client=client, rewrite_model=model)
                # 二道过滤：只保留相关度足够高的片段。
                # 阈值太低会把无关文档硬塞给模型，导致它明明知道答案却说"文档里没有"。
                kb_hits = [(c, sc) for c, sc in kb_hits if sc >= 0.20]
                yield {
                    "type": "kb_done",
                    "hits": [
                        {
                            "doc": c.doc_name,
                            "score": round(s, 3),
                            "preview": c.text[:120].replace("\n", " "),
                        }
                        for c, s in kb_hits
                    ],
                }
        except Exception as e:  # noqa: BLE001
            yield {"type": "kb_error", "message": str(e)}
            kb_hits = []

    # ===== 第 2 步：联网搜索（知识库没命中时才搜） =====
    results: list = []
    if not kb_hits:
        do_search = should_search(
            question, force=force_search, enabled=state.search_enabled
        )
        if do_search:
            yield {"type": "search_start", "query": question}
            try:
                results = search_mod.search(question, limit=4)
            except Exception as e:  # noqa: BLE001
                results = []
                yield {"type": "search_error", "message": str(e)}
            yield {
                "type": "search_done",
                "results": [
                    {"title": r.title, "url": r.url, "snippet": r.snippet[:160]}
                    for r in results
                ],
            }

    # ===== 第 3 步：调模型流式生成 =====
    msgs = _build_messages(
        state, question, results or None, kb_hits or None, attachments, model_id
    )
    parts: list[str] = []

    import time as _time

    _t_start = _time.time()
    _t_first_reasoning = None

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=0.3 if kb_hits else 0.6,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # 推理模型（deepseek-v4.1-flash）会先在 reasoning_content 里输出思考过程。
            # 单独发一个事件，前端可以折叠展示，不混进正式回答。
            reasoning_piece = getattr(delta, "reasoning_content", None)
            if reasoning_piece:
                if _t_first_reasoning is None:
                    _t_first_reasoning = _time.time()
                yield {"type": "reasoning", "text": reasoning_piece}

            piece = delta.content
            if piece:
                parts.append(piece)
                yield {"type": "delta", "text": piece}
    except Exception as e:  # noqa: BLE001
        yield {"type": "error", "message": f"生成失败：{e}"}
        return

    answer = "".join(parts)

    # ===== 第 4 步：写入历史 =====
    # 只存干净的问答，不存检索结果，避免上下文无限膨胀
    state.messages.append({"role": "user", "content": question})
    state.messages.append(
        {"role": "assistant", "content": answer, "model_id": model}
    )
    state.trim()

    _elapsed = round(_time.time() - _t_start, 1)
    _thinking = (
        round(_time.time() - _t_first_reasoning, 1) if _t_first_reasoning else 0
    )

    yield {
        "type": "done",
        "elapsed": _elapsed,
        "thinking": _thinking,
        "sources": [{"title": r.title, "url": r.url} for r in results],
        "kb_sources": [
            {"doc": c.doc_name, "score": round(s, 3)} for c, s in kb_hits
        ],
        "answer": answer,
    }