from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.models.balance_forecast import BalanceForecast
from app.models.factor_assessment import FactorAssessment
from app.models.price_series import PriceSeries
from app.templates.monthly_report import DAILY_PRICE_SOURCE, MONTHLY_PRICE_SOURCE
from app.services.chart_style import value_axis_bounds


class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def query_price_series(
        self,
        symbols: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        daily_only: bool = False,
    ) -> list[dict[str, Any]]:
        q = self.db.query(PriceSeries)
        if symbols:
            q = q.filter(PriceSeries.symbol.in_(symbols))
        if daily_only:
            q = q.filter(PriceSeries.source == DAILY_PRICE_SOURCE)
        if start_date:
            q = q.filter(PriceSeries.trade_date >= start_date)
        if end_date:
            q = q.filter(PriceSeries.trade_date <= end_date)
        rows = q.order_by(PriceSeries.trade_date).all()
        return [
            {
                "symbol": r.symbol,
                "date": r.trade_date.isoformat(),
                "price": r.price,
                "unit": r.unit,
                "source": r.source,
            }
            for r in rows
        ]

    def latest_daily_price(self, symbol: str) -> PriceSeries | None:
        return (
            self.db.query(PriceSeries)
            .filter(PriceSeries.symbol == symbol, PriceSeries.source == DAILY_PRICE_SOURCE)
            .order_by(PriceSeries.trade_date.desc())
            .first()
        )

    def latest_daily_bounds(self, symbol: str = "Brent") -> tuple[date | None, date | None]:
        """返回某品种日频数据的最早/最晚交易日。"""
        q = self.db.query(PriceSeries).filter(
            PriceSeries.symbol == symbol,
            PriceSeries.source == DAILY_PRICE_SOURCE,
        )
        earliest = q.order_by(PriceSeries.trade_date.asc()).first()
        latest = q.order_by(PriceSeries.trade_date.desc()).first()
        if not earliest or not latest:
            return None, None
        return earliest.trade_date, latest.trade_date

    def resolve_chart_dates(
        self,
        start_date: date | None,
        end_date: date | None,
        *,
        anchor_symbol: str = "Brent",
        default_days: int = 90,
    ) -> tuple[date, date]:
        earliest, latest = self.latest_daily_bounds(anchor_symbol)
        resolved_end = end_date or latest or date.today()
        if start_date:
            resolved_start = start_date
        elif earliest:
            resolved_start = max(earliest, resolved_end - timedelta(days=default_days))
        else:
            resolved_start = resolved_end - timedelta(days=default_days)
        return resolved_start, resolved_end

    def calc_ytd_avg(self, symbol: str, as_of: date | None = None) -> float | None:
        latest = self.latest_daily_price(symbol)
        if not latest:
            return None
        end = as_of or latest.trade_date
        start = date(end.year, 1, 1)
        rows = (
            self.db.query(PriceSeries)
            .filter(
                PriceSeries.symbol == symbol,
                PriceSeries.source == DAILY_PRICE_SOURCE,
                PriceSeries.trade_date >= start,
                PriceSeries.trade_date <= end,
            )
            .all()
        )
        if not rows:
            return None
        return round(sum(r.price for r in rows) / len(rows), 2)

    @staticmethod
    def _month_bounds(year: int, month: int) -> tuple[date, date]:
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        return start, end

    def _month_price_snapshot(self, symbol: str, year: int, month: int) -> dict[str, Any]:
        start, end = self._month_bounds(year, month)
        daily_rows = (
            self.db.query(PriceSeries)
            .filter(
                PriceSeries.symbol == symbol,
                PriceSeries.source == DAILY_PRICE_SOURCE,
                PriceSeries.trade_date >= start,
                PriceSeries.trade_date <= end,
            )
            .all()
        )
        if daily_rows:
            prices = [r.price for r in daily_rows]
            return {
                "avg": round(sum(prices) / len(prices), 2),
                "min": round(min(prices), 2),
                "max": round(max(prices), 2),
                "count": len(prices),
                "source": DAILY_PRICE_SOURCE,
            }
        monthly_row = (
            self.db.query(PriceSeries)
            .filter(
                PriceSeries.symbol == symbol,
                PriceSeries.source == MONTHLY_PRICE_SOURCE,
                PriceSeries.trade_date == end,
            )
            .first()
        )
        if monthly_row:
            return {
                "avg": round(monthly_row.price, 2),
                "min": round(monthly_row.price, 2),
                "max": round(monthly_row.price, 2),
                "count": 1,
                "source": MONTHLY_PRICE_SOURCE,
            }
        return {"avg": None, "min": None, "max": None, "count": 0, "source": None}

    @staticmethod
    def _format_price(value: float | None) -> str:
        if value is None:
            return "—"
        return f"{value:.2f}"

    @staticmethod
    def _format_pct_change(value: float | None) -> str:
        if value is None:
            return "—"
        sign = "+" if value >= 0 else ""
        return f"{sign}{value:.2f}%"

    def calc_monthly_stats(self, symbol: str, year: int, month: int) -> dict[str, Any]:
        current = self._month_price_snapshot(symbol, year, month)
        if current["count"] == 0:
            return {"symbol": symbol, "year": year, "month": month, "count": 0}

        prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
        prev = self._month_price_snapshot(symbol, prev_year, prev_month)
        yoy_base = self._month_price_snapshot(symbol, year - 1, month)

        avg = current["avg"]
        prev_avg = prev["avg"]
        yoy_avg = yoy_base["avg"]
        mom = ((avg - prev_avg) / prev_avg * 100) if avg is not None and prev_avg else None
        yoy = ((avg - yoy_avg) / yoy_avg * 100) if avg is not None and yoy_avg else None
        return {
            "symbol": symbol,
            "year": year,
            "month": month,
            "count": current["count"],
            "avg": avg,
            "min": current["min"],
            "max": current["max"],
            "data_source": current["source"],
            "mom_pct": round(mom, 2) if mom is not None else None,
            "yoy_pct": round(yoy, 2) if yoy is not None else None,
            "prev_month_avg": prev_avg,
            "yoy_base_avg": yoy_avg,
        }

    def build_table_price_change_rows(
        self,
        brent: dict[str, Any],
        wti: dict[str, Any],
        review_month: int,
    ) -> list[list[str]]:
        """表1-1：基于 calc_monthly_stats 结果生成行数据（对齐样例 docx 口径）。"""

        def high_low(stats: dict[str, Any]) -> str:
            low, high = stats.get("min"), stats.get("max")
            if low is None or high is None:
                return "—"
            return f"{high:.2f}/{low:.2f}"

        def peak_trough_spread(stats: dict[str, Any]) -> str:
            low, high = stats.get("min"), stats.get("max")
            if low is None or high is None:
                return "—"
            return f"{high - low:.2f}"

        return [
            [
                f"{review_month}月均价",
                self._format_price(brent.get("avg")),
                self._format_price(wti.get("avg")),
            ],
            [
                "环比",
                self._format_pct_change(brent.get("mom_pct")),
                self._format_pct_change(wti.get("mom_pct")),
            ],
            [
                "同比",
                self._format_pct_change(brent.get("yoy_pct")),
                self._format_pct_change(wti.get("yoy_pct")),
            ],
            ["最高/最低日均结算价", high_low(brent), high_low(wti)],
            ["峰谷价差", peak_trough_spread(brent), peak_trough_spread(wti)],
        ]

    def calc_spread(
        self,
        symbol_a: str,
        symbol_b: str,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        daily_only: bool = True,
    ) -> list[dict[str, Any]]:
        a = self.query_price_series([symbol_a], start_date, end_date, daily_only=daily_only)
        b = self.query_price_series([symbol_b], start_date, end_date, daily_only=daily_only)
        b_map = {item["date"]: item["price"] for item in b}
        result = []
        for item in a:
            if item["date"] in b_map:
                result.append(
                    {
                        "date": item["date"],
                        "spread": round(item["price"] - b_map[item["date"]], 2),
                        "symbol_a": symbol_a,
                        "symbol_b": symbol_b,
                    }
                )
        return result

    @staticmethod
    def trend_direction(mom_pct: float | None, threshold: float = 0.5) -> str:
        if mom_pct is None:
            return "数据缺失"
        if mom_pct > threshold:
            return "走强"
        if mom_pct < -threshold:
            return "走弱"
        return "震荡"

    def _month_avg_spread(
        self,
        symbol_a: str,
        symbol_b: str,
        year: int,
        month: int,
        *,
        spread_mode: str = "a_minus_b",
    ) -> dict[str, Any]:
        start, end = self._month_bounds(year, month)
        rows = self.calc_spread(symbol_a, symbol_b, start, end)
        if spread_mode == "b_minus_a":
            values = [round(-item["spread"], 2) for item in rows]
        else:
            values = [item["spread"] for item in rows]
        if not values:
            return {"avg_spread": None, "count": 0}
        return {"avg_spread": round(sum(values) / len(values), 2), "count": len(values)}

    def calc_spread_monthly_stats(
        self,
        symbol_a: str,
        symbol_b: str,
        year: int,
        month: int,
        *,
        spread_mode: str = "a_minus_b",
    ) -> dict[str, Any]:
        current = self._month_avg_spread(symbol_a, symbol_b, year, month, spread_mode=spread_mode)
        if current["count"] == 0:
            return {
                "symbol_a": symbol_a,
                "symbol_b": symbol_b,
                "spread_mode": spread_mode,
                "year": year,
                "month": month,
                "count": 0,
            }
        prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
        prev = self._month_avg_spread(
            symbol_a, symbol_b, prev_year, prev_month, spread_mode=spread_mode
        )
        avg = current["avg_spread"]
        prev_avg = prev.get("avg_spread")
        mom = ((avg - prev_avg) / prev_avg * 100) if avg is not None and prev_avg else None
        return {
            "symbol_a": symbol_a,
            "symbol_b": symbol_b,
            "spread_mode": spread_mode,
            "year": year,
            "month": month,
            "count": current["count"],
            "avg_spread": avg,
            "prev_month_avg_spread": prev_avg,
            "spread_mom_pct": round(mom, 2) if mom is not None else None,
            "spread_direction": self.trend_direction(mom),
        }

    def build_spot_market_evidence(self, review_year: int, review_month: int) -> dict[str, Any]:
        """现货专章 evidence，与图1-4～1-6 同源（CNEEI price_series）。"""
        brent_futures = self.calc_monthly_stats("Brent", review_year, review_month)
        brent_spot = self.calc_monthly_stats("DTD", review_year, review_month)
        dubai = self.calc_monthly_stats("Dubai", review_year, review_month)
        espo = self.calc_monthly_stats("ESPO", review_year, review_month)
        spot_futures = self.calc_spread_monthly_stats(
            "Brent", "DTD", review_year, review_month, spread_mode="b_minus_a"
        )
        brent_dubai = self.calc_spread_monthly_stats("Brent", "Dubai", review_year, review_month)
        brent_espo = self.calc_spread_monthly_stats("Brent", "ESPO", review_year, review_month)
        trends = {
            "brent_futures": self.trend_direction(brent_futures.get("mom_pct")),
            "brent_spot": self.trend_direction(brent_spot.get("mom_pct")),
            "dubai": self.trend_direction(dubai.get("mom_pct")),
            "espo": self.trend_direction(espo.get("mom_pct")),
            "spot_futures_spread": spot_futures.get("spread_direction", "数据缺失"),
            "brent_dubai_spread": brent_dubai.get("spread_direction", "数据缺失"),
            "brent_espo_spread": brent_espo.get("spread_direction", "数据缺失"),
        }
        return {
            "review_period": f"{review_year}年{review_month}月",
            "brent_futures": brent_futures,
            "brent_spot": brent_spot,
            "dubai": dubai,
            "espo": espo,
            "spreads": {
                "spot_futures": spot_futures,
                "brent_dubai": brent_dubai,
                "brent_espo": brent_espo,
            },
            "trends": trends,
            "data_source": DAILY_PRICE_SOURCE,
        }

    def _chart_config_price_spread_combo(
        self,
        symbol_a: str,
        symbol_b: str,
        start: date,
        end: date,
        *,
        daily_only: bool,
        meta: dict[str, Any],
        spread_mode: str = "a_minus_b",
        series_names: tuple[str, str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """图1-4～1-6：期货 + 现货（左轴）+ 价差（右轴），均为折线。"""
        a_rows = self.query_price_series([symbol_a], start, end, daily_only=daily_only)
        b_rows = self.query_price_series([symbol_b], start, end, daily_only=daily_only)
        b_map = {item["date"]: item["price"] for item in b_rows}
        prices_a: list[list[Any]] = []
        prices_b: list[list[Any]] = []
        spreads: list[list[Any]] = []
        for item in a_rows:
            d = item["date"]
            if d not in b_map:
                continue
            pa, pb = item["price"], b_map[d]
            prices_a.append([d, pa])
            prices_b.append([d, pb])
            spread_val = round(pb - pa, 2) if spread_mode == "b_minus_a" else round(pa - pb, 2)
            spreads.append([d, spread_val])
        default_spread = f"{symbol_a}-{symbol_b}"
        names = series_names or (f"{symbol_a}期货", f"{symbol_b}现货", f"{default_spread}价差")
        title = kwargs.get("title") or f"{default_spread} 走势"
        return {
            "title": title,
            "yAxis": kwargs.get("yAxis") or "油价（美元/桶）",
            "yAxisRight": kwargs.get("yAxisRight") or "价差（美元/桶）",
            "source": "CNEEI",
            "dual_y": True,
            "legend_position": kwargs.get("legend_position") or "bottom",
            "meta": meta,
            "series": [
                {
                    "name": names[0],
                    "yAxisIndex": 0,
                    "data": prices_a,
                    "color": "#0070C0",
                },
                {
                    "name": names[1],
                    "yAxisIndex": 0,
                    "data": prices_b,
                    "color": "#ED7D31",
                },
                {
                    "name": names[2],
                    "yAxisIndex": 1,
                    "data": spreads,
                    "color": "#70AD47",
                    "chartType": "bar",
                },
            ],
        }

    def _chart_config_spread_combo(
        self,
        symbol_a: str,
        symbol_b: str,
        start: date,
        end: date,
        *,
        daily_only: bool,
        meta: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """兼容旧 spread_combo 调用。"""
        return self._chart_config_price_spread_combo(
            symbol_a, symbol_b, start, end, daily_only=daily_only, meta=meta, **kwargs
        )

    def query_balance_forecast(
        self,
        agency: str | None = None,
        *,
        agencies: list[str] | None = None,
        snapshot_month: str | None = None,
        periods: list[str] | None = None,
        supply_demand: list[str] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        q = self.db.query(BalanceForecast)
        if agency:
            q = q.filter(BalanceForecast.agency == agency)
        if agencies:
            q = q.filter(BalanceForecast.agency.in_(agencies))
        if snapshot_month:
            q = q.filter(BalanceForecast.snapshot_month == snapshot_month)
        if periods:
            q = q.filter(BalanceForecast.period.in_(periods))
        if supply_demand:
            q = q.filter(BalanceForecast.supply_demand.in_(supply_demand))
        rows = q.order_by(BalanceForecast.agency, BalanceForecast.period).limit(limit).all()
        return [
            {
                "agency": r.agency,
                "snapshot_month": r.snapshot_month,
                "update_date": r.update_date,
                "supply_demand": r.supply_demand,
                "period": r.period,
                "value": r.value,
                "balance_gap": r.balance_gap,
            }
            for r in rows
        ]

    def list_balance_snapshot_months(
        self,
        *,
        supply_demand: list[str] | None = None,
    ) -> list[str]:
        q = (
            self.db.query(BalanceForecast.snapshot_month)
            .filter(BalanceForecast.snapshot_month != "")
            .distinct()
        )
        if supply_demand:
            q = q.filter(BalanceForecast.supply_demand.in_(supply_demand))
        return sorted({r[0] for r in q.all() if r[0]})

    def resolve_balance_snapshot_month(
        self,
        review_year: int,
        review_month: int,
        *,
        supply_demand: list[str] | None = None,
    ) -> tuple[str | None, str, bool]:
        """表2-3：优先回顾月 snapshot；无数据则取回顾月之前（含）最新 snapshot。"""
        sd = supply_demand or ["供需差"]
        requested = f"{review_year}-{review_month:02d}"
        if self.query_balance_forecast(snapshot_month=requested, supply_demand=sd, limit=1):
            return requested, requested, False
        available = self.list_balance_snapshot_months(supply_demand=sd)
        candidates = [m for m in available if m <= requested]
        if not candidates:
            return None, requested, False
        resolved = candidates[-1]
        return resolved, requested, resolved != requested

    def query_factor_assessments(
        self,
        report_month: str | None = None,
        *,
        categories: list[str] | None = None,
        factor_names: list[str] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        q = self.db.query(FactorAssessment)
        if report_month:
            q = q.filter(FactorAssessment.report_month == report_month)
        if categories:
            q = q.filter(FactorAssessment.category.in_(categories))
        if factor_names:
            q = q.filter(FactorAssessment.factor_name.in_(factor_names))
        rows = q.limit(limit).all()
        return [
            {
                "report_month": r.report_month,
                "category": r.category,
                "factor_name": r.factor_name,
                "importance": r.importance,
                "assessment": r.assessment,
                "impact_direction": r.impact_direction,
            }
            for r in rows
        ]

    def _symbol_period_stats(self, symbol: str, start: date, end: date) -> dict[str, Any]:
        rows = (
            self.db.query(PriceSeries)
            .filter(
                PriceSeries.symbol == symbol,
                PriceSeries.source == DAILY_PRICE_SOURCE,
                PriceSeries.trade_date >= start,
                PriceSeries.trade_date <= end,
            )
            .order_by(PriceSeries.trade_date)
            .all()
        )
        if rows:
            prices = [r.price for r in rows]
            last = rows[-1]
            return {
                "latest_price": round(last.price, 2),
                "latest_date": last.trade_date.isoformat(),
                "period_avg": round(sum(prices) / len(prices), 2),
                "period_min": round(min(prices), 2),
                "period_max": round(max(prices), 2),
                "data_points": len(prices),
                "data_source": DAILY_PRICE_SOURCE,
            }
        monthly_row = (
            self.db.query(PriceSeries)
            .filter(
                PriceSeries.symbol == symbol,
                PriceSeries.source == MONTHLY_PRICE_SOURCE,
                PriceSeries.trade_date >= start,
                PriceSeries.trade_date <= end,
            )
            .order_by(PriceSeries.trade_date.desc())
            .first()
        )
        if monthly_row:
            p = round(monthly_row.price, 2)
            return {
                "latest_price": p,
                "latest_date": monthly_row.trade_date.isoformat(),
                "period_avg": p,
                "period_min": p,
                "period_max": p,
                "data_points": 1,
                "data_source": MONTHLY_PRICE_SOURCE,
            }
        return {
            "latest_price": None,
            "latest_date": None,
            "period_avg": None,
            "period_min": None,
            "period_max": None,
            "data_points": 0,
            "data_source": DAILY_PRICE_SOURCE,
        }

    def dashboard_summary(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        start, end = self.resolve_chart_dates(start_date, end_date)
        symbols = ["Brent", "WTI", "Dubai", "Oman"]
        summary = {symbol: self._symbol_period_stats(symbol, start, end) for symbol in symbols}
        return {
            "symbols": summary,
            "range": {"start_date": start.isoformat(), "end_date": end.isoformat()},
            "dataset_count": self.db.query(PriceSeries).count(),
            **self._price_meta(),
        }

    def _price_meta(self) -> dict[str, Any]:
        earliest, latest = self.latest_daily_bounds("Brent")
        return {
            "price_meta": {
                "latest_date": latest.isoformat() if latest else None,
                "earliest_date": earliest.isoformat() if earliest else None,
                "data_source": DAILY_PRICE_SOURCE,
            }
        }

    def chart_config(self, chart_type: str, **kwargs) -> dict[str, Any]:
        daily_only = kwargs.get("daily_only", True)
        anchor = kwargs.get("symbol_a") or (kwargs.get("symbols") or ["Brent"])[0]
        start, end = self.resolve_chart_dates(
            kwargs.get("start_date"),
            kwargs.get("end_date"),
            anchor_symbol=anchor,
            default_days=int(kwargs.get("default_days") or 90),
        )
        meta = {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "data_source": DAILY_PRICE_SOURCE if daily_only else "mixed",
        }
        if chart_type == "price_trend":
            symbols = kwargs.get("symbols", ["Brent", "WTI"])
            data = self.query_price_series(symbols, start, end, daily_only=daily_only)
            df = pd.DataFrame(data)
            series = []
            if not df.empty:
                for sym in symbols:
                    sub = df[df["symbol"] == sym]
                    series.append({"name": sym, "data": sub[["date", "price"]].values.tolist()})
            title = kwargs.get("title") or "国际原油期货价格走势"
            dual_y = bool(kwargs.get("dual_y"))
            result: dict[str, Any] = {
                "title": title,
                "yAxis": kwargs.get("yAxis") or "油价（美元/桶）",
                "source": "CNEEI",
                "series": series,
                "meta": meta,
                "legend_position": kwargs.get("legend_position") or ("bottom" if dual_y else "upper right"),
                "dual_y": dual_y,
            }
            if dual_y:
                result["yAxisRight"] = kwargs.get("yAxisRight") or "现货（美元/桶）"
                for idx, sym in enumerate(symbols):
                    if idx < len(result["series"]):
                        result["series"][idx]["yAxisIndex"] = idx
            return result
        if chart_type == "spread":
            symbol_a = kwargs.get("symbol_a", "Brent")
            symbol_b = kwargs.get("symbol_b", "WTI")
            if kwargs.get("spread_combo") or kwargs.get("price_spread_combo"):
                skip = {
                    "spread_combo",
                    "price_spread_combo",
                    "start_date",
                    "end_date",
                    "daily_only",
                    "symbol_a",
                    "symbol_b",
                }
                combo_kw = {k: v for k, v in kwargs.items() if k not in skip}
                return self._chart_config_price_spread_combo(
                    symbol_a, symbol_b, start, end, daily_only=daily_only, meta=meta, **combo_kw
                )
            spread = self.calc_spread(symbol_a, symbol_b, start, end, daily_only=daily_only)
            title = kwargs.get("title") or f"{symbol_a}-{symbol_b} 价差"
            return {
                "title": title,
                "xAxis": "日期",
                "yAxis": "价差 (USD/bbl)",
                "source": "CNEEI",
                "series": [{"name": title, "data": [[d["date"], d["spread"]] for d in spread]}],
                "meta": meta,
            }
        if chart_type == "balance":
            return self._chart_config_balance(**kwargs)
        return {"title": chart_type, "series": []}

    def _chart_config_balance(self, **kwargs: Any) -> dict[str, Any]:
        rows = self.query_balance_forecast(
            agencies=kwargs.get("agencies"),
            snapshot_month=kwargs.get("snapshot_month"),
            periods=kwargs.get("periods"),
            supply_demand=kwargs.get("supply_demand"),
        )
        buckets: dict[str, dict[str, Any]] = {}
        for r in rows:
            sd = str(r["supply_demand"])
            label = f"{r['agency']} {sd}"
            if label not in buckets:
                entry: dict[str, Any] = {
                    "name": label,
                    "data": [],
                    "yAxisIndex": 1 if sd == "供需差" else 0,
                }
                if sd == "供需差":
                    entry["lineStyle"] = {"type": "dashed", "width": 2}
                buckets[label] = entry
            buckets[label]["data"].append([r["period"], r["value"]])

        series = list(buckets.values())
        for serie in series:
            serie["data"].sort(key=lambda p: str(p[0]))

        left_series = [s for s in series if s["yAxisIndex"] == 0]
        right_series = [s for s in series if s["yAxisIndex"] == 1]
        dual_y = bool(left_series and right_series)
        if not left_series and right_series:
            for serie in right_series:
                serie["yAxisIndex"] = 0
                serie.pop("lineStyle", None)
            dual_y = False

        result: dict[str, Any] = {
            "title": kwargs.get("title") or "机构供需预测对比",
            "xAxis": "周期",
            "yAxis": "供应/需求（百万桶/天）" if dual_y else "百万桶/天",
            "source": "IEA/EIA/S&P",
            "series": series,
            "dual_y": dual_y,
            "y_axis_scale": True,
        }
        left_bounds = value_axis_bounds(
            self._balance_series_values(series, 0),
            min_span=2.0,
        )
        if left_bounds:
            result["yAxisMin"], result["yAxisMax"] = left_bounds
        if dual_y:
            result["yAxisRight"] = kwargs.get("yAxisRight") or "供需差（百万桶/天）"
            result["legend_position"] = "bottom"
            right_bounds = value_axis_bounds(
                self._balance_series_values(series, 1),
                min_span=0.4,
            )
            if right_bounds:
                result["yAxisRightMin"], result["yAxisRightMax"] = right_bounds
        return result

    @staticmethod
    def _balance_series_values(series: list[dict[str, Any]], y_axis_index: int) -> list[float]:
        values: list[float] = []
        for serie in series:
            if serie.get("yAxisIndex", 0) != y_axis_index:
                continue
            for _, raw in serie.get("data") or []:
                try:
                    values.append(float(raw))
                except (TypeError, ValueError):
                    continue
        return values
