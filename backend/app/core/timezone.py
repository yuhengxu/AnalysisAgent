"""北京时间（东八区 / Asia/Shanghai）统一工具。"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def now_beijing() -> datetime:
    """返回带时区信息的当前北京时间。"""
    return datetime.now(BEIJING_TZ)


def now_beijing_naive() -> datetime:
    """返回无时区的北京时间（用于 SQLite 等 naive 存储）。"""
    return now_beijing().replace(tzinfo=None)


def format_beijing_iso(dt: datetime | None) -> str | None:
    """将 datetime 序列化为带 +08:00 的 ISO 字符串。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        aware = dt.replace(tzinfo=BEIJING_TZ)
    else:
        aware = dt.astimezone(BEIJING_TZ)
    return aware.isoformat(timespec="milliseconds")


def beijing_timestamp() -> str:
    """文件名等场景使用的北京时间戳。"""
    return now_beijing_naive().strftime("%Y%m%d_%H%M%S")
