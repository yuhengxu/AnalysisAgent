"""月报表2-1/2-2/2-3 深度研究填充。

- 表2-3：优先从平台 ``balance_forecasts``（供需差）读取，禁止臆造。
- 表2-1：通过 DeepSearch 联网获取，禁止猜测或编造。
- 表2-2：由大模型基于宏观形势预测 GDP 增速，可手工修正。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core import llm
from app.core.config import settings
from app.core.timezone import now_beijing_naive
from app.services.analytics import AnalyticsService

logger = logging.getLogger("service.report_table_research")

_DEBUG_LOG_PATH = "/home/ubuntu/AnalysisAgent/.cursor/debug-e48142.log"


def _debug_log(hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    # #region agent log
    try:
        import time
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "sessionId": "e48142",
                "hypothesisId": hypothesis_id,
                "location": location,
                "message": message,
                "data": data,
                "timestamp": int(time.time() * 1000),
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass
    # #endregion


def _resolve_web_research_provider() -> str | None:
    """联网研究仅允许使用 Volcengine DeepSearch。"""
    if llm.deep_search_available() and llm.is_enabled("volcengine"):
        return "volcengine"
    return None


def _resolve_llm_provider() -> str | None:
    """任意已启用的大模型 provider（用于表2-2 预测）。"""
    default = settings.default_llm_provider
    if llm.is_enabled(default):
        return default
    for candidate in ("volcengine", "deepseek", "openai"):
        if llm.is_enabled(candidate):
            return candidate
    return None


def _deep_search_system() -> str:
    """与 Agent DeepSearch 模式对齐。"""
    today = now_beijing_naive().strftime("%Y年%m月%d日")
    return (
        f"你是宏观经济数据研究员，具备联网搜索能力。今天是 {today}。\n"
        "请联网查询用户指定的 PMI 数据，详细列出美国、欧元区、中国的"
        "综合/制造业/服务业 PMI 初值、终值及环比变化（百分点），并注明来源机构。"
    )


def _period_label(year: int, month: int) -> str:
    return f"{year}年{month}月"


def _pmi_period_guard(
    pmi_year: int,
    pmi_month: int,
    review_year: int | None = None,
    review_month: int | None = None,
) -> str:
    """深度研究检索词中的期别约束，防止查错月份。"""
    pmi_label = _period_label(pmi_year, pmi_month)
    if review_year is None or review_month is None:
        return f"须为 {pmi_label} 当期 PMI 数据，勿用其他月份。"
    review_label = _period_label(review_year, review_month)
    return (
        f"月报回顾月 {review_label}，本表 PMI 查证期别与回顾月一致为 {pmi_label}。"
        f"仅查询 {pmi_label} 当期 PMI，勿用其他月份。"
    )


def _prev_period(year: int, month: int) -> tuple[int, int]:
    if month > 1:
        return year, month - 1
    return year - 1, 12

# yuebao 样例机构顺序与显示名
SUPPLY_AGENCY_ORDER = ["IEA", "EIA", "S&P", "WM", "Rystad"]
SUPPLY_AGENCY_ALIASES: dict[str, str] = {
    "IEA": "IEA",
    "EIA": "EIA",
    "S&P": "S&P",
    "SP": "S&P",
    "WM": "WM",
    "WoodMac": "WM",
    "Woodmac": "WM",
    "Wood Mackenzie": "WM",
    "Rystad": "Rystad",
    "Rystad Energy": "Rystad",
}
SUPPLY_QUARTERS = ("2026Q1", "2026Q2", "2026Q3", "2026Q4")

GDP_REGIONS = ["全球", "美国", "欧元区", "东盟", "沙特阿拉伯", "俄罗斯"]

PMI_ROW_SPECS: list[tuple[str, str, str]] = [
    ("综合", "初值", "composite_flash"),
    ("综合", "环比变化", "composite_mom"),
    ("制造业", "终值", "mfg_final"),
    ("制造业", "环比变化", "mfg_mom"),
    ("服务业", "初值", "svc_flash"),
    ("服务业", "环比变化", "svc_mom"),
]
PMI_COLUMNS: list[tuple[str, str]] = [
    ("美国", "us"),
    ("欧元区", "eurozone"),
    ("中国", "china"),
]
PMI_MANDATORY_REGIONS = ("us", "china")
PMI_CORE_FIELDS = ("composite_flash", "mfg_final", "svc_flash")
PMI_REGION_PRIORITY = {"us": 0, "china": 1, "eurozone": 2}
PMI_MAX_DEEPSEARCH_CALLS = 25

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _snapshot_month(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def _format_signed(value: float | int | str | None, *, decimals: int = 1) -> str:
    if value is None or value == "":
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value).strip()
    if decimals == 0:
        rounded = round(num)
        if rounded == 0 and abs(num) < 0.05:
            return "+0" if num >= 0 else "-0"
        sign = "+" if rounded > 0 else ("-" if rounded < 0 else "+0")
        return f"{sign}{abs(rounded)}"
    rounded = round(num, decimals)
    if abs(rounded) < 10 ** (-decimals) / 2:
        return f"+0.{'0' * decimals}" if decimals else "+0"
    sign = "+" if rounded > 0 else "-"
    return f"{sign}{abs(rounded):.{decimals}f}"


def _format_decimal(value: float | int | str | None, *, decimals: int = 2) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{round(float(value), decimals):.{decimals}f}"
    except (TypeError, ValueError):
        return str(value).strip()


def extract_json_object(text: str) -> dict[str, Any] | None:
    """从 Browser/LLM 文本中提取 JSON 对象。"""
    if not text:
        return None
    for pat in (_JSON_BLOCK_RE, _JSON_OBJECT_RE):
        for match in pat.finditer(text):
            blob = match.group(1) if pat is _JSON_BLOCK_RE else match.group(0)
            try:
                parsed = json.loads(blob)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def pmi_table_title(pmi_year: int, pmi_month: int) -> str:
    return f"表2-1 全球主要经济体{pmi_year}年{pmi_month}月PMI"


def gdp_table_title() -> str:
    return "表2-2 全球主要经济体GDP增速预测，%"


def supply_table_title() -> str:
    return "表2-3 机构对全球石油供应过剩量的预测（单位：百万桶/天）"


def default_pmi_table(pmi_year: int, pmi_month: int) -> dict[str, Any]:
    return {
        "title": pmi_table_title(pmi_year, pmi_month),
        "source": "S&P Global、Eurostat、国家统计局",
        "headers": ["PMI", "PMI", "美国", "欧元区", "中国"],
        "rows": [[a, b, "", "", ""] for a, b, _ in PMI_ROW_SPECS],
    }


def default_gdp_table() -> dict[str, Any]:
    return {
        "title": gdp_table_title(),
        "source": "IMF、世界银行",
        "headers": ["国家/地区", "2026", "较2026.1预测变化"],
        "rows": [[region, "", ""] for region in GDP_REGIONS],
    }


def default_supply_table(review_year: int) -> dict[str, Any]:
    headers = ["机构", f"{review_year}Q1", f"{review_year}Q2", f"{review_year}Q3", f"{review_year}Q4"]
    return {
        "title": supply_table_title(),
        "source": "IEA、EIA、S&P、Wood Mackenzie、Rystad",
        "headers": headers,
        "rows": [[name, "", "", "", ""] for name in SUPPLY_AGENCY_ORDER],
    }


def build_pmi_rows(region_data: dict[str, dict[str, Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for label_a, label_b, field in PMI_ROW_SPECS:
        row = [label_a, label_b]
        is_mom = field.endswith("_mom")
        for _, key in PMI_COLUMNS:
            cell = (region_data.get(key) or {}).get(field)
            if cell is None or cell == "":
                row.append("")
            elif is_mom:
                row.append(_format_signed(cell))
            else:
                row.append(_format_decimal(cell, decimals=1))
        rows.append(row)
    return rows


def build_gdp_rows(items: list[dict[str, Any]]) -> list[list[str]]:
    by_region = {
        str(item.get("region", "")).strip(): item
        for item in items
        if isinstance(item, dict) and item.get("region")
    }
    rows: list[list[str]] = []
    for region in GDP_REGIONS:
        item = by_region.get(region) or {}
        forecast = item.get("forecast_2026")
        revision = item.get("revision_vs_jan2026")
        rows.append([
            region,
            _format_decimal(forecast, decimals=1) if forecast not in (None, "") else "",
            _format_signed(revision) if revision not in (None, "") else "",
        ])
    return rows


class ReportTableResearchService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics = AnalyticsService(db)

    def pmi_reference_month(self, review_year: int, review_month: int) -> tuple[int, int]:
        """表2-1 PMI 查证期别：与回顾月一致。"""
        return review_year, review_month

    def fetch_pmi_gdp_tables(
        self,
        pmi_year: int,
        pmi_month: int,
        review_year: int,
        review_month: int,
        *,
        fetch_pmi: bool = True,
        fetch_gdp: bool = True,
    ) -> dict[str, Any]:
        """联网查证 PMI/GDP 表，不写 content。"""
        return self._research_pmi_and_gdp(
            pmi_year, pmi_month, review_year, review_month,
            fetch_pmi=fetch_pmi, fetch_gdp=fetch_gdp,
        )

    def fill_tables(
        self,
        content: dict[str, Any],
        review_year: int,
        review_month: int,
    ) -> dict[str, Any]:
        """填充表2-1/2-2/2-3，返回来源元数据。"""
        pmi_y, pmi_m = self.pmi_reference_month(review_year, review_month)
        tables = content.setdefault("tables", {})
        meta: dict[str, Any] = {
            "pmi_period": _period_label(pmi_y, pmi_m),
            "supply_snapshot": _snapshot_month(review_year, review_month),
            "sources": {},
        }

        supply_tbl = self.build_supply_balance_table(review_year, review_month)
        if supply_tbl:
            tables["table_supply_balance"] = supply_tbl
            meta["sources"]["table_supply_balance"] = supply_tbl.get("source_meta", {})
            meta["supply_snapshot"] = supply_tbl.get("source_meta", {}).get(
                "snapshot_month", _snapshot_month(review_year, review_month),
            )

        tables.setdefault("table_macro_pmi", default_pmi_table(pmi_y, pmi_m))
        tables.setdefault("table_demand_forecast", default_gdp_table())
        tables["table_macro_pmi"]["title"] = pmi_table_title(pmi_y, pmi_m)
        tables["table_demand_forecast"]["title"] = gdp_table_title()
        tables.setdefault("table_supply_balance", default_supply_table(review_year))

        if _resolve_web_research_provider() or _resolve_llm_provider():
            from app.services.report_table_data import resolve_gdp_llm_predict_enabled

            fetch_gdp = resolve_gdp_llm_predict_enabled()
            research = self._research_pmi_and_gdp(
                pmi_y, pmi_m, review_year, review_month,
                fetch_pmi=True, fetch_gdp=fetch_gdp,
            )
            meta["deep_research"] = research.get("deep_research", {})
            meta["gdp_llm_predict_enabled"] = fetch_gdp
            if research.get("pmi_table"):
                tables["table_macro_pmi"] = research["pmi_table"]
                meta["sources"]["table_macro_pmi"] = research.get("pmi_meta", {})
            if fetch_gdp and research.get("gdp_table"):
                tables["table_demand_forecast"] = research["gdp_table"]
                meta["sources"]["table_demand_forecast"] = research.get("gdp_meta", {})
        else:
            meta["deep_research"] = {
                "enabled": False,
                "reason": "DeepSearch 未配置",
            }

        return meta

    def build_supply_balance_table(
        self,
        review_year: int,
        review_month: int,
    ) -> dict[str, Any] | None:
        snapshot, requested, used_fallback = self.analytics.resolve_balance_snapshot_month(
            review_year, review_month, supply_demand=["供需差"],
        )
        if not snapshot:
            logger.warning(
                "表2-3：回顾月 %s 无供需差 snapshot，且无更早数据",
                _snapshot_month(review_year, review_month),
            )
            return None
        if used_fallback:
            logger.info(
                "表2-3：回顾月 %s 无数据，回退至 snapshot %s",
                requested, snapshot,
            )
        quarters = tuple(f"{review_year}Q{i}" for i in range(1, 5))
        rows_raw = self.analytics.query_balance_forecast(
            supply_demand=["供需差"],
            snapshot_month=snapshot,
            periods=list(quarters),
            limit=200,
        )
        if not rows_raw:
            logger.warning("表2-3：snapshot=%s 无供需差数据", snapshot)
            return None

        by_display: dict[str, dict[str, float]] = {}
        source_agencies: list[str] = []
        for row in rows_raw:
            canonical = SUPPLY_AGENCY_ALIASES.get(row["agency"])
            if not canonical:
                continue
            by_display.setdefault(canonical, {})[row["period"]] = float(row["value"])
            if row["agency"] not in source_agencies:
                source_agencies.append(row["agency"])

        if not by_display:
            return None

        table_rows: list[list[str]] = []
        filled_agencies: list[str] = []
        for agency in SUPPLY_AGENCY_ORDER:
            period_vals = by_display.get(agency)
            if not period_vals:
                continue
            filled_agencies.append(agency)
            table_rows.append([
                agency,
                *[_format_decimal(period_vals.get(q), decimals=2) for q in quarters],
            ])

        if not table_rows:
            return None

        return {
            "title": supply_table_title(),
            "source": "IEA、EIA、S&P、Wood Mackenzie、Rystad",
            "headers": ["机构", *quarters],
            "rows": table_rows,
            "source_meta": {
                "snapshot_month": snapshot,
                "requested_snapshot_month": requested,
                "snapshot_fallback": used_fallback,
                "agencies": filled_agencies,
                "db_agencies": source_agencies,
                "verified": True,
            },
        }

    def _research_pmi_and_gdp(
        self,
        pmi_year: int,
        pmi_month: int,
        review_year: int,
        review_month: int,
        *,
        fetch_pmi: bool = True,
        fetch_gdp: bool = True,
    ) -> dict[str, Any]:
        prompt = self._build_pmi_prompt(pmi_year, pmi_month, review_year, review_month)
        out: dict[str, Any] = {}
        provider = _resolve_web_research_provider()
        # #region agent log
        _debug_log(
            "H1",
            "report_table_research._research_pmi_and_gdp:entry",
            "web research provider resolved",
            {
                "provider": provider,
                "deep_search_available": llm.deep_search_available(),
                "default_llm_provider": settings.default_llm_provider,
                "pmi_period": f"{pmi_year}-{pmi_month:02d}",
                "review_period": f"{review_year}-{review_month:02d}",
            },
        )
        # #endregion

        if provider:
            try:
                with llm.llm_context("report_table_research", review_year=review_year, review_month=review_month):
                    if fetch_pmi and not out.get("pmi_table"):
                        pmi_parsed, pmi_meta = self._research_pmi_via_web(
                            provider,
                            pmi_year,
                            pmi_month,
                            review_year,
                            review_month,
                        )
                        ref_urls = self._references_to_urls(pmi_meta.get("references"))
                        pmi_block = pmi_parsed.get("table_macro_pmi") or pmi_parsed
                        pmi_rows = pmi_block.get("rows") if isinstance(pmi_block, dict) else {}
                        # #region agent log
                        _debug_log(
                            "H2",
                            "report_table_research._research_pmi_and_gdp:pmi",
                            "PMI deep research result",
                            {
                                "provider": provider,
                                "model": pmi_meta.get("deepsearch_bot_id") or pmi_meta.get("model"),
                                "deep_search": pmi_meta.get("deep_search"),
                                "reference_count": len(ref_urls),
                                "ref_titles": [
                                    (r.get("title") or "")[:80]
                                    for r in (pmi_meta.get("references") or [])
                                    if isinstance(r, dict)
                                ][:5],
                                "pmi_has_values": self._pmi_has_values(pmi_rows if isinstance(pmi_rows, dict) else {}),
                                "mandatory_filled": self._pmi_mandatory_filled(pmi_rows if isinstance(pmi_rows, dict) else {}),
                                "missing_regions": self._pmi_missing_mandatory(pmi_rows if isinstance(pmi_rows, dict) else {}),
                            },
                        )
                        # #endregion
                        out.setdefault("deep_research", {})["pmi"] = pmi_meta
                        self._apply_pmi_gdp_payload(
                            out,
                            pmi_parsed if "table_macro_pmi" in pmi_parsed else {"table_macro_pmi": pmi_parsed},
                            ref_urls,
                            pmi_year,
                            pmi_month,
                            True,
                            False,
                        )
            except llm.LLMUnavailable as exc:
                logger.warning("表2-1：DeepSearch 不可用：%s", exc)
                out["deep_research"] = {"error": str(exc)}

        if fetch_gdp and not out.get("gdp_table"):
            gdp_parsed, gdp_meta = self._predict_gdp_forecast(review_year, review_month)
            # #region agent log
            gdp_block = (gdp_parsed or {}).get("table_demand_forecast") or (gdp_parsed or {})
            gdp_rows = gdp_block.get("rows") if isinstance(gdp_block, dict) else []
            _debug_log(
                "H4",
                "report_table_research._research_pmi_and_gdp:gdp_predict",
                "GDP LLM prediction result",
                {
                    "provider": gdp_meta.get("provider"),
                    "model": gdp_meta.get("model"),
                    "gdp_has_values": self._gdp_has_values(gdp_rows if isinstance(gdp_rows, list) else []),
                    "predicted": True,
                },
            )
            # #endregion
            if gdp_parsed:
                out.setdefault("gdp_predict", {})["meta"] = gdp_meta
                self._apply_pmi_gdp_payload(
                    out,
                    gdp_parsed if "table_demand_forecast" in gdp_parsed else {"table_demand_forecast": gdp_parsed},
                    [],
                    pmi_year,
                    pmi_month,
                    False,
                    True,
                    gdp_predicted=True,
                )
            else:
                out["gdp_predict"] = gdp_meta

        # #region agent log
        pmi_meta = (out.get("deep_research") or {}).get("pmi") or {}
        _debug_log(
            "H3",
            "report_table_research._research_pmi_and_gdp:exit",
            "research result",
            {
                "pmi_table": bool(out.get("pmi_table")),
                "gdp_table": bool(out.get("gdp_table")),
                "deepsearch_calls": pmi_meta.get("deepsearch_calls"),
                "rate_limited": bool(pmi_meta.get("rate_limited")),
            },
        )
        # #endregion
        return out

    def _research_pmi_via_web(
        self,
        provider: str,
        pmi_year: int,
        pmi_month: int,
        review_year: int | None = None,
        review_month: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """DeepSearch 串行联网：每次只发一个请求，等返回后再发下一个。"""
        struct_provider = _resolve_llm_provider() or provider
        meta: dict[str, Any] = {"deep_search": True, "provider": provider}
        combined_texts: list[str] = []
        all_references: list[Any] = []
        deepsearch_calls = 0
        rate_limited = False
        search_log: list[dict[str, Any]] = []

        def _sequential_search(prompt: str, label: str) -> str:
            nonlocal deepsearch_calls, rate_limited
            if rate_limited:
                search_log.append({"label": label, "skipped": "rate_limited"})
                return ""
            if deepsearch_calls >= PMI_MAX_DEEPSEARCH_CALLS:
                search_log.append({"label": label, "skipped": "max_calls"})
                return ""
            content, search_meta = self._search_pmi_with_deepsearch(provider, prompt)
            deepsearch_calls += 1
            if search_meta.get("rate_limited"):
                rate_limited = True
            refs = search_meta.get("references") or []
            all_references.extend(refs)
            if content:
                combined_texts.append(content)
            entry = {
                "label": label,
                "call": deepsearch_calls,
                "rate_limited": bool(search_meta.get("rate_limited")),
                "content_len": len(content or ""),
                "ref_count": len(refs),
            }
            search_log.append(entry)
            # #region agent log
            _debug_log(
                "H8",
                "report_table_research._research_pmi_via_web:step",
                "sequential DeepSearch step",
                entry,
            )
            # #endregion
            return content or ""

        # 1. 全局检索
        content = _sequential_search(
            self._build_pmi_search_prompt(
                pmi_year, pmi_month, review_year, review_month,
            ),
            "global",
        )
        rows: dict[str, Any] = {}
        if content or all_references:
            rows = self._extract_pmi_rows_from_text(
                content, struct_provider, pmi_year, pmi_month, all_references,
            )

        # 2. 结构化补全
        if not self._pmi_mandatory_filled(rows) and (content or all_references):
            ref_brief = self._references_to_brief(all_references)
            structured, struct_meta = self._structure_pmi_table(
                content,
                ref_brief,
                pmi_year,
                pmi_month,
                struct_provider,
                require_us_china=True,
            )
            meta["structure_fallback"] = struct_meta
            rows = self._merge_pmi_region_rows(rows, self._pmi_rows_from_payload(structured))

        # 3. 按国别串行补查（美国 → 中国 → 欧元区）
        for region_key in (*PMI_MANDATORY_REGIONS, "eurozone"):
            if rate_limited or self._pmi_mandatory_filled(rows):
                break
            block = (rows or {}).get(region_key) or {}
            if region_key in PMI_MANDATORY_REGIONS and self._pmi_region_has_core_values(block):
                continue
            if region_key == "eurozone" and isinstance(block, dict) and block:
                if any(block.get(f) not in (None, "") for f in PMI_CORE_FIELDS):
                    continue
            region_content = _sequential_search(
                self._build_pmi_region_search_prompt(
                    region_key, pmi_year, pmi_month, review_year, review_month,
                ),
                f"region:{region_key}",
            )
            if region_content or all_references:
                region_rows = self._extract_pmi_rows_from_text(
                    region_content,
                    struct_provider,
                    pmi_year,
                    pmi_month,
                    all_references,
                    focus_region=region_key,
                )
                rows = self._merge_pmi_region_rows(rows, region_rows)

        # 4. 按国别串行补查缺失字段（一国一次）
        for region_key, missing_fields in self._pmi_missing_fields_by_region(rows).items():
            if rate_limited:
                break
            if not missing_fields:
                continue
            gap_content = _sequential_search(
                self._build_pmi_region_gap_prompt(
                    region_key, missing_fields, pmi_year, pmi_month,
                    review_year, review_month,
                ),
                f"gap:{region_key}",
            )
            if gap_content:
                gap_rows = self._extract_pmi_rows_from_text(
                    gap_content,
                    struct_provider,
                    pmi_year,
                    pmi_month,
                    all_references,
                    focus_region=region_key,
                )
                rows = self._merge_pmi_region_rows(rows, gap_rows)

        # 5. 美国/中国仍缺字段时，逐字段串行专项补查
        for region_key, field_key in self._pmi_missing_fields_sorted(rows):
            if rate_limited or deepsearch_calls >= PMI_MAX_DEEPSEARCH_CALLS:
                meta["field_search_truncated"] = True
                break
            if region_key not in PMI_MANDATORY_REGIONS:
                continue
            if self._pmi_mandatory_filled(rows):
                break
            block = (rows or {}).get(region_key) or {}
            if block.get(field_key) not in (None, ""):
                continue
            field_content = _sequential_search(
                self._build_pmi_field_search_prompt(
                    region_key, field_key, pmi_year, pmi_month,
                    review_year, review_month,
                ),
                f"field:{region_key}.{field_key}",
            )
            if field_content:
                field_rows = self._extract_pmi_rows_from_text(
                    field_content,
                    struct_provider,
                    pmi_year,
                    pmi_month,
                    all_references,
                    focus_region=region_key,
                    focus_field=field_key,
                )
                rows = self._merge_pmi_region_rows(rows, field_rows)

        # 6. 汇总全部查证正文后再结构化一次
        if not self._pmi_mandatory_filled(rows) and combined_texts and not rate_limited:
            ref_brief = self._references_to_brief(all_references)
            structured, struct_meta = self._structure_pmi_table(
                "\n\n".join(combined_texts),
                ref_brief,
                pmi_year,
                pmi_month,
                struct_provider,
                require_us_china=True,
            )
            meta["structure_fallback_final"] = struct_meta
            rows = self._merge_pmi_region_rows(rows, self._pmi_rows_from_payload(structured))

        meta["references"] = all_references
        meta["searches"] = search_log
        meta["pmi_extract"] = (
            "structured"
            if meta.get("structure_fallback") or meta.get("structure_fallback_final")
            else "direct"
        )
        meta["mandatory_filled"] = self._pmi_mandatory_filled(rows)
        meta["rate_limited"] = rate_limited
        meta["deepsearch_calls"] = deepsearch_calls
        meta["missing_fields"] = [
            f"{r}.{f}" for r, f in self._pmi_missing_fields_sorted(rows)
        ]
        # #region agent log
        _debug_log(
            "H5",
            "report_table_research._research_pmi_via_web:result",
            "PMI web research result",
            {
                "struct_provider": struct_provider,
                "mandatory_filled": meta["mandatory_filled"],
                "reference_count": len(all_references),
                "rate_limited": rate_limited,
                "deepsearch_calls": deepsearch_calls,
                "remaining_missing": meta["missing_fields"][:8],
            },
        )
        # #endregion
        return {
            "table_macro_pmi": {
                "pmi_year": pmi_year,
                "pmi_month": pmi_month,
                "sources": self._references_to_urls(all_references),
                "rows": rows,
            },
        }, meta

    def _search_pmi_with_deepsearch(
        self,
        provider: str,
        user_prompt: str,
    ) -> tuple[str, dict[str, Any]]:
        try:
            content, meta = llm.chat_with_meta(
                [
                    {"role": "system", "content": _deep_search_system()},
                    {"role": "user", "content": user_prompt},
                ],
                provider=provider,
                mode="deep_research",
                temperature=0.4,
                json_mode=False,
            )
            return content, meta
        except llm.LLMUnavailable as exc:
            err = str(exc)
            rate_limited = "429" in err
            logger.warning(
                "DeepSearch %s：%s | prompt=%s",
                "限流" if rate_limited else "失败",
                err,
                user_prompt[:120],
            )
            return "", {"references": [], "error": err, "rate_limited": rate_limited}

    def _extract_pmi_rows_from_text(
        self,
        content: str,
        struct_provider: str,
        pmi_year: int,
        pmi_month: int,
        references: list[Any] | None,
        *,
        focus_region: str | None = None,
        focus_field: str | None = None,
    ) -> dict[str, Any]:
        parsed = extract_json_object(content or "")
        if parsed:
            rows = self._pmi_rows_from_payload(parsed)
            if focus_region and focus_field:
                block = rows.get(focus_region)
                val = block.get(focus_field) if isinstance(block, dict) else None
                if val not in (None, ""):
                    return {focus_region: {focus_field: val}}
            elif focus_region:
                block = rows.get(focus_region)
                if isinstance(block, dict) and self._pmi_region_has_core_values(block):
                    return {focus_region: block}
            elif self._pmi_has_values(rows):
                return rows
        ref_brief = self._references_to_brief(references)
        structured, _ = self._structure_pmi_table(
            content or "",
            ref_brief,
            pmi_year,
            pmi_month,
            struct_provider,
            focus_region=focus_region,
            focus_field=focus_field,
            require_us_china=focus_region in PMI_MANDATORY_REGIONS,
        )
        extracted = self._pmi_rows_from_payload(structured)
        if focus_region and focus_field:
            block = extracted.get(focus_region) or {}
            val = block.get(focus_field) if isinstance(block, dict) else None
            if val not in (None, ""):
                return {focus_region: {focus_field: val}}
            return {}
        if focus_region:
            block = extracted.get(focus_region)
            return {focus_region: block} if isinstance(block, dict) else {}
        return extracted

    @staticmethod
    def _pmi_rows_from_payload(parsed: dict[str, Any]) -> dict[str, Any]:
        pmi_block = parsed.get("table_macro_pmi") or parsed
        rows = pmi_block.get("rows") if isinstance(pmi_block, dict) else {}
        return rows if isinstance(rows, dict) else {}

    @staticmethod
    def _merge_pmi_region_rows(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = {k: dict(v) for k, v in (base or {}).items() if isinstance(v, dict)}
        for region, block in (incoming or {}).items():
            if not isinstance(block, dict):
                continue
            target = merged.setdefault(region, {})
            for field, val in block.items():
                if val not in (None, "") and target.get(field) in (None, ""):
                    target[field] = val
        return merged

    @staticmethod
    def _pmi_region_has_core_values(region_data: dict[str, Any]) -> bool:
        if not isinstance(region_data, dict):
            return False
        return any(region_data.get(field) not in (None, "") for field in PMI_CORE_FIELDS)

    @classmethod
    def _pmi_mandatory_filled(cls, region_data: dict[str, Any]) -> bool:
        return all(
            cls._pmi_region_has_core_values((region_data or {}).get(key) or {})
            for key in PMI_MANDATORY_REGIONS
        )

    @classmethod
    def _pmi_missing_mandatory(cls, region_data: dict[str, Any]) -> list[str]:
        return [
            key for key in PMI_MANDATORY_REGIONS
            if not cls._pmi_region_has_core_values((region_data or {}).get(key) or {})
        ]

    @classmethod
    def _pmi_missing_fields(cls, region_data: dict[str, Any]) -> list[tuple[str, str]]:
        missing: list[tuple[str, str]] = []
        for _, region_key in PMI_COLUMNS:
            block = (region_data or {}).get(region_key) or {}
            if not isinstance(block, dict):
                block = {}
            for _, _, field_key in PMI_ROW_SPECS:
                if block.get(field_key) in (None, ""):
                    missing.append((region_key, field_key))
        return missing

    @classmethod
    def _pmi_missing_fields_sorted(cls, region_data: dict[str, Any]) -> list[tuple[str, str]]:
        field_order = {field: idx for idx, (_, _, field) in enumerate(PMI_ROW_SPECS)}

        def _sort_key(item: tuple[str, str]) -> tuple[int, int]:
            region_key, field_key = item
            return (
                PMI_REGION_PRIORITY.get(region_key, 9),
                field_order.get(field_key, 99),
            )

        return sorted(cls._pmi_missing_fields(region_data), key=_sort_key)

    @classmethod
    def _pmi_missing_fields_by_region(cls, region_data: dict[str, Any]) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for region_key, field_key in cls._pmi_missing_fields_sorted(region_data):
            grouped.setdefault(region_key, []).append(field_key)
        return grouped

    @staticmethod
    def _pmi_region_label(region_key: str) -> str:
        for label, key in PMI_COLUMNS:
            if key == region_key:
                return label
        return region_key

    @staticmethod
    def _pmi_field_row_labels(field_key: str) -> tuple[str, str]:
        for label_a, label_b, field in PMI_ROW_SPECS:
            if field == field_key:
                return label_a, label_b
        return "", field_key

    def _structure_pmi_table(
        self,
        research_text: str,
        references_brief: str,
        pmi_year: int,
        pmi_month: int,
        provider: str,
        *,
        focus_region: str | None = None,
        focus_field: str | None = None,
        require_us_china: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        pmi_label = _period_label(pmi_year, pmi_month)
        region_note = ""
        if focus_region and focus_field:
            region_label = ReportTableResearchService._pmi_region_label(focus_region)
            row_a, row_b = ReportTableResearchService._pmi_field_row_labels(focus_field)
            region_note = (
                f"仅提取 {region_label}（{focus_region}）的 {row_a} PMI {row_b}（字段 {focus_field}），"
                "只输出这一项数值。"
            )
        elif focus_region == "us":
            region_note = "仅提取美国（us）数据，优先 S&P Global / ISM 公布的 PMI。"
        elif focus_region == "china":
            region_note = "仅提取中国（china）数据，优先国家统计局公布的制造业 PMI 与非制造业 PMI。"
        elif focus_region == "eurozone":
            region_note = "仅提取欧元区（eurozone）数据，优先 S&P Global / Eurostat 公布的 PMI。"
        mandatory_note = (
            "美国和中国的 PMI 为全网公开数据，必须填写 composite_flash / mfg_final / svc_flash 中至少一项；"
            "欧元区缺失可留 null。"
            if require_us_china else
            "美国和中国的 PMI 为全网公开数据，必须填写；欧元区缺失可留 null。"
        )
        user_prompt = (
            f"请将以下 {pmi_label} PMI 联网查证结果整理为表2-1 JSON。\n"
            f"{region_note}\n"
            f"{mandatory_note}\n"
            "国家/地区键名：us（美国）、eurozone（欧元区）、china（中国）。\n"
            "字段：composite_flash/composite_mom（综合 PMI 初值及环比变化），"
            "mfg_final/mfg_mom（制造业终值及环比），svc_flash/svc_mom（服务业初值及环比）。\n"
            "环比变化单位为百分点；仅填查证摘要或检索片段中出现的数值，缺失项留 null。\n\n"
            f"【查证正文】\n{(research_text or '')[:5000]}\n\n"
            f"【检索摘要】\n{references_brief[:6000]}\n\n"
            "严格只输出 JSON：\n"
            "{\n"
            '  "table_macro_pmi": {\n'
            f'    "pmi_year": {pmi_year}, "pmi_month": {pmi_month},\n'
            '    "sources": [],\n'
            '    "rows": {"us": {...}, "eurozone": {...}, "china": {...}}\n'
            "  }\n"
            "}"
        )
        return llm.chat_json_with_meta(
            "你是数据结构化助手。从查证摘要提取 PMI 数值填入 JSON。"
            "美国、中国的 PMI 为公开数据，摘要中出现时必须填入，不得留空。",
            user_prompt,
            provider=provider,
            mode="normal",
            temperature=0.0,
        )

    @staticmethod
    def _references_to_brief(references: list[Any] | None, *, max_chars: int = 6000) -> str:
        parts: list[str] = []
        total = 0
        for ref in references or []:
            if not isinstance(ref, dict):
                continue
            title = str(ref.get("title") or "").strip()
            summary = str(ref.get("summary") or ref.get("snippet") or "").strip()
            if not title and not summary:
                continue
            block = f"- {title}\n  {summary[:800]}"
            if total + len(block) > max_chars:
                break
            parts.append(block)
            total += len(block)
        return "\n".join(parts)

    def _deep_research_json(
        self,
        provider: str,
        user_prompt: str,
        *,
        table_key: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """与 Agent 一致：DeepSearch 用 json_mode=False 联网，再从正文提取 JSON。"""
        content, meta = llm.chat_with_meta(
            [
                {"role": "system", "content": _deep_search_system()},
                {"role": "user", "content": user_prompt},
            ],
            provider=provider,
            mode="deep_research",
            temperature=0.2,
            json_mode=False,
        )
        parsed = extract_json_object(content)
        if parsed:
            return parsed, meta
        logger.warning("表 %s：DeepSearch 正文无法解析 JSON，尝试结构化二次调用", table_key)
        structured, struct_meta = llm.chat_json_with_meta(
            "你是数据结构化助手。根据查证摘要提取 JSON，禁止编造，缺失字段留 null。",
            f"主题：{table_key}\n\n查证摘要：\n{content[:6000]}\n\n请严格只输出 JSON。",
            provider=provider,
            mode="normal",
            temperature=0.0,
        )
        meta["structure_fallback"] = struct_meta
        return structured, meta

    def _predict_gdp_forecast(
        self,
        review_year: int,
        review_month: int,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """表2-2：由大模型预测 GDP 增速，不联网查证。"""
        provider = _resolve_llm_provider()
        if not provider:
            return None, {"error": "大模型未配置", "predicted": True}
        today = now_beijing_naive().strftime("%Y年%m月%d日")
        review_label = _period_label(review_year, review_month)
        user_prompt = self._build_gdp_predict_prompt(review_year, review_month, today, review_label)
        try:
            with llm.llm_context(
                "report_table_gdp_predict",
                review_year=review_year,
                review_month=review_month,
            ):
                parsed, meta = llm.chat_json_with_meta(
                    "你是宏观经济分析师。请基于当前全球宏观形势，合理预测各经济体 GDP 增速。"
                    "输出须为 JSON，数值保留一位小数，revision 为较年初预测的变化（百分点，带正负号语义）。",
                    user_prompt,
                    provider=provider,
                    mode="normal",
                    temperature=0.3,
                )
            meta["provider"] = provider
            meta["predicted"] = True
            return parsed, meta
        except llm.LLMUnavailable as exc:
            logger.warning("表2-2：大模型预测不可用：%s", exc)
            return None, {"error": str(exc), "predicted": True, "provider": provider}

    @staticmethod
    def _build_pmi_search_prompt(
        pmi_year: int,
        pmi_month: int,
        review_year: int | None = None,
        review_month: int | None = None,
    ) -> str:
        """与 Agent 对话相同的简短检索词，确保 DeepSearch 命中 PMI 来源。"""
        pmi_label = _period_label(pmi_year, pmi_month)
        today = now_beijing_naive().strftime("%Y年%m月%d日")
        guard = _pmi_period_guard(pmi_year, pmi_month, review_year, review_month)
        return f"今天是 {today}。\n全球主要经济体{pmi_label}PMI。{guard}"

    @staticmethod
    def _build_pmi_region_gap_prompt(
        region_key: str,
        missing_fields: list[str],
        pmi_year: int,
        pmi_month: int,
        review_year: int | None = None,
        review_month: int | None = None,
    ) -> str:
        """一国别一次检索，补齐该国所有缺失 PMI 字段。"""
        pmi_label = _period_label(pmi_year, pmi_month)
        today = now_beijing_naive().strftime("%Y年%m月%d日")
        guard = _pmi_period_guard(pmi_year, pmi_month, review_year, review_month)
        region_label = ReportTableResearchService._pmi_region_label(region_key)
        source_hint = {
            "us": "S&P Global、ISM",
            "china": "国家统计局",
            "eurozone": "S&P Global、Eurostat",
        }.get(region_key, "")
        items: list[str] = []
        for field_key in missing_fields:
            row_a, row_b = ReportTableResearchService._pmi_field_row_labels(field_key)
            items.append(f"{row_a}PMI{row_b}")
        return (
            f"今天是 {today}。\n"
            f"请联网查询 {pmi_label}{region_label} 以下 PMI 数据，给出具体数值"
            f"{'及环比变化（百分点）' if any(f.endswith('_mom') for f in missing_fields) else ''}：\n"
            f"{ '、'.join(items) }\n"
            + (f"数据来源：{source_hint}\n" if source_hint else "")
            + guard
        )

    @staticmethod
    def _build_pmi_field_search_prompt(
        region_key: str,
        field_key: str,
        pmi_year: int,
        pmi_month: int,
        review_year: int | None = None,
        review_month: int | None = None,
    ) -> str:
        """针对单个缺失单元格生成专项检索词。"""
        pmi_label = _period_label(pmi_year, pmi_month)
        today = now_beijing_naive().strftime("%Y年%m月%d日")
        guard = _pmi_period_guard(pmi_year, pmi_month, review_year, review_month)
        region_label = ReportTableResearchService._pmi_region_label(region_key)
        row_a, row_b = ReportTableResearchService._pmi_field_row_labels(field_key)
        source_hint = {
            "us": "S&P Global、ISM",
            "china": "国家统计局",
            "eurozone": "S&P Global、Eurostat",
        }.get(region_key, "")
        if field_key.endswith("_mom"):
            metric = f"{row_a}PMI{row_b}"
        elif field_key.endswith("_flash"):
            metric = f"{row_a}PMI{row_b}"
        else:
            metric = f"{row_a}PMI{row_b}"
        return (
            f"今天是 {today}。\n"
            f"{pmi_label}{region_label}{metric}"
            + (f"（{source_hint}）" if source_hint else "")
            + f"。{guard}"
        )

    @staticmethod
    def _build_pmi_region_search_prompt(
        region_key: str,
        pmi_year: int,
        pmi_month: int,
        review_year: int | None = None,
        review_month: int | None = None,
    ) -> str:
        pmi_label = _period_label(pmi_year, pmi_month)
        today = now_beijing_naive().strftime("%Y年%m月%d日")
        guard = _pmi_period_guard(pmi_year, pmi_month, review_year, review_month)
        if region_key == "china":
            return (
                f"今天是 {today}。\n"
                f"{pmi_label}中国官方制造业PMI和非制造业PMI（国家统计局）。{guard}"
            )
        if region_key == "us":
            return (
                f"今天是 {today}。\n"
                f"{pmi_label}美国标普全球PMI和ISM制造业PMI（综合、制造、服务业）。{guard}"
            )
        return f"今天是 {today}。\n全球主要经济体{pmi_label}PMI。{guard}"

    @staticmethod
    def _build_pmi_prompt(
        pmi_year: int,
        pmi_month: int,
        review_year: int | None = None,
        review_month: int | None = None,
    ) -> str:
        """构造 DeepSearch 使用的详细检索 prompt。"""
        pmi_label = _period_label(pmi_year, pmi_month)
        guard = _pmi_period_guard(pmi_year, pmi_month, review_year, review_month)
        return (
            f"请联网查询全球主要经济体 {pmi_label} PMI（美国、欧元区、中国）。\n"
            f"{guard}\n"
            "需要：综合/制造业/服务业 PMI 初值、终值及环比变化（百分点）。\n"
            "来源：S&P Global、Eurostat、国家统计局。\n\n"
            "严格只输出 JSON：\n"
            "{\n"
            '  "table_macro_pmi": {\n'
            f'    "pmi_year": {pmi_year}, "pmi_month": {pmi_month},\n'
            '    "rows": {"us": {...}, "eurozone": {...}, "china": {...}}\n'
            "  }\n"
            "}"
        )

    @staticmethod
    def _build_gdp_predict_prompt(
        review_year: int,
        review_month: int,
        today: str,
        review_label: str,
    ) -> str:
        if review_month == 12:
            outlook_label = f"{review_year + 1}年1月"
        else:
            outlook_label = f"{review_year}年{review_month + 1}月"
        return (
            f"今天是 {today}。请为《国际油价月报》（回顾月 {review_label}）"
            f"填写表2-2「全球主要经济体GDP增速预测，%」。\n"
            f"本表按回顾月 {review_label} 语境预测，写入 snapshot 键为回顾月 {review_label}，"
            f"对应展望月报 {outlook_label}。\n"
            f"预测目标年度：{review_year}年。\n"
            f"国家/地区：{', '.join(GDP_REGIONS)}。\n\n"
            "请结合当前全球经济形势、货币政策、地缘与能源市场等因素，"
            "给出你对各国家/地区 GDP 增速的预测值，"
            "以及相较年初（1月）预测的调整幅度（百分点，正数为上调、负数为下调）。\n"
            "这是预测表，允许基于专业判断给出合理数值，不必引用具体网页来源。\n\n"
            "严格只输出 JSON，不要 Markdown：\n"
            "{\n"
            '  "table_demand_forecast": {\n'
            '    "rows": [\n'
            f'      {{"region": "全球", "forecast_2026": 3.1, "revision_vs_jan2026": -0.2}}\n'
            "    ]\n"
            "  }\n"
            "}"
        )

    @staticmethod
    def _references_to_urls(references: list[Any] | None) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for ref in references or []:
            candidate = ref if isinstance(ref, str) else (ref.get("url") if isinstance(ref, dict) else None)
            if candidate and str(candidate).startswith("http") and candidate not in seen:
                seen.add(str(candidate))
                urls.append(str(candidate))
        return urls

    def _apply_pmi_gdp_payload(
        self,
        out: dict[str, Any],
        parsed: dict[str, Any],
        ref_urls: list[str],
        pmi_year: int,
        pmi_month: int,
        fetch_pmi: bool,
        fetch_gdp: bool,
        *,
        gdp_predicted: bool = False,
    ) -> None:
        pmi_payload = parsed.get("table_macro_pmi") or {}
        gdp_payload = parsed.get("table_demand_forecast") or {}
        pmi_sources = [
            u for u in (pmi_payload.get("sources") or []) if isinstance(u, str) and u.startswith("http")
        ]
        gdp_sources = [
            u for u in (gdp_payload.get("sources") or []) if isinstance(u, str) and u.startswith("http")
        ]
        if ref_urls:
            pmi_sources = list(dict.fromkeys(pmi_sources + ref_urls))
            gdp_sources = list(dict.fromkeys(gdp_sources + ref_urls))

        region_data = pmi_payload.get("rows") or {}
        if (
            fetch_pmi
            and isinstance(region_data, dict)
            and self._pmi_has_values(region_data)
            and self._pmi_mandatory_filled(region_data)
        ):
            out["pmi_table"] = {
                **default_pmi_table(pmi_year, pmi_month),
                "rows": build_pmi_rows(region_data),
                "source_urls": pmi_sources,
            }
            out["pmi_meta"] = {
                "sources": pmi_sources,
                "verified": bool(pmi_sources),
                "mandatory_filled": True,
                "missing_fields": [
                    f"{r}.{f}" for r, f in self._pmi_missing_fields_sorted(region_data)
                ],
            }
        elif fetch_pmi and isinstance(region_data, dict) and self._pmi_has_values(region_data):
            out["pmi_meta"] = {
                "sources": pmi_sources,
                "verified": bool(pmi_sources),
                "mandatory_filled": False,
                "missing_regions": self._pmi_missing_mandatory(region_data),
            }

        gdp_rows = gdp_payload.get("rows") or []
        if fetch_gdp and isinstance(gdp_rows, list) and self._gdp_has_values(gdp_rows):
            gdp_table = {
                **default_gdp_table(),
                "rows": build_gdp_rows(gdp_rows),
                "source_urls": gdp_sources,
            }
            if gdp_predicted:
                gdp_table["source"] = "大模型预测"
            out["gdp_table"] = gdp_table
            out["gdp_meta"] = {
                "sources": gdp_sources,
                "verified": bool(gdp_sources) and not gdp_predicted,
                "predicted": gdp_predicted,
            }

    @staticmethod
    def _pmi_has_values(region_data: dict[str, Any]) -> bool:
        for _, key in PMI_COLUMNS:
            block = region_data.get(key)
            if not isinstance(block, dict):
                continue
            if any(block.get(field) not in (None, "") for _, _, field in PMI_ROW_SPECS):
                return True
        return False

    @staticmethod
    def _gdp_has_values(rows: list[Any]) -> bool:
        for item in rows:
            if not isinstance(item, dict):
                continue
            if item.get("forecast_2026") not in (None, "") or item.get("revision_vs_jan2026") not in (None, ""):
                return True
        return False
