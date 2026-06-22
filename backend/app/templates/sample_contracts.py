"""样例文件契约。

这些常量来自 ``yuebao/`` 下的 Excel/Word 样例，用来约束导入解析、
预测表导出和月报图表/表格插入位置。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[3]
YUEBAO_DIR = ROOT_DIR / "yuebao"
PREDICTION_SAMPLE_DIR = YUEBAO_DIR / "prediction"
REPORT_SAMPLE_DIR = YUEBAO_DIR / "yuebao"

PRICE_SAMPLE_PATH = YUEBAO_DIR / "原油价格表. 20260603.xlsx"
BALANCE_SAMPLE_PATH = YUEBAO_DIR / "供需平衡表.xlsx"
REPORT_SAMPLE_PATH = REPORT_SAMPLE_DIR / "国际油价月报2026年第5期（总56期）.docx"

PRICE_HEADER_MARKERS = {
    "WTI(期)",
    "布伦特(期)",
    "阿曼(期)",
    "沪原油(期)",
    "迪拜",
    "阿曼",
    "DTD",
    "ESPO",
}
PRICE_SKIP_ROW_KEYWORDS = ("平均", "本周", "较上月", "变化率", "环比", "同比")

BALANCE_HEADER_NAMES = {
    "agency": "预测机构",
    "update_date": "更新日期",
    "supply_demand": "供需",
}
BALANCE_AGENCIES = {"IEA", "EIA", "IHS", "S&P", "WoodMac", "Wood Mackenzie", "Rystad"}
BALANCE_SUPPLY_DEMAND_VALUES = {"供", "需", "供需差"}
BALANCE_SUPPLY_DEMAND_ALIASES = {
    "供应": "供",
    "需求": "需",
    "供需差": "供需差",
    "供": "供",
    "需": "需",
}
BALANCE_SHEET_NAME_RE = r"^\d{6}$"
PRICE_SHEET_NAME_RE = r"^\d{4}年\d{1,2}月$"

PREDICTION_SHEET_BOUNDS = {
    "title_cell": "B3",
    "header_row": 5,
    "first_factor_row": 6,
    "factor_col": "B",
    "importance_cols": ("C", "D", "E", "F", "G"),
    "judgment_col": "H",
    "impact_cols": ("I", "J", "K"),
    "max_col": "K",
}

REPORT_TABLE_ANCHORS: dict[str, str] = {
    "table_price_change": "review_futures",
    "table_macro_pmi": "factor_macro",
    "table_demand_forecast": "factor_demand",
    "table_supply_balance": "factor_supply",
    "table_scenario": "outlook_scenario",
    "table_agency": "outlook_agency",
}

REPORT_CHART_ANCHORS: list[dict[str, Any]] = [
    {
        "id": "chart_futures_price",
        "section_id": "review_futures",
        "title": "图1-1  {year}年{month}月国际原油期货价格走势图",
        "source": "CNEEI",
        "chart_type": "futures_month",
        "symbols": ["Brent", "WTI"],
    },
    {
        "id": "chart_brent_position_structure",
        "section_id": "review_futures",
        "title": "图1-2  ICE Brent原油期货持仓结构走势图",
        "source": "ICE/CFTC",
        "chart_type": "brent_position_structure",
    },
    {
        "id": "chart_brent_position_composition",
        "section_id": "review_futures",
        "title": "图1-3  ICE Brent原油期货持仓者构成与价格走势图",
        "source": "ICE/CFTC",
        "chart_type": "brent_position_composition",
    },
    {
        "id": "chart_brent_spot_future",
        "section_id": "review_spot",
        "title": "图1-4  Brent期现货价格走势",
        "source": "CNEEI",
        "chart_type": "price_spread_combo",
        "symbol_a": "Brent",
        "symbol_b": "DTD",
        "spread_mode": "b_minus_a",
        "series_names": ["布伦特期货", "布伦特现货", "布伦特现货-期货价差"],
        "yAxis": "油价（美元/桶）",
        "yAxisRight": "现货-期货价差（美元/桶）",
    },
    {
        "id": "chart_brent_dubai_spread",
        "section_id": "review_spot",
        "title": "图1-5  Brent-Dubai现货价差走势",
        "source": "CNEEI",
        "chart_type": "price_spread_combo",
        "symbol_a": "Brent",
        "symbol_b": "Dubai",
        "spread_mode": "a_minus_b",
        "series_names": ["Brent期货", "Dubai现货", "Brent-Dubai价差"],
        "yAxis": "油价（美元/桶）",
        "yAxisRight": "价差（美元/桶）",
    },
    {
        "id": "chart_brent_espo_spread",
        "section_id": "review_spot",
        "title": "图1-6  Brent-ESPO价差走势",
        "source": "CNEEI",
        "chart_type": "price_spread_combo",
        "symbol_a": "Brent",
        "symbol_b": "ESPO",
        "spread_mode": "a_minus_b",
        "series_names": ["Brent期货", "ESPO", "Brent-ESPO"],
        "yAxis": "油价（美元/桶）",
        "yAxisRight": "价差（美元/桶）",
    },
]


def is_sample_aggregate_label(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and any(keyword in text for keyword in PRICE_SKIP_ROW_KEYWORDS)
