"""月报图表渲染入口（兼容层，委托 chart_render 双引擎路由）。"""
from __future__ import annotations

from app.services.chart_render import render_report_chart

__all__ = ["render_report_chart"]
