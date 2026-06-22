from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.deps import require_admin
from app.services.llm_log import LlmLogService

router = APIRouter(prefix="/llm-logs", tags=["llm-logs"], dependencies=[Depends(require_admin)])


@router.get("")
def list_llm_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: str | None = None,
    status: str | None = None,
):
    return LlmLogService().list_logs(
        page=page,
        page_size=page_size,
        source=source,
        status=status,
    )


@router.get("/sources")
def list_llm_log_sources():
    return LlmLogService().list_sources()


@router.get("/{log_id}")
def get_llm_log(log_id: int):
    try:
        return LlmLogService().get_log(log_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
