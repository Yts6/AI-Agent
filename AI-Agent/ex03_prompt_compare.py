"""示例 3：Prompt 效果对比实验。

同一个问题，不同 Prompt 写法，输出质量和成本差多少？
这是 Prompt 工程的核心方法——用实验说话，而不是凭感觉。

观察重点：
- A/B 写得笼统 → 模型自由发挥 → 花更多 token 还不一定答到点上
- C/D 给了结构和示例 → 输出更收敛 → 反而更省 token

运行：python ex03_prompt_compare.py
"""

from dataclasses import dataclass

from config import get_client

QUESTION = "我用 Python 写了个函数，运行时提示 KeyError: 'name'，怎么解决？"

PROMPTS = {
    "A 直接问（基线）": "我遇到 KeyError: 'name'，怎么解决？",

    "B 补充上下文": (
        "我用 Python 写了个函数，运行时提示 KeyError: 'name'，怎么解决？"
    ),

    "C 角色 + 输出结构": (
        "你是一位经验丰富的 Python 工程师。请分析下面的报错并给出解决方案。\n\n"
        "报错信息：KeyError: 'name'\n"
        "语言：Python\n"
        "场景：访问字典的某个键时出错\n\n"
        "请严格按以下结构回答，每部分不超过 5 行：\n"
        "1. 原因（一句话）\n"
        "2. 解决方案（给可运行代码）\n"
        "3. 如何预防"
    ),

    "D 角色 + 结构 + Few-shot": (
        "你是一位经验丰富的 Python 工程师。请分析报错并给出解决方案。\n\n"
        "示例输入：AttributeError: 'NoneType' object has no attribute 'get'\n"
        "示例输出：\n"
        "1. 原因：变量是 None，调用 .get() 时触发。\n"
        "2. 解决方案：\n"
        "   obj = response.get('data') or {}\n"
        "3. 预防：接口返回后先做空值校验。\n\n"
        "现在处理这个（结构同上，每部分不超过 5 行）：\n"
        "报错信息：KeyError: 'name'\n"
        "语言：Python\n"
        "场景：访问字典的某个键时出错"
    ),
}


@dataclass
class Result:
    label: str
    prompt_chars: int
    prompt_tokens: int
    completion_tokens: int
    answer: str
    truncated: bool


def run_one(label: str, prompt: str, max_tokens: int = 900) -> Result:
    client, model, _ = get_client()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=max_tokens,
    )
    answer = (resp.choices[0].message.content or "").strip()
    u = resp.usage

    print(f"\n{'=' * 62}")
    print(f"【{label}】")
    print(f"{'=' * 62}")
    print(answer)
    print(f"\n[统计] prompt {u.prompt_tokens} tok + completion {u.completion_tokens} tok "
          f"= 共 {(u.prompt_tokens or 0) + (u.completion_tokens or 0)} tok")

    return Result(
        label=label,
        prompt_chars=len(prompt),
        prompt_tokens=u.prompt_tokens or 0,
        completion_tokens=u.completion_tokens or 0,
        answer=answer,
        truncated=(u.completion_tokens or 0) >= max_tokens,
    )


def print_summary(results: list[Result]) -> None:
    print(f"\n{'=' * 62}")
    print("汇总对比")
    print("=" * 62)
    header = f"{'写法':<26}{'输入tok':>8}{'输出tok':>8}{'总tok':>8}{'超长截断':>10}"
    print(header)
    print("-" * 62)
    for r in results:
        total = r.prompt_tokens + r.completion_tokens
        flag = "是" if r.truncated else "-"
        print(f"{r.label:<26}{r.prompt_tokens:>8}{r.completion_tokens:>8}{total:>8}{flag:>10}")

    print("-" * 62)
    print("怎么读这张表：")
    print("  1. 输出 token 越多 ≠ 答案越好。A 往往在堆砌所有可能情况。")
    print("  2. C/D 给了结构约束，模型会挑重点说，反而更短更准。")
    print("  3. 输入 token 增加几倍，成本远低于输出自由发挥的浪费。")
    print("  4. 出现「超长截断」说明你该给模型更明确的长度约束。")
    print("\n实践建议：")
    print("  - 先用 A 快速试，看模型懂不懂这个任务")
    print("  - 再用 C/D 定稿，把结构固化进你的 prompt 模板")
    print("  - 每次改 prompt 都跑一遍对比，用数据判断，别凭感觉")


def main() -> None:
    print(f"待测试问题：{QUESTION}")
    print(f"对比 {len(PROMPTS)} 种 Prompt 写法的输出质量与 token 成本")

    results = [run_one(label, prompt) for label, prompt in PROMPTS.items()]
    print_summary(results)


if __name__ == "__main__":
    main()
