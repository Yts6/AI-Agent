"""通用工具：token 估算、计时、文本处理。"""

import re
import time
from contextlib import contextmanager


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数。

    英文约 4 字符/token，中文约 1.5 字符/token。
    精确计算请用 tiktoken，这里只是快速估算成本。
    """
    if not text:
        return 0
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    other = len(text) - chinese
    return int(chinese / 1.5 + other / 4)


@contextmanager
def timer(label: str = ""):
    """计时上下文管理器。用法：
    with timer("检索"):
        do_something()
    """
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print(f"[{label}] 耗时 {elapsed:.2f}s" if label else f"耗时 {elapsed:.2f}s")


def truncate(text: str, limit: int = 200) -> str:
    """截断长文本用于日志显示。"""
    text = text.replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "..."
