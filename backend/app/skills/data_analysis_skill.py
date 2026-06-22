import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core import llm
from app.schemas.common import AnalysisQueryParams, DataQueryParams
from app.services.data_query import DataQueryService

_ANALYSIS_SYSTEM_PROMPT = (
    "你是能源数据分析助手，职责是解读平台数据库查询结果（evidence）。\n"
    "硬性规则：\n"
    "1. 只能使用 evidence 中出现的数值、日期、机构、周期；禁止引用证据范围外的「近期」「最新」「当前市场」等外部行情。\n"
    "2. 用户问题若含「近期」等模糊时间，一律以 evidence.params 与【数据范围】为准，不得自行扩展时间窗口。\n"
    "3. 证据缺失的指标须明确写「证据中无该数据」，禁止用常识或训练知识补数。\n"
    "4. 引用数值时注明对应品种/机构/月份或日期，优先使用 monthly_stats、series、balance.rows 中的字段。"
)


class DataAnalysisSkill:
    def __init__(self, db: Session):
        self.db = db
        self.query_service = DataQueryService(db)

    def query(self, params: DataQueryParams) -> dict[str, Any]:
        start = time.time()
        data = self.query_service.query(params)
        charts = self.query_service.charts_for(params) if getattr(params, "include_charts", True) else []
        return {
            "params": params.model_dump(mode="json"),
            "data": data,
            "charts": charts,
            "tools_called": ["data_query"],
            "duration_ms": round((time.time() - start) * 1000, 1),
        }

    def analyze(
        self,
        params: AnalysisQueryParams,
        provider: str | None = None,
        model: str | None = None,
        mode: str = "deep_research",
    ) -> dict[str, Any]:
        result = self.query(params)
        response = ""
        if params.question.strip():
            if provider and provider != "mock" and llm.is_enabled(provider):
                evidence = self._build_llm_evidence(params, result["data"])
                llm_text = llm.chat(
                    [
                        {"role": "system", "content": _ANALYSIS_SYSTEM_PROMPT},
                        {"role": "user", "content": self._build_user_prompt(params, evidence)},
                    ],
                    provider=provider,
                    model=model,
                    mode=mode,
                )
                response = llm_text or self._format_summary(params.question, result["data"])
            else:
                response = self._format_summary(params.question, result["data"])
        result["response"] = response
        return result

    @staticmethod
    def _describe_scope(params: DataQueryParams) -> str:
        lines = [f"品类：{params.category}"]
        if params.start_date or params.end_date:
            lines.append(f"价格日度范围：{params.start_date or '…'} 至 {params.end_date or '…'}")
        if params.year and params.month:
            ym = f"{params.year}-{params.month:02d}"
            if params.category in ("balance", "mixed"):
                lines.append(f"供需快照月（snapshot_month）：{ym}")
            elif params.category == "factor":
                lines.append(f"因素报告月（report_month）：{ym}")
            else:
                lines.append(f"价格统计月：{ym}")
        if params.symbols:
            lines.append(f"品种：{', '.join(params.symbols)}")
        if params.agencies:
            lines.append(f"机构：{', '.join(params.agencies)}")
        if params.supply_demand:
            lines.append(f"供需类型：{', '.join(params.supply_demand)}")
        if params.periods:
            lines.append(f"周期：{', '.join(params.periods)}")
        if params.factor_categories:
            lines.append(f"因素大类：{', '.join(params.factor_categories)}")
        if params.factor_names:
            lines.append(f"因素名：{', '.join(params.factor_names)}")
        lines.append("以上范围为本次数据库查询条件，分析不得超出该范围。")
        return "\n".join(lines)

    def _build_llm_evidence(self, params: AnalysisQueryParams, data: dict[str, Any]) -> dict[str, Any]:
        """压缩 evidence 供 LLM 阅读，保留统计与明细、日度序列仅保留首尾样本。"""
        compact: dict[str, Any] = {"params": params.model_dump(mode="json"), "data": {}}
        raw = data

        def compact_block(block: dict[str, Any], *, is_price: bool) -> dict[str, Any]:
            out = dict(block)
            series = block.get("series") or []
            if is_price and series:
                out["series_count"] = len(series)
                out["series_sample"] = series[:5] + (series[-3:] if len(series) > 8 else [])
                out.pop("series", None)
            return out

        if raw.get("category") == "mixed":
            if raw.get("price"):
                compact["data"]["price"] = compact_block(raw["price"], is_price=True)
            if raw.get("balance"):
                compact["data"]["balance"] = raw["balance"]
            if raw.get("factor"):
                compact["data"]["factor"] = raw["factor"]
        elif raw.get("category") == "price":
            compact["data"] = compact_block(raw, is_price=True)
        else:
            compact["data"] = raw

        compact["summary"] = self._evidence_digest(data)
        return compact

    @staticmethod
    def _evidence_digest(data: dict[str, Any]) -> str:
        parts: list[str] = []
        blocks: list[tuple[str, dict]] = []
        if data.get("category") == "mixed":
            for key in ("price", "balance", "factor"):
                if data.get(key):
                    blocks.append((key, data[key]))
        else:
            blocks.append((str(data.get("category", "data")), data))

        for name, block in blocks:
            if name == "price" or block.get("monthly_stats") is not None:
                stats = block.get("monthly_stats") or []
                series = block.get("series") or []
                parts.append(f"价格：月度统计 {len(stats)} 项，日度 {len(series)} 条")
            elif name == "balance" or block.get("rows") is not None:
                rows = block.get("rows") or []
                parts.append(f"供需：{len(rows)} 条（快照月 {block.get('snapshot_month', '—')}）")
            elif name == "factor" or block.get("rows") is not None:
                rows = block.get("rows") or []
                parts.append(f"因素：{len(rows)} 条")
        return "；".join(parts) if parts else "无数据"

    def _build_user_prompt(self, params: AnalysisQueryParams, evidence: dict[str, Any]) -> str:
        focus = params.question.strip() or "全面解读证据中的数据变化与业务含义"
        return (
            f"【数据范围（唯一有效时间窗口，不得超出）】\n"
            f"{self._describe_scope(params)}\n\n"
            f"【数据摘要】\n{evidence.get('summary', '')}\n\n"
            f"【用户分析重点】\n{focus}\n"
            f"（若重点含「近期」等表述，仍须严格限定在上述数据范围内解读。）\n\n"
            f"【evidence】\n"
            f"{json.dumps(evidence, ensure_ascii=False, default=str)}"
        )

    @staticmethod
    def _format_summary(question: str, data: dict[str, Any]) -> str:
        lines = [f"基于平台数据库查询结果：{question or '数据查询结果'}"]
        if "price" in data or data.get("category") == "price":
            block = data.get("price", data)
            stats = block.get("monthly_stats") or []
            for item in stats[:4]:
                month = item.get("month")
                month_label = f"{month:02d}" if isinstance(month, int) else "—"
                lines.append(
                    f"- {item.get('symbol')} {item.get('year')}-{month_label}: "
                    f"均价 {item.get('avg')}，环比 {item.get('mom_pct')}%，同比 {item.get('yoy_pct')}%"
                )
            if block.get("series"):
                lines.append(f"- 日度序列 {len(block['series'])} 条")
        if "balance" in data or data.get("category") == "balance":
            block = data.get("balance", data)
            rows = block.get("rows") or []
            lines.append(f"- 供需记录 {len(rows)} 条（快照月 {block.get('snapshot_month', '—')}）")
        if "factor" in data or data.get("category") == "factor":
            block = data.get("factor", data)
            lines.append(f"- 因素记录 {len(block.get('rows') or [])} 条")
        return "\n".join(lines)
