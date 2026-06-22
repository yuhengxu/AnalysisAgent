"""月报图表 PyEcharts 渲染引擎（独立主题，高分辨率导出）。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pyecharts import options as opts
from pyecharts.charts import Bar, Line

from app.core.config import settings
from app.services import chart_echarts_style as theme
from app.services.chart_playwright import render_chart_to_png
from app.services.chart_style import parse_series_data

logger = logging.getLogger(__name__)


def _canvas_size() -> tuple[int, int]:
    w = settings.chart_echarts_width or theme.CANVAS_WIDTH
    h = settings.chart_echarts_height or theme.CANVAS_HEIGHT
    return int(w), int(h)


def _init_opts() -> opts.InitOpts:
    w, h = _canvas_size()
    return opts.InitOpts(
        width=f"{w}px",
        height=f"{h}px",
        bg_color=theme.BG_COLOR,
    )


def _text_style(size: int, color: str = theme.TEXT_SECONDARY, weight: str = "normal") -> opts.TextStyleOpts:
    return opts.TextStyleOpts(
        font_family=theme.FONT_FAMILY,
        font_size=size,
        color=color,
        font_weight=weight,
    )


def _value_axis(name: str, *, position: str = "left") -> opts.AxisOpts:
    return opts.AxisOpts(
        type_="value",
        name=name,
        position=position,
        name_gap=theme.AXIS_NAME_GAP,
        name_textstyle_opts=_text_style(theme.FONT_AXIS_NAME, theme.TEXT_PRIMARY, "600"),
        axislabel_opts=opts.LabelOpts(
            color=theme.TEXT_SECONDARY,
            font_size=theme.FONT_AXIS_LABEL,
            font_family=theme.FONT_FAMILY,
            margin=theme.AXIS_LABEL_MARGIN,
        ),
        axisline_opts=opts.AxisLineOpts(
            is_show=True,
            linestyle_opts=opts.LineStyleOpts(color=theme.AXIS_LINE, width=1.5),
        ),
        splitline_opts=opts.SplitLineOpts(
            is_show=True,
            linestyle_opts=opts.LineStyleOpts(color=theme.GRID_LINE, width=1, type_="solid"),
        ),
        split_number=6,
    )


def _category_axis(point_count: int) -> opts.AxisOpts:
    return opts.AxisOpts(
        type_="category",
        boundary_gap=True,
        axislabel_opts=opts.LabelOpts(
            color=theme.TEXT_SECONDARY,
            font_size=theme.FONT_AXIS_LABEL,
            font_family=theme.FONT_FAMILY,
            rotate=theme.X_LABEL_ROTATE,
            margin=theme.AXIS_LABEL_MARGIN,
            interval=theme.x_axis_label_interval(point_count),
            formatter=theme.X_AXIS_LABEL_FORMATTER,
        ),
        axisline_opts=opts.AxisLineOpts(
            is_show=True,
            linestyle_opts=opts.LineStyleOpts(color=theme.AXIS_LINE, width=1.5),
        ),
        axistick_opts=opts.AxisTickOpts(is_show=False),
        splitline_opts=opts.SplitLineOpts(is_show=False),
    )


def _legend_opts(position: str) -> opts.LegendOpts:
    base = dict(
        textstyle_opts=_text_style(theme.FONT_LEGEND, theme.TEXT_PRIMARY),
        item_width=theme.LEGEND_ITEM_WIDTH,
        item_height=theme.LEGEND_ITEM_HEIGHT,
        item_gap=theme.LEGEND_ITEM_GAP,
        legend_icon="roundRect",
    )
    if position == "bottom":
        return opts.LegendOpts(pos_bottom="2%", orient="horizontal", **base)
    if position == "right":
        return opts.LegendOpts(pos_right="1%", pos_top="middle", orient="vertical", **base)
    return opts.LegendOpts(pos_top="2%", pos_right="2%", orient="vertical", **base)


def _apply_grid(chart: Line, dual_y: bool) -> None:
    grid = theme.GRID_DUAL if dual_y else theme.GRID_SINGLE
    chart.options["grid"] = [grid]


def _apply_title(chart: Line, title: str) -> None:
    if not title:
        return
    chart.options["title"] = [
        {
            "text": title,
            "left": "center",
            "top": "1.5%",
            "textStyle": {
                "fontFamily": theme.FONT_FAMILY,
                "fontSize": theme.FONT_TITLE,
                "fontWeight": "600",
                "color": theme.TEXT_PRIMARY,
            },
        }
    ]


def _apply_line_series_options(chart: Line, point_count: int) -> None:
    line_w, _ = theme.line_style_for_density(point_count)
    for s in chart.options.get("series", []):
        if s.get("type") != "line":
            continue
        s["connectNulls"] = False
        s["showSymbol"] = False
        s["symbolSize"] = 0
        ls = s.get("lineStyle")
        if isinstance(ls, dict):
            ls["width"] = line_w
        else:
            s["lineStyle"] = {"width": line_w}
        if point_count > theme.DENSE_POINT_THRESHOLD:
            s["sampling"] = "lttb"


def build_chart_from_config(config: dict[str, Any]) -> Line | None:
    series_list = config.get("series") or []
    parsed = parse_series_data(series_list)
    if not parsed:
        return None

    all_dates, aligned = theme.align_parsed_series(parsed)
    point_count = len(all_dates)
    if point_count == 0:
        return None

    dual_y = bool(config.get("dual_y"))
    legend_pos = theme.legend_position_key(config.get("legend_position"), dual_y)
    line_w, symbol_size = theme.line_style_for_density(point_count)
    bar_width, bar_opacity = theme.bar_style_for_density(point_count)

    line_series = [(n, c, v, m) for n, c, v, m in aligned if m.get("chartType") != "bar"]
    bar_series = [(n, c, v, m) for n, c, v, m in aligned if m.get("chartType") == "bar"]

    line = Line(init_opts=_init_opts())
    line.add_xaxis(all_dates)

    for idx, (name, color, values, meta) in enumerate(line_series):
        color = theme.series_color(name, idx, color)
        line.add_yaxis(
            name,
            values,
            yaxis_index=meta.get("yAxisIndex", 0),
            color=color,
            is_smooth=False,
            symbol="none",
            symbol_size=symbol_size,
            is_symbol_show=symbol_size > 0,
            linestyle_opts=opts.LineStyleOpts(width=line_w, color=color),
            label_opts=opts.LabelOpts(is_show=False),
            z=4,
        )

    if dual_y and bar_series:
        spread_values: list[float] = []
        for _, _, values, _ in bar_series:
            spread_values.extend(v for v in values if v is not None)
        bounds = theme.spread_yaxis_bounds(spread_values)
        y_min = bounds[0] if bounds else None
        y_max = bounds[1] if bounds else None
        line.extend_axis(
            yaxis=opts.AxisOpts(
                type_="value",
                name=config.get("yAxisRight") or "价差（美元/桶）",
                position="right",
                min_=y_min,
                max_=y_max,
                name_gap=theme.AXIS_NAME_GAP,
                name_textstyle_opts=_text_style(theme.FONT_AXIS_NAME, theme.TEXT_PRIMARY, "600"),
                axislabel_opts=opts.LabelOpts(
                    color=theme.TEXT_SECONDARY,
                    font_size=theme.FONT_AXIS_LABEL,
                    font_family=theme.FONT_FAMILY,
                    margin=theme.AXIS_LABEL_MARGIN,
                    formatter=theme.RIGHT_AXIS_LABEL_FORMATTER,
                ),
                axisline_opts=opts.AxisLineOpts(
                    is_show=True,
                    linestyle_opts=opts.LineStyleOpts(color=theme.AXIS_LINE, width=1.5),
                ),
                splitline_opts=opts.SplitLineOpts(is_show=False),
                split_number=5,
                min_interval=1,
            )
        )
        bar = Bar()
        bar.add_xaxis(all_dates)
        for idx, (name, color, values, meta) in enumerate(bar_series):
            color = theme.series_color(name, idx + 2, color)
            bar.add_yaxis(
                name,
                values,
                yaxis_index=1,
                color=color,
                bar_width=bar_width,
                itemstyle_opts=opts.ItemStyleOpts(
                    color=color,
                    opacity=bar_opacity,
                    border_radius=[1, 1, 0, 0],
                ),
                label_opts=opts.LabelOpts(is_show=False),
                z=1,
            )
        line = line.overlap(bar)

    left_y_name = config.get("yAxis") or "油价（美元/桶）"
    line.set_global_opts(
        tooltip_opts=opts.TooltipOpts(
            trigger="axis",
            textstyle_opts=_text_style(theme.FONT_TOOLTIP),
            axis_pointer_type="line",
        ),
        legend_opts=_legend_opts(legend_pos),
        xaxis_opts=_category_axis(point_count),
        yaxis_opts=_value_axis(left_y_name),
    )
    _apply_grid(line, dual_y)
    if config.get("show_chart_title"):
        _apply_title(line, str(config.get("title") or ""))
    _apply_line_series_options(line, point_count)
    line.options["animation"] = False
    return line


def render_report_chart_echarts(config: dict[str, Any], out: Path) -> bool:
    """PyEcharts + Playwright 高分辨率 PNG 导出。"""
    try:
        chart = build_chart_from_config(config)
        if chart is None:
            return False
        return render_chart_to_png(chart, out)
    except Exception as exc:
        logger.warning("PyEcharts 渲染失败: %s", exc)
        return False
