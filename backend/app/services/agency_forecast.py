"""咨询机构油价预测手工录入服务（兼容层，底层写入 report_table_snapshots）。"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.timezone import format_beijing_iso, now_beijing_naive
from app.models.agency_forecast import AgencyForecastManual
from app.models.user import User
from app.services.report_table_data import ReportTableDataService, review_from_outlook
from app.templates.monthly_report import DEFAULT_TABLES

AGENCY_TABLE_TEMPLATE = DEFAULT_TABLES["table_agency"]


class AgencyForecastService:
    def __init__(self, db: Session):
        self.db = db
        self.table_data = ReportTableDataService(db)

    @staticmethod
    def default_rows() -> list[list[str]]:
        return [list(row) for row in AGENCY_TABLE_TEMPLATE["rows"]]

    def get(self, year: int, month: int) -> dict[str, Any] | None:
        """按展望月读取（兼容旧 API）。"""
        ry, rm = review_from_outlook(year, month)
        snap = self.table_data.get_table(ry, rm, "table_agency")
        if snap:
            return {
                "year": year,
                "month": month,
                "rows": snap["rows"],
                "headers": snap["headers"],
                "title": snap["title"],
                "updated_at": snap.get("updated_at"),
            }
        row = (
            self.db.query(AgencyForecastManual)
            .filter(AgencyForecastManual.year == year, AgencyForecastManual.month == month)
            .first()
        )
        if not row:
            return None
        return self._legacy_to_dict(row)

    def list_all(self) -> list[dict[str, Any]]:
        periods = self.table_data.list_periods()
        result: list[dict[str, Any]] = []
        for p in periods:
            oy, om = p["review_year"], p["review_month"]
            from app.services.report_table_data import outlook_from_review
            outlook_y, outlook_m = outlook_from_review(int(oy), int(om))
            snap = self.table_data.get_table(int(oy), int(om), "table_agency")
            if snap:
                result.append({
                    "year": outlook_y,
                    "month": outlook_m,
                    "rows": snap["rows"],
                    "headers": snap["headers"],
                    "title": snap["title"],
                    "updated_at": snap.get("updated_at"),
                })
        if result:
            return result
        rows = (
            self.db.query(AgencyForecastManual)
            .order_by(AgencyForecastManual.year.desc(), AgencyForecastManual.month.desc())
            .all()
        )
        return [self._legacy_to_dict(r) for r in rows]

    def upsert(
        self,
        year: int,
        month: int,
        rows: list[list[str]],
        user: User | None = None,
    ) -> dict[str, Any]:
        ry, rm = review_from_outlook(year, month)
        snap = self.table_data.upsert_manual(ry, rm, "table_agency", rows, user)
        return {
            "year": year,
            "month": month,
            "rows": snap["rows"],
            "headers": snap["headers"],
            "title": snap["title"],
            "updated_at": snap.get("updated_at"),
        }

    def table_for_report(self, year: int, month: int) -> dict[str, Any] | None:
        """按展望月返回表3-2。"""
        ry, rm = review_from_outlook(year, month)
        snap = self.table_data.get_table(ry, rm, "table_agency")
        if not snap:
            return None
        return {
            "title": snap["title"],
            "source": snap["source"],
            "headers": snap["headers"],
            "rows": snap["rows"],
        }

    @staticmethod
    def _legacy_to_dict(row: AgencyForecastManual) -> dict[str, Any]:
        try:
            rows = json.loads(row.rows_json or "[]")
        except json.JSONDecodeError:
            rows = []
        return {
            "year": row.year,
            "month": row.month,
            "rows": rows,
            "headers": AGENCY_TABLE_TEMPLATE["headers"],
            "title": AGENCY_TABLE_TEMPLATE["title"],
            "updated_at": format_beijing_iso(row.updated_at),
        }
