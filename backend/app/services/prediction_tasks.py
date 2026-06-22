"""预测表生成异步任务（内存态，供前端轮询进度）。"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from datetime import datetime

from app.core.database import SessionLocal
from app.core.timezone import BEIJING_TZ, format_beijing_iso
from app.schemas.common import PredictionGenerateRequest
from app.services.prediction import PredictionService


@dataclass
class PredictionGenerateTask:
    id: str
    status: str = "pending"  # pending | running | success | error
    step: int = 0
    total_steps: int = 7
    step_label: str = ""
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None


_lock = threading.Lock()
_tasks: dict[str, PredictionGenerateTask] = {}


def _set_task(task_id: str, **kwargs: Any) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        for key, value in kwargs.items():
            setattr(task, key, value)


def create_task(total_steps: int = 7, body: PredictionGenerateRequest | None = None) -> PredictionGenerateTask:
    if body and body.unrestricted_mode:
        total_steps = 1
    task = PredictionGenerateTask(
        id=uuid.uuid4().hex,
        total_steps=total_steps,
        message="任务已创建，等待执行…",
    )
    with _lock:
        _tasks[task.id] = task
    return task


def get_task(task_id: str) -> PredictionGenerateTask | None:
    with _lock:
        return _tasks.get(task_id)


def start_task(task_id: str, body: PredictionGenerateRequest) -> None:
    thread = threading.Thread(
        target=_run_task,
        args=(task_id, body),
        daemon=True,
        name=f"pred-gen-{task_id[:8]}",
    )
    thread.start()


def _run_task(task_id: str, body: PredictionGenerateRequest) -> None:
    _set_task(
        task_id,
        status="running",
        message="正在初始化生成任务…",
    )

    def on_progress(step: int, total: int, label: str) -> None:
        _set_task(
            task_id,
            step=step,
            total_steps=total,
            step_label=label,
            message=f"第 {step}/{total} 步：{label}",
        )

    db = SessionLocal()
    try:
        result = PredictionService(db).generate(
            symbol=body.symbol,
            year=body.year,
            month=body.month,
            provider=body.model_provider,
            model=body.model_name,
            mode=body.mode,
            extra_instruction=body.extra_instruction,
            on_progress=on_progress,
            trusted_sources_only=body.trusted_sources_only,
            unrestricted_mode=body.unrestricted_mode,
        )
        _set_task(
            task_id,
            status="success",
            step=result.get("total_steps", 7),
            total_steps=result.get("total_steps", 7),
            step_label="完成",
            message=f"已生成：{result.get('title', '预测分析表')}",
            result=result,
            finished_at=time.time(),
        )
    except Exception as exc:  # noqa: BLE001
        _set_task(
            task_id,
            status="error",
            error=str(exc),
            message=f"生成失败：{exc}",
            finished_at=time.time(),
        )
    finally:
        db.close()


def _epoch_to_beijing_iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return format_beijing_iso(datetime.fromtimestamp(ts, BEIJING_TZ))


def task_to_dict(task: PredictionGenerateTask) -> dict[str, Any]:
    return {
        "task_id": task.id,
        "status": task.status,
        "step": task.step,
        "total_steps": task.total_steps,
        "step_label": task.step_label,
        "message": task.message,
        "result": task.result,
        "error": task.error,
        "started_at": _epoch_to_beijing_iso(task.started_at),
        "finished_at": _epoch_to_beijing_iso(task.finished_at),
        "elapsed_ms": int(
            ((task.finished_at or time.time()) - task.started_at) * 1000
        ),
    }
