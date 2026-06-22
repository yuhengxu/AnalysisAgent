import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_beijing_naive

ALL_PAGE_KEYS = [
    "dashboard",
    "data",
    "analysis",
    "prediction",
    "forecast",
    "reports",
]

ADMIN_PAGE_KEYS = [
    "users",
    "settings",
    "monitor",
]

PAGE_LABELS: dict[str, str] = {
    "dashboard": "总览",
    "data": "数据中心",
    "analysis": "智能分析",
    "prediction": "预测分析表",
    "forecast": "预测模型",
    "reports": "报告中心",
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="user")
    allowed_pages_json: Mapped[str] = mapped_column(Text, default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_beijing_naive,
        onupdate=now_beijing_naive,
    )

    def allowed_pages(self) -> list[str]:
        if self.role == "admin":
            return ALL_PAGE_KEYS + ADMIN_PAGE_KEYS
        try:
            return json.loads(self.allowed_pages_json or "[]")
        except json.JSONDecodeError:
            return []

    def business_allowed_pages(self) -> list[str]:
        if self.role == "admin":
            return ALL_PAGE_KEYS
        try:
            return json.loads(self.allowed_pages_json or "[]")
        except json.JSONDecodeError:
            return []
