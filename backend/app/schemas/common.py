from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, field_validator

Mode = Literal["normal", "deep_research"]


def _normalize_mode_value(v: Any) -> str:
    """归一化模式取值；兼容旧版 reasoning_effort（off/high/max→deep_research）。"""
    if v in (None, ""):
        return "deep_research"
    if v in ("normal", "off", "none"):
        return "normal"
    value = str(v).strip().lower().replace("-", "_")
    if value in ("deep_research", "research", "deep", "high", "max"):
        return "deep_research"
    return "normal"


class _ModeMixin(BaseModel):
    mode: Mode = "deep_research"

    @field_validator("mode", mode="before")
    @classmethod
    def _validate_mode(cls, v: Any) -> str:
        return _normalize_mode_value(v)


class AgentRequest(_ModeMixin):
    prompt: str
    skill: str = "analyze"
    model_provider: str | None = None
    model_name: str | None = None
    trusted_sources_only: bool = False


class ChatMessage(BaseModel):
    role: str
    content: str


class AgentChatRequest(_ModeMixin):
    messages: list[ChatMessage]
    skill_hint: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    trusted_sources_only: bool = False


class ReportGenerateRequest(_ModeMixin):
    issue_no: str = "2026年第6期（总57期）"
    report_date: str = "2026年6月7日"
    review_year: int = 2026
    review_month: int = 5
    outlook_year: int = 2026
    outlook_month: int = 6
    model_provider: str | None = None
    model_name: str | None = None
    extra_instruction: str = ""
    trusted_sources_only: bool = False
    unrestricted_mode: bool = False


class ReportUpdateRequest(BaseModel):
    content: dict[str, Any]
    title: str | None = None


class ReviseRequest(_ModeMixin):
    section_id: str
    instruction: str
    model_provider: str | None = None
    model_name: str | None = None


class PredictionGenerateRequest(_ModeMixin):
    symbol: str = "Brent"
    year: int = 2026
    month: int = 6
    model_provider: str | None = None
    model_name: str | None = None
    extra_instruction: str = ""
    trusted_sources_only: bool = False
    unrestricted_mode: bool = False


class PredictionUpdateRequest(BaseModel):
    content: dict[str, Any]
    title: str | None = None


class PredictionReviseRequest(_ModeMixin):
    factor_idx: int
    field: Literal["judgment"]
    instruction: str
    model_provider: str | None = None
    model_name: str | None = None


class SettingsUpdate(BaseModel):
    default_llm_provider: str = "volcengine"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"


class DataQueryParams(BaseModel):
    category: Literal["price", "balance", "factor", "mixed"] = "price"
    start_date: date | None = None
    end_date: date | None = None
    year: int | None = None
    month: int | None = None
    symbols: list[str] = []
    agencies: list[str] = []
    supply_demand: list[str] = []
    periods: list[str] = []
    factor_categories: list[str] = []
    factor_names: list[str] = []
    indicators: list[str] = []
    page: int = 1
    page_size: int = 50


class AnalysisQueryParams(DataQueryParams):
    question: str = ""
    include_charts: bool = True
    model_provider: str | None = None
    model_name: str | None = None
    mode: Mode = "deep_research"
