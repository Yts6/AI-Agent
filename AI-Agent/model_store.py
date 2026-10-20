# -*- coding: utf-8 -*-
"""模型注册表：支持内置模型 + 用户自定义模型（网页端增删改）。

存储：AI-Agent/models.json
格式：
{
  "custom": [
    {
      "id": "my-gpt4",
      "label": "我的 GPT-4",
      "tag": "自定义",
      "desc": "OpenAI 官方",
      "provider": "openai",       # 决定 base_url 模板
      "base_url": "https://api.openai.com/v1",
      "model": "gpt-4o",
      "api_key": "sk-xxx",
      "vision": false,
      "reasoning": false,
      "enabled": true
    }
  ]
}
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STORE = BASE_DIR / "models.json"

# 常见服务商预设，方便前端一键填 base_url
PROVIDER_PRESETS = [
    {
        "id": "dashscope",
        "name": "阿里云百炼",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen3.5-flash", "qwen3.5-plus", "qwen3-vl-plus", "qwen-max", "qwen-long"],
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    {
        "id": "moonshot",
        "name": "月之暗面 Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "kimi-latest"],
    },
    {
        "id": "zhipu",
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-flash", "glm-4-plus", "glm-4v-plus"],
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "o1-mini"],
    },
    {
        "id": "siliconflow",
        "name": "硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3"],
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models": ["anthropic/claude-sonnet-4", "google/gemini-2.0-flash"],
    },
    {
        "id": "custom",
        "name": "自定义（任意 OpenAI 兼容接口）",
        "base_url": "",
        "models": [],
    },
]


def _db():
    """懒加载数据库连接，避免循环导入。"""
    import db as db_mod

    return db_mod.get_db()


def _load() -> dict:
    """兼容旧接口：返回 {custom: [...]}。"""
    return {"custom": list_custom()}


def list_custom() -> list[dict]:
    """返回所有自定义模型（含密钥，仅内部使用）。"""
    try:
        rows = _db().list_models(only_enabled=False)
    except Exception:
        rows = []
    out = []
    for r in rows:
        m = dict(r)
        m["vision"] = bool(m.get("vision"))
        m["reasoning"] = bool(m.get("reasoning"))
        m["enabled"] = bool(m.get("enabled"))
        out.append(m)
    return out


def list_custom_public() -> list[dict]:
    """返回给前端的版本：隐藏完整 key，只留尾号。"""
    out = []
    for m in list_custom():
        item = dict(m)
        key = item.get("api_key", "") or ""
        if key:
            item["api_key"] = "****" + key[-4:] if len(key) > 8 else "****"
        item["has_key"] = bool(key)
        out.append(item)
    return out


def get_custom(model_id: str) -> dict | None:
    try:
        r = _db().get_model(model_id)
    except Exception:
        return None
    if not r:
        return None
    r["vision"] = bool(r.get("vision"))
    r["reasoning"] = bool(r.get("reasoning"))
    r["enabled"] = bool(r.get("enabled"))
    return r


def add_custom(payload: dict) -> dict:
    """新增一个自定义模型。"""
    mid = (payload.get("id") or "").strip()
    if not mid:
        raise ValueError("模型 id 不能为空")
    if not mid.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise ValueError("模型 id 只能包含字母、数字、- _ .")

    if get_custom(mid):
        raise ValueError(f"模型 {mid} 已存在")
    if mid in _builtin_ids():
        raise ValueError(f"{mid} 与内置模型重名")

    entry = {
        "id": mid,
        "label": (payload.get("label") or mid).strip(),
        "tag": (payload.get("tag") or "自定义").strip(),
        "desc": (payload.get("desc") or "").strip(),
        "provider": (payload.get("provider") or "custom").strip(),
        "base_url": (payload.get("base_url") or "").strip(),
        "model": (payload.get("model") or mid).strip(),
        "api_key": (payload.get("api_key") or "").strip(),
        "vision": bool(payload.get("vision")),
        "reasoning": bool(payload.get("reasoning")),
        "enabled": True,
        "created": time.time(),
    }
    if not entry["base_url"]:
        raise ValueError("接口地址不能为空")
    if not entry["api_key"]:
        raise ValueError("API Key 不能为空")

    _db().add_model(entry)
    return entry


def update_custom(model_id: str, payload: dict) -> dict:
    """更新自定义模型。api_key 为空表示不修改。"""
    cur = get_custom(model_id)
    if not cur:
        raise ValueError(f"模型 {model_id} 不存在")

    patch: dict = {}
    for k in ("label", "tag", "desc", "base_url", "model", "provider"):
        if k in payload and payload[k] is not None:
            patch[k] = str(payload[k]).strip()
    if payload.get("api_key"):
        patch["api_key"] = str(payload["api_key"]).strip()
    for k in ("vision", "reasoning", "enabled"):
        if k in payload:
            patch[k] = bool(payload[k])

    _db().update_model(model_id, patch)
    return get_custom(model_id) or cur


def remove_custom(model_id: str) -> bool:
    try:
        return _db().delete_model(model_id)
    except Exception:
        return False


def _builtin_ids() -> list[str]:
    """内置模型 id（从 config.MODEL_CATALOG 读取，避免循环导入）。"""
    try:
        import config

        return [m["id"] for m in config.MODEL_CATALOG]
    except Exception:
        return []


def test_connection(base_url: str, api_key: str, model: str) -> dict:
    """测试一个模型能否连通。返回 {ok, message, latency}。"""
    from openai import OpenAI

    if not base_url or not api_key or not model:
        return {"ok": False, "message": "接口地址、Key、模型名都不能为空", "latency": 0}

    t0 = time.time()
    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=30, max_retries=0)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "回复两个字：你好"}],
            max_tokens=20,
        )
        latency = time.time() - t0
        reply = (resp.choices[0].message.content or "").strip()
        return {
            "ok": True,
            "message": f"连接成功，模型回复：{reply[:50]}",
            "latency": round(latency, 2),
        }
    except Exception as e:
        msg = str(e)
        # 常见错误翻译成人话
        if "401" in msg or "Invalid API key" in msg or "Authentication" in msg:
            hint = "API Key 无效或已过期"
        elif "404" in msg or "model" in msg.lower() and "not exist" in msg.lower():
            hint = "模型名不存在，或该账号没有权限"
        elif "429" in msg:
            hint = "请求过于频繁或额度不足"
        elif "timeout" in msg.lower() or "timed out" in msg.lower():
            hint = "连接超时，检查接口地址是否正确"
        elif "Connection" in msg:
            hint = "无法连接，检查接口地址和网络"
        else:
            hint = msg[:120]
        return {"ok": False, "message": hint, "latency": round(time.time() - t0, 2)}
