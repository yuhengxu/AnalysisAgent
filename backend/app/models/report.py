from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_beijing_naive


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    issue_no: Mapped[str] = mapped_column(String(50))
    report_date: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="draft")
    content_json: Mapped[str] = mapped_column(Text, default="{}")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    docx_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    author: Mapped[str] = mapped_column(String(100), default="")
    reviewer: Mapped[str] = mapped_column(String(100), default="")
    approver: Mapped[str] = mapped_column(String(100), default="")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing_naive, onupdate=now_beijing_naive)
