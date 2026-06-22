"""月报表格快照服务测试。"""
from __future__ import annotations

import json

import pytest

from app.core.database import SessionLocal
from app.services.report_table_data import (
    ReportTableDataService,
    ReviewPeriodMismatch,
    build_table_scenario_rows,
    normalize_report_periods,
    outlook_from_review,
    resolve_data_center_periods,
    resolve_gdp_llm_predict_enabled,
    review_from_outlook,
    web_fetch_options,
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_outlook_review_roundtrip():
    assert outlook_from_review(2026, 5) == (2026, 6)
    assert review_from_outlook(2026, 6) == (2026, 5)
    assert outlook_from_review(2026, 12) == (2027, 1)
    assert review_from_outlook(2027, 1) == (2026, 12)


def test_resolve_data_center_periods():
    periods = resolve_data_center_periods(2026, 5, outlook_year=2026, outlook_month=6)
    assert periods["review_label"] == "2026年5月"
    assert periods["outlook_label"] == "2026年6月"
    assert periods["pmi_label"] == "2026年5月"
    cross = resolve_data_center_periods(2026, 12, outlook_year=2027, outlook_month=1)
    assert cross["pmi_label"] == "2026年12月"


def test_resolve_data_center_periods_mismatch():
    with pytest.raises(ReviewPeriodMismatch):
        resolve_data_center_periods(2026, 6, outlook_year=2026, outlook_month=6)


def test_fetch_web_returns_periods(db, monkeypatch):
    monkeypatch.setattr(
        "app.core.llm.deep_search_available",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.core.llm.is_enabled",
        lambda provider=None: False,
    )
    svc = ReportTableDataService(db)
    result = svc.fetch_web(
        2026, 5, outlook_year=2026, outlook_month=6, table_keys=["table_macro_pmi"],
    )
    assert result["periods"]["review_label"] == "2026年5月"
    assert result["periods"]["pmi_label"] == "2026年5月"
    assert "DeepSearch" in result["errors"]["table_macro_pmi"]
    assert result["gdp_llm_predict_enabled"] is False


def test_fetch_web_skips_gdp_by_default(db, monkeypatch):
    monkeypatch.setattr("app.core.llm.deep_search_available", lambda: True)
    monkeypatch.setattr("app.core.llm.is_enabled", lambda provider=None: True)

    class _FakeResearch:
        def fetch_pmi_gdp_tables(self, *args, **kwargs):
            assert kwargs.get("fetch_gdp") is False
            return {"pmi_table": None, "deep_research": {"pmi": {}}}

    svc = ReportTableDataService(db)
    svc.research = _FakeResearch()
    result = svc.fetch_web(2026, 5, outlook_year=2026, outlook_month=6)
    assert "table_demand_forecast" in result["skipped"]
    assert result["skip_notes"]["table_demand_forecast"]


def test_fetch_web_gdp_when_enabled(db, monkeypatch):
    monkeypatch.setattr("app.core.llm.deep_search_available", lambda: True)
    monkeypatch.setattr("app.core.llm.is_enabled", lambda provider=None: True)
    monkeypatch.setattr(ReportTableDataService, "_is_manual_locked", lambda *a, **k: False)

    class _FakeResearch:
        def fetch_pmi_gdp_tables(self, *args, **kwargs):
            assert kwargs.get("fetch_gdp") is True
            return {
                "gdp_table": {
                    "title": "表2-2",
                    "source": "",
                    "headers": ["全球", "2026", "变化"],
                    "rows": [["全球", "3.1", "-0.2"]],
                },
            }

    svc = ReportTableDataService(db)
    svc.research = _FakeResearch()
    result = svc.fetch_web(
        2099, 3,
        outlook_year=2099,
        outlook_month=4,
        enable_gdp_llm_predict=True,
        table_keys=["table_demand_forecast"],
    )
    assert "table_demand_forecast" in result["fetched"]
    assert result["gdp_llm_predict_enabled"] is True


def test_web_fetch_options_default():
    opts = web_fetch_options()
    assert opts["gdp_llm_predict_default"] is False
    assert resolve_gdp_llm_predict_enabled() is False
    assert resolve_gdp_llm_predict_enabled(True) is True


def test_normalize_report_periods():
    review, outlook = normalize_report_periods(2026, 5, 2026, 7, primary="review")
    assert review == (2026, 5)
    assert outlook == (2026, 6)
    review, outlook = normalize_report_periods(2026, 6, 2026, 6, primary="outlook")
    assert review == (2026, 5)
    assert outlook == (2026, 6)
    review, outlook = normalize_report_periods(2026, 12, 2027, 1, primary="outlook")
    assert review == (2026, 12)
    assert outlook == (2027, 1)


def test_load_for_report_normalizes_review_from_outlook(db):
    svc = ReportTableDataService(db)
    tables, meta = svc.load_for_report(2026, 6, 2026, 6)
    assert meta["review_period"] == "2026年5月"
    assert tables["table_scenario"]["rows"][0][0] == "2026年6月"


def test_sync_derived_price_and_supply(db):
    svc = ReportTableDataService(db)
    result = svc.sync_derived(2026, 5, 2026, 6)
    assert "table_price_change" in result["synced"] or result["errors"].get("table_price_change")
    assert "table_supply_balance" in result["synced"] or result["errors"].get("table_supply_balance")
    loaded = svc.list_tables(2026, 5)
    supply = next(t for t in loaded["tables"] if t["table_key"] == "table_supply_balance")
    if supply["has_values"]:
        iea = next(row for row in supply["table"]["rows"] if row[0] == "IEA")
        assert iea[1] == "0.20"


def test_manual_upsert_web_table(db):
    svc = ReportTableDataService(db)
    rows = [
        ["全球", "3.1", "-0.2"],
        ["美国", "2.3", "-0.1"],
        ["欧元区", "1.1", "-0.2"],
        ["东盟", "4.1", "-0.1"],
        ["沙特阿拉伯", "3.1", "-1.4"],
        ["俄罗斯", "1.1", "0.3"],
    ]
    svc.upsert_manual(2026, 5, "table_demand_forecast", rows)
    snap = svc.get_table(2026, 5, "table_demand_forecast")
    assert snap is not None
    assert snap["rows"][0] == ["全球", "3.1", "-0.2"]
    assert snap["is_manual_override"] is True


def test_load_for_report_missing_tables(db):
    svc = ReportTableDataService(db)
    tables, meta = svc.load_for_report(2099, 1, 2099, 2)
    assert "table_price_change" in tables
    assert "table_macro_pmi" in meta["missing_tables"]


def test_build_table_scenario_rows():
    model = {
        "scenarios": [
            {"scenario": "baseline", "point": 95, "low": 90, "high": 100},
            {"scenario": "optimistic", "point": 98, "low": 95, "high": 100},
            {"scenario": "pessimistic", "point": 92, "low": 90, "high": 95},
        ]
    }
    rows = build_table_scenario_rows(model, 2026, 6)
    assert rows is not None
    assert rows[0][0] == "2026年6月"
    assert rows[0][1] == "95"


def test_periods_from_import():
    assert ReportTableDataService.periods_from_import(
        "price", {"imported_sheets": ["2026年5月", "invalid"]},
    ) == [(2026, 5)]
    assert ReportTableDataService.periods_from_import(
        "balance", {"imported_sheets": ["202605"]},
    ) == [(2026, 5)]
    assert ReportTableDataService.periods_from_import("factor", {}) == []


def test_sync_derived_after_import_price(db):
    svc = ReportTableDataService(db)
    result = svc.sync_derived_after_import(
        "price",
        {"imported_sheets": ["2026年5月"]},
    )
    assert result["periods"] == [{"review_year": 2026, "review_month": 5}]
    assert "2026-05" in result["synced"]
