"""月报表格快照：按回顾月存储 6 张动态表。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_beijing_naive


class ReportTableSnapshot(Base):
    __tablename__ = "report_table_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "review_year",
            "review_month",
            "table_key",
            name="uq_report_table_snapshot_ym_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_year: Mapped[int] = mapped_column(Integer, index=True)
    review_month: Mapped[int] = mapped_column(Integer, index=True)
    table_key: Mapped[str] = mapped_column(String(40), index=True)
    source_category: Mapped[str] = mapped_column(String(10))  # derived | web
    title: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(200), default="")
    headers_json: Mapped[str] = mapped_column(Text, default="[]")
    rows_json: Mapped[str] = mapped_column(Text, default="[]")
    source_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    is_manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_beijing_naive, onupdate=now_beijing_naive
    )
