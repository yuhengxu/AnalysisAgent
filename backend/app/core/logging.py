"""统一日志配置模块。

设计目标（供后续维护者参考）：
- 全项目只在 ``app.main`` 启动时调用一次 :func:`setup_logging`。
- 同时输出到控制台与滚动文件 ``logs/app.log``（按大小切割，保留若干份）。
- 业务代码通过标准 ``logging.getLogger(name)`` 获取 logger，无需关心 handler。
  推荐命名：``llm``、``skill.prediction``、``skill.report``、``service.xxx``、``api``。

日志级别可通过环境变量 ``LOG_LEVEL`` 覆盖（默认 INFO）。
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.timezone import BEIJING_TZ

_CONFIGURED = False

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class BeijingFormatter(logging.Formatter):
    """日志时间统一使用北京时间。"""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, BEIJING_TZ)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(timespec="seconds")


def setup_logging(logs_dir: Path | str = "./logs", level: str | None = None) -> None:
    """初始化根日志器。幂等：重复调用不会重复添加 handler。"""
    global _CONFIGURED
    if _CONFIGURED:
        return

    logs_path = Path(logs_dir)
    logs_path.mkdir(parents=True, exist_ok=True)
    log_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()

    root = logging.getLogger()
    root.setLevel(log_level)

    formatter = BeijingFormatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        logs_path / "app.log",
        maxBytes=5 * 1024 * 1024,  # 单文件 5MB
        backupCount=5,             # 保留 5 份历史
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # 大模型对话专用日志（完整记录每轮请求与应答摘要）
    dialogue_handler = RotatingFileHandler(
        logs_path / "llm_dialogue.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    dialogue_handler.setFormatter(formatter)
    dialogue_logger = logging.getLogger("llm.dialogue")
    dialogue_logger.setLevel(log_level)
    dialogue_logger.addHandler(dialogue_handler)
    dialogue_logger.propagate = False

    # 降低第三方库噪声
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _CONFIGURED = True
    logging.getLogger("app").info("日志系统已初始化，level=%s, dir=%s", log_level, logs_path)


def get_logger(name: str) -> logging.Logger:
    """语义化获取 logger 的便捷封装。"""
    return logging.getLogger(name)
