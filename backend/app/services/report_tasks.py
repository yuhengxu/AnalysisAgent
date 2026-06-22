"""月报生成异步任务（内存态，供前端轮询进度）。"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.database import SessionLocal
from app.core.timezone import BEIJING_TZ, format_beijing_iso
from app.models.user import User
from app.schemas.common import ReportGenerateRequest
from app.services.report import ReportService


@dataclass
class ReportGenerateTask:
    id: str
    status: str = "pending"  # pending | running | success | error
    step: int = 0
    total_steps: int = 3
    step_label: str = ""
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    user_id: int | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None


_lock = threading.Lock()
_tasks: dict[str, ReportGenerateTask] = {}


def _set_task(task_id: str, **kwargs: Any) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        for key, value in kwargs.items():
            setattr(task, key, value)


def create_task(body: ReportGenerateRequest, user_id: int | None = None) -> ReportGenerateTask:
    total_steps = 1 if body.unrestricted_mode else 3
    task = ReportGenerateTask(
        id=uuid.uuid4().hex,
        total_steps=total_steps,
        user_id=user_id,
        message="任务已创建，等待执行…",
    )
    with _lock:
        _tasks[task.id] = task
    return task


def get_task(task_id: str) -> ReportGenerateTask | None:
    with _lock:
        return _tasks.get(task_id)


def start_task(task_id: str, body: ReportGenerateRequest) -> None:
    thread = threading.Thread(
        target=_run_task,
        args=(task_id, body),
        daemon=True,
        name=f"report-gen-{task_id[:8]}",
    )
    thread.start()


def _progress(task_id: str, step: int, total: int, label: str) -> None:
    _set_task(
        task_id,
        step=step,
        total_steps=total,
        step_label=label,
        message=f"第 {step}/{total} 步：{label}",
    )


def _run_task(task_id: str, body: ReportGenerateRequest) -> None:
    task = get_task(task_id)
    user: User | None = None
    total = task.total_steps if task else 3

    _set_task(task_id, status="running", message="正在初始化生成任务…")

    db = SessionLocal()
    try:
        if task and task.user_id:
            user = db.query(User).filter(User.id == task.user_id).first()

        if total > 1:
            _progress(task_id, 1, total, "采集权威数据与证据")
        else:
            _set_task(task_id, step=1, step_label="深度研究仿写", message="正在基于样例仿写月报…")

        if total > 1:
            _progress(task_id, 2, total, "大模型撰写月报初稿")

        result = ReportService(db).generate_monthly_draft(
            issue_no=body.issue_no,
            report_date=body.report_date,
            review_month=(body.review_year, body.review_month),
            outlook_month=(body.outlook_year, body.outlook_month),
            provider=body.model_provider,
            model=body.model_name,
            mode=body.mode,
            extra_instruction=body.extra_instruction,
            trusted_sources_only=body.trusted_sources_only,
            unrestricted_mode=body.unrestricted_mode,
            user=user,
        )

        if total > 1:
            _progress(task_id, 3, total, "保存并导出 Word")

        _set_task(
            task_id,
            status="success",
            step=total,
            total_steps=total,
            step_label="完成",
            message=f"已生成：{result.get('title', '月报')}",
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


def task_to_dict(task: ReportGenerateTask) -> dict[str, Any]:
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
        "elapsed_ms": int(((task.finished_at or time.time()) - task.started_at) * 1000),
    }
