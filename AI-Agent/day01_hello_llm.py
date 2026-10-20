"""第一个大模型调用示例 —— 看懂最小可运行版本。

这个文件故意保留"手写版"，方便你看清每一步在做什么。
理解后再看 config.py 里的封装，就知道为什么那样设计。

运行：python day01_hello_llm.py
需要：项目根目录的 .env 中配置至少一个 API Key
"""

import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import env_status, get_client


def main() -> None:
    # 1. 拿到客户端和模型名（config 里已按优先级选好）
    client, model, platform = get_client()

    print(f"配置文件: {env_status()}")
    print(f"使用平台: {platform}")
    print(f"使用模型: {model}\n")

    # 2. 构造消息列表
    #    system 设定角色和行为，user 是用户输入
    messages = [
        {"role": "system", "content": "你是一个简洁的助手，回答控制在三句话以内。"},
        {"role": "user", "content": "用三句话解释什么是 RAG，以及它为什么能减少大模型的幻觉。"},
    ]

    print("问题：", messages[-1]["content"])
    print("回答：", end="", flush=True)

    # 3. 发起请求，stream=True 表示流式返回（边生成边显示）
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        temperature=0.7,  # 0 最确定，2 最发散，一般 0.7 左右
    )

    # 4. 逐块读取并打印
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)

    print("\n")


if __name__ == "__main__":
    main()
