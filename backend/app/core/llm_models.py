"""各 provider 可选模型目录（前端设置页展示用）。

火山方舟接入点 ID 因账号/地域可能不同，可通过环境变量 ``VOLCENGINE_MODEL_CATALOG``
传入 JSON 数组覆盖或追加（格式见 ``.env.example``）。
"""
from __future__ import annotations

import json
from typing import Any, TypedDict

from app.core.config import settings


class LlmModelOption(TypedDict):
    id: str
    label: str
    family: str
    hint: str


# 火山方舟已验证可用的推理 model 字段（OpenAI 兼容 /chat/completions）
VOLCENGINE_MODELS: list[LlmModelOption] = [
    {
        "id": "doubao-seed-2-0-pro-260215",
        "label": "Doubao-Seed-2.0-pro",
        "family": "doubao",
        "hint": "默认推荐，综合能力强，适合日常对话与生成",
    },
    {
        "id": "doubao-seed-2-0-lite-260215",
        "label": "Doubao-Seed-2.0-lite",
        "family": "doubao",
        "hint": "轻量快速，适合高频短问答与批量任务",
    },
    {
        "id": "deepseek-v4-pro",
        "label": "DeepSeek-V4-pro",
        "family": "deepseek",
        "hint": "方舟接入 DeepSeek V4 Pro；深度研究仍走 DeepSearch 智能体",
    },
    {
        "id": "deepseek-v4-flash",
        "label": "DeepSeek-V4-flash",
        "family": "deepseek",
        "hint": "方舟接入 DeepSeek V4 Flash，低延迟高性价比",
    },
]

DEEPSEEK_MODELS: list[LlmModelOption] = [
    {
        "id": "deepseek-v4-pro",
        "label": "DeepSeek V4 Pro",
        "family": "deepseek",
        "hint": "官方 API，支持深度思考（深度研究模式）",
    },
    {
        "id": "deepseek-chat",
        "label": "DeepSeek Chat",
        "family": "deepseek",
        "hint": "官方 API 对话模型",
    },
    {
        "id": "deepseek-reasoner",
        "label": "DeepSeek Reasoner",
        "family": "deepseek",
        "hint": "官方 API 推理模型",
    },
]

OPENAI_MODELS: list[LlmModelOption] = [
    {
        "id": "gpt-4o-mini",
        "label": "GPT-4o mini",
        "family": "openai",
        "hint": "轻量快速",
    },
    {
        "id": "gpt-4o",
        "label": "GPT-4o",
        "family": "openai",
        "hint": "综合能力更强",
    },
]

MOCK_MODELS: list[LlmModelOption] = [
    {
        "id": "mock",
        "label": "Mock",
        "family": "mock",
        "hint": "本地规则兜底，不调用大模型",
    },
]

FAMILY_LABELS: dict[str, str] = {
    "doubao": "豆包",
    "deepseek": "DeepSeek",
    "qwen": "通义千问",
    "openai": "OpenAI",
    "mock": "Mock",
}


def _parse_catalog_override(raw: str) -> list[LlmModelOption]:
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[LlmModelOption] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        out.append(
            {
                "id": str(item["id"]),
                "label": str(item.get("label") or item["id"]),
                "family": str(item.get("family") or "custom"),
                "hint": str(item.get("hint") or ""),
            }
        )
    return out


def _merge_models(base: list[LlmModelOption], override: list[LlmModelOption]) -> list[LlmModelOption]:
    """override 中同 id 的项覆盖 base，其余追加到末尾。"""
    by_id = {m["id"]: dict(m) for m in base}
    for m in override:
        by_id[m["id"]] = dict(m)
    # 保持 base 顺序，再追加 override 中新增的 id
    seen: set[str] = set()
    merged: list[LlmModelOption] = []
    for m in base:
        if m["id"] in by_id:
            merged.append(by_id[m["id"]])  # type: ignore[arg-type]
            seen.add(m["id"])
    for m in override:
        if m["id"] not in seen:
            merged.append(m)
            seen.add(m["id"])
    return merged


def _ensure_default_in_list(models: list[LlmModelOption], default_id: str) -> list[LlmModelOption]:
    if any(m["id"] == default_id for m in models):
        return models
    return [
        {
            "id": default_id,
            "label": f"默认（{default_id}）",
            "family": "custom",
            "hint": "来自环境变量 VOLCENGINE_MODEL / 前端已保存的自定义接入点",
        },
        *models,
    ]


def get_models_for_provider(provider: str) -> list[LlmModelOption]:
    p = (provider or "").lower()
    if p == "volcengine":
        override = _parse_catalog_override(settings.volcengine_model_catalog)
        models = _merge_models(VOLCENGINE_MODELS, override)
        return _ensure_default_in_list(models, settings.volcengine_model)
    if p == "deepseek":
        return _ensure_default_in_list(DEEPSEEK_MODELS, settings.deepseek_model)
    if p == "openai":
        return _ensure_default_in_list(OPENAI_MODELS, settings.openai_model)
    if p == "mock":
        return MOCK_MODELS
    return []


def get_default_model_for_provider(provider: str) -> str:
    p = (provider or "").lower()
    if p == "volcengine":
        return settings.volcengine_model
    if p == "deepseek":
        return settings.deepseek_model
    if p == "openai":
        return settings.openai_model
    return "mock"


def model_families(models: list[LlmModelOption]) -> list[dict[str, Any]]:
    """按 family 分组，供前端 optgroup 渲染。"""
    groups: dict[str, list[LlmModelOption]] = {}
    order: list[str] = []
    for m in models:
        fam = m.get("family") or "other"
        if fam not in groups:
            groups[fam] = []
            order.append(fam)
        groups[fam].append(m)
    return [
        {
            "family": fam,
            "label": FAMILY_LABELS.get(fam, fam),
            "models": groups[fam],
        }
        for fam in order
    ]
