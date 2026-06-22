"""供需平衡图表配置测试。"""
from __future__ import annotations

from app.services.analytics import AnalyticsService


def test_balance_chart_dual_y_for_supply_demand_and_gap(monkeypatch):
    svc = AnalyticsService(db=None)  # type: ignore[arg-type]
    monkeypatch.setattr(
        svc,
        "query_balance_forecast",
        lambda **_: [
            {"agency": "IEA", "supply_demand": "供", "period": "2026Q1", "value": 102.5},
            {"agency": "IEA", "supply_demand": "需", "period": "2026Q1", "value": 101.2},
            {"agency": "IEA", "supply_demand": "供需差", "period": "2026Q1", "value": 1.3},
        ],
    )

    cfg = svc._chart_config_balance()
    assert cfg["dual_y"] is True
    assert cfg["y_axis_scale"] is True
    assert cfg["yAxisMin"] < 102.5
    assert cfg["yAxisMax"] > 101.2
    assert cfg["yAxisMin"] > 50  # 不应从 0 起
    assert cfg["yAxisRightMin"] < 1.3
    assert cfg["yAxisRightMax"] > 1.3
    assert cfg["yAxisRight"] == "供需差（百万桶/天）"
    gap = next(s for s in cfg["series"] if "供需差" in s["name"])
    supply = next(s for s in cfg["series"] if s["name"].endswith(" 供"))
    assert gap["yAxisIndex"] == 1
    assert gap["lineStyle"] == {"type": "dashed", "width": 2}
    assert supply["yAxisIndex"] == 0


def test_balance_chart_single_y_when_only_gap(monkeypatch):
    svc = AnalyticsService(db=None)  # type: ignore[arg-type]
    monkeypatch.setattr(
        svc,
        "query_balance_forecast",
        lambda **_: [
            {"agency": "IEA", "supply_demand": "供需差", "period": "2026Q1", "value": -0.8},
        ],
    )

    cfg = svc._chart_config_balance()
    assert cfg["dual_y"] is False
    assert cfg["y_axis_scale"] is True
    assert "yAxisMin" in cfg
    assert cfg["yAxisMin"] > -5
    assert cfg["series"][0]["yAxisIndex"] == 0
    assert "lineStyle" not in cfg["series"][0]
