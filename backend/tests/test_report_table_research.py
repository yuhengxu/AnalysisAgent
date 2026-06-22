"""月报表2-x 深度研究/数据库填充测试。"""

from __future__ import annotations



import json



import pytest



from app.core.database import SessionLocal

from app.services.report_table_research import (

    ReportTableResearchService,

    build_gdp_rows,

    build_pmi_rows,

    extract_json_object,

    pmi_table_title,

)

from app.templates.monthly_report import default_content





def _mock_deepsearch_pmi(monkeypatch, payload: dict):

    """模拟 DeepSearch 串行返回 PMI JSON。"""

    monkeypatch.setattr(

        "app.services.report_table_research.llm.is_enabled",

        lambda provider=None: provider in (None, "volcengine", "deepseek"),

    )

    monkeypatch.setattr(

        "app.services.report_table_research.llm.deep_search_available",

        lambda: True,

    )



    def _fake_search(self, provider, user_prompt):

        return json.dumps(payload, ensure_ascii=False), {

            "references": [{"url": "https://www.example.com/pmi", "title": "PMI"}],

        }



    monkeypatch.setattr(

        ReportTableResearchService,

        "_search_pmi_with_deepsearch",

        _fake_search,

    )





@pytest.fixture

def db():

    session = SessionLocal()

    try:

        yield session

    finally:

        session.close()





def test_extract_json_object_from_codeblock():

    text = '说明\n```json\n{"table_macro_pmi": {"rows": {}}}\n```'

    parsed = extract_json_object(text)

    assert parsed and "table_macro_pmi" in parsed





def test_build_pmi_rows_format():

    region_data = {

        "us": {

            "composite_flash": 52.0,

            "composite_mom": 1.7,

            "mfg_final": 54.5,

            "mfg_mom": 0.0,

            "svc_flash": 51.3,

            "svc_mom": 1.5,

        },

        "eurozone": {

            "composite_flash": 48.6,

            "composite_mom": -1.9,

        },

    }

    rows = build_pmi_rows(region_data)

    assert rows[0] == ["综合", "初值", "52.0", "48.6", ""]

    assert rows[1][2] == "+1.7"

    assert rows[1][3] == "-1.9"

    assert rows[3][2] == "+0.0"





def test_build_gdp_rows():

    items = [

        {"region": "全球", "forecast_2026": 3.1, "revision_vs_jan2026": -0.2},

        {"region": "美国", "forecast_2026": 2.3, "revision_vs_jan2026": -0.1},

    ]

    rows = build_gdp_rows(items)

    assert rows[0] == ["全球", "3.1", "-0.2"]

    assert rows[1] == ["美国", "2.3", "-0.1"]

    assert rows[2][0] == "欧元区"





def test_pmi_missing_fields_sorted():

    svc = ReportTableResearchService.__new__(ReportTableResearchService)

    rows = {

        "us": {"composite_flash": 51.7},

        "china": {},

        "eurozone": {"mfg_final": 51.4},

    }

    missing = svc._pmi_missing_fields_sorted(rows)

    assert ("china", "composite_flash") in missing

    assert ("us", "mfg_final") in missing

    assert missing[0][0] in ("us", "china")

    prompt = ReportTableResearchService._build_pmi_region_gap_prompt(

        "us", ["mfg_final", "composite_mom"], 2026, 5,

    )

    assert "2026年5月" in prompt

    assert "美国" in prompt

    assert "制造业" in prompt

    grouped = svc._pmi_missing_fields_by_region(rows)

    assert "china" in grouped

    assert "composite_flash" in grouped["china"]





def test_pmi_mandatory_and_merge():

    svc = ReportTableResearchService.__new__(ReportTableResearchService)

    partial = {"us": {"composite_flash": 51.7}, "china": {}}

    assert svc._pmi_mandatory_filled(partial) is False

    assert svc._pmi_missing_mandatory(partial) == ["china"]

    merged = svc._merge_pmi_region_rows(

        partial,

        {"china": {"mfg_final": 49.5, "mfg_mom": -0.3}, "us": {"mfg_final": 55.3}},

    )

    assert merged["us"]["composite_flash"] == 51.7

    assert merged["us"]["mfg_final"] == 55.3

    assert merged["china"]["mfg_final"] == 49.5

    assert svc._pmi_mandatory_filled(merged) is True





def test_supply_balance_from_db(db):

    svc = ReportTableResearchService(db)

    tbl = svc.build_supply_balance_table(2026, 5)

    assert tbl is not None

    assert "2026Q1" in tbl["headers"]

    agencies = [row[0] for row in tbl["rows"]]

    assert "IEA" in agencies

    assert "EIA" in agencies

    iea = next(row for row in tbl["rows"] if row[0] == "IEA")

    assert iea[1] == "0.20"

    assert iea[2] == "-3.70"

    meta = tbl["source_meta"]
    assert meta["requested_snapshot_month"] == "2026-05"
    assert meta["snapshot_month"] == "2026-05"
    assert meta["snapshot_fallback"] is False


def test_supply_balance_fallback_to_latest_prior_month(db):
    from app.models.balance_forecast import BalanceForecast

    snapshot_prior = "2198-04"
    for q, val in [("2198Q1", 1.11), ("2198Q2", 2.22), ("2198Q3", 3.33), ("2198Q4", 4.44)]:
        db.add(
            BalanceForecast(
                dataset_id=9991,
                agency="IEA",
                snapshot_month=snapshot_prior,
                update_date="test",
                supply_demand="供需差",
                period=q,
                value=val,
            )
        )
    db.commit()

    svc = ReportTableResearchService(db)
    resolved, requested, used_fallback = svc.analytics.resolve_balance_snapshot_month(2198, 5)
    assert requested == "2198-05"
    assert resolved == snapshot_prior
    assert used_fallback is True

    tbl = svc.build_supply_balance_table(2198, 5)
    assert tbl is not None
    assert tbl["source_meta"]["snapshot_month"] == snapshot_prior
    assert tbl["source_meta"]["snapshot_fallback"] is True
    iea = next(row for row in tbl["rows"] if row[0] == "IEA")
    assert iea[1] == "1.11"





def test_pmi_search_prompt_includes_review_guard():
    prompt = ReportTableResearchService._build_pmi_search_prompt(2026, 5, 2026, 5)
    assert "2026年5月" in prompt
    assert "与回顾月一致" in prompt
    assert "勿用其他月份" in prompt


def test_fill_tables_without_deepsearch(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.report_table_research.llm.deep_search_available",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.services.report_table_research.llm.is_enabled",
        lambda provider=None: False,
    )
    svc = ReportTableResearchService(db)
    content = default_content("2026年第5期", "2026年5月7日")
    meta = svc.fill_tables(content, 2026, 5)

    assert meta["pmi_period"] == "2026年5月"

    assert content["tables"]["table_macro_pmi"]["title"] == pmi_table_title(2026, 5)

    supply = content["tables"]["table_supply_balance"]

    assert len(supply["rows"]) >= 4

    assert supply["rows"][0][0] == "IEA"





def test_apply_pmi_gdp_without_sources(db, monkeypatch):

    payload = {

        "table_macro_pmi": {

            "rows": {

                "us": {"composite_flash": 52.0, "composite_mom": 1.7},

                "china": {"mfg_final": 49.5},

            },

        },

    }

    _mock_deepsearch_pmi(monkeypatch, payload)



    def _fake_gdp_predict(self, review_year, review_month):

        return (

            {"table_demand_forecast": {"rows": [{"region": "全球", "forecast_2026": 3.1, "revision_vs_jan2026": -0.2}]}},

            {"provider": "deepseek", "predicted": True},

        )



    monkeypatch.setattr(ReportTableResearchService, "_predict_gdp_forecast", _fake_gdp_predict)

    svc = ReportTableResearchService(db)

    research = svc.fetch_pmi_gdp_tables(2026, 5, 2026, 5)

    assert research.get("pmi_table")

    assert research.get("gdp_table")

    assert research["pmi_table"]["rows"][0][2] == "52.0"





def test_fill_tables_with_deepsearch(db, monkeypatch):

    payload = {

        "table_macro_pmi": {

            "pmi_year": 2026,

            "pmi_month": 5,

            "sources": ["https://www.imf.org/example"],

            "rows": {

                "us": {"composite_flash": 52.0, "composite_mom": 1.7},

                "china": {"mfg_final": 49.5},

            },

        },

    }

    _mock_deepsearch_pmi(monkeypatch, payload)

    svc = ReportTableResearchService(db)

    content = default_content("2026年第5期", "2026年5月7日")

    meta = svc.fill_tables(content, 2026, 5)

    assert meta["sources"]["table_macro_pmi"]["verified"] is True

    assert content["tables"]["table_macro_pmi"]["rows"][0][2] == "52.0"





def test_sequential_deepsearch_stops_on_rate_limit(db, monkeypatch):

    """429 限流后不再继续发后续 DeepSearch 请求。"""

    calls: list[str] = []



    def _fake_search(self, provider, user_prompt):

        calls.append(user_prompt[:40])

        if len(calls) == 1:

            return "", {"references": [], "rate_limited": True, "error": "429"}

        return json.dumps({"table_macro_pmi": {"rows": {"us": {"composite_flash": 52.0}}}}), {"references": []}



    monkeypatch.setattr(

        "app.services.report_table_research.llm.is_enabled",

        lambda provider=None: provider in (None, "volcengine", "deepseek"),

    )

    monkeypatch.setattr(

        "app.services.report_table_research.llm.deep_search_available",

        lambda: True,

    )

    monkeypatch.setattr(ReportTableResearchService, "_search_pmi_with_deepsearch", _fake_search)



    svc = ReportTableResearchService(db)

    _, meta = svc._research_pmi_via_web("volcengine", 2026, 5)

    assert meta["rate_limited"] is True

    assert meta["deepsearch_calls"] == 1

    assert len(calls) == 1





def test_predict_gdp_forecast(db, monkeypatch):

    def _fake_chat_json_with_meta(system, user, **kwargs):

        return (

            {

                "table_demand_forecast": {

                    "rows": [

                        {"region": "全球", "forecast_2026": 3.1, "revision_vs_jan2026": -0.2},

                        {"region": "美国", "forecast_2026": 2.3, "revision_vs_jan2026": -0.1},

                    ],

                },

            },

            {"provider": kwargs.get("provider"), "model": "test-model", "mode": "normal"},

        )



    monkeypatch.setattr(

        "app.services.report_table_research.llm.is_enabled",

        lambda provider=None: provider in (None, "deepseek"),

    )

    monkeypatch.setattr(

        "app.services.report_table_research.llm.deep_search_available",

        lambda: False,

    )

    monkeypatch.setattr(

        "app.services.report_table_research.llm.chat_json_with_meta",

        _fake_chat_json_with_meta,

    )

    svc = ReportTableResearchService(db)

    research = svc.fetch_pmi_gdp_tables(2026, 5, 2026, 5, fetch_pmi=False, fetch_gdp=True)

    assert research.get("gdp_table")

    assert research["gdp_table"]["source"] == "大模型预测"

    assert research["gdp_meta"]["predicted"] is True

    assert research["gdp_table"]["rows"][0] == ["全球", "3.1", "-0.2"]

