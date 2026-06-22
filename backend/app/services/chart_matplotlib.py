"""月报图表 matplotlib 渲染引擎。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.services.chart_style import (
    AXIS_COLOR,
    FONT_CANDIDATES,
    GRID_COLOR,
    LINE_WIDTH,
    MPL_DPI,
    MPL_FIGSIZE,
    PLOT_BORDER,
    SPREAD_BAR_ALPHA,
    SPREAD_BAR_WIDTH_MAX,
    SPREAD_BAR_WIDTH_MIN,
    SPREAD_Y_SCALE_FACTOR,
    X_LABEL_ROTATION,
    series_color,
    spread_yaxis_bounds,
    thin_x_labels,
)

logger = logging.getLogger(__name__)

_theme_applied = False
_resolved_font: str | None = None


def resolve_cjk_font() -> str | None:
    global _resolved_font
    if _resolved_font:
        return _resolved_font
    try:
        from matplotlib import font_manager
    except ImportError:
        return None
    for path in FONT_CANDIDATES:
        if not path.exists():
            continue
        try:
            font_manager.fontManager.addfont(str(path))
            name = font_manager.FontProperties(fname=str(path)).get_name()
            _resolved_font = name
            logger.info("月报图表使用字体: %s (%s)", name, path)
            return name
        except OSError as exc:
            logger.debug("字体加载失败 %s: %s", path, exc)
    return None


def apply_matplotlib_theme() -> None:
    global _theme_applied
    if _theme_applied:
        return
    try:
        import matplotlib as mpl
    except ImportError:
        return

    font_name = resolve_cjk_font()
    if font_name:
        mpl.rcParams["font.sans-serif"] = [font_name, "DejaVu Sans"]
    mpl.rcParams["axes.unicode_minus"] = False
    mpl.rcParams["figure.facecolor"] = "#FFFFFF"
    mpl.rcParams["axes.facecolor"] = "#FFFFFF"
    mpl.rcParams["axes.edgecolor"] = PLOT_BORDER
    mpl.rcParams["axes.labelcolor"] = AXIS_COLOR
    mpl.rcParams["xtick.color"] = AXIS_COLOR
    mpl.rcParams["ytick.color"] = AXIS_COLOR
    mpl.rcParams["grid.color"] = GRID_COLOR
    mpl.rcParams["grid.linestyle"] = "-"
    mpl.rcParams["grid.linewidth"] = 0.5
    mpl.rcParams["legend.frameon"] = True
    mpl.rcParams["legend.framealpha"] = 0.92
    mpl.rcParams["legend.edgecolor"] = "#E7E7E7"
    _theme_applied = True


def _style_axes(ax, *, grid: bool = True) -> None:
    ax.spines["top"].set_visible(True)
    ax.spines["right"].set_visible(True)
    ax.spines["left"].set_color(PLOT_BORDER)
    ax.spines["bottom"].set_color(PLOT_BORDER)
    ax.spines["top"].set_color(PLOT_BORDER)
    ax.spines["right"].set_color(PLOT_BORDER)
    ax.tick_params(axis="both", labelsize=8, colors=AXIS_COLOR, direction="out", length=3, width=0.6)
    if grid:
        ax.grid(True, axis="y", color=GRID_COLOR, linewidth=0.5, alpha=0.9, zorder=0)
        ax.set_axisbelow(True)


def render_report_chart_matplotlib(config: dict[str, Any], out: Path) -> bool:
    """渲染单张月报图表（matplotlib）。"""
    apply_matplotlib_theme()
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.ticker import MaxNLocator
    except ImportError:
        logger.error("未安装 matplotlib，无法渲染月报图表")
        return False

    series_list = config.get("series") or []
    if not any((s.get("data") or []) for s in series_list):
        return False

    dual_y = bool(config.get("dual_y"))
    legend_pos = config.get("legend_position") or ("bottom" if dual_y else "upper right")
    show_chart_title = bool(config.get("show_chart_title"))

    fig, ax = plt.subplots(figsize=MPL_FIGSIZE, dpi=MPL_DPI)
    fig.patch.set_facecolor("#FFFFFF")
    margin = {"left": 0.10, "right": 0.88 if dual_y else 0.94, "top": 0.94, "bottom": 0.22}
    if legend_pos == "bottom":
        margin["bottom"] = 0.30
    fig.subplots_adjust(**margin)

    ax2 = ax.twinx() if dual_y else None
    if ax2 is not None:
        _style_axes(ax2, grid=False)
        ax2.spines["left"].set_visible(False)
        ax2.set_zorder(1)
        ax.set_zorder(2)
        ax.patch.set_visible(False)

    primary_dates: list[str] = []
    plotted = False
    spread_ys: list[float] = []

    for idx, serie in enumerate(series_list):
        points = serie.get("data") or []
        clean: list[tuple[str, float]] = []
        for x, y in points:
            try:
                clean.append((str(x), float(y)))
            except (TypeError, ValueError):
                continue
        if not clean:
            continue

        plotted = True
        name = serie.get("name") or f"系列{idx + 1}"
        color = serie.get("color") or series_color(name, idx)
        xs = [p[0] for p in clean]
        ys = [p[1] for p in clean]
        use_ax = ax2 if serie.get("yAxisIndex") == 1 and ax2 is not None else ax

        if not primary_dates:
            primary_dates = xs

        x_idx = range(len(xs))
        n_pts = max(len(xs), 1)
        if serie.get("chartType") == "bar":
            spread_ys.extend(ys)
            bar_width = max(SPREAD_BAR_WIDTH_MIN, min(SPREAD_BAR_WIDTH_MAX, 0.72 / n_pts))
            use_ax.bar(
                x_idx,
                ys,
                label=name,
                color=color,
                width=bar_width,
                alpha=SPREAD_BAR_ALPHA,
                edgecolor="none",
                zorder=1,
            )
        else:
            use_ax.plot(
                x_idx,
                ys,
                label=name,
                color=color,
                linewidth=LINE_WIDTH,
                linestyle=serie.get("linestyle") or "-",
                solid_capstyle="round",
                zorder=4,
            )

    if not plotted:
        plt.close(fig)
        return False

    ax.set_xticks(range(len(primary_dates)))
    ax.set_xticklabels(
        thin_x_labels(primary_dates),
        rotation=X_LABEL_ROTATION,
        ha="right",
        fontsize=8,
    )
    ax.tick_params(axis="x", pad=2)
    _style_axes(ax)

    y_label = config.get("yAxis") or "油价（美元/桶）"
    ax.set_ylabel(y_label, fontsize=9, color=AXIS_COLOR, labelpad=6)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, prune=None))

    if ax2 is not None:
        y2_label = config.get("yAxisRight") or "价差（美元/桶）"
        ax2.set_ylabel(y2_label, fontsize=9, color=AXIS_COLOR, labelpad=6)
        ax2.yaxis.set_major_locator(MaxNLocator(nbins=6, prune=None))
        ax2.tick_params(axis="y", labelsize=8, colors=AXIS_COLOR)
        bounds = spread_yaxis_bounds(spread_ys)
        if bounds:
            ax2.set_ylim(bounds[0], bounds[1])

    x_label = config.get("xAxis")
    if x_label:
        ax.set_xlabel(x_label, fontsize=9, color=AXIS_COLOR, labelpad=4)

    if show_chart_title and config.get("title"):
        fig.suptitle(str(config["title"])[:90], fontsize=11, fontweight="600", color="#000000", y=0.98)

    handles, labels = [], []
    for axis in (ax, ax2):
        if axis is None:
            continue
        h, l = axis.get_legend_handles_labels()
        handles.extend(h)
        labels.extend(l)

    if handles:
        loc_map = {
            "right": "center left",
            "upper right": "upper right",
            "bottom": "upper center",
        }
        bbox = {
            "right": (1.02, 0.5),
            "upper right": (1.0, 1.0),
            "bottom": (0.5, -0.16),
        }
        ax.legend(
            handles,
            labels,
            loc=loc_map.get(legend_pos, "upper right"),
            bbox_to_anchor=bbox.get(legend_pos),
            ncol=1 if legend_pos == "right" else min(3, len(handles)),
            fontsize=8,
            labelcolor=AXIS_COLOR,
            frameon=True,
            fancybox=False,
            borderpad=0.4,
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor="#FFFFFF", edgecolor="none", bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)
    return True
