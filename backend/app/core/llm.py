"""统一大模型客户端（双调用模式）。

支持四类 provider：
- ``volcengine``：火山方舟豆包（默认 ``doubao-seed-2-0-pro-260215``，OpenAI 兼容，生产默认）。
- ``deepseek``：DeepSeek V4（默认 ``deepseek-v4-pro``，兼容保留）。
- ``openai``：任意 OpenAI 兼容服务。
- ``mock``：本地降级，不联网，抛出 ``LLMUnavailable``，由各 skill 走规则兜底。

调用模式（mode）：
- ``normal``：普通模式，直接调用对话模型，响应快，适合日常对话与常规生成。
- ``deep_research``：深度研究模式——
  * DeepSeek：开启深度思考（``thinking`` + ``reasoning_effort``）。
  * 豆包（volcengine）：改为调用 **DeepSearch** 智能体应用
    （``/bots/chat/completions``，集成浏览器使用、联网搜索、知识库、
    网页解析、ChatPPT、Python 代码执行器等 MCP 服务），
    需配置 ``VOLCENGINE_DEEPSEARCH_BOT_ID``；未配置时自动降级为普通模式。
  * 其他 provider：等同普通模式。

所有 skill 通过本模块调用大模型，避免在业务代码里散落 HTTP 细节。
每轮对话自动写入 ``llm_dialogue_logs`` 表与 ``logs/llm_dialogue.log``。
"""
from __future__ import annotations

import json
import logging
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Literal

import httpx

from app.core.config import settings

logger = logging.getLogger("llm")

Mode = Literal["normal", "deep_research"]

_llm_source: ContextVar[str] = ContextVar("llm_source", default="unknown")
_llm_meta: ContextVar[dict[str, Any]] = ContextVar("llm_meta", default={})


@contextmanager
def llm_context(source: str, **meta: Any) -> Iterator[None]:
    """设置当前大模型调用的业务来源，供对话日志归档。"""
    tok_src = _llm_source.set(source)
    tok_meta = _llm_meta.set(dict(meta))
    try:
        yield
    finally:
        _llm_source.reset(tok_src)
        _llm_meta.reset(tok_meta)


class LLMUnavailable(Exception):
    """大模型不可用（未配置 key、网络错误等），调用方应走规则兜底。"""


def normalize_mode(mode: str | None) -> Mode:
    """归一化调用模式；兼容旧版 reasoning_effort 取值（high/max → 深度研究）。"""
    if not mode:
        return "deep_research"
    value = str(mode).strip().lower().replace("-", "_")
    if value in ("deep_research", "research", "deep", "high", "max"):
        return "deep_research"
    return "normal"


def _resolve(provider: str | None, model: str | None) -> tuple[str, str, str, str]:
    """返回 (provider, base_url, api_key, model)。"""
    provider = (provider or settings.default_llm_provider or "mock").lower()
    if provider == "deepseek":
        return (
            "deepseek",
            settings.deepseek_base_url.rstrip("/"),
            settings.deepseek_api_key,
            model or settings.deepseek_model,
        )
    if provider == "volcengine":
        return (
            "volcengine",
            settings.volcengine_base_url.rstrip("/"),
            settings.volcengine_api_key,
            model or settings.volcengine_model,
        )
    if provider == "openai":
        return (
            "openai",
            settings.openai_base_url.rstrip("/"),
            settings.openai_api_key,
            model or settings.openai_model,
        )
    return ("mock", "", "", model or "mock")


def _supports_thinking_mode(model_name: str) -> bool:
    lower = model_name.lower()
    return any(tag in lower for tag in ("v4", "reasoner"))


def is_enabled(provider: str | None = None) -> bool:
    p, _, key, _ = _resolve(provider, None)
    return p != "mock" and bool(key)


def deep_search_available() -> bool:
    """豆包 DeepSearch 智能体是否已配置。"""
    return bool(settings.volcengine_deepsearch_bot_id)


def test_connection(
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """发送最小请求测试大模型连通性，返回状态与回复摘要。"""
    p, _, key, model_name = _resolve(provider, model)
    if p == "mock" or not key:
        return {
            "ok": False,
            "provider": p,
            "model": model_name,
            "message": f"provider={p} 未配置可用 API Key",
        }
    start = time.time()
    try:
        reply = chat(
            [{"role": "user", "content": "请回复：连接成功"}],
            provider=provider,
            model=model,
            temperature=0,
            max_tokens=32,
            mode="normal",
        )
        duration = (time.time() - start) * 1000
        return {
            "ok": True,
            "provider": p,
            "model": model_name,
            "message": "连接成功",
            "reply": reply[:200],
            "duration_ms": round(duration, 1),
        }
    except LLMUnavailable as exc:
        duration = (time.time() - start) * 1000
        return {
            "ok": False,
            "provider": p,
            "model": model_name,
            "message": str(exc),
            "duration_ms": round(duration, 1),
        }


def _record_dialogue(
    *,
    provider: str,
    model_name: str,
    messages: list[dict[str, str]],
    response_content: str,
    status: str,
    error_message: str,
    duration_ms: float,
    extra_meta: dict[str, Any],
) -> None:
    from app.services.llm_log import record_dialogue

    meta = {**_llm_meta.get(), **extra_meta}
    record_dialogue(
        source=_llm_source.get(),
        provider=provider,
        model_name=model_name,
        request_messages=messages,
        response_content=response_content,
        status=status,
        error_message=error_message,
        duration_ms=duration_ms,
        meta=meta,
    )


def _build_request(
    p: str,
    base_url: str,
    model_name: str,
    messages: list[dict[str, str]],
    *,
    mode: Mode,
    temperature: float,
    json_mode: bool,
    max_tokens: int | None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """组装请求 URL、payload 与日志元信息（按 provider × mode 路由）。"""
    endpoint = "chat/completions"
    payload: dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    meta: dict[str, Any] = {
        "mode": mode,
        "temperature": temperature,
        "json_mode": json_mode,
        "thinking_enabled": False,
        "deep_search": False,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    deep = mode == "deep_research"
    if deep and p == "deepseek":
        # DeepSeek 深度研究 = 开启深度思考
        if _supports_thinking_mode(model_name):
            payload["thinking"] = {"type": "enabled"}
            effort = (settings.deepseek_reasoning_effort or "high").lower()
            if effort in ("high", "max"):
                payload["reasoning_effort"] = effort
            meta["thinking_enabled"] = True
        else:
            logger.warning("模型 %s 不支持深度思考，深度研究模式降级为普通调用", model_name)
    elif deep and p == "volcengine":
        # 豆包深度研究 = 调用 DeepSearch 智能体（bots 接口）
        bot_id = settings.volcengine_deepsearch_bot_id
        if bot_id:
            endpoint = "bots/chat/completions"
            payload["model"] = bot_id
            meta["deep_search"] = True
            meta["deepsearch_bot_id"] = bot_id
        else:
            logger.warning("未配置 VOLCENGINE_DEEPSEARCH_BOT_ID，豆包深度研究模式降级为普通调用")

    # JSON 输出：思考模型与 DeepSearch 智能体不保证支持 response_format，
    # 统一由 _parse_json 从正文提取；其余 provider 走原生 json_object。
    if json_mode and not meta["thinking_enabled"] and not meta["deep_search"] and not _supports_thinking_mode(payload["model"]):
        payload["response_format"] = {"type": "json_object"}

    url = f"{base_url}/{endpoint}"
    return url, payload, meta


def chat(
    messages: list[dict[str, str]],
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    json_mode: bool = False,
    max_tokens: int | None = None,
    mode: str | None = "deep_research",
) -> str:
    """调用大模型，返回文本内容。失败抛出 ``LLMUnavailable``。

    默认 ``deep_research``；DeepSeek 开启深度思考，豆包路由到 DeepSearch 智能体。
    """
    content, _ = chat_with_meta(
        messages,
        provider=provider,
        model=model,
        temperature=temperature,
        json_mode=json_mode,
        max_tokens=max_tokens,
        mode=mode,
    )
    return content


def chat_with_meta(
    messages: list[dict[str, str]],
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    json_mode: bool = False,
    max_tokens: int | None = None,
    mode: str | None = "deep_research",
) -> tuple[str, dict[str, Any]]:
    """调用大模型，返回 (文本内容, 元信息含 references 等)。"""
    p, base_url, api_key, model_name = _resolve(provider, model)
    if p == "mock" or not api_key:
        raise LLMUnavailable(f"provider={p} 未配置可用 API Key")

    resolved_mode = normalize_mode(mode)
    url, payload, extra_meta = _build_request(
        p,
        base_url,
        model_name,
        messages,
        mode=resolved_mode,
        temperature=temperature,
        json_mode=json_mode,
        max_tokens=max_tokens,
    )
    log_model = str(payload["model"])

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    timeout = settings.llm_deep_timeout if resolved_mode == "deep_research" else settings.llm_timeout
    start = time.time()
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            reasoning = message.get("reasoning_content") or ""
            if reasoning:
                extra_meta["reasoning_content_preview"] = reasoning[:800]
            references = data.get("references")
            if references:
                extra_meta["references"] = references
        duration = (time.time() - start) * 1000
        _record_dialogue(
            provider=p,
            model_name=log_model,
            messages=messages,
            response_content=content,
            status="success",
            error_message="",
            duration_ms=duration,
            extra_meta=extra_meta,
        )
        return content, extra_meta
    except Exception as exc:  # noqa: BLE001
        duration = (time.time() - start) * 1000
        err = str(exc)
        logger.warning(
            "LLM 调用失败 provider=%s model=%s mode=%s err=%s", p, log_model, resolved_mode, exc
        )
        _record_dialogue(
            provider=p,
            model_name=log_model,
            messages=messages,
            response_content="",
            status="error",
            error_message=err,
            duration_ms=duration,
            extra_meta=extra_meta,
        )
        raise LLMUnavailable(err) from exc


def chat_json(
    system: str,
    user: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    mode: str | None = "deep_research",
) -> dict[str, Any]:
    """要求大模型输出 JSON，返回解析后的 dict。失败抛出 ``LLMUnavailable``。"""
    parsed, _ = chat_json_with_meta(
        system,
        user,
        provider=provider,
        model=model,
        temperature=temperature,
        mode=mode,
    )
    return parsed


def chat_json_with_meta(
    system: str,
    user: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    mode: str | None = "deep_research",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """要求大模型输出 JSON，返回 (解析 dict, 元信息)。"""
    content, meta = chat_with_meta(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        provider=provider,
        model=model,
        temperature=temperature,
        json_mode=True,
        mode=mode,
    )
    return _parse_json(content), meta


def _parse_json(content: str) -> dict[str, Any]:
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMUnavailable(f"无法解析大模型 JSON 输出：{exc}") from exc
    raise LLMUnavailable("大模型未返回有效 JSON")
