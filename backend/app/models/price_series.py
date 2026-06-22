from datetime import date, datetime
from sqlalchemy import String, DateTime, Float, Integer, Date, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timezone import now_beijing_naive


class PriceSeries(Base):
    __tablename__ = "price_series"
    __table_args__ = (
        Index("ix_price_symbol_date", "symbol", "trade_date"),
        UniqueConstraint("symbol", "trade_date", "source", name="uq_price_symbol_date_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(Integer, index=True)
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    price: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(30), default="USD/bbl")
    source: Mapped[str] = mapped_column(String(100), default="CNEEI")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_beijing_naive)
