"""月报服务：生成（调用 skill）、增删改查、导出 Word（含表格）。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timezone import beijing_timestamp, format_beijing_iso, now_beijing_naive
from app.models.report import Report
from app.models.user import User
from app.models.report_template import ReportTemplate
from app.services.analytics import AnalyticsService
from app.services.chart_export import ChartExportService
from app.services.report_table_data import (
    ReportTableDataService,
    SYSTEM_TABLE_KEYS,
    normalize_report_periods,
    outlook_from_review,
    review_from_outlook,
)
from app.services.report_docx import build_monthly_report_document
from app.services.report_latex import (
    compile_latex_to_pdf,
    convert_tex_to_docx,
    latex_tools_available,
    write_monthly_report_tex,
)
from app.skills.evidence_guard import guard_report_content
from app.skills.report_skill import ReportSkill
from app.skills.report_unrestricted_skill import ReportUnrestrictedSkill
from app.templates.monthly_report import (
    MONTHLY_REPORT_TEMPLATE,
    default_content,
    get_template_json,
)


class ReportService:
    def __init__(self, db: Session):
        self.db = db
        self.skill = ReportSkill(db)
        self.unrestricted_skill = ReportUnrestrictedSkill(db)

    # ------------------------------------------------------------------ #
    def ensure_default_template(self) -> ReportTemplate:
        tpl = self.db.query(ReportTemplate).filter(ReportTemplate.name == "国际油价月报").first()
        if tpl:
            latest = get_template_json()
            if tpl.structure_json != latest:
                tpl.structure_json = latest
                self.db.commit()
            return tpl
        tpl = ReportTemplate(
            name="国际油价月报",
            report_type="monthly",
            structure_json=get_template_json(),
        )
        self.db.add(tpl)
        self.db.commit()
        self.db.refresh(tpl)
        return tpl

    # ------------------------------------------------------------------ #
    @staticmethod
    def _scope_query(query, user: User | None):
        if user is None or user.role == "admin":
            return query
        return query.filter(Report.user_id == user.id)

    def generate_monthly_draft(
        self,
        issue_no: str,
        report_date: str,
        review_month: tuple[int, int],
        outlook_month: tuple[int, int],
        provider: str | None = None,
        model: str | None = None,
        mode: str = "deep_research",
        extra_instruction: str = "",
        trusted_sources_only: bool = False,
        unrestricted_mode: bool = False,
        user: User | None = None,
    ) -> dict[str, Any]:
        review_month, outlook_month = normalize_report_periods(
            review_month[0],
            review_month[1],
            outlook_month[0],
            outlook_month[1],
            primary="outlook",
        )
        tpl = self.ensure_default_template()
        if unrestricted_mode:
            result = self.unrestricted_skill.generate(
                issue_no=issue_no,
                report_date=report_date,
                review_month=review_month,
                outlook_month=outlook_month,
                provider=provider,
                model=model,
                mode=mode,
                extra_instruction=extra_instruction,
            )
        else:
            result = self.skill.generate(
                issue_no=issue_no,
                report_date=report_date,
                review_month=review_month,
                outlook_month=outlook_month,
                provider=provider,
                model=model,
                mode=mode,
                extra_instruction=extra_instruction,
                trusted_sources_only=trusted_sources_only,
            )
        content = result["content"]
        report = Report(
            template_id=tpl.id,
            title=f"{content['cover']['title']}{issue_no}",
            issue_no=issue_no,
            report_date=report_date,
            status="draft",
            user_id=user.id if user else None,
            content_json=json.dumps(content, ensure_ascii=False),
            evidence_json=json.dumps(
                {
                    "evidence": result["evidence"],
                    "sources": result["sources_used"],
                    "web_references": result.get("web_references", []),
                    "llm_used": result["llm_used"],
                    "references": result.get("references", {}),
                    "outlook_year": outlook_month[0],
                    "outlook_month": outlook_month[1],
                    "review_year": review_month[0],
                    "review_month": review_month[1],
                },
                ensure_ascii=False,
                default=str,
            ),
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        docx_path = self.export_docx(report.id)
        report.docx_path = str(docx_path)
        self.db.commit()
        return {
            "id": report.id,
            "title": report.title,
            "status": report.status,
            "docx_path": report.docx_path,
            "content": content,
            "evidence": result["evidence"],
            "sources": result["sources_used"],
            "web_references": result.get("web_references", []),
            "llm_used": result["llm_used"],
            "references": result.get("references", {}),
            "outlook_year": outlook_month[0],
            "outlook_month": outlook_month[1],
            "review_year": review_month[0],
            "review_month": review_month[1],
            "table_snapshots": (result.get("evidence") or {}).get("table_snapshots", {}),
        }

    # ------------------------------------------------------------------ #
    def list_reports(self, user: User | None = None) -> list[dict[str, Any]]:
        query = self.db.query(Report).order_by(Report.created_at.desc())
        rows = self._scope_query(query, user).all()
        return [
            {
                "id": r.id,
                "title": r.title,
                "issue_no": r.issue_no,
                "report_date": r.report_date,
                "status": r.status,
                "docx_path": r.docx_path,
                "updated_at": format_beijing_iso(r.updated_at),
            }
            for r in rows
        ]

    def get_report(self, report_id: int, user: User | None = None) -> Report | None:
        report = self.db.get(Report, report_id)
        if not report:
            return None
        if user and user.role != "admin" and report.user_id not in (user.id, None):
            return None
        return report

    def get_report_detail(self, report_id: int, user: User | None = None) -> dict[str, Any]:
        report = self.get_report(report_id, user)
        if not report:
            raise ValueError("Report not found")
        meta = json.loads(report.evidence_json or "{}")
        content = json.loads(report.content_json)
        content = self._refresh_report_tables(content, meta)
        content = self._refresh_spot_guard(content, meta)
        return {
            "id": report.id,
            "title": report.title,
            "issue_no": report.issue_no,
            "report_date": report.report_date,
            "status": report.status,
            "content": content,
            "evidence": meta.get("evidence", meta),
            "sources": meta.get("sources", []),
            "web_references": meta.get("web_references", []),
            "llm_used": meta.get("llm_used", False),
            "references": meta.get("references", {}),
            "charts": meta.get("charts", {}),
            "outlook_year": meta.get("outlook_year"),
            "outlook_month": meta.get("outlook_month"),
            "review_year": meta.get("review_year"),
            "review_month": meta.get("review_month"),
            "docx_path": report.docx_path,
            "structure": MONTHLY_REPORT_TEMPLATE,
        }

    def update_content(
        self,
        report_id: int,
        content: dict[str, Any],
        title: str | None = None,
        user: User | None = None,
    ) -> dict[str, Any]:
        report = self.get_report(report_id, user)
        if not report:
            raise ValueError("Report not found")
        report.content_json = json.dumps(content, ensure_ascii=False)
        if title:
            report.title = title
        report.status = "reviewed"
        report.updated_at = now_beijing_naive()
        self.db.commit()
        return {"id": report.id, "status": "updated"}

    def delete_report(self, report_id: int, user: User | None = None) -> None:
        report = self.get_report(report_id, user)
        if not report:
            raise ValueError("Report not found")
        if report.docx_path:
            path = Path(report.docx_path)
            if path.exists():
                path.unlink()
        self.db.delete(report)
        self.db.commit()

    # ------------------------------------------------------------------ #
    def _chart_period(self, report: Report) -> tuple[int | None, int | None]:
        meta = json.loads(report.evidence_json or "{}")
        return meta.get("review_year"), meta.get("review_month")

    def _refresh_report_tables(
        self,
        content: dict[str, Any],
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        """从 report_table_snapshots 重载 6 张系统表。"""
        ry = meta.get("review_year")
        rm = meta.get("review_month")
        oy = meta.get("outlook_year")
        om = meta.get("outlook_month")
        if oy and om:
            ry, rm = review_from_outlook(int(oy), int(om))
        elif ry and rm:
            oy, om = outlook_from_review(int(ry), int(rm))
        else:
            return content
        tables, _ = ReportTableDataService(self.db).load_for_report(int(ry), int(rm), int(oy), int(om))
        for key in SYSTEM_TABLE_KEYS:
            if key in tables:
                tbl = content.setdefault("tables", {}).setdefault(key, {})
                tbl.update({
                    k: tables[key][k]
                    for k in ("title", "source", "headers", "rows")
                    if k in tables[key]
                })
        return content

    def _refresh_spot_guard(
        self,
        content: dict[str, Any],
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        """打开/导出时重算 spot_market 并校验 review_spot 方向一致性。"""
        ry = meta.get("review_year")
        rm = meta.get("review_month")
        if not ry or not rm:
            return content
        spot_market = AnalyticsService(self.db).build_spot_market_evidence(int(ry), int(rm))
        evidence = dict(meta.get("evidence") or {})
        evidence["spot_market"] = spot_market
        return guard_report_content(content, evidence)

    def _prepare_export_bundle(
        self, report_id: int, user: User | None = None
    ) -> tuple[Report, dict[str, Any], dict[str, str], int | None, int | None]:
        """导出前刷新系统表、校验 spot 方向并生成图表。"""
        report = self.get_report(report_id, user)
        if not report:
            raise ValueError("Report not found")
        content = json.loads(report.content_json)
        if "sections" not in content:
            content = self._upgrade_legacy(content, report)
        meta = json.loads(report.evidence_json or "{}")
        content = self._refresh_report_tables(content, meta)
        content = self._refresh_spot_guard(content, meta)
        ry, rm = self._chart_period(report)
        charts = ChartExportService(self.db).generate_report_charts(
            report_id, content, review_year=ry, review_month=rm
        )
        self._merge_evidence_meta(report, {"charts": charts})
        return report, content, charts, ry, rm

    def _latex_work_dir(self, report_id: int) -> Path:
        return settings.exports_dir / f"latex_{report_id}_{beijing_timestamp()}"

    def export_tex(self, report_id: int, user: User | None = None) -> Path:
        _, content, charts, ry, rm = self._prepare_export_bundle(report_id, user)
        work_dir = self._latex_work_dir(report_id)
        tex_path = work_dir / "monthly_report.tex"
        write_monthly_report_tex(
            content, tex_path, charts, review_year=ry, review_month=rm, work_dir=work_dir
        )
        return tex_path

    def export_pdf(self, report_id: int, user: User | None = None) -> Path:
        tex_path = self.export_tex(report_id, user)
        pdf_path = compile_latex_to_pdf(tex_path, tex_path.parent)
        out = settings.exports_dir / f"report_{report_id}_{beijing_timestamp()}.pdf"
        shutil.copy2(pdf_path, out)
        return out

    def export_docx_via_latex(self, report_id: int, user: User | None = None) -> Path:
        tex_path = self.export_tex(report_id, user)
        out = settings.exports_dir / f"report_{report_id}_{beijing_timestamp()}.docx"
        convert_tex_to_docx(tex_path, out)
        return out

    def export_docx(self, report_id: int, user: User | None = None, *, via_latex: bool = False) -> Path:
        tools = latex_tools_available()
        if via_latex and tools["pandoc"]:
            try:
                return self.export_docx_via_latex(report_id, user)
            except RuntimeError:
                pass
        _, content, charts, ry, rm = self._prepare_export_bundle(report_id, user)
        doc = build_monthly_report_document(
            content, charts, review_year=ry, review_month=rm
        )
        out = settings.exports_dir / f"report_{report_id}_{beijing_timestamp()}.docx"
        doc.save(out)
        return out

    def _resolve_charts(
        self,
        report: Report,
        content: dict[str, Any],
        charts: dict[str, str] | None = None,
    ) -> dict[str, str]:
        need_regenerate = not charts
        if charts and not need_regenerate:
            need_regenerate = any(
                not ChartExportService.is_valid_chart_file(path) for path in charts.values()
            )
        if need_regenerate:
            ry, rm = self._chart_period(report)
            charts = ChartExportService(self.db).generate_report_charts(
                report.id, content, review_year=ry, review_month=rm
            )
            self._merge_evidence_meta(report, {"charts": charts})
        return charts or {}

    def get_chart_file(self, report_id: int, chart_id: str, user: User | None = None) -> Path:
        report = self.get_report(report_id, user)
        if not report:
            raise ValueError("Report not found")
        content = json.loads(report.content_json)
        meta = json.loads(report.evidence_json or "{}")
        charts = self._resolve_charts(report, content, meta.get("charts") or {})
        path_str = charts.get(chart_id)
        if not path_str:
            raise ValueError("Chart not available")
        path = Path(path_str)
        if not ChartExportService.is_valid_chart_file(path):
            raise ValueError("Chart file missing")
        return path

    def ensure_charts(self, report_id: int, user: User | None = None) -> dict[str, str]:
        report = self.get_report(report_id, user)
        if not report:
            raise ValueError("Report not found")
        content = json.loads(report.content_json)
        meta = json.loads(report.evidence_json or "{}")
        return self._resolve_charts(report, content, meta.get("charts") or {})

    def _merge_evidence_meta(self, report: Report, extra: dict[str, Any]) -> None:
        try:
            meta = json.loads(report.evidence_json or "{}")
        except json.JSONDecodeError:
            meta = {}
        meta.update(extra)
        report.evidence_json = json.dumps(meta, ensure_ascii=False, default=str)
        self.db.commit()

    def _upgrade_legacy(self, legacy: dict[str, Any], report: Report) -> dict[str, Any]:
        """把旧版扁平 content 升级为结构化 content。"""
        content = default_content(report.issue_no, report.report_date)
        content["cover"]["org"] = legacy.get("cover_org", content["cover"]["org"])
        content["cover"]["dept"] = legacy.get("cover_dept", content["cover"]["dept"])
        content["summary"] = legacy.get("summary", "")
        for sec in content["sections"]:
            if sec["level"] == 2 and legacy.get(sec["id"]):
                sec["content"] = legacy[sec["id"]]
        content["approval"] = {
            "author": legacy.get("approval_author", ""),
            "reviewer": legacy.get("approval_reviewer", ""),
            "approver": legacy.get("approval_approver", ""),
            "signer": "",
        }
        return content
