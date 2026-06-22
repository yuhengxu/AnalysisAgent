"""大模型配置与连通性检测。"""

from fastapi import APIRouter, Depends, Query

from app.core import llm
from app.core.config import settings
from app.core.llm_models import (
    get_default_model_for_provider,
    get_models_for_provider,
    model_families,
)

from app.core.deps import require_admin

router = APIRouter(prefix="/llm", tags=["llm"], dependencies=[Depends(require_admin)])


def _provider_entry(provider_id: str, label: str, **extra) -> dict:
    models = get_models_for_provider(provider_id)
    return {
        "id": provider_id,
        "label": label,
        "model": get_default_model_for_provider(provider_id),
        "default_model": get_default_model_for_provider(provider_id),
        "models": models,
        "model_groups": model_families(models),
        **extra,
    }


@router.get("/providers")
def list_providers():
    """返回可用模型提供商、可选模型列表及配置状态（不含密钥）。"""
    return {
        "default": settings.default_llm_provider,
        "providers": [
            _provider_entry(
                "volcengine",
                "火山方舟（豆包 / DeepSeek / 千问）",
                enabled=llm.is_enabled("volcengine"),
                deep_research_available=llm.deep_search_available(),
                deep_research_label="DeepSearch 智能体（联网搜索/浏览器/代码执行等 MCP）",
            ),
            _provider_entry(
                "deepseek",
                "DeepSeek 官方 API",
                enabled=llm.is_enabled("deepseek"),
                deep_research_available=True,
                deep_research_label=f"深度思考（{settings.deepseek_reasoning_effort or 'high'}）",
            ),
            _provider_entry(
                "openai",
                "OpenAI 兼容",
                enabled=llm.is_enabled("openai"),
                deep_research_available=False,
                deep_research_label="",
            ),
            _provider_entry(
                "mock",
                "Mock（规则兜底）",
                enabled=True,
                deep_research_available=False,
                deep_research_label="",
            ),
        ],
    }


@router.get("/models")
def list_models(provider: str = Query("volcengine")):
    """返回指定 provider 的可选模型（含分组）。"""
    models = get_models_for_provider(provider)
    return {
        "provider": provider,
        "default_model": get_default_model_for_provider(provider),
        "models": models,
        "groups": model_families(models),
    }


@router.post("/test")
def test_llm(provider: str = "volcengine", model: str | None = None):
    """测试指定 provider 的大模型连接。"""
    return llm.test_connection(provider=provider, model=model)
