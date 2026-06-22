import json
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.timezone import now_beijing_naive
from app.models.forecast_result import ForecastResult
from app.models.price_series import PriceSeries
from app.services.analytics import AnalyticsService


class ForecastService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics = AnalyticsService(db)

    def run_forecast(
        self,
        symbol: str = "Brent",
        horizon_months: int = 1,
        *,
        year: int | None = None,
        month: int | None = None,
    ) -> dict[str, Any]:
        rows = (
            self.db.query(PriceSeries)
            .filter(PriceSeries.symbol == symbol)
            .order_by(PriceSeries.trade_date)
            .all()
        )
        if len(rows) < 10:
            baseline = 61.0
            evidence = {"method": "fallback_default", "reason": "insufficient_data"}
        else:
            df = pd.DataFrame([{"date": r.trade_date, "price": r.price} for r in rows])
            df["month"] = pd.to_datetime(df["date"]).dt.to_period("M")
            monthly = df.groupby("month")["price"].mean().reset_index()
            monthly["price"] = monthly["price"].astype(float)
            if len(monthly) >= 3:
                ma3 = monthly["price"].tail(3).mean()
                trend = monthly["price"].diff().tail(3).mean()
                baseline = float(ma3 + (trend or 0))
            else:
                baseline = float(monthly["price"].mean())
            volatility = float(monthly["price"].std() or 2.0)
            evidence = {
                "method": "moving_average_trend",
                "monthly_points": len(monthly),
                "volatility": round(volatility, 2),
                "last_month_avg": round(float(monthly["price"].iloc[-1]), 2),
            }

        low = round(baseline - 3, 2)
        high = round(baseline + 3, 2)
        scenarios = [
            ("baseline", round(baseline, 2), low, high),
            ("optimistic", round(baseline + 3, 2), round(baseline, 2), round(baseline + 6, 2)),
            ("pessimistic", round(baseline - 3, 2), round(baseline - 6, 2), round(baseline, 2)),
        ]
        if year and month:
            period = f"{year}-{month:02d}"
        else:
            period = now_beijing_naive().strftime("%Y-%m")
        saved = []
        for scenario, point, lo, hi in scenarios:
            fr = ForecastResult(
                symbol=symbol,
                period=period,
                scenario=scenario,
                point_value=point,
                low_value=lo,
                high_value=hi,
                model_name="ma_trend_v1",
                evidence_json=json.dumps(evidence, ensure_ascii=False),
            )
            self.db.add(fr)
            saved.append(fr)
        self.db.commit()
        return {
            "symbol": symbol,
            "period": period,
            "scenarios": [
                {"scenario": s, "point": p, "low": lo, "high": hi} for s, p, lo, hi in scenarios
            ],
            "evidence": evidence,
        }

    def get_forecast_for_period(
        self, symbol: str, year: int, month: int, *, auto_run: bool = True
    ) -> dict[str, Any] | None:
        """获取指定月份最新情景预测；无记录时可选择自动运行模型。"""
        period = f"{year}-{month:02d}"
        rows = (
            self.db.query(ForecastResult)
            .filter(ForecastResult.symbol == symbol, ForecastResult.period == period)
            .order_by(ForecastResult.created_at.desc())
            .all()
        )
        if not rows and auto_run:
            result = self.run_forecast(symbol, year=year, month=month)
            if result.get("period") == period:
                return result
            rows = (
                self.db.query(ForecastResult)
                .filter(ForecastResult.symbol == symbol, ForecastResult.period == period)
                .order_by(ForecastResult.created_at.desc())
                .all()
            )
        if not rows:
            rows = (
                self.db.query(ForecastResult)
                .filter(ForecastResult.symbol == symbol)
                .order_by(ForecastResult.created_at.desc())
                .limit(9)
                .all()
            )
            if not rows:
                return None
            period = rows[0].period

        by_scenario: dict[str, dict[str, Any]] = {}
        evidence: dict[str, Any] = {}
        for r in rows:
            if r.period != period or r.scenario in by_scenario:
                continue
            by_scenario[r.scenario] = {
                "scenario": r.scenario,
                "point": r.point_value,
                "low": r.low_value,
                "high": r.high_value,
            }
            if not evidence and r.evidence_json:
                try:
                    evidence = json.loads(r.evidence_json)
                except json.JSONDecodeError:
                    evidence = {}
        if not by_scenario:
            return None
        order = ["baseline", "optimistic", "pessimistic"]
        scenarios = [by_scenario[s] for s in order if s in by_scenario]
        return {
            "symbol": symbol,
            "period": period,
            "scenarios": scenarios,
            "evidence": evidence,
            "model_name": rows[0].model_name,
        }

    def list_forecasts(self, symbol: str | None = None) -> list[dict[str, Any]]:
        q = self.db.query(ForecastResult)
        if symbol:
            q = q.filter(ForecastResult.symbol == symbol)
        rows = q.order_by(ForecastResult.created_at.desc()).limit(20).all()
        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "period": r.period,
                "scenario": r.scenario,
                "point_value": r.point_value,
                "low_value": r.low_value,
                "high_value": r.high_value,
                "model_name": r.model_name,
            }
            for r in rows
        ]

    def backtest_summary(self, symbol: str = "Brent") -> dict[str, Any]:
        rows = (
            self.db.query(PriceSeries)
            .filter(PriceSeries.symbol == symbol)
            .order_by(PriceSeries.trade_date)
            .all()
        )
        if len(rows) < 20:
            return {"symbol": symbol, "mape": None, "direction_accuracy": None}
        df = pd.DataFrame([{"date": r.trade_date, "price": r.price} for r in rows])
        df["month"] = pd.to_datetime(df["date"]).dt.to_period("M")
        monthly = df.groupby("month")["price"].mean().reset_index()
        preds = monthly["price"].shift(1).rolling(3).mean()
        actual = monthly["price"]
        valid = preds.notna() & actual.notna()
        if valid.sum() == 0:
            return {"symbol": symbol, "mape": None, "direction_accuracy": None}
        mape = float((np.abs((actual[valid] - preds[valid]) / actual[valid])).mean() * 100)
        direction = float(
            np.mean(np.sign(actual[valid].diff()) == np.sign(preds[valid].diff()))
        )
        return {"symbol": symbol, "mape": round(mape, 2), "direction_accuracy": round(direction, 2)}
