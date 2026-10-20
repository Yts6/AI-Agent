"""项目配置与模型客户端。

统一管理 API Key、模型选择、超时和重试，避免每个脚本重复写。

关于 .env 的位置：代码放在 AI-Agent/ 子目录，而 .env 在项目根目录。
这里用「从本文件位置向上查找 .env」的方式定位，
无论从哪个目录运行脚本都能读到配置，不依赖当前工作目录。
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


def _find_env_file() -> Path | None:
    """从当前文件所在目录向上查找 .env，最多找 4 层。"""
    here = Path(__file__).resolve().parent
    for _ in range(4):
        candidate = here / ".env"
        if candidate.is_file():
            return candidate
        if here.parent == here:  # 已到盘符根
            break
        here = here.parent
    return None


_ENV_PATH = _find_env_file()
if _ENV_PATH:
    load_dotenv(_ENV_PATH)
else:
    load_dotenv()  # 兜底：按 dotenv 默认规则找，找不到也不报错


def env_status() -> str:
    """返回 .env 定位情况，用于自检和排错。"""
    if _ENV_PATH:
        return f"已加载 {_ENV_PATH}"
    return "未找到 .env（已从脚本目录向上查找 4 层）"


@dataclass(frozen=True)
class ModelConfig:
    """一个模型端点的配置。"""

    name: str           # 展示名
    base_url: str       # API 地址
    model: str          # 模型名
    api_key: str        # 密钥


# 可选模型清单（前端下拉框用）
# id 是 API 里的 model 参数，label 是展示名
MODEL_CATALOG = [
    {
        "id": "qwen3.5-flash",
        "label": "qwen3.5-flash",
        "tag": "最新",
        "desc": "最新一代，带深度思考，速度快",
        "reasoning": True,
    },
    {
        "id": "qwen3.5-plus",
        "label": "qwen3.5-plus",
        "tag": "最强",
        "desc": "最新旗舰，复杂推理和多模态最强",
        "reasoning": True,
    },
    {
        "id": "qwen3-vl-plus",
        "label": "qwen3-vl-plus",
        "tag": "视觉",
        "desc": "能看懂图片，识图、OCR、图表分析",
        "vision": True,
        "reasoning": True,
    },
    {
        "id": "qwen3-coder-flash",
        "label": "qwen3-coder-flash",
        "tag": "代码",
        "desc": "代码专用，写代码和改 bug 更快更准",
    },
    {
        "id": "deepseek-v4.1-flash",
        "label": "deepseek-v4.1-flash",
        "tag": "推理",
        "desc": "DeepSeek 思维链，擅长数学和逻辑",
        "reasoning": True,
    },
    {
        "id": "qwen-flash",
        "label": "qwen-flash",
        "tag": "免费",
        "desc": "经典款，稳定、免费、响应快",
    },
    {
        "id": "qwen-turbo",
        "label": "qwen-turbo",
        "tag": "免费",
        "desc": "均衡型，比 flash 稍强",
    },
    {
        "id": "qwen-plus",
        "label": "qwen-plus",
        "tag": "更强",
        "desc": "复杂推理，质量明显更好",
    },
    {
        "id": "qwen-max",
        "label": "qwen-max",
        "tag": "旗舰",
        "desc": "上一代旗舰，推理能力强",
    },
    {
        "id": "qwen-long",
        "label": "qwen-long",
        "tag": "长文本",
        "desc": "超长上下文，适合读整本书",
    },
]
_DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def list_models() -> list[dict]:
    """返回所有可用模型：内置（需有 Key）+ 自定义。"""
    out: list[dict] = []

    # 内置模型（百炼）
    if os.getenv("DASHSCOPE_API_KEY"):
        for m in MODEL_CATALOG:
            out.append(dict(m))

    # 自定义模型
    try:
        import model_store

        for m in model_store.list_custom():
            if not m.get("enabled", True):
                continue
            out.append(
                {
                    "id": m["id"],
                    "label": m.get("label") or m["id"],
                    "tag": m.get("tag") or "自定义",
                    "desc": m.get("desc") or "",
                    "vision": bool(m.get("vision")),
                    "reasoning": bool(m.get("reasoning")),
                    "custom": True,
                }
            )
    except Exception:
        pass

    return out


def get_model_by_id(model_id: str) -> ModelConfig | None:
    """按模型 id 取配置。先查内置，再查自定义。"""
    # 1. 自定义模型优先（用户显式添加的）
    try:
        import model_store

        m = model_store.get_custom(model_id)
        if m and m.get("enabled", True):
            return ModelConfig(
                m.get("label") or model_id,
                m["base_url"],
                m["model"],
                m["api_key"],
            )
    except Exception:
        pass

    # 2. 内置模型
    key = os.getenv("DASHSCOPE_API_KEY")
    if not key:
        return None
    for m in MODEL_CATALOG:
        if m["id"] == model_id:
            return ModelConfig("通义千问", _DASHSCOPE_BASE, model_id, key)
    return None


def supports_vision(model_id: str) -> bool:
    """判断模型是否支持图片输入。"""
    try:
        import model_store

        m = model_store.get_custom(model_id)
        if m:
            return bool(m.get("vision"))
    except Exception:
        pass

    for m in MODEL_CATALOG:
        if m["id"] == model_id:
            return bool(m.get("vision"))
    return False


def get_model_meta(model_id: str) -> dict:
    """返回模型的完整元信息（tag / desc / vision / reasoning）。"""
    try:
        import model_store

        m = model_store.get_custom(model_id)
        if m:
            return {
                "id": m["id"],
                "label": m.get("label") or m["id"],
                "tag": m.get("tag") or "自定义",
                "desc": m.get("desc") or "",
                "vision": bool(m.get("vision")),
                "reasoning": bool(m.get("reasoning")),
                "custom": True,
            }
    except Exception:
        pass

    for m in MODEL_CATALOG:
        if m["id"] == model_id:
            return dict(m)
    return {}


def _available_configs() -> list[ModelConfig]:
    """按优先级收集所有已配置密钥的模型。"""
    configs: list[ModelConfig] = []

    # 主模型：阿里云百炼（免费）
    if key := os.getenv("DASHSCOPE_API_KEY"):
        configs.append(
            ModelConfig(
                "通义千问",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "qwen-flash",
                key,
            )
        )
    if key := os.getenv("ZHIPU_API_KEY"):
        configs.append(
            ModelConfig(
                "智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash", key
            )
        )
    if key := os.getenv("SILICONFLOW_API_KEY"):
        configs.append(
            ModelConfig(
                "硅基流动",
                "https://api.siliconflow.cn/v1",
                "Qwen/Qwen2.5-7B-Instruct",
                key,
            )
        )
    if key := os.getenv("DEEPSEEK_API_KEY"):
        # 已弃用但保留兼容
        configs.append(
            ModelConfig("DeepSeek", "https://api.deepseek.com", "deepseek-chat", key)
        )

    # 自定义模型兜底（内置都不可用时）
    try:
        import model_store

        for m in model_store.list_custom():
            if m.get("enabled", True) and m.get("api_key"):
                configs.append(
                    ModelConfig(
                        m.get("label") or m["id"], m["base_url"], m["model"], m["api_key"]
                    )
                )
    except Exception:
        pass

    return configs


def get_client(model_id: str = "") -> tuple[OpenAI, str, str]:
    """返回 (客户端, 模型名, 平台名)。

    Args:
        model_id: 指定模型 id。为空则用默认。
    """
    if model_id:
        cfg = get_model_by_id(model_id)
        if cfg:
            client = OpenAI(
                api_key=cfg.api_key,
                base_url=cfg.base_url,
                timeout=90,
                max_retries=1,
            )
            return client, cfg.model, cfg.name

    configs = _available_configs()
    if not configs:
        raise RuntimeError(
            "没有可用的 API Key。\n"
            f"  当前 {env_status()}\n"
            "  请在网页端右上角「设置」里添加模型，或编辑 .env 填写 DASHSCOPE_API_KEY。"
        )
    cfg = configs[0]
    client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url, timeout=90, max_retries=1)
    return client, cfg.model, cfg.name

def chat(
    messages: list[dict],
    *,
    temperature: float = 0.7,
    stream: bool = False,
    retries: int = 3,
):
    """单轮调用封装，带简单的重试。

    Args:
        messages: OpenAI 格式的消息列表
        temperature: 0-2，越低越确定
        stream: 是否流式返回
        retries: 失败重试次数

    Returns:
        stream=True 时返回生成器；否则返回完整文本
    """
    client, model, _ = get_client()

    if stream:
        return client.chat.completions.create(
            model=model, messages=messages, temperature=temperature, stream=True
        )

    last_err = None
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, temperature=temperature
            )
            return resp.choices[0].message.content
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries - 1:
                time.sleep(2**attempt)  # 1s, 2s, 4s 退避
    raise RuntimeError(f"调用失败（已重试 {retries} 次）: {last_err}")


def stream_print(messages: list[dict], *, temperature: float = 0.7) -> str:
    """流式打印回答，返回完整文本。"""
    gen = chat(messages, temperature=temperature, stream=True)
    parts: list[str] = []
    for chunk in gen:
        if chunk.choices and chunk.choices[0].delta.content:
            piece = chunk.choices[0].delta.content
            parts.append(piece)
            print(piece, end="", flush=True)
    print()
    return "".join(parts)