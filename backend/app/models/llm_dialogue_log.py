from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_beijing_naive


class LlmDialogueLog(Base):
    """大模型每轮对话记录：客户请求 + 模型应答。"""

    __tablename__ = "llm_dialogue_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(80), default="unknown")
    provider: Mapped[str] = mapped_column(String(50), default="")
    model_name: Mapped[str] = mapped_column(String(100), default="")
    request_messages: Mapped[str] = mapped_column(Text, default="[]")
    response_content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="success")
    error_message: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing_naive)
