"""ECharts 月报图表专用主题（与 matplotlib 完全独立）。"""
from __future__ import annotations

import math
from typing import Any

from pyecharts.commons.utils import JsCode

# —— 画布（CSS 逻辑像素；导出 PNG = 尺寸 × EXPORT_PIXEL_RATIO）——
CANVAS_WIDTH = 1400
CANVAS_HEIGHT = 780
EXPORT_PIXEL_RATIO = 3

# —— 字体 ——
FONT_FAMILY = "'Noto Sans CJK SC', 'Source Han Sans SC', 'Microsoft YaHei', sans-serif"
FONT_AXIS_LABEL = 24
FONT_AXIS_NAME = 26
FONT_LEGEND = 22
FONT_TITLE = 28
FONT_TOOLTIP = 18

# —— 色彩（高对比、适合 Word 嵌入）——
BG_COLOR = "#FFFFFF"
TEXT_PRIMARY = "#1A1A1A"
TEXT_SECONDARY = "#555555"
GRID_LINE = "#E5E7EB"
AXIS_LINE = "#9CA3AF"

SERIES_PALETTE = (
    "#2563EB",  # 蓝
    "#EA580C",  # 橙
    "#16A34A",  # 绿
    "#9333EA",  # 紫
    "#0891B2",  # 青
)

# —— 线 / 柱 ——
LINE_WIDTH = 3.0
LINE_WIDTH_DENSE = 2.2
SYMBOL_SIZE = 0
DENSE_POINT_THRESHOLD = 40
BAR_WIDTH = "26%"
BAR_WIDTH_DENSE = "55%"
BAR_OPACITY = 0.45
BAR_OPACITY_DENSE = 0.32
SPREAD_Y_SCALE = 2.2

# —— 轴标签 ——
X_LABEL_ROTATE = 35
X_TARGET_TICKS = 12

# —— 布局（containLabel 保证轴文字不被裁切）——
GRID_SINGLE = {"left": "7%", "right": "5%", "top": "18%", "bottom": "22%", "containLabel": True}
GRID_DUAL = {"left": "7%", "right": "10%", "top": "16%", "bottom": "28%", "containLabel": True}

LEGEND_ITEM_WIDTH = 36
LEGEND_ITEM_HEIGHT = 18
LEGEND_ITEM_GAP = 28
AXIS_NAME_GAP = 34
AXIS_LABEL_MARGIN = 16

MIN_EXPORT_BYTES = 25_000

# X 轴类目必须用唯一完整日期；标签显示由 formatter 控制
X_AXIS_LABEL_FORMATTER = JsCode(
    """
function (value) {
  if (!value || value.length < 10) return '';
  var y = value.substring(2, 4);
  var m = value.substring(5, 7);
  return y + '/' + m;
}
"""
)

# 右轴（价差）刻度显示整数
RIGHT_AXIS_LABEL_FORMATTER = JsCode(
    """
function (value) {
  if (value == null || isNaN(value)) return '';
  return Math.round(value).toString();
}
"""
)


def series_color(name: str, idx: int, override: str | None = None) -> str:
    if override:
        return override
    if "价差" in name or "spread" in name.lower():
        return SERIES_PALETTE[2]
    return SERIES_PALETTE[idx % len(SERIES_PALETTE)]


def align_parsed_series(
    parsed: list[tuple[str, str, list[str], list[float], dict[str, Any]]],
) -> tuple[list[str], list[tuple[str, str, list[float | None], dict[str, Any]]]]:
    """按日期并集排序对齐各 series；X 轴使用完整 ISO 日期避免类目重复/空串错位。"""
    date_set: set[str] = set()
    for _, _, dates, _, _ in parsed:
        date_set.update(dates)
    all_dates = sorted(date_set)

    aligned: list[tuple[str, str, list[float | None], dict[str, Any]]] = []
    for name, color, dates, values, meta in parsed:
        lookup = dict(zip(dates, values))
        aligned.append((name, color, [lookup.get(d) for d in all_dates], meta))
    return all_dates, aligned


def x_axis_label_interval(point_count: int) -> int:
    if point_count <= X_TARGET_TICKS:
        return 0
    return max(1, point_count // X_TARGET_TICKS)


def line_style_for_density(point_count: int) -> tuple[float, int]:
    if point_count > DENSE_POINT_THRESHOLD:
        return LINE_WIDTH_DENSE, 0
    return LINE_WIDTH, SYMBOL_SIZE


def bar_style_for_density(point_count: int) -> tuple[str, float]:
    if point_count > DENSE_POINT_THRESHOLD:
        return BAR_WIDTH_DENSE, BAR_OPACITY_DENSE
    return BAR_WIDTH, BAR_OPACITY


def spread_yaxis_bounds(values: list[float]) -> tuple[float, float] | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    lo, hi = min(nums), max(nums)
    span = max(hi - lo, abs(hi) * 0.12, 0.6)
    mid = (hi + lo) / 2
    half = span * SPREAD_Y_SCALE / 2
    return math.floor(mid - half), math.ceil(mid + half)


def legend_position_key(raw: str | None, dual_y: bool) -> str:
    if raw in ("bottom", "upper right", "right"):
        return raw
    return "bottom" if dual_y else "upper right"


def inject_export_css(html: str) -> str:
    css = f"""
<style>
  html, body {{
    margin: 0; padding: 0;
    background: {BG_COLOR};
    font-family: {FONT_FAMILY};
    -webkit-font-smoothing: antialiased;
  }}
  .chart-container {{
    margin: 0 auto;
  }}
</style>
"""
    return html.replace("</head>", css + "</head>", 1)
