from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_beijing_naive


class AgencyForecastManual(Base):
    """咨询机构 Brent 油价预测（每月手工录入，对应月报表3-2）。"""

    __tablename__ = "agency_forecast_manual"
    __table_args__ = (UniqueConstraint("year", "month", name="uq_agency_forecast_ym"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)
    rows_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_beijing_naive, onupdate=now_beijing_naive
    )
