from datetime import datetime
from sqlalchemy import String, DateTime, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_beijing_naive


class ForecastResult(Base):
    __tablename__ = "forecast_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(50), default="Brent")
    period: Mapped[str] = mapped_column(String(30))
    scenario: Mapped[str] = mapped_column(String(30))  # baseline / optimistic / pessimistic
    point_value: Mapped[float] = mapped_column(Float)
    low_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_name: Mapped[str] = mapped_column(String(100))
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing_naive)
