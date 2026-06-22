"""Playwright 将 PyEcharts HTML 导出为高分辨率 PNG。"""
from __future__ import annotations

import base64
import logging
import shutil
import tempfile
from pathlib import Path

from app.core.config import settings
from app.services import chart_echarts_style as theme
from app.services.chart_style import MIN_CHART_BYTES

logger = logging.getLogger(__name__)

ECHARTS_JS = Path(__file__).resolve().parent.parent / "static" / "echarts" / "echarts.min.js"


def _export_pixel_ratio() -> int:
    scale = settings.chart_echarts_device_scale or theme.EXPORT_PIXEL_RATIO
    return max(2, min(int(scale), 4))


def _decode_data_url(data_url: str) -> bytes | None:
    if not data_url or not data_url.startswith("data:image"):
        return None
    try:
        _, encoded = data_url.split(",", 1)
        return base64.b64decode(encoded)
    except (ValueError, TypeError):
        return None


def html_to_png(html_path: Path, out: Path) -> bool:
    """在浏览器中渲染 HTML，通过 ECharts getDataURL 导出高清 PNG。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("未安装 playwright，无法导出 PyEcharts PNG")
        return False

    w = settings.chart_echarts_width or theme.CANVAS_WIDTH
    h = settings.chart_echarts_height or theme.CANVAS_HEIGHT
    pixel_ratio = _export_pixel_ratio()

    try:
        with sync_playwright() as p:
            browser_type = getattr(p, settings.playwright_browser, p.chromium)
            browser = browser_type.launch(headless=True)
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(html_path.resolve().as_uri(), wait_until="load")
            page.wait_for_function(
                """() => {
                    if (typeof echarts === 'undefined') return false;
                    const el = document.querySelector('.chart-container');
                    if (!el) return false;
                    const inst = echarts.getInstanceByDom(el);
                    return inst && inst.getWidth() > 0;
                }""",
                timeout=15_000,
            )
            page.evaluate(
                """() => {
                    const el = document.querySelector('.chart-container');
                    const inst = echarts.getInstanceByDom(el);
                    if (inst) inst.resize();
                }"""
            )
            page.wait_for_timeout(200)
            data_url = page.evaluate(
                """([ratio, bg]) => {
                    const el = document.querySelector('.chart-container');
                    const inst = echarts.getInstanceByDom(el);
                    if (!inst) return null;
                    return inst.getDataURL({
                        type: 'png',
                        pixelRatio: ratio,
                        backgroundColor: bg,
                    });
                }""",
                [pixel_ratio, theme.BG_COLOR],
            )
            browser.close()
    except Exception as exc:
        logger.warning("Playwright 导出失败: %s", exc)
        return False

    png_bytes = _decode_data_url(data_url)
    if not png_bytes:
        logger.warning("ECharts getDataURL 未返回有效 PNG")
        return False
    if len(png_bytes) < theme.MIN_EXPORT_BYTES:
        logger.warning(
            "PyEcharts PNG 过小 (%d bytes < %d)，疑似渲染空白",
            len(png_bytes),
            theme.MIN_EXPORT_BYTES,
        )
        return False

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png_bytes)
    return len(png_bytes) >= MIN_CHART_BYTES


def render_chart_to_png(chart: object, out: Path) -> bool:
    """PyEcharts Chart → 临时 HTML（本地 echarts.js）→ 高清 PNG。"""
    if not ECHARTS_JS.is_file():
        logger.error("缺少本地 ECharts 资源: %s", ECHARTS_JS)
        return False

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        html_path = tmpdir / "chart.html"
        shutil.copy2(ECHARTS_JS, tmpdir / "echarts.min.js")
        chart.js_host = "./"  # type: ignore[attr-defined]
        chart.render(str(html_path))  # type: ignore[attr-defined]
        html_path.write_text(theme.inject_export_css(html_path.read_text(encoding="utf-8")), encoding="utf-8")
        return html_to_png(html_path, out)
