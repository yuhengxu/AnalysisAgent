"""月报图表双引擎渲染测试。"""
from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from app.services.chart_echarts import build_chart_from_config
from app.services.chart_export import ChartExportService
from app.services.chart_render import render_report_chart
from app.services.chart_style import spread_yaxis_bounds


def _combo_config() -> dict:
    dates = ["2026-05-01", "2026-05-02", "2026-05-03"]
    return {
        "title": "图1-4",
        "dual_y": True,
        "yAxis": "油价（美元/桶）",
        "yAxisRight": "价差（美元/桶）",
        "legend_position": "bottom",
        "series": [
            {
                "name": "布伦特期货",
                "yAxisIndex": 0,
                "color": "#0070C0",
                "data": [[d, 100 + i] for i, d in enumerate(dates)],
            },
            {
                "name": "布伦特现货",
                "yAxisIndex": 0,
                "color": "#ED7D31",
                "data": [[d, 105 + i] for i, d in enumerate(dates)],
            },
            {
                "name": "布伦特现货-期货价差",
                "yAxisIndex": 1,
                "chartType": "bar",
                "color": "#70AD47",
                "data": [[d, 5.0 + i * 0.5] for i, d in enumerate(dates)],
            },
        ],
    }


class SpreadBoundsTests(unittest.TestCase):
    def test_spread_yaxis_expanded(self):
        bounds = spread_yaxis_bounds([2.0, 5.0, 8.0])
        self.assertIsNotNone(bounds)
        lo, hi = bounds  # type: ignore[misc]
        self.assertLess(hi - lo, 20)


class ChartPlotRangeTests(unittest.TestCase):
    def test_twelve_month_window(self):
        start, end = ChartExportService._chart_plot_date_range(2026, 5)
        self.assertEqual(start, date(2025, 6, 1))
        self.assertEqual(end, date(2026, 5, 31))

    def test_january_review_crosses_year(self):
        start, end = ChartExportService._chart_plot_date_range(2026, 1)
        self.assertEqual(start, date(2025, 2, 1))
        self.assertEqual(end, date(2026, 1, 31))

    def test_align_misaligned_series(self):
        from app.services import chart_echarts_style as theme

        parsed = [
            ("A", "#000", ["2026-01-01", "2026-01-02", "2026-01-03"], [1.0, 2.0, 3.0], {}),
            ("B", "#111", ["2026-01-01", "2026-01-03"], [10.0, 30.0], {}),
        ]
        dates, aligned = theme.align_parsed_series(parsed)
        self.assertEqual(dates, ["2026-01-01", "2026-01-02", "2026-01-03"])
        self.assertEqual(aligned[1][2], [10.0, None, 30.0])


class EchartsBuilderTests(unittest.TestCase):
    def test_build_combo_has_overlap(self):
        chart = build_chart_from_config(_combo_config())
        self.assertIsNotNone(chart)
        opts = chart.options  # type: ignore[attr-defined]
        self.assertTrue(len(opts.get("series", [])) >= 3)

    def test_no_title_on_chart_by_default(self):
        chart = build_chart_from_config(_combo_config())
        self.assertIsNotNone(chart)
        opts = chart.options  # type: ignore[attr-defined]
        title = opts.get("title")
        self.assertFalse(isinstance(title, list) and title and title[0].get("text"))


class ChartTitleFormatTests(unittest.TestCase):
    def test_format_chart_title_replaces_year_month(self):
        anchor = {"title": "图1-1  {year}年{month}月国际原油期货价格走势图"}
        title = ChartExportService.format_chart_title(anchor, review_year=2026, review_month=5)
        self.assertEqual(title, "图1-1  2026年5月国际原油期货价格走势图")

    def test_format_chart_title_without_placeholders(self):
        anchor = {"title": "图1-4  Brent期现货价格走势"}
        title = ChartExportService.format_chart_title(anchor, review_year=2026, review_month=5)
        self.assertEqual(title, "图1-4  Brent期现货价格走势")


class RouterTests(unittest.TestCase):
    @patch("app.services.chart_render.render_report_chart_matplotlib")
    @patch("app.services.chart_render.settings")
    def test_default_matplotlib(self, mock_settings, mock_mpl):
        mock_settings.chart_renderer = "matplotlib"
        mock_mpl.return_value = True
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "t.png"
            ok = render_report_chart(_combo_config(), out)
        self.assertTrue(ok)
        mock_mpl.assert_called_once()

    @patch("app.services.chart_render.render_report_chart_matplotlib")
    @patch("app.services.chart_echarts.render_report_chart_echarts")
    @patch("app.services.chart_render.settings")
    def test_echarts_fallback(self, mock_settings, mock_echarts, mock_mpl):
        mock_settings.chart_renderer = "echarts"
        mock_settings.chart_echarts_fallback = True
        mock_echarts.return_value = False
        mock_mpl.return_value = True
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "t.png"
            ok = render_report_chart(_combo_config(), out)
        self.assertTrue(ok)
        mock_echarts.assert_called_once()
        mock_mpl.assert_called_once()


if __name__ == "__main__":
    unittest.main()
