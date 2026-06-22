from datetime import date
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.balance_forecast import BalanceForecast
from app.models.factor_assessment import FactorAssessment
from app.models.price_series import PriceSeries
from app.schemas.common import DataQueryParams
from app.services.analytics import AnalyticsService


class DataQueryService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics = AnalyticsService(db)

    def catalog(self) -> dict[str, Any]:
        price_months = (
            self.db.query(
                func.strftime("%Y", PriceSeries.trade_date),
                func.strftime("%m", PriceSeries.trade_date),
            )
            .filter(PriceSeries.source.in_(["CNEEI", "CNEEI_MONTHLY"]))
            .distinct()
            .all()
        )
        month_set = sorted({f"{y}-{int(m):02d}" for y, m in price_months if y and m})
        symbols = sorted({r[0] for r in self.db.query(PriceSeries.symbol).distinct().all()})
        agencies = sorted({r[0] for r in self.db.query(BalanceForecast.agency).distinct().all()})
        snapshot_months = sorted(
            {r[0] for r in self.db.query(BalanceForecast.snapshot_month).filter(BalanceForecast.snapshot_month != "").distinct().all()}
        )
        periods = sorted({r[0] for r in self.db.query(BalanceForecast.period).distinct().all()})
        supply_demand = sorted({r[0] for r in self.db.query(BalanceForecast.supply_demand).distinct().all()})
        report_months = sorted(
            {
                r[0]
                for r in self.db.query(FactorAssessment.report_month).distinct().all()
                if r[0] and r[0] != "unknown"
            }
        )
        categories = sorted({r[0] for r in self.db.query(FactorAssessment.category).filter(FactorAssessment.category != "").distinct().all()})
        factor_names = sorted({r[0] for r in self.db.query(FactorAssessment.factor_name).distinct().all()})

        return {
            "price": {
                "symbols": symbols,
                "month_range": {"min": month_set[0] if month_set else None, "max": month_set[-1] if month_set else None},
                "months": month_set,
                "indicators": ["price", "monthly_avg", "mom_pct", "yoy_pct", "min", "max"],
            },
            "balance": {
                "agencies": agencies,
                "snapshot_months": snapshot_months,
                "periods": periods,
                "supply_demand": supply_demand or ["供", "需", "供需差"],
            },
            "factor": {
                "report_months": report_months,
                "categories": categories,
                "names": factor_names,
                "indicators": ["importance", "assessment", "impact_direction"],
            },
        }

    def query(self, params: DataQueryParams) -> dict[str, Any]:
        if params.category == "mixed":
            return {
                "category": "mixed",
                "price": self._query_price(params),
                "balance": self._query_balance(params),
                "factor": self._query_factor(params),
            }
        if params.category == "price":
            return {"category": "price", **self._query_price(params)}
        if params.category == "balance":
            return {"category": "balance", **self._query_balance(params)}
        return {"category": "factor", **self._query_factor(params)}

    def _ym_label(self, year: int | None, month: int | None) -> str | None:
        if year and month:
            return f"{year}-{month:02d}"
        return None

    def _query_price(self, params: DataQueryParams) -> dict[str, Any]:
        symbols = params.symbols or ["Brent", "WTI"]
        start = params.start_date
        end = params.end_date
        monthly_stats: list[dict[str, Any]] = []
        if params.year and params.month:
            for sym in symbols:
                monthly_stats.append(self.analytics.calc_monthly_stats(sym, params.year, params.month))
        series = self.analytics.query_price_series(symbols, start, end)
        return {"symbols": symbols, "monthly_stats": monthly_stats, "series": series, "total": len(series)}

    def _query_balance(self, params: DataQueryParams) -> dict[str, Any]:
        snapshot = self._ym_label(params.year, params.month)
        rows = self.analytics.query_balance_forecast(
            agencies=params.agencies or None,
            snapshot_month=snapshot,
            periods=params.periods or None,
            supply_demand=params.supply_demand or None,
        )
        offset = (params.page - 1) * params.page_size
        page_rows = rows[offset : offset + params.page_size]
        return {"rows": page_rows, "total": len(rows), "snapshot_month": snapshot}

    def _query_factor(self, params: DataQueryParams) -> dict[str, Any]:
        report_month = self._ym_label(params.year, params.month)
        rows = self.analytics.query_factor_assessments(
            report_month=report_month,
            categories=params.factor_categories or None,
            factor_names=params.factor_names or None,
        )
        offset = (params.page - 1) * params.page_size
        page_rows = rows[offset : offset + params.page_size]
        return {"rows": page_rows, "total": len(rows), "report_month": report_month}

    def charts_for(self, params: DataQueryParams) -> list[dict[str, Any]]:
        charts: list[dict[str, Any]] = []
        symbols = params.symbols or ["Brent", "WTI"]
        if params.category in ("price", "mixed"):
            charts.append(
                self.analytics.chart_config(
                    "price_trend",
                    symbols=symbols,
                    start_date=params.start_date,
                    end_date=params.end_date,
                )
            )
            charts.append(
                self.analytics.chart_config(
                    "spread",
                    start_date=params.start_date,
                    end_date=params.end_date,
                )
            )
        if params.category in ("balance", "mixed"):
            snapshot = self._ym_label(params.year, params.month)
            charts.append(
                self.analytics.chart_config(
                    "balance",
                    agencies=params.agencies,
                    snapshot_month=snapshot,
                    periods=params.periods,
                    supply_demand=params.supply_demand,
                )
            )
        return charts

    def build_report_params(
        self,
        review_year: int,
        review_month: int,
        *,
        outlook_year: int | None = None,
        outlook_month: int | None = None,
    ) -> DataQueryParams:
        oy, om = outlook_year or review_year, outlook_month or review_month
        outlook_periods = [f"{oy}Q{q}" for q in range(1, 5)]
        start, end = self.analytics._month_bounds(review_year, review_month)
        return DataQueryParams(
            category="mixed",
            year=review_year,
            month=review_month,
            start_date=start,
            end_date=end,
            symbols=["Brent", "WTI"],
            agencies=["IEA", "EIA"],
            periods=outlook_periods,
            supply_demand=["供", "需"],
            indicators=["avg", "mom_pct", "yoy_pct", "value", "balance_gap"],
        )
