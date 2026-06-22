"""月报 LaTeX 导出单元测试。"""
from __future__ import annotations

from pathlib import Path

from app.services.report_latex import build_monthly_report_tex, escape_latex, write_monthly_report_tex
from app.templates.monthly_report import default_content


def test_escape_latex_special_chars():
    assert escape_latex("100% & $50") == r"100\% \& \$50"
    assert escape_latex("Brent_WTI") == r"Brent\_WTI"


def test_build_monthly_report_tex_contains_structure():
    content = default_content("2026年第5期（总56期）", "2026年6月")
    content["summary"] = "本月国际油价震荡下行。"
    for sec in content["sections"]:
        if sec.get("id") == "review_futures":
            sec["content"] = "Brent 期货均价 72 美元/桶。"
            break

    tex = build_monthly_report_tex(content, charts={})
    assert r"\documentclass" in tex
    assert "cnoocblue" in tex
    assert r"\reportcover" in tex
    assert r"\begin{tcolorbox}" in tex
    assert "中国海油集团能源经济研究院" in tex
    assert "内容摘要" in tex
    assert "一、原油市场回顾" in tex
    assert "Brent 期货均价" in tex
    assert r"\rowcolor{tableheadbg}" in tex
    assert r"\end{document}" in tex


def test_write_monthly_report_tex_creates_file(tmp_path: Path):
    content = default_content("2026年第5期", "2026年6月")
    out = tmp_path / "report.tex"
    write_monthly_report_tex(content, out, charts={}, work_dir=tmp_path)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "国际油价月报" in text
