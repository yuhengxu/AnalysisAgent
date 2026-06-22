"""月报表格快照：派生同步、联网获取、手工修正、月报加载。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timezone import format_beijing_iso, now_beijing_naive
from app.models.report_table_snapshot import ReportTableSnapshot
from app.models.user import User
from app.services.analytics import AnalyticsService
from app.services.forecast import ForecastService
from app.services.report_table_research import (
    ReportTableResearchService,
    default_gdp_table,
    default_pmi_table,
)
from app.templates.monthly_report import DEFAULT_TABLES

logger = logging.getLogger("service.report_table_data")

DERIVED_TABLE_KEYS = ("table_price_change", "table_supply_balance", "table_scenario")
WEB_TABLE_KEYS = ("table_macro_pmi", "table_demand_forecast", "table_agency")
SYSTEM_TABLE_KEYS = DERIVED_TABLE_KEYS + WEB_TABLE_KEYS

_TABLE_CATEGORY: dict[str, str] = {k: "derived" for k in DERIVED_TABLE_KEYS}
_TABLE_CATEGORY.update({k: "web" for k in WEB_TABLE_KEYS})

_SHEET_PERIOD_RE = re.compile(r"^(\d{4})年(\d{1,2})月$")
_BALANCE_SHEET_RE = re.compile(r"^(\d{4})(\d{2})$")


def outlook_from_review(review_year: int, review_month: int) -> tuple[int, int]:
    """回顾月 → 展望月（生成月报期别）。例：5 月回顾 → 6 月展望。"""
    if review_month == 12:
        return review_year + 1, 1
    return review_year, review_month + 1


def review_from_outlook(outlook_year: int, outlook_month: int) -> tuple[int, int]:
    """展望月 → 回顾月。例：6 月展望 → 5 月回顾；1 月展望 → 上年 12 月回顾。"""
    if outlook_month == 1:
        return outlook_year - 1, 12
    return outlook_year, outlook_month - 1


def normalize_report_periods(
    review_year: int,
    review_month: int,
    outlook_year: int,
    outlook_month: int,
    *,
    primary: str = "outlook",
) -> tuple[tuple[int, int], tuple[int, int]]:
    """确保回顾月与展望月成对（展望 = 回顾 + 1 月，含跨年）。"""
    if primary == "review":
        oy, om = outlook_from_review(review_year, review_month)
        return (review_year, review_month), (oy, om)
    ry, rm = review_from_outlook(outlook_year, outlook_month)
    return (ry, rm), (outlook_year, outlook_month)


class ReviewPeriodMismatch(ValueError):
    """数据中心请求的回顾月与展望月不成对。"""


def pmi_reference_month(review_year: int, review_month: int) -> tuple[int, int]:
    """表2-1 PMI 查证期别：与回顾月一致。"""
    return review_year, review_month


def resolve_data_center_periods(
    review_year: int,
    review_month: int,
    *,
    outlook_year: int | None = None,
    outlook_month: int | None = None,
) -> dict[str, Any]:
    """解析数据中心操作的期别，可选校验展望月与回顾月是否成对。"""
    if not (1 <= review_month <= 12):
        raise ValueError("review_month 须在 1–12")
    ry, rm = review_year, review_month
    oy, om = outlook_from_review(ry, rm)
    if outlook_year is not None and outlook_month is not None:
        expected = review_from_outlook(int(outlook_year), int(outlook_month))
        if (ry, rm) != expected:
            raise ReviewPeriodMismatch(
                f"回顾月 {ry}年{rm}月 与展望月 {int(outlook_year)}年{int(outlook_month)}月不匹配；"
                f"回顾 {ry}年{rm}月 对应展望 {oy}年{om}月，"
                f"展望 {int(outlook_year)}年{int(outlook_month)}月 对应回顾 "
                f"{expected[0]}年{expected[1]}月"
            )
    py, pm = pmi_reference_month(ry, rm)
    return {
        "review_year": ry,
        "review_month": rm,
        "outlook_year": oy,
        "outlook_month": om,
        "pmi_year": py,
        "pmi_month": pm,
        "review_label": f"{ry}年{rm}月",
        "outlook_label": f"{oy}年{om}月",
        "pmi_label": f"{py}年{pm}月",
    }


def resolve_gdp_llm_predict_enabled(enable: bool | None = None) -> bool:
    """表2-2 是否启用大模型预测（请求参数优先，否则读配置，默认关）。"""
    if enable is not None:
        return bool(enable)
    return bool(settings.report_table_gdp_llm_predict)


def web_fetch_options() -> dict[str, Any]:
    """数据中心联网获取可选项（供前端展示开关默认值）。"""
    return {
        "gdp_llm_predict_default": bool(settings.report_table_gdp_llm_predict),
        "gdp_manual_hint": "表2-2 默认手工填写；勾选「大模型预测表2-2」后才会在深度研究中调用",
    }


def _quarter_label(month: int) -> str:
    return ("一", "二", "三", "四")[(month - 1) // 3]


def _has_row_values(rows: list[list[str]]) -> bool:
    for row in rows:
        for cell in row[1:]:
            if str(cell or "").strip():
                return True
    return False


def build_table_scenario_rows(
    forecast_model: dict[str, Any] | None,
    outlook_year: int,
    outlook_month: int,
) -> list[list[str]] | None:
    if not forecast_model:
        return None
    by_name = {
        s.get("scenario"): s
        for s in forecast_model.get("scenarios", [])
        if isinstance(s, dict)
    }
    baseline = by_name.get("baseline") or {}
    optimistic = by_name.get("optimistic") or {}
    pessimistic = by_name.get("pessimistic") or {}

    def cell(scenario: dict[str, Any], *keys: str) -> str:
        for key in keys:
            val = scenario.get(key)
            if val is not None and val != "":
                text = f"{round(float(val), 2):.2f}".rstrip("0").rstrip(".")
                return text
        return ""

    q = _quarter_label(outlook_month)
    return [
        [
            f"{outlook_year}年{outlook_month}月",
            cell(baseline, "point"),
            cell(pessimistic, "low", "point"),
            cell(optimistic, "high", "point"),
        ],
        [
            f"{outlook_year}年{q}季度",
            cell(baseline, "point"),
            cell(pessimistic, "low", "point"),
            cell(optimistic, "high", "point"),
        ],
        [
            f"{outlook_year}年全年",
            cell(baseline, "point"),
            cell(pessimistic, "low", "point"),
            cell(optimistic, "high", "point"),
        ],
    ]


class ReportTableDataService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics = AnalyticsService(db)
        self.forecast = ForecastService(db)
        self.research = ReportTableResearchService(db)

    @staticmethod
    def table_schema() -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for key in SYSTEM_TABLE_KEYS:
            tpl = DEFAULT_TABLES[key]
            items.append({
                "table_key": key,
                "source_category": _TABLE_CATEGORY[key],
                "title": tpl["title"],
                "source": tpl["source"],
                "headers": tpl["headers"],
                "default_rows": [list(r) for r in tpl["rows"]],
            })
        return items

    def list_periods(self) -> list[dict[str, Any]]:
        rows = (
            self.db.query(
                ReportTableSnapshot.review_year,
                ReportTableSnapshot.review_month,
            )
            .distinct()
            .order_by(
                ReportTableSnapshot.review_year.desc(),
                ReportTableSnapshot.review_month.desc(),
            )
            .all()
        )
        result: list[dict[str, Any]] = []
        for ry, rm in rows:
            status = self._period_status(int(ry), int(rm))
            result.append({"review_year": ry, "review_month": rm, **status})
        return result

    def list_tables(self, review_year: int, review_month: int) -> dict[str, Any]:
        snapshots = self._load_map(review_year, review_month)
        pmi_y, pmi_m = self.research.pmi_reference_month(review_year, review_month)
        oy, om = outlook_from_review(review_year, review_month)
        tables: list[dict[str, Any]] = []
        for key in SYSTEM_TABLE_KEYS:
            snap = snapshots.get(key)
            tpl = self._default_table_dict(key, review_year, review_month, pmi_y, pmi_m, oy, om)
            tables.append({
                "table_key": key,
                "source_category": _TABLE_CATEGORY[key],
                "exists": snap is not None,
                "is_manual_override": bool(snap.is_manual_override) if snap else False,
                "updated_at": format_beijing_iso(snap.updated_at) if snap else None,
                "source_urls": self._parse_json(snap.source_urls_json, []) if snap else [],
                "has_values": _has_row_values(self._parse_json(snap.rows_json, [])) if snap else False,
                "table": self._snapshot_to_dict(snap) if snap else tpl,
            })
        status = self._period_status(review_year, review_month, snapshots)
        missing_tables = [t["table_key"] for t in tables if not t["has_values"]]
        return {
            "review_year": review_year,
            "review_month": review_month,
            "outlook_year": oy,
            "outlook_month": om,
            "pmi_year": pmi_y,
            "pmi_month": pmi_m,
            **status,
            "missing_tables": missing_tables,
            "tables": tables,
        }

    def get_table(self, review_year: int, review_month: int, table_key: str) -> dict[str, Any] | None:
        snap = self._get_snapshot(review_year, review_month, table_key)
        if not snap:
            return None
        return self._snapshot_to_dict(snap)

    def sync_derived(
        self,
        review_year: int,
        review_month: int,
        outlook_year: int | None = None,
        outlook_month: int | None = None,
        *,
        table_keys: list[str] | None = None,
        user: User | None = None,
    ) -> dict[str, Any]:
        periods = resolve_data_center_periods(
            review_year,
            review_month,
            outlook_year=outlook_year,
            outlook_month=outlook_month,
        )
        ry, rm = periods["review_year"], periods["review_month"]
        oy, om = periods["outlook_year"], periods["outlook_month"]
        keys = [k for k in (table_keys or DERIVED_TABLE_KEYS) if k in DERIVED_TABLE_KEYS]
        synced: list[str] = []
        errors: dict[str, str] = {}
        for key in keys:
            try:
                tbl = self._compute_derived_table(key, ry, rm, oy, om)
                if tbl:
                    self._save_snapshot(
                        ry, rm, key, "derived", tbl,
                        source_urls=[], is_manual_override=False, user=user,
                    )
                    synced.append(key)
                else:
                    errors[key] = "无可用源数据"
            except Exception as exc:  # noqa: BLE001
                errors[key] = str(exc)
        return {"synced": synced, "errors": errors, "periods": periods}

    @staticmethod
    def periods_from_import(category: str, import_result: dict[str, Any]) -> list[tuple[int, int]]:
        periods: set[tuple[int, int]] = set()
        sheets = import_result.get("imported_sheets") or []
        if category == "price":
            for name in sheets:
                match = _SHEET_PERIOD_RE.match(str(name).strip())
                if match:
                    periods.add((int(match.group(1)), int(match.group(2))))
        elif category == "balance":
            for name in sheets:
                match = _BALANCE_SHEET_RE.fullmatch(str(name).strip())
                if match:
                    periods.add((int(match.group(1)), int(match.group(2))))
        return sorted(periods)

    def sync_derived_after_import(
        self,
        category: str,
        import_result: dict[str, Any],
        *,
        user: User | None = None,
    ) -> dict[str, Any]:
        if category not in {"price", "balance"}:
            return {"periods": [], "synced": {}}
        table_keys = ["table_price_change"] if category == "price" else ["table_supply_balance"]
        periods = self.periods_from_import(category, import_result)
        synced: dict[str, dict[str, Any]] = {}
        for ry, rm in periods:
            result = self.sync_derived(ry, rm, table_keys=table_keys, user=user)
            synced[f"{ry:04d}-{rm:02d}"] = result
        return {
            "periods": [{"review_year": y, "review_month": m} for y, m in periods],
            "synced": synced,
        }

    def fetch_web(
        self,
        review_year: int,
        review_month: int,
        *,
        outlook_year: int | None = None,
        outlook_month: int | None = None,
        table_keys: list[str] | None = None,
        enable_gdp_llm_predict: bool | None = None,
        user: User | None = None,
    ) -> dict[str, Any]:
        periods = resolve_data_center_periods(
            review_year,
            review_month,
            outlook_year=outlook_year,
            outlook_month=outlook_month,
        )
        ry, rm = periods["review_year"], periods["review_month"]
        pmi_y, pmi_m = periods["pmi_year"], periods["pmi_month"]
        gdp_llm_enabled = resolve_gdp_llm_predict_enabled(enable_gdp_llm_predict)
        keys = [k for k in (table_keys or WEB_TABLE_KEYS) if k in WEB_TABLE_KEYS]
        fetched: list[str] = []
        skipped: list[str] = []
        skip_notes: dict[str, str] = {}
        errors: dict[str, str] = {}

        if "table_demand_forecast" in keys and not gdp_llm_enabled:
            skipped.append("table_demand_forecast")
            skip_notes["table_demand_forecast"] = "表2-2 未启用大模型预测，请手工填写"
            keys = [k for k in keys if k != "table_demand_forecast"]

        pmi_gdp_keys = [k for k in keys if k in ("table_macro_pmi", "table_demand_forecast")]
        if pmi_gdp_keys:
            from app.core import llm

            can_research = llm.deep_search_available() or llm.is_enabled()
            if not can_research:
                for k in pmi_gdp_keys:
                    errors[k] = "DeepSearch/大模型均未配置"
            else:
                need_pmi = "table_macro_pmi" in pmi_gdp_keys
                need_gdp = "table_demand_forecast" in pmi_gdp_keys and gdp_llm_enabled
                if need_pmi and self._is_manual_locked(ry, rm, "table_macro_pmi"):
                    skipped.append("table_macro_pmi")
                    need_pmi = False
                if need_gdp and self._is_manual_locked(ry, rm, "table_demand_forecast"):
                    skipped.append("table_demand_forecast")
                    need_gdp = False
                if need_pmi or need_gdp:
                    research = self.research.fetch_pmi_gdp_tables(
                        pmi_y, pmi_m, ry, rm,
                        fetch_pmi=need_pmi, fetch_gdp=need_gdp,
                    )
                    if need_pmi and research.get("pmi_table"):
                        tbl = research["pmi_table"]
                        self._save_snapshot(
                            ry, rm, "table_macro_pmi", "web", tbl,
                            source_urls=tbl.get("source_urls", []),
                            is_manual_override=False, user=user,
                        )
                        fetched.append("table_macro_pmi")
                    elif need_pmi:
                        pmi_meta = (research.get("deep_research") or {}).get("pmi") or {}
                        if pmi_meta.get("rate_limited"):
                            errors["table_macro_pmi"] = (
                                "DeepSearch 被限流(429)，请等待 2–5 分钟后重试"
                            )
                        else:
                            errors["table_macro_pmi"] = "联网未返回美国/中国 PMI 数据（必填）"
                    if need_gdp and research.get("gdp_table"):
                        tbl = research["gdp_table"]
                        self._save_snapshot(
                            ry, rm, "table_demand_forecast", "web", tbl,
                            source_urls=tbl.get("source_urls", []),
                            is_manual_override=False, user=user,
                        )
                        fetched.append("table_demand_forecast")
                    elif need_gdp:
                        errors["table_demand_forecast"] = "大模型未返回 GDP 预测"

        return {
            "fetched": fetched,
            "skipped": skipped,
            "skip_notes": skip_notes,
            "errors": errors,
            "periods": periods,
            "gdp_llm_predict_enabled": gdp_llm_enabled,
        }

    def upsert_manual(
        self,
        review_year: int,
        review_month: int,
        table_key: str,
        rows: list[list[str]],
        user: User | None = None,
    ) -> dict[str, Any]:
        if table_key not in WEB_TABLE_KEYS:
            raise ValueError(f"{table_key} 不允许手工编辑")
        pmi_y, pmi_m = self.research.pmi_reference_month(review_year, review_month)
        oy, om = outlook_from_review(review_year, review_month)
        base = self._default_table_dict(table_key, review_year, review_month, pmi_y, pmi_m, oy, om)
        normalized = self._normalize_rows(base["rows"], rows)
        base["rows"] = normalized
        snap = self._save_snapshot(
            review_year, review_month, table_key, "web", base,
            source_urls=self._existing_urls(review_year, review_month, table_key),
            is_manual_override=True, user=user,
        )
        return self._snapshot_to_dict(snap)

    def load_for_report(
        self,
        review_year: int,
        review_month: int,
        outlook_year: int,
        outlook_month: int,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        (review_year, review_month), (outlook_year, outlook_month) = normalize_report_periods(
            review_year,
            review_month,
            outlook_year,
            outlook_month,
            primary="outlook",
        )
        snapshots = self._load_map(review_year, review_month)
        pmi_y, pmi_m = self.research.pmi_reference_month(review_year, review_month)
        tables: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        meta: dict[str, Any] = {"review_period": f"{review_year}年{review_month}月"}

        for key in SYSTEM_TABLE_KEYS:
            snap = snapshots.get(key)
            if snap:
                tables[key] = self._snapshot_to_dict(snap)
            else:
                missing.append(key)
                tables[key] = self._default_table_dict(
                    key, review_year, review_month, pmi_y, pmi_m, outlook_year, outlook_month,
                )

        meta["missing_tables"] = missing
        meta["filled_count"] = len(SYSTEM_TABLE_KEYS) - len(missing)
        return tables, meta

    def migrate_agency_forecasts(self) -> int:
        from app.models.agency_forecast import AgencyForecastManual

        rows = self.db.query(AgencyForecastManual).all()
        count = 0
        tpl = DEFAULT_TABLES["table_agency"]
        for row in rows:
            ry, rm = review_from_outlook(row.year, row.month)
            try:
                parsed_rows = json.loads(row.rows_json or "[]")
            except json.JSONDecodeError:
                continue
            existing = self._get_snapshot(ry, rm, "table_agency")
            if existing:
                continue
            tbl = {
                "title": tpl["title"],
                "source": tpl["source"],
                "headers": tpl["headers"],
                "rows": parsed_rows,
            }
            self._save_snapshot(
                ry, rm, "table_agency", "web", tbl,
                source_urls=[], is_manual_override=True,
                user_id=row.updated_by,
            )
            count += 1
        return count

    def _compute_derived_table(
        self,
        table_key: str,
        review_year: int,
        review_month: int,
        outlook_year: int,
        outlook_month: int,
    ) -> dict[str, Any] | None:
        if table_key == "table_price_change":
            brent = self.analytics.calc_monthly_stats("Brent", review_year, review_month)
            wti = self.analytics.calc_monthly_stats("WTI", review_year, review_month)
            if brent.get("count", 0) == 0 and wti.get("count", 0) == 0:
                return None
            tpl = dict(DEFAULT_TABLES["table_price_change"])
            tpl["rows"] = self.analytics.build_table_price_change_rows(brent, wti, review_month)
            return tpl
        if table_key == "table_supply_balance":
            return self.research.build_supply_balance_table(review_year, review_month)
        if table_key == "table_scenario":
            model = self.forecast.get_forecast_for_period("Brent", outlook_year, outlook_month)
            rows = build_table_scenario_rows(model, outlook_year, outlook_month)
            if not rows:
                return None
            tpl = dict(DEFAULT_TABLES["table_scenario"])
            tpl["rows"] = rows
            return tpl
        return None

    def _default_table_dict(
        self,
        table_key: str,
        review_year: int,
        review_month: int,
        pmi_y: int,
        pmi_m: int,
        outlook_year: int,
        outlook_month: int,
    ) -> dict[str, Any]:
        if table_key == "table_macro_pmi":
            return default_pmi_table(pmi_y, pmi_m)
        if table_key == "table_demand_forecast":
            tbl = default_gdp_table()
            tbl["headers"] = ["国家/地区", str(review_year), "较2026.1预测变化"]
            return tbl
        if table_key == "table_supply_balance":
            from app.services.report_table_research import default_supply_table
            return default_supply_table(review_year)
        tpl = json.loads(json.dumps(DEFAULT_TABLES[table_key], ensure_ascii=False))
        if table_key == "table_scenario":
            q = _quarter_label(outlook_month)
            tpl["rows"] = [
                [f"{outlook_year}年{outlook_month}月", "", "", ""],
                [f"{outlook_year}年{q}季度", "", "", ""],
                [f"{outlook_year}年全年", "", "", ""],
            ]
        return tpl

    def _period_status(
        self,
        review_year: int,
        review_month: int,
        snapshots: dict[str, ReportTableSnapshot] | None = None,
    ) -> dict[str, Any]:
        snapshots = snapshots or self._load_map(review_year, review_month)
        filled = sum(
            1 for key in SYSTEM_TABLE_KEYS
            if snapshots.get(key) and _has_row_values(self._parse_json(snapshots[key].rows_json, []))
        )
        return {
            "filled_count": filled,
            "total_count": len(SYSTEM_TABLE_KEYS),
            "derived_filled": sum(
                1 for k in DERIVED_TABLE_KEYS
                if snapshots.get(k) and _has_row_values(self._parse_json(snapshots[k].rows_json, []))
            ),
            "web_filled": sum(
                1 for k in WEB_TABLE_KEYS
                if snapshots.get(k) and _has_row_values(self._parse_json(snapshots[k].rows_json, []))
            ),
        }

    def _is_manual_locked(self, review_year: int, review_month: int, table_key: str) -> bool:
        snap = self._get_snapshot(review_year, review_month, table_key)
        return bool(snap and snap.is_manual_override)

    def _existing_urls(self, review_year: int, review_month: int, table_key: str) -> list[str]:
        snap = self._get_snapshot(review_year, review_month, table_key)
        if not snap:
            return []
        return self._parse_json(snap.source_urls_json, [])

    def _load_map(self, review_year: int, review_month: int) -> dict[str, ReportTableSnapshot]:
        rows = (
            self.db.query(ReportTableSnapshot)
            .filter(
                ReportTableSnapshot.review_year == review_year,
                ReportTableSnapshot.review_month == review_month,
            )
            .all()
        )
        return {r.table_key: r for r in rows}

    def _get_snapshot(
        self, review_year: int, review_month: int, table_key: str,
    ) -> ReportTableSnapshot | None:
        return (
            self.db.query(ReportTableSnapshot)
            .filter(
                ReportTableSnapshot.review_year == review_year,
                ReportTableSnapshot.review_month == review_month,
                ReportTableSnapshot.table_key == table_key,
            )
            .first()
        )

    def _save_snapshot(
        self,
        review_year: int,
        review_month: int,
        table_key: str,
        source_category: str,
        table: dict[str, Any],
        *,
        source_urls: list[str],
        is_manual_override: bool,
        user: User | None = None,
        user_id: int | None = None,
    ) -> ReportTableSnapshot:
        row = self._get_snapshot(review_year, review_month, table_key)
        now = now_beijing_naive()
        payload = {
            "title": str(table.get("title", "")),
            "source": str(table.get("source", "")),
            "headers_json": json.dumps(table.get("headers", []), ensure_ascii=False),
            "rows_json": json.dumps(table.get("rows", []), ensure_ascii=False),
            "source_urls_json": json.dumps(source_urls or table.get("source_urls", []), ensure_ascii=False),
            "is_manual_override": is_manual_override,
            "computed_at": now,
            "updated_at": now,
        }
        uid = user.id if user else user_id
        if row:
            for k, v in payload.items():
                setattr(row, k, v)
            if uid is not None:
                row.updated_by = uid
        else:
            row = ReportTableSnapshot(
                review_year=review_year,
                review_month=review_month,
                table_key=table_key,
                source_category=source_category,
                updated_by=uid,
                **payload,
            )
            self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def _snapshot_to_dict(self, snap: ReportTableSnapshot) -> dict[str, Any]:
        return {
            "title": snap.title,
            "source": snap.source,
            "headers": self._parse_json(snap.headers_json, []),
            "rows": self._parse_json(snap.rows_json, []),
            "source_urls": self._parse_json(snap.source_urls_json, []),
            "table_key": snap.table_key,
            "source_category": snap.source_category,
            "is_manual_override": snap.is_manual_override,
            "updated_at": format_beijing_iso(snap.updated_at),
        }

    @staticmethod
    def _parse_json(raw: str | None, default: Any) -> Any:
        try:
            return json.loads(raw or "")
        except json.JSONDecodeError:
            return default

    @staticmethod
    def _normalize_rows(template_rows: list[list[str]], rows: list[list[str]]) -> list[list[str]]:
        result: list[list[str]] = []
        for idx, template in enumerate(template_rows):
            if idx < len(rows) and isinstance(rows[idx], list):
                row = [str(c) for c in rows[idx]]
                while len(row) < len(template):
                    row.append("")
                result.append(row[: len(template)])
            else:
                result.append(list(template))
        return result
