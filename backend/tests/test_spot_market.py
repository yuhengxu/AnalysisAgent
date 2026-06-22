"""现货 evidence 与图表配置测试。"""
from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock

from app.services.analytics import AnalyticsService
from app.skills.evidence_guard import guard_report_content


class TrendDirectionTests(unittest.TestCase):
    def test_trend_thresholds(self):
        self.assertEqual(AnalyticsService.trend_direction(2.0), "走强")
        self.assertEqual(AnalyticsService.trend_direction(-2.0), "走弱")
        self.assertEqual(AnalyticsService.trend_direction(0.3), "震荡")
        self.assertEqual(AnalyticsService.trend_direction(None), "数据缺失")


class PriceSpreadComboTests(unittest.TestCase):
    def setUp(self):
        self.svc = AnalyticsService(MagicMock())
        self.svc.query_price_series = MagicMock(
            return_value=[
                {"date": "2026-05-01", "price": 100.0},
                {"date": "2026-05-02", "price": 101.0},
            ]
        )

    def test_chart14_three_series_b_minus_a(self):
        cfg = self.svc._chart_config_price_spread_combo(
            "Brent",
            "DTD",
            date(2026, 5, 1),
            date(2026, 5, 31),
            daily_only=True,
            meta={},
            spread_mode="b_minus_a",
            series_names=("布伦特期货", "布伦特现货", "布伦特现货-期货价差"),
            yAxisRight="现货-期货价差（美元/桶）",
        )
        self.assertEqual(len(cfg["series"]), 3)
        self.assertEqual(cfg["series"][0]["name"], "布伦特期货")
        self.assertEqual(cfg["series"][2]["yAxisIndex"], 1)
        self.assertEqual(cfg["series"][2]["data"][0][1], 0.0)

    def test_chart15_spread_a_minus_b(self):
        cfg = self.svc._chart_config_price_spread_combo(
            "Brent",
            "Dubai",
            date(2026, 5, 1),
            date(2026, 5, 31),
            daily_only=True,
            meta={},
            spread_mode="a_minus_b",
            series_names=("Brent期货", "Dubai现货", "Brent-Dubai价差"),
        )
        self.assertEqual(cfg["series"][2]["data"][0][1], 0.0)


class SpotGuardTests(unittest.TestCase):
    def test_repair_weakens_when_spot_down(self):
        content = {
            "sections": [
                {
                    "id": "review_spot",
                    "level": 2,
                    "content": "5月布伦特现货价格大幅走强，DTD 均价高于上月。",
                }
            ]
        }
        evidence = {
            "spot_market": {
                "trends": {"brent_spot": "走弱", "dubai": "震荡", "espo": "震荡"}
            }
        }
        guard_report_content(content, evidence)
        self.assertIn("走弱", content["sections"][0]["content"])
        self.assertNotIn("走强", content["sections"][0]["content"])


if __name__ == "__main__":
    unittest.main()
