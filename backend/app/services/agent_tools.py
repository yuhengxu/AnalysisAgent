"""Agent 可调用的本地平台数据工具。

联网检索由大模型 DeepSearch 直接完成，不再经过独立浏览器服务。
"""
from __future__ import annotations

import json
from typing import Any

from app.core.timezone import now_beijing_naive
from app.services.analytics import AnalyticsService


class AgentTools:
    TOOL_CATALOG = [
        {
            "id": "query_platform_data",
            "name": "平台数据库",
            "desc": "读取平台内油价、价差、供需平衡等结构化数据",
        },
    ]

    def __init__(self, analytics: AnalyticsService):
        self.analytics = analytics

    @staticmethod
    def list_tools() -> list[dict[str, str]]:
        return AgentTools.TOOL_CATALOG

    @staticmethod
    def _platform_latest_date(dashboard: dict[str, Any]) -> str | None:
        symbols = dashboard.get("symbols") or {}
        dates = [v.get("latest_date") for v in symbols.values() if v.get("latest_date")]
        return max(dates) if dates else None

    @staticmethod
    def _today_iso() -> str:
        return now_beijing_naive().strftime("%Y-%m-%d")

    def _platform_data_stale(self) -> bool:
        dash = self.analytics.dashboard_summary()
        latest = self._platform_latest_date(dash)
        if not latest:
            return True
        return latest < self._today_iso()

    def plan_tools(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        search_plan: dict[str, Any] | None = None,
    ) -> list[str]:
        """本地工具仅负责平台结构化数据；联网由 DeepSearch 完成。"""
        return ["query_platform_data"]

    def execute(
        self,
        tool_id: str,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        search_plan: dict[str, Any] | None = None,
    ) -> Any:
        if tool_id == "query_platform_data":
            return self._query_platform_data(prompt)
        return {"error": f"unknown tool: {tool_id}"}

    def gather_context(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        search_plan: dict[str, Any] | None = None,
    ) -> tuple[list[str], dict[str, Any]]:
        tools_called: list[str] = []
        evidence: dict[str, Any] = {
            "_meta": {
                "today": self._today_iso(),
                "platform_data_stale": self._platform_data_stale(),
                "online_provider": "deepsearch",
            }
        }
        if search_plan is not None:
            evidence["_meta"]["search_plan"] = {
                "need_search": search_plan.get("need_search"),
                "reason": search_plan.get("reason", ""),
                "search_queries": search_plan.get("search_queries", []),
            }

        for tool_id in self.plan_tools(prompt, history, search_plan):
            tools_called.append(tool_id)
            try:
                evidence[tool_id] = self.execute(tool_id, prompt, history, search_plan)
            except Exception as exc:  # noqa: BLE001
                evidence[tool_id] = {"error": str(exc)}
        return tools_called, evidence

    def _query_platform_data(self, prompt: str) -> dict[str, Any]:
        lower = prompt.lower()
        symbols = []
        for sym in ("Brent", "WTI", "Dubai", "Oman"):
            if sym.lower() in lower:
                symbols.append(sym)
        if not symbols:
            symbols = ["Brent", "WTI"]

        dash = self.analytics.dashboard_summary()
        latest = self._platform_latest_date(dash)
        payload: dict[str, Any] = {
            "dashboard": dash,
            "symbols": symbols,
            "latest_date": latest,
            "today": self._today_iso(),
            "is_stale": latest < self._today_iso() if latest else True,
        }
        if any(k in lower for k in ("价差", "spread")):
            payload["spread"] = self.analytics.calc_spread("Brent", "WTI")[-15:]
        if "balance" in lower or "供需" in prompt:
            payload["balance_forecast"] = self.analytics.query_balance_forecast()[:20]
        return payload

    @staticmethod
    def evidence_brief(evidence: dict[str, Any]) -> str:
        brief: dict[str, Any] = {}
        meta = evidence.get("_meta", {})
        if meta:
            brief["_meta"] = meta

        for key, val in evidence.items():
            if key.startswith("_"):
                continue
            if key == "query_platform_data":
                brief[key] = val
            else:
                brief[key] = val
        return json.dumps(brief, ensure_ascii=False, default=str)
