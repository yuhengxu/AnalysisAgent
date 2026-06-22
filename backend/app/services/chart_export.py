"""报告图表 PNG 导出。"""
from __future__ import annotations

import base64
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.analytics import AnalyticsService
from app.services.chart_theme import render_report_chart
from app.templates.sample_contracts import REPORT_CHART_ANCHORS

logger = logging.getLogger(__name__)

MIN_CHART_BYTES = 1024

EMPTY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


class ChartExportService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics = AnalyticsService(db)

    def generate_report_charts(
        self,
        report_id: int,
        content: dict[str, Any],
        *,
        review_year: int | None = None,
        review_month: int | None = None,
    ) -> dict[str, str]:
        ry, rm = review_year, review_month
        if ry is None or rm is None:
            ry, rm = self._review_period_from_content(content)
        # 作图专用：取回顾月往前 12 个自然日（不影响正文/表格统计）
        start, end = self._chart_plot_date_range(ry, rm)
        charts: dict[str, str] = {}
        for anchor in REPORT_CHART_ANCHORS:
            title = self.format_chart_title(
                anchor, review_year=ry, review_month=rm, content=content
            )
            config = self._chart_config(anchor, content, start, end, title)
            if not config.get("series"):
                continue
            out = settings.charts_dir / f"report_{report_id}_{anchor['id']}.png"
            if self._render_chart(config, out):
                charts[anchor["id"]] = str(out)
            else:
                logger.warning("图表 %s 渲染失败或文件过小，已跳过", anchor["id"])
        return charts

    @staticmethod
    def format_chart_title(
        anchor: dict[str, Any],
        *,
        review_year: int | None = None,
        review_month: int | None = None,
        content: dict[str, Any] | None = None,
    ) -> str:
        template = str(anchor.get("title", ""))
        ry, rm = review_year, review_month
        if ry is None or rm is None:
            if content is None:
                return template
            ry, rm = ChartExportService._review_period_from_content(content)
        try:
            return template.format(year=ry, month=rm)
        except (KeyError, ValueError):
            return template

    @staticmethod
    def is_valid_chart_file(path: str | Path | None) -> bool:
        if not path:
            return False
        p = Path(path)
        return p.exists() and p.stat().st_size >= MIN_CHART_BYTES

    @staticmethod
    def _review_period_from_content(content: dict[str, Any]) -> tuple[int, int]:
        cover_date = (content.get("cover") or {}).get("date", "")
        import re

        m = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月", str(cover_date))
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            if mo == 1:
                return y - 1, 12
            return y, mo - 1
        today = date.today()
        if today.month == 1:
            return today.year - 1, 12
        return today.year, today.month - 1

    @staticmethod
    def _chart_plot_date_range(review_year: int, review_month: int) -> tuple[date, date]:
        """月报 PNG 作图区间：回顾月往前 12 个自然月至回顾月末（仅 chart_export 使用）。"""
        _, end = AnalyticsService._month_bounds(review_year, review_month)
        month = review_month - 11
        year = review_year
        while month <= 0:
            month += 12
            year -= 1
        start = date(year, month, 1)
        return start, end

    def _chart_config(
        self,
        anchor: dict[str, Any],
        content: dict[str, Any],
        start: date,
        end: date,
        title: str,
    ) -> dict[str, Any]:
        chart_type = anchor.get("chart_type", "")
        if chart_type == "futures_month":
            symbols = anchor.get("symbols") or ["Brent", "WTI"]
            return self.analytics.chart_config(
                "price_trend",
                symbols=symbols,
                start_date=start,
                end_date=end,
                title=title,
                daily_only=True,
            )
        if chart_type == "price_spread_combo":
            names = anchor.get("series_names")
            return self.analytics.chart_config(
                "spread",
                symbol_a=anchor.get("symbol_a", "Brent"),
                symbol_b=anchor.get("symbol_b", "Dubai"),
                start_date=start,
                end_date=end,
                title=title,
                daily_only=True,
                price_spread_combo=True,
                spread_mode=anchor.get("spread_mode", "a_minus_b"),
                series_names=tuple(names) if names else None,
                yAxis=anchor.get("yAxis"),
                yAxisRight=anchor.get("yAxisRight"),
                legend_position=anchor.get("legend_position", "bottom"),
            )
        # 持仓类图表：待 CFTC/ICE 数据源确认后接入 query_position_series
        if chart_type in ("brent_position_structure", "brent_position_composition"):
            return {"title": title, "series": []}
        return {"title": title, "series": []}

    def _render_chart(self, config: dict[str, Any], out: Path) -> bool:
        out.parent.mkdir(parents=True, exist_ok=True)
        ok = render_report_chart(config, out)
        if ok and out.exists() and out.stat().st_size >= MIN_CHART_BYTES:
            return True
        if out.exists():
            out.unlink(missing_ok=True)
        out.write_bytes(EMPTY_PNG)
        return False

    @staticmethod
    def charts_json(charts: dict[str, str]) -> str:
        return json.dumps(charts, ensure_ascii=False)
