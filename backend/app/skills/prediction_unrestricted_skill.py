"""无限制模式 · 油价预测分析表 skill。

基于 yuebao/prediction 上一期样例，将样例全文交给深度研究模型，
仅保留格式约束，不做数据真实性/时效性校验。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core import llm
from app.core.llm import llm_context
from app.skills.sample_loader import load_prediction_sample, prev_period
from app.templates.prediction_table import (
    IMPACT_OPTIONS,
    PREDICTION_FACTORS,
    all_factor_defs,
)

logger = logging.getLogger("skill.prediction_unrestricted")

SYSTEM_PROMPT = (
    "你是中国海油集团能源经济研究院的国际油价分析专家。"
    "你的任务是根据提供的《近期国际油价预测分析表》样例，更新数据与判断，生成目标月份的新版预测分析表。"
    "要求：\n"
    "1) 语言风格、行文结构、数据引用口径须与样例完全一致，不得创新表述方式。\n"
    "2) 每个影响因素须给出 importance(1-5 整数)、judgment(形势判断及支撑指标,150-300字)、"
    "impact(只能取 促涨/持平/促跌 之一)。\n"
    "3) 给出布伦特首行合约当月与次月价格预测(区间幅度不超过5美元,以及均价)。\n"
    "4) 不要求数据真实性或时效性核验，可基于样例逻辑合理推演更新。\n"
    "5) 严格输出 JSON，不要包含任何额外说明文字。"
)


class PredictionUnrestrictedSkill:
    name = "predict_table_unrestricted"
    label = "油价预测分析表（无限制）"

    def __init__(self, db: Session):
        del db

    def generate(
        self,
        symbol: str = "Brent",
        year: int = 2026,
        month: int = 6,
        provider: str | None = None,
        model: str | None = None,
        mode: str = "deep_research",
        extra_instruction: str = "",
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        sample = load_prediction_sample(year, month)
        sample_year = sample.get("sample_year")
        sample_month = sample.get("sample_month")
        review_year, review_month = prev_period(year, month)
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1

        if on_progress:
            on_progress(1, 1, "深度研究仿写预测分析表")

        user = (
            f"这是{sample_year}年{sample_month}月的油价预测分析表样例，"
            f"请你更新数据，生成{year}年{month}月的油价预测分析表。\n"
            f"数据回顾月：{review_year}年{review_month}月；标的：{symbol}。\n\n"
            f"【样例全文（yuebao/prediction）】\n"
            f"{json.dumps(sample, ensure_ascii=False, default=str)}\n\n"
            f"{extra_instruction}\n\n"
            "请严格输出如下 JSON：\n"
            "{\n"
            '  "factors": [\n'
            '    {"category": "macro", "id": "1.1", "name": "全球货币政策", '
            '"importance": 3, "judgment": "...", "impact": "持平"}\n'
            "  ],\n"
            '  "price_forecast": {\n'
            f'    "current_month": {{"label": "{year}年{month}月份布伦特首行合约价格预测", '
            '"range_low": 80, "range_high": 85, "avg": 82},\n'
            f'    "next_month": {{"label": "{next_year}年{next_month}月份布伦特首行合约价格预测", '
            '"range_low": 78, "range_high": 83, "avg": 80}\n'
            "  }\n"
            "}\n"
            f"factors 必须覆盖全部 {len(all_factor_defs())} 个因素（id 与样例一致）。"
            "impact 只能是 促涨/持平/促跌。区间幅度不超过 5 美元。"
        )

        llm_used = False
        content: dict[str, Any] | None = None
        if llm.is_enabled(provider):
            try:
                with llm_context(
                    "prediction_unrestricted_skill",
                    year=year,
                    month=month,
                    sample_year=sample_year,
                    sample_month=sample_month,
                    mode=mode,
                ):
                    raw = llm.chat_json(
                        SYSTEM_PROMPT,
                        user,
                        provider=provider,
                        model=model,
                        mode=mode,
                    )
                content = self._normalize(raw, year, month)
                llm_used = True
            except llm.LLMUnavailable as exc:
                logger.warning("无限制预测 skill 大模型不可用：%s", exc)

        if content is None:
            content = self._fallback_from_sample(sample, year, month)

        return {
            "content": content,
            "evidence": {
                "mode": "unrestricted",
                "sample_file": sample.get("sample_file"),
                "sample_year": sample_year,
                "sample_month": sample_month,
                "target_period": f"{year}年{month}月",
            },
            "sources_used": [{"name": sample.get("sample_file", "yuebao样例"), "url": "", "categories": ["样例"]}],
            "web_references": [],
            "llm_used": llm_used,
            "model": model or "",
            "total_steps": 1,
        }

    def _normalize(self, raw: dict[str, Any], year: int, month: int) -> dict[str, Any]:
        defs = all_factor_defs()
        by_id = {str(f.get("id")): f for f in raw.get("factors", []) if isinstance(f, dict)}
        factors = []
        for d in defs:
            item = by_id.get(d["id"], {})
            importance = item.get("importance", 1)
            try:
                importance = int(importance)
            except (TypeError, ValueError):
                importance = 1
            importance = min(5, max(1, importance))
            impact = str(item.get("impact", "持平")).strip()
            if impact not in IMPACT_OPTIONS:
                impact = "持平"
            factors.append(
                {
                    "category": d["category"],
                    "category_title": d["category_title"],
                    "id": d["id"],
                    "name": d["name"],
                    "importance": importance,
                    "judgment": str(item.get("judgment", "")).strip(),
                    "impact": impact,
                }
            )

        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        pf = raw.get("price_forecast", {}) or {}
        cm = pf.get("current_month", {}) or {}
        nm = pf.get("next_month", {}) or {}
        return {
            "factors": factors,
            "price_forecast": {
                "current_month": {
                    "label": cm.get("label", f"{year}年{month}月份布伦特首行合约价格预测"),
                    "range_low": cm.get("range_low"),
                    "range_high": cm.get("range_high"),
                    "avg": cm.get("avg"),
                },
                "next_month": {
                    "label": nm.get("label", f"{next_year}年{next_month}月份布伦特首行合约价格预测"),
                    "range_low": nm.get("range_low"),
                    "range_high": nm.get("range_high"),
                    "avg": nm.get("avg"),
                },
            },
        }

    @staticmethod
    def _fallback_from_sample(sample: dict[str, Any], year: int, month: int) -> dict[str, Any]:
        """大模型不可用时直接复用样例结构（仅更新期别标签）。"""
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        factors = json.loads(json.dumps(sample.get("factors", []), ensure_ascii=False))
        pf = sample.get("price_forecast", {})
        cm = pf.get("current_month", {})
        nm = pf.get("next_month", {})
        return {
            "factors": factors,
            "price_forecast": {
                "current_month": {
                    "label": f"{year}年{month}月份布伦特首行合约价格预测",
                    "range_low": cm.get("range_low"),
                    "range_high": cm.get("range_high"),
                    "avg": cm.get("avg"),
                },
                "next_month": {
                    "label": f"{next_year}年{next_month}月份布伦特首行合约价格预测",
                    "range_low": nm.get("range_low"),
                    "range_high": nm.get("range_high"),
                    "avg": nm.get("avg"),
                },
            },
        }
