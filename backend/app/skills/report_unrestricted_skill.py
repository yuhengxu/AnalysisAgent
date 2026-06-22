"""无限制模式 · 国际油价月报 skill。

基于 yuebao/yuebao 上一期样例，将样例全文交给深度研究模型，
仅保留格式约束，不做数据真实性/时效性校验。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core import llm
from app.core.llm import llm_context
from app.services.analytics import AnalyticsService
from app.skills.evidence_guard import guard_report_content
from app.services.report_table_data import ReportTableDataService, SYSTEM_TABLE_KEYS
from app.skills.sample_loader import load_report_sample
from app.templates.monthly_report import DEFAULT_SECTIONS, default_content

logger = logging.getLogger("skill.report_unrestricted")

SYSTEM_PROMPT = (
    "你是中国海油集团能源经济研究院的资深石油经济分析师，负责撰写《国际油价月报》。"
    "你的任务是根据提供的月报样例，更新数据与判断，生成目标期别的新版月报。"
    "要求：\n"
    "1) 语言风格、章节结构、表格口径须与样例完全一致，不得创新表述方式。\n"
    "2) 每个 level=2 子章节正文 200-400 字，须引用具体数据并标注来源机构。\n"
    "3) 不要求数据真实性或时效性核验，可基于样例逻辑合理推演更新。\n"
    "4) 严格输出 JSON，不要包含任何额外说明文字。"
)


class ReportUnrestrictedSkill:
    name = "report_unrestricted"
    label = "国际油价月报（无限制）"

    def __init__(self, db: Session):
        self.db = db
        self.analytics = AnalyticsService(db)

    def generate(
        self,
        issue_no: str,
        report_date: str,
        review_month: tuple[int, int],
        outlook_month: tuple[int, int],
        provider: str | None = None,
        model: str | None = None,
        mode: str = "deep_research",
        extra_instruction: str = "",
    ) -> dict[str, Any]:
        ry, rm = review_month
        oy, om = outlook_month
        sample = load_report_sample(oy, om)
        base = default_content(issue_no, report_date)
        section_ids = [s["id"] for s in DEFAULT_SECTIONS if s.get("level") == 2]
        section_list = "\n".join(
            f'- id={s["id"]} 标题="{s["title"]}"'
            for s in DEFAULT_SECTIONS
            if s.get("level") == 2
        )

        user = (
            f"这是{sample.get('sample_year')}年{sample.get('sample_month')}月的国际油价月报样例，"
            f"请你更新数据，生成{oy}年{om}月的国际油价月报。\n"
            f"回顾月份：{ry}年{rm}月；展望月份：{oy}年{om}月。\n"
            f"本期期号：{issue_no}；报告日期：{report_date}。\n\n"
            f"【样例全文（yuebao/yuebao）】\n"
            f"{json.dumps(sample, ensure_ascii=False, default=str)}\n\n"
            f"【现货市场数据库摘要（review_spot 须引用，与图1-4~1-6 同源）】\n"
            f"{json.dumps(AnalyticsService(self.db).build_spot_market_evidence(ry, rm), ensure_ascii=False, default=str)}\n\n"
            f"【需要撰写的子章节（保持 id 不变，标题可按当月主题润色）】\n{section_list}\n\n"
            f"{extra_instruction}\n\n"
            "请严格输出如下 JSON：\n"
            "{\n"
            '  "summary": "内容摘要,可两段,用\\n分隔",\n'
            '  "sections": [{"id": "review_futures", "title": "（一）期货市场回顾", "content": "..."}],\n'
            '  "tables": {\n'
            '    "table_price_change": {"rows": []},\n'
            f'    "table_scenario": {{"rows": [["{oy}年{om}月","104","100","150"],["本季度","95","90","120"],["全年","80","75","90"]]}},\n'
            f'    "table_agency": {{"rows": [["{oy}年{om}月","125","112","109"],["本季度","112","90","105"],["全年","90","80","95"]]}}\n'
            "  },\n"
            '  "approval": {"author": "执笔：...", "reviewer": "初审：...", "approver": "审核：...", "signer": "签发：..."}\n'
            "}\n"
            f"sections 必须覆盖全部子章节 id：{', '.join(section_ids)}。\n"
            "注意：表1-1（table_price_change）由系统从数据库后处理，请勿填写 rows。"
        )

        llm_used = False
        content = base
        if llm.is_enabled(provider):
            try:
                with llm_context(
                    "report_unrestricted_skill",
                    review_year=ry,
                    review_month=rm,
                    outlook_year=oy,
                    outlook_month=om,
                    sample_year=sample.get("sample_year"),
                    sample_month=sample.get("sample_month"),
                    mode=mode,
                ):
                    raw = llm.chat_json(
                        SYSTEM_PROMPT,
                        user,
                        provider=provider,
                        model=model,
                        mode=mode,
                    )
                content = self._merge(base, raw)
                llm_used = True
            except llm.LLMUnavailable as exc:
                logger.warning("无限制月报 skill 大模型不可用：%s", exc)

        brent = self.analytics.calc_monthly_stats("Brent", ry, rm)
        wti = self.analytics.calc_monthly_stats("WTI", ry, rm)
        spot_market = self.analytics.build_spot_market_evidence(ry, rm)
        evidence = {
            "mode": "unrestricted",
            "sample_file": sample.get("sample_file"),
            "sample_year": sample.get("sample_year"),
            "sample_month": sample.get("sample_month"),
            "review_period": f"{ry}年{rm}月",
            "outlook_period": f"{oy}年{om}月",
            "brent": brent,
            "wti": wti,
            "spot_market": spot_market,
        }
        content = guard_report_content(content, evidence)
        tables, table_meta = ReportTableDataService(self.db).load_for_report(ry, rm, oy, om)
        for key in SYSTEM_TABLE_KEYS:
            if key in tables:
                content.setdefault("tables", {})[key] = {
                    k: v for k, v in tables[key].items()
                    if k in ("title", "source", "headers", "rows")
                }
        evidence["table_snapshots"] = table_meta

        return {
            "content": content,
            "evidence": evidence,
            "sources_used": [
                {"name": sample.get("sample_file", "yuebao样例"), "url": "", "categories": ["样例"]}
            ],
            "references": {},
            "web_references": [],
            "llm_used": llm_used,
            "model": model or "",
        }

    def _merge(self, base: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
        content = json.loads(json.dumps(base, ensure_ascii=False))
        if raw.get("summary"):
            content["summary"] = str(raw["summary"]).strip()
        sec_by_id = {str(s.get("id")): s for s in raw.get("sections", []) if isinstance(s, dict)}
        for sec in content["sections"]:
            if sec["level"] != 2:
                continue
            got = sec_by_id.get(sec["id"])
            if got:
                if got.get("title"):
                    sec["title"] = str(got["title"]).strip()
                sec["content"] = str(got.get("content", "")).strip()
        raw_tables = raw.get("tables", {}) or {}
        for key, tbl in content["tables"].items():
            if key in SYSTEM_TABLE_KEYS:
                continue
            rt = raw_tables.get(key)
            if isinstance(rt, dict) and isinstance(rt.get("rows"), list):
                tbl["rows"] = [[str(c) for c in row] for row in rt["rows"] if isinstance(row, list)]
        appr = raw.get("approval", {}) or {}
        for k in ("author", "reviewer", "approver", "signer"):
            if appr.get(k):
                content["approval"][k] = str(appr[k]).strip()
        return content
