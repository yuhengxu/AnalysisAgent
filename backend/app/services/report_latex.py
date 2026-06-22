"""月报 LaTeX 导出：生成 .tex、编译 PDF、经 pandoc 转 Word。"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.services.chart_export import ChartExportService
from app.templates.sample_contracts import REPORT_CHART_ANCHORS, REPORT_TABLE_ANCHORS

logger = logging.getLogger(__name__)

LATEX_DIR = Path(__file__).resolve().parents[1] / "templates" / "latex"
PREAMBLE_PATH = LATEX_DIR / "monthly_report_preamble.tex"
POSTAMBLE_PATH = LATEX_DIR / "monthly_report_postamble.tex"

_LATEX_SPECIAL = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escape_latex(text: str) -> str:
    """转义 LaTeX 特殊字符。"""
    return "".join(_LATEX_SPECIAL.get(ch, ch) for ch in str(text))


def latex_tools_available() -> dict[str, bool]:
    """检测 xelatex / pandoc 是否可用。"""
    return {
        "xelatex": shutil.which("xelatex") is not None,
        "pandoc": shutil.which("pandoc") is not None,
    }


def build_monthly_report_tex(
    content: dict[str, Any],
    charts: dict[str, str] | None = None,
    *,
    review_year: int | None = None,
    review_month: int | None = None,
    chart_dir: Path | None = None,
) -> str:
    """根据结构化月报 JSON 生成完整 LaTeX 源码。"""
    charts = charts or {}
    parts: list[str] = [_read_template(PREAMBLE_PATH)]

    cover = content.get("cover", {})
    parts.append(
        "\\reportcover"
        f"{{{escape_latex(cover.get('org', ''))}}}"
        f"{{{escape_latex(cover.get('title', ''))}}}"
        f"{{{escape_latex(cover.get('issue', ''))}}}"
        f"{{{escape_latex(cover.get('dept', ''))}}}"
        f"{{{escape_latex(cover.get('date', ''))}}}\n"
    )

    summary = str(content.get("summary", "")).strip()
    if summary:
        summary_body = "\n\n".join(
            f"\\reportbody{{{escape_latex(block)}}}"
            for block in _split_paragraphs(summary)
        )
        parts.append(f"\\reportsummary{{{summary_body}}}\n")

    tables = content.get("tables", {})
    chart_anchors: dict[str, list[dict[str, Any]]] = {}
    for item in REPORT_CHART_ANCHORS:
        chart_anchors.setdefault(item["section_id"], []).append(item)

    for sec in content.get("sections", []):
        level = sec.get("level", 2)
        title = escape_latex(sec.get("title", ""))
        if level == 1:
            parts.append(f"\\section*{{{title}}}\n")
        else:
            parts.append(f"\\subsection*{{{title}}}\n")
            body = sec.get("content")
            if body:
                for block in _split_paragraphs(str(body)):
                    parts.append(f"\\reportbody{{{escape_latex(block)}}}\n")

        sec_id = sec.get("id")
        for chart in chart_anchors.get(sec_id, []):
            tex = _render_chart(chart, charts.get(chart["id"]), content, review_year, review_month)
            if tex:
                parts.append(tex)

        for table_key, anchor_id in REPORT_TABLE_ANCHORS.items():
            if sec_id == anchor_id:
                parts.append(_render_table(tables.get(table_key), table_key=table_key))

    approval = content.get("approval", {})
    parts.append("\n\\vspace{16pt}\n\\noindent\n")
    for key in ("author", "reviewer", "approver"):
        text = approval.get(key, "")
        if text:
            parts.append(f"\\reportbody{{{escape_latex(text)}}}\n")

    dist = tables.get("table_distribution")
    if dist and dist.get("headers"):
        parts.append(_render_distribution_table(dist))

    signer = approval.get("signer", "")
    if signer:
        parts.append(f"\n\\vspace{{6pt}}\n\\noindent \\reportbody{{{escape_latex(signer)}}}\n")
    elif approval.get("author") or approval.get("reviewer") or approval.get("approver"):
        parts.append("\\reportapprovalline\n")

    parts.append(_read_template(POSTAMBLE_PATH))
    return "".join(parts)


def write_monthly_report_tex(
    content: dict[str, Any],
    out_path: Path,
    charts: dict[str, str] | None = None,
    *,
    review_year: int | None = None,
    review_month: int | None = None,
    work_dir: Path | None = None,
) -> Path:
    """写入 .tex 文件，并将图表复制到工作目录供 xelatex 引用。"""
    work_dir = work_dir or out_path.parent
    work_dir.mkdir(parents=True, exist_ok=True)
    _stage_charts(charts or {}, work_dir)
    tex = build_monthly_report_tex(
        content,
        charts,
        review_year=review_year,
        review_month=review_month,
    )
    out_path.write_text(tex, encoding="utf-8")
    return out_path


def compile_latex_to_pdf(tex_path: Path, work_dir: Path | None = None) -> Path:
    """使用 xelatex 编译 PDF（运行两遍以稳定目录/引用）。"""
    if not shutil.which("xelatex"):
        raise RuntimeError("未安装 xelatex，请安装 TeX Live（如 texlive-xetex ctex）")
    work_dir = work_dir or tex_path.parent
    work_dir.mkdir(parents=True, exist_ok=True)
    tex_name = tex_path.name
    cmd = [
        "xelatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        tex_name,
    ]
    for _ in range(2):
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir)
        if result.returncode != 0:
            log_tail = (result.stdout or "") + (result.stderr or "")
            raise RuntimeError(f"xelatex 编译失败:\n{log_tail[-2000:]}")
    pdf_path = work_dir / f"{tex_path.stem}.pdf"
    if not pdf_path.exists():
        raise RuntimeError("xelatex 未生成 PDF 文件")
    return pdf_path


def convert_tex_to_docx(tex_path: Path, out_path: Path) -> Path:
    """使用 pandoc 将 LaTeX 转为 Word。"""
    if not shutil.which("pandoc"):
        raise RuntimeError("未安装 pandoc，请安装后重试（apt install pandoc）")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = tex_path.parent
    cmd = [
        "pandoc",
        tex_path.name,
        "-o",
        str(out_path.resolve()),
        "--from=latex",
        "--to=docx",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir)
    if result.returncode != 0:
        log_tail = (result.stdout or "") + (result.stderr or "")
        raise RuntimeError(f"pandoc 转换失败:\n{log_tail[-2000:]}")
    return out_path


def _read_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _split_paragraphs(text: str) -> list[str]:
    blocks: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped:
            blocks.append(stripped)
    return blocks


def _stage_charts(charts: dict[str, str], work_dir: Path) -> None:
    """将图表 PNG 复制到 LaTeX 工作目录的 charts/ 子目录。"""
    chart_dir = work_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    for chart_id, path_str in charts.items():
        src = Path(path_str)
        if ChartExportService.is_valid_chart_file(str(src)):
            dst = chart_dir / f"{chart_id}.png"
            shutil.copy2(src, dst)


def _chart_filename(chart_id: str) -> str:
    return f"charts/{chart_id}.png"


def _render_chart(
    chart: dict[str, Any],
    path: str | None,
    content: dict[str, Any],
    review_year: int | None,
    review_month: int | None,
) -> str:
    if not ChartExportService.is_valid_chart_file(path):
        return ""
    rel = _chart_filename(chart["id"])
    title = ChartExportService.format_chart_title(
        chart,
        review_year=review_year,
        review_month=review_month,
        content=content,
    )
    parts = ["\n\\begin{figure}[H]\n\\centering\n"]
    parts.append(f"\\includegraphics[width=0.9\\linewidth]{{{rel}}}\n")
    if title:
        parts.append(f"\\caption{{{escape_latex(title)}}}\n")
    parts.append("\\end{figure}\n")
    source = chart.get("source", "")
    if source:
        parts.append(f"{{\\small\\color{{gray}}数据来源：{escape_latex(source)}}}\n")
    parts.append("\\vspace{6pt}\n\n")
    return "".join(parts)


def _table_caption(title: str) -> str:
    """从完整标题中提取 \\caption 文字（去掉「表X-X 」前缀）。"""
    text = title.strip()
    if text.startswith("表") and " " in text:
        return text.split(" ", 1)[1]
    return text


def _render_table(tbl: dict[str, Any] | None, *, table_key: str = "") -> str:
    if not tbl or not tbl.get("headers"):
        return ""

    headers = tbl["headers"]
    rows = tbl.get("rows", [])
    ncol = len(headers)
    title = tbl.get("title", "")
    source = tbl.get("source", "")

    parts: list[str] = ["\n\\begin{table}[H]\n\\centering\n"]
    if title:
        parts.append(f"\\caption{{{escape_latex(_table_caption(title))}}}\n")
    parts.append("\\small\n\\setlength{\\tabcolsep}{6pt}\n")

    if ncol <= 4:
        width = "0.92\\linewidth"
        if ncol == 1:
            col_spec = "Y"
        else:
            col_spec = "L{3.2cm}" + "Y" * (ncol - 1)
        parts.append(f"\\begin{{tabularx}}{{{width}}}{{{col_spec}}}\n")
    else:
        col_spec = "|" + "c|" * ncol
        parts.append(f"\\begin{{tabular}}{{{col_spec}}}\n\\hline\n")

    parts.append("\\rowcolor{tableheadbg}\n")
    header_cells = []
    for h in headers:
        cell = escape_latex(str(h))
        header_cells.append(f"\\color{{white}}\\textbf{{{cell}}}")
    parts.append(" & ".join(header_cells) + " \\\\\n")

    if ncol > 4:
        parts.append("\\hline\n")

    for idx, row in enumerate(rows):
        color = "tablerowodd" if idx % 2 == 0 else "tableroweven"
        parts.append(f"\\rowcolor{{{color}}}\n")
        cells = [escape_latex(str(row[i]) if i < len(row) else "") for i in range(ncol)]
        parts.append(" & ".join(cells) + " \\\\\n")

    if ncol <= 4:
        parts.append("\\bottomrule\n\\end{tabularx}\n")
    else:
        parts.append("\\hline\n\\end{tabular}\n")

    parts.append("\\end{table}\n")
    if source:
        parts.append(f"{{\\small\\color{{gray}}\\raggedright 数据来源：{escape_latex(source)}}}\n")
    parts.append("\\vspace{6pt}\n\n")
    return "".join(parts)


def _render_distribution_table(tbl: dict[str, Any]) -> str:
    """报送抄送表（与 report_claude.tex 一致的单列宽表格）。"""
    rows = tbl.get("rows", [])
    if not rows:
        return ""

    parts = ["\n\\reportapprovalline\n\n\\begin{table}[H]\n\\small\n"]
    parts.append("\\begin{tabularx}{\\linewidth}{|X|}\n\\hline\n")
    for row in rows:
        text = str(row[0]) if row else ""
        if "：" in text:
            label, body = text.split("：", 1)
            parts.append(f"\\textbf{{{escape_latex(label)}：}}{escape_latex(body)} \\\\\n\\hline\n")
        else:
            parts.append(f"{escape_latex(text)} \\\\\n\\hline\n")
    parts.append("\\end{tabularx}\n\\end{table}\n\n")
    return "".join(parts)
