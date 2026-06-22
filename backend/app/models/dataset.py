from datetime import datetime
from sqlalchemy import String, DateTime, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_beijing_naive


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(50))  # csv, xlsx, api
    category: Mapped[str] = mapped_column(String(50))  # price, balance, factor, report
    file_path: Mapped[str] = mapped_column(String(500))
    schema_json: Mapped[str] = mapped_column(Text, default="{}")
    version: Mapped[int] = mapped_column(Integer, default=1)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing_naive)
