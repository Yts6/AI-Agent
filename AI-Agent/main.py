"""项目入口：验证环境是否配置成功。

运行：python main.py
"""

import os
import sys

# Windows 控制台中文输出修复
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import env_status


def check_env() -> bool:
    """检查 Python 版本和依赖库是否就绪。"""
    print("=" * 50)
    print("环境检查")
    print("=" * 50)

    major, minor = sys.version_info[:2]
    print(f"Python: {sys.version.split()[0]}", end="  ")
    if (major, minor) < (3, 9):
        print("[失败] 需要 3.9 以上")
        return False
    print("[OK]")

    libs = [
        ("openai", "OpenAI SDK"),
        ("langchain", "LangChain"),
        ("langgraph", "LangGraph"),
        ("dotenv", "python-dotenv"),
        ("streamlit", "Streamlit"),
        ("fastapi", "FastAPI"),
        ("chromadb", "ChromaDB"),
    ]
    ok = True
    for mod, name in libs:
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", None) or "?"
            print(f"{name:<16} {ver:<14} [OK]")
        except ImportError:
            print(f"{name:<16} {'-':<14} [缺失]")
            ok = False

    print("-" * 50)
    print(f"配置文件: {env_status()}")
    keys = {
        "DEEPSEEK_API_KEY": "DeepSeek",
        "ZHIPU_API_KEY": "智谱 AI",
        "SILICONFLOW_API_KEY": "硅基流动",
        "DASHSCOPE_API_KEY": "阿里百炼",
    }
    found = [name for k, name in keys.items() if os.getenv(k)]
    if found:
        print(f"已配置的 API: {'、'.join(found)}")
    else:
        print("尚未配置任何 API Key")
        print("  请复制 .env.example 为 .env，填入至少一个 Key")
        ok = False

    print("=" * 50)
    print("环境就绪，可以开始了！" if ok else "环境未就绪，请按上面的提示修复")
    return ok


if __name__ == "__main__":
    sys.exit(0 if check_env() else 1)
