from datetime import datetime
from sqlalchemy import String, DateTime, Float, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_beijing_naive


class BalanceForecast(Base):
    __tablename__ = "balance_forecasts"
    __table_args__ = (
        UniqueConstraint(
            "agency",
            "snapshot_month",
            "supply_demand",
            "period",
            name="uq_balance_agency_snapshot_sd_period",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(Integer, index=True)
    agency: Mapped[str] = mapped_column(String(50))
    snapshot_month: Mapped[str] = mapped_column(String(10), index=True, default="")
    update_date: Mapped[str] = mapped_column(String(20))
    supply_demand: Mapped[str] = mapped_column(String(10))  # 供 / 需
    period: Mapped[str] = mapped_column(String(20))
    value: Mapped[float] = mapped_column(Float)
    balance_gap: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing_naive)
