from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.schemas.common import AnalysisQueryParams, DataQueryParams
from app.skills.data_analysis_skill import DataAnalysisSkill

router = APIRouter(prefix="/analysis", tags=["analysis"], dependencies=[Depends(get_current_user)])


@router.post("/query")
def analysis_query(params: DataQueryParams, db: Session = Depends(get_db)):
    return DataAnalysisSkill(db).query(params)


@router.post("/run")
def analysis_run(params: AnalysisQueryParams, db: Session = Depends(get_db)):
    return DataAnalysisSkill(db).analyze(
        params,
        provider=params.model_provider,
        model=params.model_name,
        mode=params.mode,
    )
