from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_beijing_naive


class ReportTemplate(Base):
    __tablename__ = "report_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    report_type: Mapped[str] = mapped_column(String(50))  # monthly / weekly
    structure_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing_naive)
