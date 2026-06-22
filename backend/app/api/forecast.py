from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_page
from app.services.forecast import ForecastService

router = APIRouter(prefix="/forecast", tags=["forecast"], dependencies=[Depends(require_page("forecast"))])


@router.post("/run")
def run_forecast(symbol: str = Query("Brent"), db: Session = Depends(get_db)):
    return ForecastService(db).run_forecast(symbol)


@router.get("")
def list_forecasts(symbol: str | None = None, db: Session = Depends(get_db)):
    return ForecastService(db).list_forecasts(symbol)


@router.get("/backtest")
def backtest(symbol: str = "Brent", db: Session = Depends(get_db)):
    return ForecastService(db).backtest_summary(symbol)
