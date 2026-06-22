"""月报图表渲染路由（matplotlib / PyEcharts 双引擎）。"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.chart_matplotlib import render_report_chart_matplotlib

logger = logging.getLogger(__name__)


def render_report_chart(config: dict[str, Any], out: Path) -> bool:
    """按 CHART_RENDERER 选择引擎；echarts 失败时可回退 matplotlib。"""
    renderer = (settings.chart_renderer or "matplotlib").lower()
    title = str(config.get("title", ""))[:60]
    t0 = time.perf_counter()

    if renderer == "echarts":
        from app.services.chart_echarts import render_report_chart_echarts

        ok = render_report_chart_echarts(config, out)
        if ok:
            logger.info("月报图表 echarts 渲染成功: %s (%.2fs)", title, time.perf_counter() - t0)
            return True
        if settings.chart_echarts_fallback:
            logger.warning("PyEcharts 渲染失败，回退 matplotlib: %s", title)
            ok = render_report_chart_matplotlib(config, out)
            if ok:
                logger.info("月报图表 matplotlib 回退成功: %s (%.2fs)", title, time.perf_counter() - t0)
            return ok
        logger.error("PyEcharts 渲染失败且未开启回退 (CHART_ECHARTS_FALLBACK=false): %s", title)
        return False

    ok = render_report_chart_matplotlib(config, out)
    if ok:
        logger.debug("月报图表 matplotlib 渲染成功: %s (%.2fs)", title, time.perf_counter() - t0)
    return ok
