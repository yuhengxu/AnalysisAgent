"""月报图表共享样式常量（matplotlib / PyEcharts 共用）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# 样例 docx chart1：Brent #0070C0、WTI #C00000；chart5/6：accent 蓝/橙/绿
SAMPLE_COLORS: dict[str, Any] = {
    "Brent": "#0070C0",
    "WTI": "#C00000",
    "DTD": "#ED7D31",
    "Dubai": "#ED7D31",
    "ESPO": "#ED7D31",
    "Oman": "#ED7D31",
    "spread": "#70AD47",
    "default": ("#0070C0", "#C00000", "#ED7D31", "#70AD47", "#7030A0", "#00B0F0"),
}

BG_COLOR = "#FFFFFF"
AXIS_COLOR = "#595959"
GRID_COLOR = "#D9D9D9"
PLOT_BORDER = "#BFBFBF"
FONT_FAMILY = "Noto Sans CJK SC, Microsoft YaHei, sans-serif"

LINE_WIDTH = 2.25
X_LABEL_ROTATION = 30
SPREAD_BAR_WIDTH_MAX = 0.22
SPREAD_BAR_WIDTH_MIN = 0.06
SPREAD_Y_SCALE_FACTOR = 2.4
SPREAD_BAR_ALPHA = 0.52
SPREAD_BAR_WIDTH_PCT = "35%"

# matplotlib: 6.4in @ 200dpi；PyEcharts: 像素尺寸
MPL_FIGSIZE = (6.4, 3.35)
MPL_DPI = 200
ECHARTS_WIDTH = 1280
ECHARTS_HEIGHT = 670

MIN_CHART_BYTES = 1024

FONT_CANDIDATES = (
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NotoSansSC-Regular.otf",
)


def series_color(name: str, idx: int) -> str:
    if name in SAMPLE_COLORS and isinstance(SAMPLE_COLORS[name], str):
        return SAMPLE_COLORS[name]
    if "价差" in name or "spread" in name.lower() or "-" in name:
        return SAMPLE_COLORS["spread"]
    defaults = SAMPLE_COLORS["default"]
    return defaults[idx % len(defaults)]


def thin_x_labels(dates: list[str], max_ticks: int = 10) -> list[str]:
    if len(dates) <= max_ticks:
        return [d[5:] if len(d) >= 10 else d for d in dates]
    step = max(1, len(dates) // max_ticks)
    thinned: list[str] = []
    for idx, label in enumerate(dates):
        if idx % step == 0 or idx == len(dates) - 1:
            short = label[5:] if len(label) >= 10 else label
            thinned.append(short)
        else:
            thinned.append("")
    return thinned


def spread_yaxis_bounds(values: list[float]) -> tuple[float, float] | None:
    if not values:
        return None
    lo, hi = min(values), max(values)
    span = max(hi - lo, abs(hi) * 0.15, 0.8)
    mid = (hi + lo) / 2
    half = span * SPREAD_Y_SCALE_FACTOR / 2
    return mid - half, mid + half


def value_axis_bounds(
    values: list[float],
    *,
    padding_ratio: float = 0.12,
    min_span: float = 1.0,
) -> tuple[float, float] | None:
    """按数据范围计算 Y 轴上下界（不强制从 0 起）。"""
    if not values:
        return None
    lo, hi = min(values), max(values)
    span = max(hi - lo, min_span)
    pad = span * padding_ratio
    return lo - pad, hi + pad


def parse_series_data(series_list: list[dict[str, Any]]) -> list[tuple[str, str, list[str], list[float], dict[str, Any]]]:
    """解析 chart_config series 为 (name, color, dates, values, meta) 列表。"""
    parsed: list[tuple[str, str, list[str], list[float], dict[str, Any]]] = []
    for idx, serie in enumerate(series_list):
        points = serie.get("data") or []
        dates: list[str] = []
        values: list[float] = []
        for x, y in points:
            try:
                dates.append(str(x))
                values.append(float(y))
            except (TypeError, ValueError):
                continue
        if not values:
            continue
        name = serie.get("name") or f"系列{idx + 1}"
        color = serie.get("color") or series_color(name, idx)
        parsed.append((name, color, dates, values, serie))
    return parsed
