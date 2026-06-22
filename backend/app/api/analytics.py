from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_page
from app.models.user import User
from app.services.analytics import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(get_current_user)])


@router.get("/dashboard")
def dashboard(
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_page("dashboard")),
):
    return AnalyticsService(db).dashboard_summary(start_date, end_date)


@router.get("/prices")
def prices(
    symbols: str = Query("Brent,WTI"),
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    return AnalyticsService(db).query_price_series(sym_list, start_date, end_date)


@router.get("/spread")
def spread(
    symbol_a: str = "Brent",
    symbol_b: str = "WTI",
    db: Session = Depends(get_db),
):
    return AnalyticsService(db).calc_spread(symbol_a, symbol_b)


@router.get("/balance")
def balance(agency: str | None = None, db: Session = Depends(get_db)):
    return AnalyticsService(db).query_balance_forecast(agency)


@router.get("/factors")
def factors(report_month: str | None = None, db: Session = Depends(get_db)):
    return AnalyticsService(db).query_factor_assessments(report_month)


@router.get("/charts/{chart_type}")
def chart(
    chart_type: str,
    symbols: str = Query("Brent,WTI"),
    start_date: date | None = None,
    end_date: date | None = None,
    agency: str | None = None,
    snapshot_month: str | None = None,
    daily_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    agencies = [agency] if agency else None
    return AnalyticsService(db).chart_config(
        chart_type,
        symbols=sym_list,
        start_date=start_date,
        end_date=end_date,
        agencies=agencies,
        snapshot_month=snapshot_month,
        daily_only=daily_only,
    )


@router.get("/monthly-stats")
def monthly_stats(symbol: str = "Brent", year: int = 2026, month: int = 5, db: Session = Depends(get_db)):
    return AnalyticsService(db).calc_monthly_stats(symbol, year, month)
