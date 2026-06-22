from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.common import (
    PredictionGenerateRequest,
    PredictionReviseRequest,
    PredictionUpdateRequest,
)
from app.services.prediction import PredictionService
from app.services.prediction_tasks import create_task, get_task, start_task, task_to_dict
from app.skills.sources import TRUSTED_SOURCES

router = APIRouter(prefix="/prediction", tags=["prediction"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("")
def list_predictions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return PredictionService(db).list_predictions(user)


@router.get("/sources")
def list_sources(user: User = Depends(get_current_user)):
    return TRUSTED_SOURCES


@router.post("/generate")
def generate_prediction(
    body: PredictionGenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return PredictionService(db).generate(
        symbol=body.symbol,
        year=body.year,
        month=body.month,
        provider=body.model_provider,
        model=body.model_name,
        mode=body.mode,
        extra_instruction=body.extra_instruction,
        trusted_sources_only=body.trusted_sources_only,
        unrestricted_mode=body.unrestricted_mode,
        user=user,
    )


@router.post("/generate/async")
def generate_prediction_async(body: PredictionGenerateRequest, user: User = Depends(get_current_user)):
    """异步生成：立即返回 task_id，前端轮询 /generate/tasks/{task_id} 获取进度。"""
    task = create_task(body=body)
    start_task(task.id, body)
    return task_to_dict(task)


@router.get("/generate/tasks/{task_id}")
def get_prediction_task(task_id: str, user: User = Depends(get_current_user)):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return task_to_dict(task)


@router.get("/{pred_id}")
def get_prediction(
    pred_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return PredictionService(db).get_detail(pred_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{pred_id}")
def update_prediction(
    pred_id: int,
    body: PredictionUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return PredictionService(db).update_content(pred_id, body.content, body.title, user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{pred_id}/revise")
def revise_prediction_field(
    pred_id: int,
    body: PredictionReviseRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return PredictionService(db).revise_factor_field(
            pred_id,
            factor_idx=body.factor_idx,
            field=body.field,
            instruction=body.instruction,
            provider=body.model_provider,
            model=body.model_name,
            mode=body.mode,
            user=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{pred_id}/export")
def export_prediction(
    pred_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        path = PredictionService(db).export_xlsx(pred_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name, media_type=XLSX_MEDIA)


@router.delete("/{pred_id}")
def delete_prediction(
    pred_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        PredictionService(db).delete(pred_id, user)
        return {"id": pred_id, "status": "deleted"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
