"""国际油价月报 skill。

职责：
1. 采集平台数据库的权威基本面数据（价格月度统计、价差、供需平衡、因素评估）。
2. 结合可信数据源清单，调用大模型生成结构化月报（封面/摘要/各章节/表格/审核）。
3. 大模型不可用时使用规则兜底，保证始终可产出初稿。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core import llm
from app.core.llm import llm_context
from app.models.prediction import Prediction
from app.services.analytics import AnalyticsService
from app.services.data_query import DataQueryService
from app.skills.data_analysis_skill import DataAnalysisSkill
from app.services.report_table_data import ReportTableDataService, SYSTEM_TABLE_KEYS
from app.services.forecast import ForecastService
from app.skills.sources import (
    categories_from_items,
    report_sections_with_sources,
    sources_brief,
    sources_brief_by_item,
    sources_for,
    sources_payload,
)
from app.skills.verified_data import (
    CONFIDENCE_AUTHORITATIVE,
    CONFIDENCE_LEVELS,
    apply_authoritative_source,
    data_period_rules,
    data_points_brief,
    normalize_source_url,
    period_label,
)
from app.skills.evidence_guard import guard_report_content
from app.templates.monthly_report import DEFAULT_SECTIONS, default_content

logger = logging.getLogger("skill.report")

SYSTEM_PROMPT_STRICT = (
    "你是中国海油集团能源经济研究院的资深石油经济分析师，负责撰写《国际油价月报》。"
    "要求：1) 文风专业、严谨、数据详实，符合行业研究报告口径。"
    "2) 每个子章节正文 200-400 字，须引用具体数据并标注来源机构（如 EIA、IEA、OPEC、S&P 等），"
    "引用须含完整期别（如「2026年5月」），禁止省略年份；"
    "并为每个 level=2 子章节给出 confidence_level（致信水平，只能取 权威数据/模型推断）。"
    "3) 从互联网搜集到的真实数据:confidence_level 为「权威数据」,并填写 source_url。"
    "4) 大模型自行推导的数据:confidence_level 为「模型推断」,不填 source_url。"
    "5) 第三章展望须优先引用【平台预测模型】情景结果填写表3-1，并引用【预测分析表】影响因素与价格判断。"
    "6) outlook_model、outlook_scenario、outlook_conclusion 必须与预测模型/预测表数据一致，不得另编数字。"
    "7) 严格输出 JSON，不要包含任何额外说明文字。"
)

SYSTEM_PROMPT_PLATFORM = (
    "你是中国海油集团能源经济研究院的资深石油经济分析师，负责撰写《国际油价月报》。"
    "要求：1) 文风专业、严谨、数据详实，符合行业研究报告口径。"
    "2) 每个子章节正文 200-400 字，须引用具体数据并在正文中标注来源机构，引用须含完整期别；"
    "并为每个 level=2 子章节给出 confidence_level（致信水平，只能取 权威数据/模型推断）。"
    "3) 互联网真实数据标注「权威数据」并填写 source_url;自行推导标注「模型推断」。"
    "4) 第三章展望须优先引用【平台预测模型】情景结果填写表3-1，并引用【预测分析表】影响因素与价格判断。"
    "5) outlook_model、outlook_scenario、outlook_conclusion 必须与预测模型/预测表数据一致，不得另编数字。"
    "6) 严格输出 JSON，不要包含任何额外说明文字。"
)


def _system_prompt(trusted_sources_only: bool) -> str:
    return SYSTEM_PROMPT_STRICT if trusted_sources_only else SYSTEM_PROMPT_PLATFORM


class ReportSkill:
    name = "report"
    label = "国际油价月报"

    def __init__(self, db: Session):
        self.db = db
        self.analytics = AnalyticsService(db)
        self.forecast = ForecastService(db)
        self._web_references: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    def gather_evidence(
        self,
        review_year: int,
        review_month: int,
        outlook_year: int,
        outlook_month: int,
        symbol: str = "Brent",
    ) -> dict[str, Any]:
        query_svc = DataQueryService(self.db)
        params = query_svc.build_report_params(
            review_year,
            review_month,
            outlook_year=outlook_year,
            outlook_month=outlook_month,
        )
        data_result = DataAnalysisSkill(self.db).query(params)
        data = data_result.get("data", {})
        price_stats = data.get("price", {}).get("monthly_stats", [])
        brent = next(
            (s for s in price_stats if s.get("symbol") == "Brent"),
            self.analytics.calc_monthly_stats("Brent", review_year, review_month),
        )
        wti = next(
            (s for s in price_stats if s.get("symbol") == "WTI"),
            self.analytics.calc_monthly_stats("WTI", review_year, review_month),
        )
        start, end = self.analytics._month_bounds(review_year, review_month)
        spread = self.analytics.calc_spread("Brent", "WTI", start, end)[-10:]
        balance = data.get("balance", {}).get("rows", [])
        factors = self.analytics.query_factor_assessments(f"{review_year}-{review_month:02d}")
        forecast_model = self.forecast.get_forecast_for_period(symbol, outlook_year, outlook_month)
        prediction_table = self._load_prediction_table(symbol, outlook_year, outlook_month)
        macro_evidence: dict[str, Any] = {"data_points": []}
        return {
            "review_period": period_label(review_year, review_month),
            "outlook_period": period_label(outlook_year, outlook_month),
            "brent": brent,
            "wti": wti,
            "spot_market": self.analytics.build_spot_market_evidence(review_year, review_month),
            "brent_wti_spread_tail": spread,
            "price_monthly_table": {"brent": brent, "wti": wti},
            "balance_table": balance,
            "balance_forecast_sample": balance,
            "query_params": params.model_dump(mode="json"),
            "data": data,
            "factor_assessment_count": len(factors),
            "forecast_model": forecast_model,
            "prediction_table": prediction_table,
            "verified_macro": macro_evidence,
        }

    def _load_prediction_table(
        self, symbol: str, year: int, month: int
    ) -> dict[str, Any] | None:
        row = (
            self.db.query(Prediction)
            .filter(Prediction.symbol == symbol, Prediction.year == year, Prediction.month == month)
            .order_by(Prediction.created_at.desc())
            .first()
        )
        if not row:
            return None
        try:
            content = json.loads(row.content_json)
        except json.JSONDecodeError:
            content = {}
        factors = content.get("factors", []) if isinstance(content, dict) else []
        top_factors = sorted(
            [f for f in factors if isinstance(f, dict)],
            key=lambda f: int(f.get("importance", 0) or 0),
            reverse=True,
        )[:10]
        return {
            "id": row.id,
            "title": row.title,
            "year": row.year,
            "month": row.month,
            "llm_used": bool(row.llm_used),
            "price_forecast": content.get("price_forecast"),
            "top_factors": [
                {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "importance": f.get("importance"),
                    "impact": f.get("impact"),
                    "confidence_level": f.get("confidence_level"),
                    "source_url": f.get("source_url"),
                    "judgment": str(f.get("judgment", ""))[:280],
                }
                for f in top_factors
            ],
            "factor_count": len(factors),
        }

    # ------------------------------------------------------------------ #
    def generate(
        self,
        issue_no: str,
        report_date: str,
        review_month: tuple[int, int],
        outlook_month: tuple[int, int],
        provider: str | None = None,
        model: str | None = None,
        mode: str = "deep_research",
        extra_instruction: str = "",
        trusted_sources_only: bool = False,
    ) -> dict[str, Any]:
        ry, rm = review_month
        oy, om = outlook_month
        evidence = self.gather_evidence(ry, rm, oy, om)
        sections_with_sources = report_sections_with_sources(DEFAULT_SECTIONS)
        scoped_categories = categories_from_items(sections_with_sources)
        used_sources = sources_for(*scoped_categories) if trusted_sources_only else []
        content = default_content(issue_no, report_date)
        self._web_references = []

        llm_used = False
        if llm.is_enabled(provider):
            try:
                content = self._generate_with_llm(
                    content,
                    evidence,
                    ry,
                    rm,
                    oy,
                    om,
                    provider,
                    model,
                    extra_instruction,
                    sections_with_sources,
                    scoped_categories,
                    mode,
                    trusted_sources_only=trusted_sources_only,
                )
                llm_used = True
            except llm.LLMUnavailable as exc:
                logger.warning("月报 skill 大模型不可用，降级规则兜底：%s", exc)
                content = self._fallback(content, evidence, ry, rm, oy, om)
        else:
            content = self._fallback(content, evidence, ry, rm, oy, om)
        content = guard_report_content(content, evidence)
        tables, table_meta = ReportTableDataService(self.db).load_for_report(
            ry, rm, oy, om,
        )
        for key in SYSTEM_TABLE_KEYS:
            if key in tables:
                content.setdefault("tables", {})[key] = {
                    k: v for k, v in tables[key].items()
                    if k in ("title", "source", "headers", "rows")
                }
        evidence["table_snapshots"] = table_meta

        return {
            "content": content,
            "evidence": evidence,
            "sources_used": self._build_sources_used(
                used_sources, self._web_references, trusted_sources_only
            ),
            "references": {
                "forecast_model": bool(evidence.get("forecast_model")),
                "prediction_table": bool(evidence.get("prediction_table")),
                "prediction_id": (evidence.get("prediction_table") or {}).get("id"),
            },
            "web_references": [
                {"title": r.get("title", ""), "url": r.get("url", "")}
                for r in self._web_references
            ],
            "llm_used": llm_used,
            "model": model or "",
        }

    @staticmethod
    def _build_sources_used(
        used_sources: list[dict[str, Any]],
        web_refs: list[dict[str, str]],
        trusted_sources_only: bool,
    ) -> list[dict[str, Any]]:
        sources = [
            {"name": s["name"], "url": s["url"], "categories": s["categories"]}
            for s in used_sources
        ]
        if not trusted_sources_only:
            seen: set[str] = set()
            for ref in web_refs:
                url = ref.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    sources.append(
                        {
                            "name": ref.get("title", "DeepSearch 查证"),
                            "url": url,
                            "categories": ["DeepSearch"],
                        }
                    )
        return sources

    # ------------------------------------------------------------------ #
    def _generate_with_llm(
        self,
        base: dict[str, Any],
        evidence: dict[str, Any],
        ry: int,
        rm: int,
        oy: int,
        om: int,
        provider: str | None,
        model: str | None,
        extra_instruction: str,
        sections_with_sources: list[dict[str, Any]],
        scoped_categories: list[str],
        mode: str = "deep_research",
        trusted_sources_only: bool = False,
    ) -> dict[str, Any]:
        if not llm.deep_search_available() or not llm.is_enabled("volcengine"):
            raise llm.LLMUnavailable("DeepSearch 未配置，无法联网生成月报")
        provider = "volcengine"
        model = None
        mode = "deep_research"
        if trusted_sources_only:
            section_list = "\n".join(
                f'- id={s["id"]} 标题="{s["title"]}" 提示={s.get("hint", "")} '
                f'source_categories={s.get("sources", [])}'
                for s in sections_with_sources
            )
        else:
            section_list = "\n".join(
                f'- id={s["id"]} 标题="{s["title"]}" 提示={s.get("hint", "")}'
                for s in sections_with_sources
            )
        period_rules = data_period_rules(oy, om, ry, rm, strict=trusted_sources_only)
        macro_brief = data_points_brief(evidence.get("verified_macro") or {})
        if trusted_sources_only:
            sources_block = (
                f"【可信数据源（仅限以下机构，不得引用清单外来源）】\n"
                f"{sources_brief(*scoped_categories)}\n\n"
                f"【各章节限定数据源】\n{sources_brief_by_item(sections_with_sources)}\n\n"
                f"【数据源结构化入参（仅为机构说明，不含实时数值，禁止从中臆造数据）】\n"
                f"{json.dumps(sources_payload(*scoped_categories), ensure_ascii=False)}\n\n"
            )
            macro_rule = (
                "【互联网检索数据（引用时 confidence_level 为「权威数据」并填写 source_url）】\n"
            )
        else:
            sources_block = ""
            macro_rule = (
                "【互联网检索数据（引用时 confidence_level 为「权威数据」并填写 source_url）】\n"
                if macro_brief
                else ""
            )
        user = (
            f"请撰写《{base['cover']['title']}{base['cover']['issue']}》。\n"
            f"回顾月份：{ry}年{rm}月；展望月份：{oy}年{om}月。\n\n"
            f"{period_rules}\n\n"
            f"{macro_rule}"
            f"{macro_brief}\n\n"
            f"【需要撰写的子章节（保持 id 不变，标题可按当月主题润色）】\n{section_list}\n\n"
            f"{sources_block}"
            f"【平台数据库证据】\n{json.dumps(evidence, ensure_ascii=False, default=str)}\n\n"
            f"【现货市场数据库摘要（review_spot 必须引用，与图1-4~1-6 同源）】\n"
            f"{json.dumps(evidence.get('spot_market') or {}, ensure_ascii=False, default=str)}\n\n"
            "review_spot 须引用 spot_market 中 DTD（布伦特现货）、Dubai、ESPO 的均价与环比，"
            "以及 Brent-Dubai、Brent-ESPO、现货-期货价差变化；涨跌方向须与 spot_market.trends 一致，"
            "禁止将期货 Brent 的 mom_pct 直接当作现货走势；数据来源标注 CNEEI，confidence_level 为「权威数据」。\n\n"
            f"【平台预测模型（表3-1 与 outlook_scenario/outlook_model 须据此填写）】\n"
            f"{json.dumps(evidence.get('forecast_model') or {}, ensure_ascii=False, default=str)}\n\n"
            f"【预测分析表（影响因素与价格展望须据此引用，见 prediction_table）】\n"
            f"{json.dumps(evidence.get('prediction_table') or {}, ensure_ascii=False, default=str)}\n\n"
            "【联网查证】请使用 DeepSearch 自带的联网搜索能力查证最新市场、供需、宏观与地缘信息，引用时填写真实 source_url。\n\n"
            f"{extra_instruction}\n\n"
            "请严格输出如下 JSON：\n"
            "{\n"
            '  "summary": "内容摘要,可两段,用\\n分隔",\n'
            '  "sections": [{"id": "review_futures", "title": "（一）期货市场回顾", '
            f'"content": "...", "confidence_level": "{CONFIDENCE_AUTHORITATIVE}", '
            '"source_url": "https://...", "source_title": "来源标题"}],\n'
            '  "tables": {\n'
            '    "table_price_change": {"rows": []},\n'
            '    "table_scenario": {"rows": [["'
            f'{oy}年{om}月","104","100","150"],["本季度","95","90","120"],["全年","80","75","90"]]}},\n'
            "  },\n"
            "注意：表1-1（table_price_change）、表2-1（table_macro_pmi）、表2-2（table_demand_forecast）、"
            "表2-3（table_supply_balance）、表3-1（table_scenario）、表3-2（table_agency）"
            "均由数据中心月报表数据预置，请勿在 JSON 中填写这些表的 rows。\n"
            '  "approval": {"author": "执笔：...", "reviewer": "初审：...", "approver": "审核：...", "signer": "签发：..."}\n'
            "}\n"
            "sections 必须覆盖上面全部子章节 id。"
            f"每个 level=2 子章节须含 confidence_level，取值只能是 {'/'.join(CONFIDENCE_LEVELS)}。"
            "标注为权威数据时须填写 source_url。"
        )
        with llm_context(
            "report_skill",
            review_year=ry,
            review_month=rm,
            outlook_year=oy,
            outlook_month=om,
            mode=mode,
        ):
            raw, call_meta = llm.chat_json_with_meta(
                _system_prompt(trusted_sources_only),
                user,
                provider=provider,
                model=model,
                mode=mode,
            )
        self._web_references.extend(call_meta.get("references") or [])
        return self._merge(base, raw, evidence)

    # ------------------------------------------------------------------ #
    def _merge(
        self,
        base: dict[str, Any],
        raw: dict[str, Any],
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        content = json.loads(json.dumps(base, ensure_ascii=False))
        if raw.get("summary"):
            content["summary"] = str(raw["summary"]).strip()
        sec_by_id = {str(s.get("id")): s for s in raw.get("sections", []) if isinstance(s, dict)}
        for sec in content["sections"]:
            if sec["level"] != 2:
                continue
            got = sec_by_id.get(sec["id"])
            if got:
                if got.get("title"):
                    sec["title"] = str(got["title"]).strip()
                sec["content"] = str(got.get("content", "")).strip()
                apply_authoritative_source(
                    sec,
                    source_url=normalize_source_url(got.get("source_url")),
                    source_title=got.get("source_title"),
                    judgment=sec["content"],
                )
        # 表格只覆盖 rows，保留标题与来源；表1-1/表2-x/表3-2 由系统后处理，不接受 LLM 输出
        raw_tables = raw.get("tables", {}) or {}
        _system_tables = set(SYSTEM_TABLE_KEYS)
        for key, tbl in content["tables"].items():
            if key in _system_tables:
                continue
            rt = raw_tables.get(key)
            if isinstance(rt, dict) and isinstance(rt.get("rows"), list):
                tbl["rows"] = [[str(c) for c in row] for row in rt["rows"] if isinstance(row, list)]
        appr = raw.get("approval", {}) or {}
        for k in ("author", "reviewer", "approver", "signer"):
            if appr.get(k):
                content["approval"][k] = str(appr[k]).strip()
        return content

    @staticmethod
    def _spot_review_fallback(spot_market: dict[str, Any]) -> str:
        sm = spot_market or {}
        dtd = sm.get("brent_spot") or {}
        dubai = sm.get("dubai") or {}
        espo = sm.get("espo") or {}
        trends = sm.get("trends") or {}
        period = sm.get("review_period", "")
        return (
            f"{period}，布伦特现货（DTD）结算均价{dtd.get('avg', 'N/A')}美元/桶，"
            f"环比{dtd.get('mom_pct', 'N/A')}%，走势{trends.get('brent_spot', 'N/A')}；"
            f"Dubai 现货均价{dubai.get('avg', 'N/A')}美元/桶（{trends.get('dubai', 'N/A')}），"
            f"ESPO 现货均价{espo.get('avg', 'N/A')}美元/桶（{trends.get('espo', 'N/A')}）。"
            f"Brent-Dubai、Brent-ESPO 及布伦特现货-期货价差走势与图1-4～1-6 一致（数据来源：CNEEI）。"
        )

    # ------------------------------------------------------------------ #
    def _fallback(
        self,
        content: dict[str, Any],
        evidence: dict[str, Any],
        ry: int,
        rm: int,
        oy: int,
        om: int,
    ) -> dict[str, Any]:
        """无大模型时基于数据库证据生成可读初稿。"""
        brent = evidence.get("brent", {})
        wti = evidence.get("wti", {})
        avg = brent.get("avg")
        content["summary"] = (
            f"{ry}年{rm}月，国际油价{'宽幅震荡' if avg else '波动运行'}，"
            f"Brent 期货结算均价{avg if avg is not None else 'N/A'}美元/桶，"
            f"环比变化{brent.get('mom_pct', 'N/A')}%。"
            f"展望{oy}年{om}月，油价走势将受地缘局势、宏观经济及供需格局综合影响（数据来源：CNEEI）。"
        )
        history = {
            f.get("factor_name", "").strip(): f
            for f in self.analytics.query_factor_assessments()
        }
        fallback_text = {
            "review_futures": (
                f"{ry}年{rm}月，Brent 期货结算均价{brent.get('avg', 'N/A')}美元/桶，"
                f"WTI 期货结算均价{wti.get('avg', 'N/A')}美元/桶，月均价差约"
                f"{round((brent.get('avg', 0) or 0) - (wti.get('avg', 0) or 0), 2)}美元/桶（数据来源：CNEEI、ICE、NYMEX）。"
            ),
            "review_spot": self._spot_review_fallback(evidence.get("spot_market") or {}),
            "factor_macro": "主要经济体增长态势分化，PMI 与通胀数据继续影响油价预期（数据来源：S&P Global PMI、BLS、国家统计局）。",
            "factor_demand": "全球石油需求受季节性与高油价影响，环比偏弱运行（数据来源：IEA、EIA）。",
            "factor_supply": "OPEC+ 产量政策与非 OPEC 增产继续影响供应预期（数据来源：OPEC、EIA）。",
            "factor_inventory": "OECD 商业库存与战略储备变化对油价形成阶段性压力或支撑（数据来源：IEA、EIA）。",
            "factor_dollar": "美元指数与美联储政策通过金融渠道影响油价（数据来源：美联储、CME FedWatch）。",
            "factor_geo": "地缘局势仍是油价波动的重要扰动因素（数据来源：公开新闻与机构研判）。",
            "factor_position": "基金净多头与商业持仓结构反映市场情绪变化（数据来源：CFTC COT）。",
            "outlook_scenario": (
                f"基准情景下，预计{oy}年{om}月 Brent 原油期货结算均价约{avg or 'N/A'}美元/桶；"
                "低油价与高油价情景区间见表3-1（数据来源：CNEEI）。"
            ),
            "outlook_seminar": f"能源经济研究院召开国际油价研讨会，预测{oy}年{om}月 Brent 均价参考基准情景。",
            "outlook_model": "基于国际油价预测模型的结果已纳入综合判断（数据来源：CNEEI 模型）。",
            "outlook_agency": "S&P、Wood Mackenzie、Rystad 等机构预测结果见表3-2。",
            "outlook_conclusion": f"综合预测认为：{oy}年{om}月 Brent 原油期货均价约{avg or 'N/A'}美元/桶。",
        }
        for sec in content["sections"]:
            if sec["level"] == 2 and not sec.get("content"):
                # 优先用历史因素评估
                matched = ""
                for hname, hf in history.items():
                    if sec["title"][3:6] and sec["title"][3:6] in hname:
                        matched = (hf.get("assessment") or "")[:600]
                        break
                sec["content"] = matched or fallback_text.get(sec["id"], "")
        pred = evidence.get("prediction_table") or {}
        pf = pred.get("price_forecast") or {}
        cm = pf.get("current_month") or {}
        if cm.get("avg") is not None:
            outlook_line = (
                f"综合预测分析表与平台模型，预计{oy}年{om}月 Brent 首行合约均价约{cm.get('avg')}美元/桶"
                f"（区间 {cm.get('range_low', '—')}-{cm.get('range_high', '—')}）。"
            )
            for sec in content["sections"]:
                if sec.get("id") in ("outlook_conclusion", "outlook_model") and not sec.get("content"):
                    sec["content"] = outlook_line
            if pred.get("top_factors"):
                factor_bits = "；".join(
                    f"{f.get('name')}（{f.get('impact', '持平')}）"
                    for f in pred["top_factors"][:5]
                    if isinstance(f, dict)
                )
                for sec in content["sections"]:
                    if sec.get("id") == "factor_macro" and not sec.get("content"):
                        sec["content"] = f"预测分析表显示主要影响因素包括：{factor_bits}（数据来源：CNEEI 预测分析表）。"
        return content
