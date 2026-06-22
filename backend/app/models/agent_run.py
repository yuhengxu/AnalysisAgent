from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_beijing_naive


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill: Mapped[str] = mapped_column(String(50))
    prompt: Mapped[str] = mapped_column(Text)
    model_provider: Mapped[str] = mapped_column(String(50))
    model_name: Mapped[str] = mapped_column(String(100))
    tools_called: Mapped[str] = mapped_column(Text, default="[]")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    response: Mapped[str] = mapped_column(Text, default="")
    charts_json: Mapped[str] = mapped_column(Text, default="[]")
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing_naive)
