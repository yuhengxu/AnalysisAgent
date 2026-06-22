"""月报章节修订上下文组装。"""
from __future__ import annotations

import json
from typing import Any

from app.templates.sample_contracts import REPORT_TABLE_ANCHORS


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _table_for_section(section_id: str, content: dict[str, Any]) -> dict[str, Any] | None:
    tables = content.get("tables") or {}
    for table_id, anchor_section in REPORT_TABLE_ANCHORS.items():
        if anchor_section == section_id and table_id in tables:
            tbl = tables[table_id]
            return {
                "id": table_id,
                "title": tbl.get("title", ""),
                "source": tbl.get("source", ""),
                "headers": tbl.get("headers", []),
                "rows": tbl.get("rows", []),
            }
    return None


def _adjacent_sections(
    sections: list[dict[str, Any]], section_id: str, *, limit: int = 200
) -> tuple[str, str]:
    level2 = [s for s in sections if s.get("level") == 2]
    idx = next((i for i, s in enumerate(level2) if s.get("id") == section_id), -1)
    prev_text = ""
    next_text = ""
    if idx > 0:
        prev = level2[idx - 1]
        prev_text = f"{prev.get('title', '')}：{_truncate(prev.get('content', ''), limit)}"
    if 0 <= idx < len(level2) - 1:
        nxt = level2[idx + 1]
        next_text = f"{nxt.get('title', '')}：{_truncate(nxt.get('content', ''), limit)}"
    return prev_text, next_text


def _evidence_brief(evidence_meta: dict[str, Any], *, limit: int = 2000) -> str:
    evidence = evidence_meta.get("evidence", evidence_meta)
    if not isinstance(evidence, dict):
        return ""
    try:
        text = json.dumps(evidence, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return ""
    return _truncate(text, limit)


def _web_refs_brief(web_references: list[Any], *, limit: int = 5) -> str:
    lines: list[str] = []
    for item in (web_references or [])[:limit]:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("url") or ""
        url = item.get("url") or ""
        lines.append(f"- {title} ({url})")
    return "\n".join(lines)


def build_revise_context(
    *,
    content: dict[str, Any],
    section_id: str,
    target_section: dict[str, Any] | None,
    evidence_meta: dict[str, Any],
) -> str:
    """组装发送给大模型的修订上下文文本。"""
    sections = content.get("sections") or []
    parts: list[str] = []

    if section_id == "summary":
        parts.append("【章节信息】内容摘要")
    elif target_section:
        parts.append(
            "【章节信息】"
            f"{target_section.get('title', '')} / {target_section.get('hint', '')}"
        )
        if target_section.get("confidence_level"):
            parts.append(f"致信水平：{target_section['confidence_level']}")
        if target_section.get("source_url"):
            parts.append(
                f"来源：{target_section.get('source_title') or target_section.get('source_url')}"
            )

    if section_id != "summary":
        prev_text, next_text = _adjacent_sections(sections, section_id)
        if prev_text or next_text:
            parts.append(f"【相邻章节上下文】\n上一节：{prev_text or '无'}\n下一节：{next_text or '无'}")

    table = _table_for_section(section_id, content)
    if table:
        try:
            table_json = json.dumps(table, ensure_ascii=False)
        except (TypeError, ValueError):
            table_json = str(table)
        parts.append(f"【关联表格】\n{table_json}")

    evidence_brief = _evidence_brief(evidence_meta)
    if section_id == "review_spot":
        evidence = evidence_meta.get("evidence", evidence_meta)
        spot = evidence.get("spot_market") if isinstance(evidence, dict) else None
        if spot:
            try:
                spot_json = json.dumps(spot, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                spot_json = str(spot)
            parts.append(
                "【现货市场数据库摘要（须与图1-4～1-6 一致）】\n" + spot_json
            )
        elif evidence_brief:
            parts.append(f"【证据摘要】\n{evidence_brief}")
    elif evidence_brief:
        parts.append(f"【证据摘要】\n{evidence_brief}")

    web_refs = _web_refs_brief(evidence_meta.get("web_references") or [])
    if web_refs:
        parts.append(f"【联网参考】\n{web_refs}")

    return "\n\n".join(parts)
