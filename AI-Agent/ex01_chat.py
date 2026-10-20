"""示例 1：多轮对话 + 上下文管理。

演示要点：
- 对话历史怎么维护
- 上下文超长怎么裁剪
- 怎么控制 token 成本

运行：python ex01_chat.py
"""

from config import get_client, stream_print
from utils import estimate_tokens

SYSTEM_PROMPT = "你是一个耐心的编程学习助手，回答简洁准确，必要时给出代码示例。"


class ChatSession:
    """一个带历史管理的对话会话。"""

    def __init__(self, system: str = SYSTEM_PROMPT, max_history: int = 10):
        # 第一条永远是 system，后续是 user/assistant 交替
        self.messages: list[dict] = [{"role": "system", "content": system}]
        self.max_history = max_history

    def ask(self, question: str, *, stream: bool = True) -> str:
        self.messages.append({"role": "user", "content": question})
        self._trim()

        if stream:
            answer = stream_print(self.messages)
        else:
            client, model, _ = get_client()
            resp = client.chat.completions.create(model=model, messages=self.messages)
            answer = resp.choices[0].message.content
            print(answer)

        self.messages.append({"role": "assistant", "content": answer})
        return answer

    def _trim(self) -> None:
        """保留 system + 最近 max_history 轮，防止上下文无限增长。"""
        if len(self.messages) <= 1 + self.max_history * 2:
            return
        # 保留 system 和最后几条
        self.messages = [self.messages[0]] + self.messages[-(self.max_history * 2) :]

    def usage(self) -> str:
        total = sum(estimate_tokens(m["content"]) for m in self.messages)
        return f"历史 {len(self.messages) - 1} 条消息，约 {total} tokens"


def main() -> None:
    print("多轮对话演示（输入 quit 退出，输入 /usage 查看上下文用量）\n")

    session = ChatSession()
    # 预置两轮，演示上下文记忆
    demo = [
        "我叫小李，正在学 Python 做 AI 应用开发。",
        "记住我的名字和方向了吗？",
    ]
    for q in demo:
        print(f"我：{q}")
        print("AI：", end="")
        session.ask(q, stream=True)
        print()

    print("--- 开始自由对话 ---")
    while True:
        try:
            q = input("我：").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q.lower() in {"quit", "exit", "q"}:
            break
        if q == "/usage":
            print(session.usage(), "\n")
            continue
        print("AI：", end="")
        session.ask(q, stream=True)
        print()


if __name__ == "__main__":
    main()
