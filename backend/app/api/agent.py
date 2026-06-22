from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.common import AgentChatRequest, AgentRequest, ReviseRequest
from app.services.agent import AgentService
from app.services.report import ReportService

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/run")
def run_agent(
    body: AgentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return AgentService(db).run(
        prompt=body.prompt,
        skill=body.skill,
        model_provider=body.model_provider,
        model_name=body.model_name,
        mode=body.mode,
        trusted_sources_only=body.trusted_sources_only,
    )


@router.post("/chat")
def chat_agent(
    body: AgentChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return AgentService(db).chat(
        messages=[m.model_dump() for m in body.messages],
        skill_hint=body.skill_hint,
        model_provider=body.model_provider,
        model_name=body.model_name,
        mode=body.mode,
        trusted_sources_only=body.trusted_sources_only,
    )


@router.get("/skills")
def list_skills(user: User = Depends(get_current_user)):
    return [{"id": k, "name": v} for k, v in AgentService.SKILLS.items()]


@router.get("/tools")
def list_agent_tools(user: User = Depends(get_current_user)):
    from app.services.agent_tools import AgentTools

    return AgentTools.list_tools()


@router.post("/revise/{report_id}")
def revise_report(
    report_id: int,
    body: ReviseRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not ReportService(db).get_report(report_id, user):
        raise HTTPException(status_code=404, detail="Report not found")
    return AgentService(db).revise_selection(
        report_id,
        body.section_id,
        body.instruction,
        provider=body.model_provider,
        model=body.model_name,
        mode=body.mode,
    )
