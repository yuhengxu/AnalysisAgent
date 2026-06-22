"""因素表导入月份解析测试。"""
from __future__ import annotations

from app.services.data_import import DataImportService


def test_parse_factor_report_month_patterns():
    assert DataImportService._parse_factor_report_month("2026年5月油价预测分析表.xlsx") == "2026-05"
    assert DataImportService._parse_factor_report_month("2026-03") == "2026-03"
    assert DataImportService._parse_factor_report_month("202604") == "2026-04"
    assert DataImportService._parse_factor_report_month("2026_01") == "2026-01"
    assert DataImportService._parse_factor_report_month("无月份.xlsx") is None
