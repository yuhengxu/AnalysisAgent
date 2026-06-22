"""生成内容真实性护栏。"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.skills.verified_data import apply_authoritative_source

logger = logging.getLogger(__name__)

_UP_PHRASES = ("大幅走强", "明显走强", "显著走强", "强势上涨", "走强", "上涨", "攀升", "反弹", "走高")
_DOWN_PHRASES = ("大幅走弱", "明显走弱", "显著走弱", "弱势下跌", "走弱", "下跌", "回落", "下行", "走低")


def _has_direction(text: str, phrases: tuple[str, ...]) -> bool:
    return any(p in text for p in phrases)


def _replace_first(text: str, old: str, new: str) -> str:
    if old not in text:
        return text
    return text.replace(old, new, 1)


def _repair_spot_direction(text: str, trends: dict[str, str]) -> str:
    """轻量修正 review_spot 中与数据库趋势矛盾的方向词。"""
    result = text
    spot_trend = trends.get("brent_spot")
    if spot_trend == "走弱" and _has_direction(result, _UP_PHRASES):
        for phrase in _UP_PHRASES:
            if phrase in result:
                replacement = phrase.replace("走强", "走弱").replace("上涨", "下跌").replace("攀升", "回落")
                replacement = replacement.replace("反弹", "回落").replace("走高", "走低")
                if replacement != phrase:
                    result = _replace_first(result, phrase, replacement)
                    break
    elif spot_trend == "走强" and _has_direction(result, _DOWN_PHRASES):
        for phrase in _DOWN_PHRASES:
            if phrase in result:
                replacement = phrase.replace("走弱", "走强").replace("下跌", "上涨").replace("回落", "反弹")
                replacement = replacement.replace("下行", "上行").replace("走低", "走高")
                if replacement != phrase:
                    result = _replace_first(result, phrase, replacement)
                    break

    for key, entity_re in (
        ("dubai", r"Dubai|迪拜"),
        ("espo", r"ESPO"),
    ):
        trend = trends.get(key)
        if trend not in ("走强", "走弱"):
            continue
        if not re.search(entity_re, result):
            continue
        if trend == "走弱" and _has_direction(result, _UP_PHRASES):
            for phrase in ("走强", "上涨"):
                if phrase in result:
                    result = _replace_first(result, phrase, phrase.replace("强", "弱").replace("涨", "跌"))
                    break
        elif trend == "走强" and _has_direction(result, _DOWN_PHRASES):
            for phrase in ("走弱", "下跌"):
                if phrase in result:
                    result = _replace_first(result, phrase, phrase.replace("弱", "强").replace("跌", "涨"))
                    break
    return result


def _guard_review_spot(
    sec: dict[str, Any],
    spot_market: dict[str, Any],
    warnings: list[str],
) -> None:
    trends = spot_market.get("trends") or {}
    if not trends:
        return
    text = str(sec.get("content", ""))
    if not text:
        return
    spot_trend = trends.get("brent_spot")
    if spot_trend == "走弱" and _has_direction(text, _UP_PHRASES) and not _has_direction(text, _DOWN_PHRASES):
        warnings.append(f"review_spot 与 brent_spot 趋势({spot_trend})矛盾，已尝试修正方向词")
        sec["content"] = _repair_spot_direction(text, trends)
    elif spot_trend == "走强" and _has_direction(text, _DOWN_PHRASES) and not _has_direction(text, _UP_PHRASES):
        warnings.append(f"review_spot 与 brent_spot 趋势({spot_trend})矛盾，已尝试修正方向词")
        sec["content"] = _repair_spot_direction(text, trends)


def guard_prediction_content(content: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """为因素补充或校正致信水平与来源链接。"""
    del evidence
    for factor in content.get("factors", []):
        if not isinstance(factor, dict):
            continue
        factor.pop("source_refs", None)
        judgment = str(factor.get("judgment", ""))
        apply_authoritative_source(
            factor,
            source_url=factor.get("source_url"),
            source_title=factor.get("source_title"),
            judgment=judgment,
        )
    return content


def guard_report_content(
    content: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """为月报子章节补充或校正致信水平与来源链接；校验 review_spot 方向一致性。"""
    spot_market = evidence.get("spot_market") or {}
    warnings: list[str] = []
    for sec in content.get("sections", []):
        if not isinstance(sec, dict) or sec.get("level") != 2:
            continue
        if sec.get("id") == "review_spot" and spot_market:
            _guard_review_spot(sec, spot_market, warnings)
        text = str(sec.get("content", ""))
        if not text:
            continue
        apply_authoritative_source(
            sec,
            source_url=sec.get("source_url"),
            source_title=sec.get("source_title"),
            judgment=text,
        )
    if warnings:
        evidence["spot_guard_warnings"] = warnings
        for msg in warnings:
            logger.warning(msg)
    return content
