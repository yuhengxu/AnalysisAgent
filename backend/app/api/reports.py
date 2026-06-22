from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.common import ReportGenerateRequest, ReportUpdateRequest
from app.services.report import ReportService
from app.services.report_latex import latex_tools_available
from app.services.report_tasks import create_task, get_task, start_task, task_to_dict

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def list_reports(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return ReportService(db).list_reports(user)


@router.get("/template")
def get_template(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = ReportService(db).ensure_default_template()
    import json

    return {"id": tpl.id, "name": tpl.name, "structure": json.loads(tpl.structure_json)}


@router.post("/generate")
def generate_report(
    body: ReportGenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ReportService(db).generate_monthly_draft(
        issue_no=body.issue_no,
        report_date=body.report_date,
        review_month=(body.review_year, body.review_month),
        outlook_month=(body.outlook_year, body.outlook_month),
        provider=body.model_provider,
        model=body.model_name,
        mode=body.mode,
        extra_instruction=body.extra_instruction,
        trusted_sources_only=body.trusted_sources_only,
        unrestricted_mode=body.unrestricted_mode,
        user=user,
    )


@router.post("/generate/async")
def generate_report_async(
    body: ReportGenerateRequest,
    user: User = Depends(get_current_user),
):
    """异步生成：立即返回 task_id，前端轮询 /generate/tasks/{task_id} 获取进度。"""
    task = create_task(body, user_id=user.id)
    start_task(task.id, body)
    return task_to_dict(task)


@router.get("/generate/tasks/{task_id}")
def get_report_task(task_id: str, user: User = Depends(get_current_user)):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return task_to_dict(task)


@router.get("/export-tools")
def get_export_tools(user: User = Depends(get_current_user)):
    """返回 LaTeX 导出工具（xelatex / pandoc）是否可用。"""
    return latex_tools_available()


@router.get("/{report_id}")
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        detail = ReportService(db).get_report_detail(report_id, user)
        if not detail:
            raise ValueError("Report not found")
        ReportService(db).ensure_charts(report_id, user)
        return ReportService(db).get_report_detail(report_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{report_id}")
def update_report(
    report_id: int,
    body: ReportUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return ReportService(db).update_content(report_id, body.content, body.title, user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{report_id}/export")
def export_report(
    report_id: int,
    format: str = Query("docx", description="导出格式：docx | pdf | tex"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc = ReportService(db)
    fmt = format.lower().strip()
    media_types = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
        "tex": "application/x-tex",
    }
    try:
        if fmt == "pdf":
            path = svc.export_pdf(report_id, user)
        elif fmt == "tex":
            path = svc.export_tex(report_id, user)
        elif fmt == "docx":
            path = svc.export_docx(report_id, user)
        else:
            raise HTTPException(status_code=400, detail=f"不支持的导出格式: {format}")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name, media_type=media_types[fmt])


@router.get("/{report_id}/charts/{chart_id}")
def get_report_chart(
    report_id: int,
    chart_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        path = ReportService(db).get_chart_file(report_id, chart_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="image/png")


@router.delete("/{report_id}")
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        ReportService(db).delete_report(report_id, user)
        return {"id": report_id, "status": "deleted"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
