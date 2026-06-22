from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_beijing_naive


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300))
    symbol: Mapped[str] = mapped_column(String(20), default="Brent")
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    content_json: Mapped[str] = mapped_column(Text, default="{}")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    model_name: Mapped[str] = mapped_column(String(80), default="")
    llm_used: Mapped[int] = mapped_column(Integer, default=0)
    xlsx_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_beijing_naive, onupdate=now_beijing_naive
    )
