from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_beijing_naive


class FactorAssessment(Base):
    __tablename__ = "factor_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(Integer, index=True)
    report_month: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(100))
    factor_name: Mapped[str] = mapped_column(String(200))
    importance: Mapped[int] = mapped_column(Integer, default=3)
    assessment: Mapped[str] = mapped_column(Text)
    impact_direction: Mapped[str] = mapped_column(String(20))  # 促涨 / 持平 / 促跌
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing_naive)
