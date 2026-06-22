"""预测分析表 skill。

职责：
1. 从平台数据库采集权威基本面数据（价格、价差、供需平衡、历史因素评估）。
2. 结合可信数据源清单，调用大模型生成结构化的《油价预测分析表》。
3. 大模型不可用时，使用数据库历史因素 + 规则兜底，保证始终可产出。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core import llm
from app.core.llm import llm_context
from app.services.analytics import AnalyticsService
from app.skills.sources import (
    categories_from_items,
    sources_brief,
    sources_brief_by_item,
    sources_for,
    sources_payload,
)
from app.skills.verified_data import (
    CONFIDENCE_AUTHORITATIVE,
    CONFIDENCE_INFERRED,
    CONFIDENCE_LEVELS,
    append_data_gap_notice,
    apply_authoritative_source,
    data_period_rules,
    data_points_brief,
    normalize_source_url,
    period_label,
    prev_period,
    sanitize_judgment,
)
from app.skills.evidence_guard import guard_prediction_content
from app.templates.prediction_table import (
    IMPACT_OPTIONS,
    PREDICTION_FACTORS,
    all_factor_defs,
    empty_content,
)

logger = logging.getLogger("skill.prediction")

SYSTEM_PROMPT_STRICT = (
    "你是中国海油集团能源经济研究院的国际油价分析专家。"
    "你的任务是为指定月份填写《近期国际油价预测分析表》。"
    "要求：1) 每个影响因素都要给出 importance(1-5 整数,5最重要)、judgment(形势判断及支撑指标,150-300字,"
    "须引用具体数据并标注来源机构)、impact(只能取 促涨/持平/促跌 之一)、"
    "confidence_level(致信水平,只能取 权威数据/模型推断)。"
    "2) 从互联网搜集到的真实数据:confidence_level 为「权威数据」,并填写 source_url(来源网页链接,可附 source_title)。"
    "3) 大模型自行推导、无互联网来源支撑的数据:confidence_level 为「模型推断」,不填 source_url。"
    "4) 【平台数据库证据】仅供分析参考,不可替代互联网来源作为权威数据。"
    "5) 给出布伦特首行合约当月与次月价格预测(区间幅度不超过5美元,以及均价)。"
    "6) 严格输出 JSON,不要包含任何额外说明文字。"
)

SYSTEM_PROMPT_PLATFORM = (
    "你是中国海油集团能源经济研究院的国际油价分析专家。"
    "你的任务是为指定月份填写《近期国际油价预测分析表》。"
    "要求：1) 每个影响因素都要给出 importance(1-5 整数,5最重要)、judgment(形势判断及支撑指标,150-300字,"
    "须引用具体数据并在正文中标注来源机构)、impact(只能取 促涨/持平/促跌 之一)、"
    "confidence_level(致信水平,只能取 权威数据/模型推断)。"
    "2) 互联网真实数据标注「权威数据」并填写 source_url;自行推导标注「模型推断」。"
    "3) 【平台数据库证据】仅供分析参考,不可替代互联网来源作为权威数据。"
    "4) 给出布伦特首行合约当月与次月价格预测(区间幅度不超过5美元,以及均价)。"
    "5) 严格输出 JSON,不要包含任何额外说明文字。"
)


def _system_prompt(trusted_sources_only: bool) -> str:
    return SYSTEM_PROMPT_STRICT if trusted_sources_only else SYSTEM_PROMPT_PLATFORM


class PredictionSkill:
    name = "predict_table"
    label = "油价预测分析表"

    def __init__(self, db: Session):
        self.db = db
        self.analytics = AnalyticsService(db)
        self._web_references: list[dict[str, str]] = []

    # ------------------------------------------------------------------ #
    def gather_evidence(self, symbol: str, year: int, month: int) -> dict[str, Any]:
        review_year, review_month = prev_period(year, month)
        brent = self.analytics.calc_monthly_stats("Brent", review_year, review_month)
        wti = self.analytics.calc_monthly_stats("WTI", review_year, review_month)
        spread = self.analytics.calc_spread("Brent", "WTI")[-5:]
        balance = self.analytics.query_balance_forecast()[:30]
        # 历史因素评估（取最近一期，给大模型作为风格与口径参考）
        history = self.analytics.query_factor_assessments()
        macro_evidence: dict[str, Any] = {"data_points": []}
        return {
            "target_period": period_label(year, month),
            "review_period": period_label(review_year, review_month),
            "brent_last_month": brent,
            "wti_last_month": wti,
            "brent_wti_spread_tail": spread,
            "balance_forecast_sample": balance,
            "history_factor_count": len(history),
            "verified_macro": macro_evidence,
        }

    # ------------------------------------------------------------------ #
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
        trusted_sources_only: bool = False,
    ) -> dict[str, Any]:
        evidence = self.gather_evidence(symbol, year, month)
        defs = all_factor_defs()
        scoped_categories = categories_from_items(defs)
        used_sources = sources_for(*scoped_categories) if trusted_sources_only else []
        self._web_references = []

        content: dict[str, Any] | None = None
        llm_used = False
        if llm.is_enabled(provider):
            try:
                content = self._generate_with_llm(
                    defs,
                    evidence,
                    year,
                    month,
                    provider,
                    model,
                    extra_instruction,
                    scoped_categories,
                    mode,
                    on_progress,
                    trusted_sources_only=trusted_sources_only,
                )
                llm_used = True
            except llm.LLMUnavailable as exc:
                logger.warning("预测 skill 大模型不可用，降级规则兜底：%s", exc)

        if content is None:
            content = self._fallback(defs)
        content = guard_prediction_content(content, evidence)

        # 联网检索来源去重（用于前端展示与可追溯）
        web_refs: list[dict[str, str]] = []
        seen_web_urls: set[str] = set()
        for ref in self._web_references:
            url = ref.get("url", "")
            if url and url not in seen_web_urls:
                seen_web_urls.add(url)
                web_refs.append({"name": ref.get("title", ""), "url": url})

        sources_used = [
            {"name": s["name"], "url": s["url"], "categories": s["categories"]}
            for s in used_sources
        ]
        if not trusted_sources_only:
            for ref in web_refs:
                sources_used.append(
                    {"name": ref.get("name") or ref.get("title", "联网检索"), "url": ref.get("url", ""), "categories": ["联网"]}
                )

        return {
            "content": content,
            "evidence": evidence,
            "sources_used": sources_used,
            "web_references": web_refs,
            "llm_used": llm_used,
            "model": model or "",
            "total_steps": len(PREDICTION_FACTORS) + 1,
        }

    # ------------------------------------------------------------------ #
    def _generate_with_llm(
        self,
        defs: list[dict[str, Any]],
        evidence: dict[str, Any],
        year: int,
        month: int,
        provider: str | None,
        model: str | None,
        extra_instruction: str,
        scoped_categories: list[str],
        mode: str = "deep_research",
        on_progress: Callable[[int, int, str], None] | None = None,
        trusted_sources_only: bool = False,
    ) -> dict[str, Any]:
        import json

        if not llm.deep_search_available() or not llm.is_enabled("volcengine"):
            raise llm.LLMUnavailable("DeepSearch 未配置，无法联网生成预测分析表")
        provider = "volcengine"
        model = None
        mode = "deep_research"
        total_steps = len(PREDICTION_FACTORS) + 1
        all_factors: list[dict[str, Any]] = []
        review_year, review_month = prev_period(year, month)
        period_rules = data_period_rules(
            year, month, review_year, review_month, strict=trusted_sources_only
        )
        macro_brief = data_points_brief(evidence.get("verified_macro") or {})
        verified_points = (evidence.get("verified_macro") or {}).get("data_points") or []
        system_prompt = _system_prompt(trusted_sources_only)

        for step_idx, cat in enumerate(PREDICTION_FACTORS, start=1):
            cat_defs = [
                d for d in defs if d["category"] == cat["id"]
            ]
            if not cat_defs:
                continue
            if on_progress:
                on_progress(step_idx, total_steps, cat["title"])

            cat_categories = categories_from_items(cat_defs)
            if trusted_sources_only:
                factor_list = "\n".join(
                    f'- category={d["category"]} id={d["id"]} name={d["name"]} '
                    f'source_categories={d.get("sources", [])}'
                    for d in cat_defs
                )
            else:
                factor_list = "\n".join(
                    f'- category={d["category"]} id={d["id"]} name={d["name"]}'
                    for d in cat_defs
                )
            if trusted_sources_only:
                sources_block = (
                    f"【可信数据源（仅限以下机构，不得引用清单外来源）】\n"
                    f"{sources_brief(*cat_categories)}\n\n"
                    f"【各因素限定数据源】\n{sources_brief_by_item(cat_defs)}\n\n"
                    f"【数据源结构化入参（仅为机构说明，不含实时数值，禁止从中臆造数据）】\n"
                    f"{json.dumps(sources_payload(*cat_categories), ensure_ascii=False)}\n\n"
                )
                macro_rule = (
                    "【互联网检索数据（引用时 confidence_level 为「权威数据」并填写 source_url）】\n"
                )
                json_example = (
                    '    {"category": "macro", "id": "1.2", "name": "美元汇率", '
                    '"importance": 3, '
                    '"judgment": "...", '
                    '"impact": "促跌", '
                    f'"confidence_level": "{CONFIDENCE_AUTHORITATIVE}", '
                    '"source_url": "https://...", "source_title": "来源标题"}}\n'
                )
                output_rule = (
                    "factors 必须覆盖本批全部因素。impact 只能是 促涨/持平/促跌。"
                    f"confidence_level 只能是 {'/'.join(CONFIDENCE_LEVELS)}。"
                    "标注为权威数据时须填写 source_url。"
                )
            else:
                sources_block = ""
                macro_rule = (
                    "【互联网检索数据（引用时 confidence_level 为「权威数据」并填写 source_url）】\n"
                    if macro_brief
                    else ""
                )
                json_example = (
                    '    {"category": "macro", "id": "1.2", "name": "美元汇率", '
                    '"importance": 3, '
                    '"judgment": "...", '
                    '"impact": "促跌", '
                    f'"confidence_level": "{CONFIDENCE_INFERRED}"}}\n'
                )
                output_rule = (
                    "factors 必须覆盖本批全部因素。impact 只能是 促涨/持平/促跌。"
                    f"confidence_level 只能是 {'/'.join(CONFIDENCE_LEVELS)}。"
                    "标注为权威数据时须填写 source_url。"
                )
            user = (
                f"目标预测月份：{year}年{month}月；数据回顾月：{review_year}年{review_month}月。"
                f"请仅填写下列 {len(cat_defs)} 个影响因素（属于「{cat['title']}」）。\n\n"
                f"{period_rules}\n\n"
                f"{macro_rule}"
                f"{macro_brief}\n\n"
                f"【本批因素清单】\n{factor_list}\n\n"
                f"{sources_block}"
                f"【平台数据库证据（仅供分析参考，不可替代互联网来源作为权威数据）】\n"
                f"{json.dumps(evidence, ensure_ascii=False, default=str)}\n\n"
                "【联网查证】请使用 DeepSearch 自带的联网搜索能力获取最新权威数据，引用时填写真实 source_url。\n\n"
                f"{extra_instruction}\n\n"
                "请严格输出如下 JSON（仅含 factors 数组，不要输出 price_forecast）：\n"
                "{\n"
                '  "factors": [\n'
                f"{json_example}"
                "  ]\n"
                "}\n"
                f"{output_rule}"
            )
            with llm_context(
                "prediction_skill",
                year=year,
                month=month,
                factor_count=len(cat_defs),
                batch=cat["id"],
                batch_title=cat["title"],
                batch_step=step_idx,
                batch_total=total_steps,
                mode=mode,
            ):
                raw, call_meta = llm.chat_json_with_meta(
                    system_prompt,
                    user,
                    provider=provider,
                    model=model,
                    mode=mode,
                )
            self._web_references.extend(call_meta.get("references") or [])
            all_factors.extend(raw.get("factors", []))

        if on_progress:
            on_progress(total_steps, total_steps, "布伦特价格预测")

        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        factor_summary = json.dumps(
            [
                {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "importance": f.get("importance"),
                    "impact": f.get("impact"),
                }
                for f in all_factors
            ],
            ensure_ascii=False,
        )
        price_user = (
            f"目标预测月份：{year}年{month}月；数据回顾月：{review_year}年{review_month}月。"
            f"基于已完成的 {len(all_factors)} 项因素评估，给出布伦特首行合约价格预测。\n\n"
            f"{period_rules}\n\n"
            f"【因素评估摘要】\n{factor_summary}\n\n"
            f"【平台数据库证据（仅供分析参考，不可替代互联网来源作为权威数据）】\n"
            f"{json.dumps(evidence, ensure_ascii=False, default=str)}\n\n"
            f"{extra_instruction}\n\n"
            "请严格输出如下 JSON（仅含 price_forecast）：\n"
            "{\n"
            '  "price_forecast": {\n'
            f'    "current_month": {{"label": "{year}年{month}月份布伦特首行合约价格预测", '
            '"range_low": 80, "range_high": 85, "avg": 82},\n'
            f'    "next_month": {{"label": "{next_year}年{next_month}月份布伦特首行合约价格预测", '
            '"range_low": 78, "range_high": 83, "avg": 80}\n'
            "  }\n"
            "}\n"
            "区间幅度不超过 5 美元。"
        )
        with llm_context(
            "prediction_skill",
            year=year,
            month=month,
            factor_count=len(defs),
            batch="price_forecast",
            batch_title="布伦特价格预测",
            batch_step=total_steps,
            batch_total=total_steps,
            mode=mode,
        ):
            price_raw, price_meta = llm.chat_json_with_meta(
                system_prompt,
                price_user,
                provider=provider,
                model=model,
                mode=mode,
            )
        self._web_references.extend(price_meta.get("references") or [])

        return self._normalize(
            {"factors": all_factors, "price_forecast": price_raw.get("price_forecast", {})},
            defs,
            year,
            month,
            scoped_categories,
            verified_points=verified_points,
            trusted_sources_only=trusted_sources_only,
        )

    # ------------------------------------------------------------------ #
    def _normalize(
        self,
        raw: dict[str, Any],
        defs: list[dict[str, Any]],
        year: int,
        month: int,
        scoped_categories: list[str] | None = None,
        verified_points: list[dict[str, Any]] | None = None,
        trusted_sources_only: bool = False,
    ) -> dict[str, Any]:
        review_year, review_month = prev_period(year, month)
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
            judgment = sanitize_judgment(
                str(item.get("judgment", "")).strip(),
                d["name"],
                review_year=review_year,
                review_month=review_month,
                verified_points=verified_points,
                strict=trusted_sources_only,
            )
            if not judgment:
                judgment = append_data_gap_notice(judgment, d["name"])
            entry: dict[str, Any] = {
                "category": d["category"],
                "category_title": d["category_title"],
                "id": d["id"],
                "name": d["name"],
                "importance": importance,
                "judgment": judgment,
                "impact": impact,
            }
            apply_authoritative_source(
                entry,
                source_url=normalize_source_url(item.get("source_url")),
                source_title=item.get("source_title"),
                judgment=judgment,
            )
            factors.append(entry)
        pf = raw.get("price_forecast", {}) or {}
        cm = pf.get("current_month", {}) or {}
        nm = pf.get("next_month", {}) or {}
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
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

    # ------------------------------------------------------------------ #
    def _fallback(self, defs: list[dict[str, Any]]) -> dict[str, Any]:
        """大模型不可用时，用数据库历史因素评估填充。"""
        content = empty_content()
        history = {
            f.get("factor_name", "").strip(): f
            for f in self.analytics.query_factor_assessments()
        }
        for item in content["factors"]:
            # 历史 factor_name 形如 "1.1 全球货币政策"，做模糊匹配
            for hname, hf in history.items():
                if item["name"] in hname or item["id"] in hname:
                    item["importance"] = hf.get("importance", 1) or 1
                    item["judgment"] = (hf.get("assessment") or "")[:800]
                    impact = hf.get("impact_direction") or "持平"
                    item["impact"] = impact if impact in IMPACT_OPTIONS else "持平"
                    break
        return content
