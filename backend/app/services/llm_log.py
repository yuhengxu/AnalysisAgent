"""大模型对话日志服务：持久化到数据库 + 写入专用滚动日志文件。"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.database import SessionLocal
from app.core.timezone import format_beijing_iso
from app.models.llm_dialogue_log import LlmDialogueLog

dialogue_logger = logging.getLogger("llm.dialogue")


def record_dialogue(
    *,
    source: str,
    provider: str,
    model_name: str,
    request_messages: list[dict[str, str]],
    response_content: str = "",
    status: str = "success",
    error_message: str = "",
    duration_ms: float = 0,
    meta: dict[str, Any] | None = None,
) -> int | None:
    """记录一轮大模型对话，返回日志 ID（失败时返回 None）。"""
    meta = meta or {}
    req_text = json.dumps(request_messages, ensure_ascii=False)
    meta_text = json.dumps(meta, ensure_ascii=False, default=str)

    _write_file_log(
        source=source,
        provider=provider,
        model_name=model_name,
        request_messages=request_messages,
        response_content=response_content,
        status=status,
        error_message=error_message,
        duration_ms=duration_ms,
        meta=meta,
    )

    log_id: int | None = None
    db = SessionLocal()
    try:
        row = LlmDialogueLog(
            source=source,
            provider=provider,
            model_name=model_name,
            request_messages=req_text,
            response_content=response_content,
            status=status,
            error_message=error_message,
            duration_ms=duration_ms,
            meta_json=meta_text,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        log_id = row.id
    except Exception as exc:  # noqa: BLE001
        dialogue_logger.error("写入对话日志数据库失败 source=%s err=%s", source, exc)
        db.rollback()
    finally:
        db.close()
    return log_id


def _write_file_log(
    *,
    source: str,
    provider: str,
    model_name: str,
    request_messages: list[dict[str, str]],
    response_content: str,
    status: str,
    error_message: str,
    duration_ms: float,
    meta: dict[str, Any],
) -> None:
    user_parts = [m["content"] for m in request_messages if m.get("role") == "user"]
    system_parts = [m["content"] for m in request_messages if m.get("role") == "system"]
    preview_user = user_parts[-1][:500] if user_parts else ""
    preview_resp = (response_content or error_message)[:500]
    dialogue_logger.info(
        "source=%s provider=%s model=%s status=%s duration=%.1fms meta=%s\n"
        "【系统提示】%s\n"
        "【用户请求】%s\n"
        "【模型应答】%s",
        source,
        provider,
        model_name,
        status,
        duration_ms,
        json.dumps(meta, ensure_ascii=False, default=str),
        (system_parts[0][:200] + "…") if system_parts and len(system_parts[0]) > 200 else (system_parts[0] if system_parts else ""),
        preview_user + ("…" if user_parts and len(user_parts[-1]) > 500 else ""),
        preview_resp + ("…" if len(response_content or error_message) > 500 else ""),
    )


class LlmLogService:
    def list_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        source: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        db = SessionLocal()
        try:
            q = db.query(LlmDialogueLog).order_by(LlmDialogueLog.created_at.desc())
            if source:
                q = q.filter(LlmDialogueLog.source == source)
            if status:
                q = q.filter(LlmDialogueLog.status == status)
            total = q.count()
            rows = q.offset((page - 1) * page_size).limit(page_size).all()
            items = []
            for r in rows:
                msgs = json.loads(r.request_messages or "[]")
                user_text = next(
                    (m.get("content", "") for m in reversed(msgs) if m.get("role") == "user"),
                    "",
                )
                items.append(
                    {
                        "id": r.id,
                        "source": r.source,
                        "provider": r.provider,
                        "model_name": r.model_name,
                        "status": r.status,
                        "duration_ms": r.duration_ms,
                        "request_preview": user_text[:200],
                        "response_preview": (r.response_content or r.error_message)[:200],
                        "created_at": format_beijing_iso(r.created_at),
                    }
                )
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": max(1, (total + page_size - 1) // page_size),
            }
        finally:
            db.close()

    def get_log(self, log_id: int) -> dict[str, Any]:
        db = SessionLocal()
        try:
            r = db.get(LlmDialogueLog, log_id)
            if not r:
                raise ValueError("Log not found")
            return {
                "id": r.id,
                "source": r.source,
                "provider": r.provider,
                "model_name": r.model_name,
                "status": r.status,
                "error_message": r.error_message,
                "duration_ms": r.duration_ms,
                "request_messages": json.loads(r.request_messages or "[]"),
                "response_content": r.response_content,
                "meta": json.loads(r.meta_json or "{}"),
                "created_at": format_beijing_iso(r.created_at),
            }
        finally:
            db.close()

    def list_sources(self) -> list[str]:
        db = SessionLocal()
        try:
            rows = db.query(LlmDialogueLog.source).distinct().order_by(LlmDialogueLog.source).all()
            return [r[0] for r in rows if r[0]]
        finally:
            db.close()
