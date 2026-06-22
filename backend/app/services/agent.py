import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core import llm
from app.core.llm import llm_context
from app.core.config import settings
from app.core.timezone import now_beijing_naive
from app.models.agent_run import AgentRun
from app.schemas.common import AnalysisQueryParams, PredictionGenerateRequest
from app.services.agent_tools import AgentTools
from app.services.analytics import AnalyticsService
from app.skills.data_analysis_skill import DataAnalysisSkill
from app.services.forecast import ForecastService
from app.services.prediction import PredictionService
from app.services.prediction_tasks import create_task, start_task, task_to_dict
from app.services.report import ReportService
from app.services.revise_context import build_revise_context


def _agent_chat_system(*, deep_search: bool = False) -> str:
    today = now_beijing_naive().strftime("%Y年%m月%d日")
    if deep_search:
        net_boundary = (
            "【联网能力边界】\n"
            "你当前以 DeepSearch 深度研究模式运行，自带联网搜索、浏览器使用、网页解析等 MCP 能力，"
            "可直接检索并引用实时信息，但引用时必须给出真实来源（名称、URL、期别），不得编造。\n"
        )
    else:
        net_boundary = (
            "【联网能力边界】\n"
            "当前不是 DeepSearch 模式，不能声称已联网，也不能补写未经检索的网页、数字、日期或 URL。\n"
        )
    return (
        f"你是中国海油集团能源经济研究院的 AI 助手，具备能源行业专业分析能力，"
        f"同时可自由讨论各类开放式话题。今天是 {today}。语气专业、简洁、有据可查。\n\n"
        + net_boundary
        + "\n【对话范围】\n"
        "你可以回答各类问题（如天气、股票、黄金、常识、翻译、闲聊等），不限于能源话题。"
        "涉及能源市场时，优先运用专业分析能力。\n\n"
        "你可以：\n"
        "1) 解读平台数据库中的油价、价差、供需等结构化数据；\n"
        "2) 在 DeepSearch 模式下直接联网检索并回答时效性问题；\n"
        "3) 在用户明确要求时，触发平台交付能力：智能分析、情景预测、预测分析表、国际油价月报。\n"
        "【回答规则】\n"
        "- 须区分「平台数据」与「DeepSearch 联网检索」来源，只能使用实际取得的证据；\n"
        "- 工具证据不足或未覆盖用户问题时：可结合通用知识作答，"
        "须明确标注「以下为通用知识，非实时检索结果」，不得将通用知识冒充为工具检索所得；\n"
        "- 严禁编造工具未返回的数字、日期、URL，"
        "或「已检索到某数据」「我已联网查询」之类的假象；\n"
        "- 若 DeepSearch 未配置、失败或未返回结果，不得虚构检索过程或结果；"
        "可改用通用知识尝试回答（并标注来源性质），或说明无法获取实时数据；\n"
        "- 平台数据 latest_date 早于今天时，不得将其当作「今天」的价格，须标注实际日期并说明滞后；\n"
        "- 用户问「今天」价格而平台数据滞后时，应使用 DeepSearch 查证。"
    )

_VISUAL_ASSISTANT_MARKERS = ("粒子外观", "粒子配色", "微调可视化", "粒子化的能源分析助手")


class AgentService:
    SKILLS = {
        "predict_table": "油价预测分析表",
        "report": "国际油价月报",
        "predict": "情景预测模型",
        "analyze": "数据分析",
        "web_search": "DeepSearch 联网查证",
    }

    VISUAL_PRESETS: dict[str, dict[str, Any]] = {
        "idle": {
            "mood": "idle",
            "colors": ["#a8d4ff", "#E4002B", "#ffffff"],
            "particle_speed": 0.9,
            "glow_intensity": 0.55,
            "pulse_rate": 1.0,
            "status_text": "在线 · 随时为您服务",
        },
        "listening": {
            "mood": "listening",
            "colors": ["#7fb3ff", "#5ce1ff", "#ffffff"],
            "particle_speed": 1.1,
            "glow_intensity": 0.7,
            "pulse_rate": 1.3,
            "status_text": "正在聆听…",
        },
        "thinking": {
            "mood": "thinking",
            "colors": ["#c8e6ff", "#7fb3ff", "#E4002B"],
            "particle_speed": 1.8,
            "glow_intensity": 0.85,
            "pulse_rate": 2.0,
            "status_text": "思考与编排工具中…",
        },
        "analyzing": {
            "mood": "analyzing",
            "colors": ["#ff6b8a", "#E4002B", "#7fb3ff"],
            "particle_speed": 1.5,
            "glow_intensity": 0.8,
            "pulse_rate": 1.6,
            "status_text": "数据分析中",
        },
        "predicting": {
            "mood": "predicting",
            "colors": ["#5ce1ff", "#002D72", "#a8d4ff"],
            "particle_speed": 1.6,
            "glow_intensity": 0.82,
            "pulse_rate": 1.7,
            "status_text": "情景预测演算中",
        },
        "reporting": {
            "mood": "reporting",
            "colors": ["#ffd166", "#E4002B", "#ffffff"],
            "particle_speed": 1.2,
            "glow_intensity": 0.75,
            "pulse_rate": 1.4,
            "status_text": "月报撰写中",
        },
        "success": {
            "mood": "success",
            "colors": ["#6dffb8", "#7fb3ff", "#ffffff"],
            "particle_speed": 1.0,
            "glow_intensity": 0.9,
            "pulse_rate": 1.2,
            "status_text": "任务完成",
        },
        "futuristic": {
            "mood": "idle",
            "colors": ["#e8f4ff", "#5ce1ff", "#7fb3ff"],
            "particle_speed": 1.4,
            "glow_intensity": 1.0,
            "pulse_rate": 1.8,
            "status_text": "未来感粒子场",
        },
    }

    def __init__(self, db: Session):
        self.db = db
        self.analytics = AnalyticsService(db)
        self.forecast = ForecastService(db)
        self.report = ReportService(db)
        self.prediction = PredictionService(db)
        self.tools = AgentTools(self.analytics)

    @staticmethod
    def _needs_deepsearch(prompt: str) -> bool:
        """识别需要实时联网的问题；所有联网统一交给 DeepSearch。"""
        return any(
            marker in prompt
            for marker in (
                "最新", "今日", "今天", "实时", "查证", "联网", "检索", "搜索", "网上", "新闻",
                "天气", "气温", "降雨", "台风", "股票", "金价", "汇率", "收盘",
            )
        )

    def _resolve_model(self, provider: str, model_name: str | None) -> str:
        if model_name:
            return model_name
        if provider == "deepseek":
            return settings.deepseek_model
        if provider == "volcengine":
            return settings.volcengine_model
        if provider == "openai":
            return settings.openai_model
        return "mock"

    def _run_web_search(
        self,
        prompt: str,
        history: list[dict[str, str]],
        provider: str,
        model: str,
        mode: str = "deep_research",
    ) -> dict[str, Any]:
        """联网查证 skill：强制使用火山 DeepSearch，不设浏览器服务降级。"""
        safe_history = self._sanitize_history_for_llm(history)
        if not llm.deep_search_available() or not llm.is_enabled("volcengine"):
            raise llm.LLMUnavailable("DeepSearch 未配置，无法执行联网查证")
        provider = "volcengine"
        model = self._resolve_model(provider, None)
        tools_called, evidence = self.tools.gather_context(prompt, history=safe_history)
        response = self._general_chat(
            prompt,
            history,
            provider,
            model,
            "deep_research",
            evidence,
            tools_called,
            deep_search=True,
        )
        return {
            "response": response,
            "tools_called": tools_called,
            "evidence": evidence,
            "charts": [],
        }

    def run(
        self,
        prompt: str,
        skill: str = "analyze",
        model_provider: str | None = None,
        model_name: str | None = None,
        mode: str = "deep_research",
        trusted_sources_only: bool = False,
    ) -> dict[str, Any]:
        start = time.time()
        provider = model_provider or settings.default_llm_provider
        model = self._resolve_model(provider, model_name)
        mode = llm.normalize_mode(mode)
        tools_called: list[str] = []
        evidence: dict[str, Any] = {}
        charts: list[dict[str, Any]] = []

        if skill == "predict_table":
            tools_called.extend(["collect_authoritative_data", "llm_fill_prediction_table"])
            year, month = self._extract_year_month(prompt)
            pred = self.prediction.generate(
                symbol=self._extract_symbol(prompt),
                year=year,
                month=month,
                provider=None if provider == "mock" else provider,
                model=model,
                mode=mode,
                extra_instruction=prompt,
                trusted_sources_only=trusted_sources_only,
            )
            evidence["prediction_id"] = pred["id"]
            evidence["llm_used"] = pred.get("llm_used")
            response = (
                f"已生成《{pred['title']}》，覆盖六大类影响因素并给出布伦特首行合约价格预测。"
                "可在「预测分析表」页查看、校准并导出 Excel。"
            )
        elif skill == "predict":
            tools_called.extend(["run_forecast_model", "generate_chart"])
            symbol = self._extract_symbol(prompt)
            forecast = self.forecast.run_forecast(symbol)
            evidence["forecast"] = forecast
            charts = [
                self._forecast_chart_config(forecast),
                self.analytics.chart_config("price_trend", symbols=[symbol, "WTI"]),
            ]
            response = self._format_forecast_response(forecast)
        elif skill == "report":
            tools_called.extend(["collect_authoritative_data", "llm_draft_report_section"])
            year, month = self._extract_year_month(prompt)
            review_year, review_month = (year, month - 1) if month > 1 else (year - 1, 12)
            report = self.report.generate_monthly_draft(
                issue_no=f"{year}年第{month}期",
                report_date=f"{year}年{month}月",
                review_month=(review_year, review_month),
                outlook_month=(year, month),
                provider=None if provider == "mock" else provider,
                model=model,
                mode=mode,
                extra_instruction=prompt,
                trusted_sources_only=trusted_sources_only,
            )
            evidence["report_id"] = report["id"]
            evidence["llm_used"] = report.get("llm_used")
            response = f"已生成月报初稿：{report['title']}。可在报告中心查看、校准并导出 Word。"
        elif skill == "web_search":
            result = self._run_web_search(prompt, [], provider, model, mode=mode)
            tools_called = result["tools_called"]
            evidence = result["evidence"]
            response = result["response"]
        else:
            stats_year, stats_month = self._extract_year_month(prompt)
            params = AnalysisQueryParams(
                category="mixed",
                question=prompt,
                year=stats_year,
                month=stats_month,
                symbols=["Brent", "WTI"],
                include_charts=True,
                model_provider=provider,
                model_name=model,
                mode=mode,
            )
            result = DataAnalysisSkill(self.db).analyze(params, provider, model, mode)
            tools_called = list(result.get("tools_called", ["data_query"]))
            evidence = {"params": result.get("params"), "data": result.get("data")}
            charts = result.get("charts", [])
            response = result.get("response", "")

        duration = (time.time() - start) * 1000
        run = AgentRun(
            skill=skill,
            prompt=prompt,
            model_provider=provider,
            model_name=model,
            tools_called=json.dumps(tools_called, ensure_ascii=False),
            evidence_json=json.dumps(evidence, ensure_ascii=False, default=str),
            response=response,
            charts_json=json.dumps(charts, ensure_ascii=False, default=str),
            duration_ms=duration,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return {
            "id": run.id,
            "skill": skill,
            "response": response,
            "tools_called": tools_called,
            "evidence": evidence,
            "charts": charts,
            "duration_ms": duration,
        }

    def _extract_symbol(self, prompt: str) -> str:
        for sym in ("Brent", "WTI", "Dubai", "Oman"):
            if sym.lower() in prompt.lower():
                return sym
        return "Brent"

    def _extract_year_month(self, prompt: str) -> tuple[int, int]:
        import re

        m = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月", prompt)
        if m:
            return int(m.group(1)), int(m.group(2))
        m2 = re.search(r"(\d{1,2})\s*月", prompt)
        now = now_beijing_naive()
        if m2:
            return now.year, int(m2.group(1))
        return now.year, now.month

    def _forecast_chart_config(self, forecast: dict[str, Any]) -> dict[str, Any]:
        label_map = {"baseline": "基准", "optimistic": "乐观", "pessimistic": "悲观"}
        return {
            "title": f"{forecast['symbol']} {forecast['period']} 情景预测",
            "xAxis": "情景",
            "yAxis": "价格 (USD/bbl)",
            "source": "平台预测模型",
            "series": [
                {
                    "name": forecast["symbol"],
                    "data": [
                        [label_map.get(s["scenario"], s["scenario"]), s["point"]]
                        for s in forecast["scenarios"]
                    ],
                }
            ],
        }

    def _format_forecast_response(self, forecast: dict[str, Any]) -> str:
        lines = [f"【{forecast['symbol']} {forecast['period']} 预测结果】"]
        for s in forecast["scenarios"]:
            lines.append(f"- {s['scenario']}：{s['point']} USD/bbl（区间 {s['low']}-{s['high']}）")
        lines.append(f"依据：{forecast['evidence']}")
        return "\n".join(lines)

    def _format_analysis_response(self, prompt: str, evidence: dict[str, Any]) -> str:
        brent = evidence.get("brent_stats", {})
        summary = evidence.get("summary", {}).get("symbols", {})
        lines = [
            "基于平台数据的分析结论：",
            f"1. Brent 最新均价约 {brent.get('avg', 'N/A')} USD/bbl，环比 {brent.get('mom_pct', 'N/A')}%。",
        ]
        if "Brent" in summary:
            lines.append(
                f"2. Brent 最新价格 {summary['Brent']['latest_price']}，月均价 {summary['Brent']['month_avg']}。"
            )
        spread_tail = evidence.get("spread_tail", [])
        if spread_tail:
            lines.append(f"3. 近期 Brent-WTI 价差约 {spread_tail[-1]['spread']} USD/bbl。")
        lines.append("以上结论均来自数据库查询结果，可在图表区查看对应可视化。")
        return "\n".join(lines)

    def _call_llm(
        self,
        prompt: str,
        evidence: dict[str, Any],
        provider: str,
        model: str,
        mode: str = "deep_research",
    ) -> str | None:
        if not llm.is_enabled(provider):
            return None
        try:
            with llm_context("agent_analyze", prompt=prompt[:200], mode=mode):
                return llm.chat(
                    [
                        {
                            "role": "system",
                            "content": "你是能源行业数据分析助手。只能基于提供的 evidence 回答，不得编造数字。",
                        },
                        {
                            "role": "user",
                            "content": f"用户问题：{prompt}\n\n证据数据：{json.dumps(evidence, ensure_ascii=False, default=str)}",
                        },
                    ],
                    provider=provider,
                    model=model,
                    temperature=0.2,
                    mode=mode,
                )
        except llm.LLMUnavailable:
            return None

    def chat(
        self,
        messages: list[dict[str, str]],
        skill_hint: str | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
        mode: str = "deep_research",
        trusted_sources_only: bool = False,
    ) -> dict[str, Any]:
        start = time.time()
        provider = model_provider or settings.default_llm_provider
        model = self._resolve_model(provider, model_name)
        mode = llm.normalize_mode(mode)
        user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
        prompt = user_msgs[-1] if user_msgs else ""
        history = messages[:-1] if messages else []

        visual_key = self._detect_visual_intent(prompt)
        if visual_key:
            visual = dict(self.VISUAL_PRESETS[visual_key])
            reply = self._visual_reply(prompt, visual_key)
            duration = (time.time() - start) * 1000
            return {
                "message": reply,
                "visual": visual,
                "charts": [],
                "tools_called": [],
                "skill": None,
                "report_id": None,
                "duration_ms": duration,
            }

        skill = skill_hint or self._detect_skill(prompt)
        mood = "thinking"
        tools_called: list[str] = []
        charts: list[dict[str, Any]] = []
        report_id = None
        evidence: dict[str, Any] = {}

        prediction_id = None
        async_task: dict[str, Any] | None = None

        if skill == "predict_table":
            mood = "predicting"
            tools_called = ["collect_authoritative_data", "llm_fill_prediction_table"]
            year, month = self._extract_year_month(prompt)
            body = PredictionGenerateRequest(
                symbol=self._extract_symbol(prompt),
                year=year,
                month=month,
                model_provider=provider,
                model_name=model,
                mode=mode,
                extra_instruction=prompt,
                trusted_sources_only=trusted_sources_only,
            )
            task = create_task(total_steps=7)
            start_task(task.id, body)
            async_task = {**task_to_dict(task), "type": "predict_table", "skill": skill}
            reply = (
                f"已启动《{year}年{month}月油价预测分析表》生成任务（分 7 步多轮调用大模型）。\n"
                "生成过程中可继续对话；完成后将自动展示结果链接。"
            )
        elif skill:
            mood = {
                "analyze": "analyzing",
                "predict": "predicting",
                "report": "reporting",
                "web_search": "thinking",
            }.get(skill, "thinking")
            if skill == "web_search":
                run_result = self._run_web_search(
                    prompt=prompt,
                    history=history,
                    provider=provider,
                    model=model,
                    mode=mode,
                )
            else:
                run_result = self.run(
                    prompt=prompt,
                    skill=skill,
                    model_provider=provider,
                    model_name=model,
                    mode=mode,
                    trusted_sources_only=trusted_sources_only,
                )
            tools_called = run_result.get("tools_called", [])
            charts = run_result.get("charts", [])
            evidence = run_result.get("evidence", {})
            report_id = evidence.get("report_id")
            prediction_id = evidence.get("prediction_id")
            reply = self._wrap_skill_reply(
                skill, run_result["response"], prompt, run_result.get("evidence")
            )
            mood = "success"
        else:
            safe_history = self._sanitize_history_for_llm(history)
            effective_mode = mode
            # 所有实时联网统一走豆包 DeepSearch。
            use_deep_search = (
                provider == "volcengine"
                and effective_mode == "deep_research"
                and llm.deep_search_available()
            )
            if (
                not use_deep_search
                and llm.deep_search_available()
                and self._needs_deepsearch(prompt)
            ):
                provider = "volcengine"
                model = self._resolve_model(provider, None)
                effective_mode = "deep_research"
                use_deep_search = True
            tools_called, evidence = self.tools.gather_context(prompt, history=safe_history)
            reply = self._general_chat(
                prompt,
                history,
                provider,
                model,
                effective_mode,
                evidence,
                tools_called,
                deep_search=use_deep_search,
            )

        visual = dict(self.VISUAL_PRESETS.get(mood, self.VISUAL_PRESETS["idle"]))
        duration = (time.time() - start) * 1000
        run = AgentRun(
            skill=skill or "chat",
            prompt=prompt,
            model_provider=provider,
            model_name=model,
            tools_called=json.dumps(tools_called, ensure_ascii=False),
            evidence_json=json.dumps(evidence, ensure_ascii=False, default=str),
            response=reply,
            charts_json=json.dumps(charts, ensure_ascii=False, default=str),
            duration_ms=duration,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return {
            "id": run.id,
            "message": reply,
            "visual": visual,
            "charts": charts,
            "tools_called": tools_called,
            "skill": skill,
            "report_id": report_id,
            "prediction_id": prediction_id,
            "async_task": async_task,
            "duration_ms": duration,
        }

    def _detect_skill(self, prompt: str) -> str | None:
        """仅在用户明确要求「交付物」时命中 skill，其余走工具增强对话。"""
        lower = prompt.lower()
        if any(k in prompt for k in ("联网查询", "联网搜索", "上网查", "联网查一下", "网上搜", "在线检索")):
            return "web_search"
        if any(k in prompt for k in ("预测分析表", "预测表", "影响因素表")):
            return "predict_table"
        if any(k in prompt for k in ("生成月报", "国际油价月报", "撰写月报", "月报初稿")):
            return "report"
        if any(k in prompt for k in ("生成报告",)) and "月报" in prompt:
            return "report"
        if any(k in prompt for k in ("情景预测", "运行预测模型", "预测模型")):
            return "predict"
        if any(k in lower for k in ("forecast",)) and "表" not in prompt:
            return "predict"
        if any(k in prompt for k in ("运行分析", "数据分析", "分析任务")) and "表" not in prompt:
            return "analyze"
        return None

    def _detect_visual_intent(self, prompt: str) -> str | None:
        lower = prompt.lower()
        if any(k in prompt for k in ("科技感", "未来感", "科幻", "粒子", "发光", "霓虹", "悬浮")):
            return "futuristic"
        if any(k in prompt for k in ("恢复默认", "默认样式", "还原")):
            return "idle"
        if any(k in prompt for k in ("加快", "更快", "急促")):
            preset = dict(self.VISUAL_PRESETS["thinking"])
            preset["particle_speed"] = 2.4
            preset["pulse_rate"] = 2.5
            preset["status_text"] = "高速粒子流"
            self.VISUAL_PRESETS["_custom_fast"] = preset
            return "_custom_fast"
        if any(k in prompt for k in ("冷静", "慢", "舒缓")):
            preset = dict(self.VISUAL_PRESETS["idle"])
            preset["particle_speed"] = 0.5
            preset["pulse_rate"] = 0.7
            preset["status_text"] = "舒缓呼吸态"
            self.VISUAL_PRESETS["_custom_calm"] = preset
            return "_custom_calm"
        if any(k in prompt for k in ("红色", "警示", "风险")):
            preset = dict(self.VISUAL_PRESETS["analyzing"])
            preset["colors"] = ["#E4002B", "#ff4466", "#ff9eb0"]
            preset["status_text"] = "风险强调色"
            self.VISUAL_PRESETS["_custom_red"] = preset
            return "_custom_red"
        if any(k in prompt for k in ("蓝色", "冷静色调")):
            preset = dict(self.VISUAL_PRESETS["predicting"])
            preset["status_text"] = "冷色科技场"
            self.VISUAL_PRESETS["_custom_blue"] = preset
            return "_custom_blue"
        return None

    def _is_visual_only_prompt(self, prompt: str) -> bool:
        return self._detect_visual_intent(prompt) is not None

    def _sanitize_history_for_llm(self, history: list[dict[str, str]]) -> list[dict[str, str]]:
        """剔除粒子外观类对话，避免污染大模型上下文。"""
        cleaned: list[dict[str, str]] = []
        for m in history:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "user" and self._is_visual_only_prompt(content):
                continue
            if role == "assistant" and any(k in content for k in _VISUAL_ASSISTANT_MARKERS):
                continue
            cleaned.append({"role": role, "content": content})
        return cleaned[-20:]

    def _visual_reply(self, prompt: str, visual_key: str) -> str:
        preset = self.VISUAL_PRESETS.get(visual_key, self.VISUAL_PRESETS["idle"])
        status = preset.get("status_text", "已更新")
        return (
            f"已根据您的描述实时调整 Agent 粒子外观：{status}。\n"
            f"当前粒子配色：{', '.join(preset.get('colors', []))}。"
        )

    def _wrap_skill_reply(
        self,
        skill: str,
        core: str,
        prompt: str,
        evidence: dict[str, Any] | None = None,
    ) -> str:
        intro = {
            "analyze": "好的，我已完成数据分析并更新图表，结论如下：",
            "predict": "预测模型已运行完毕，情景结果如下：",
            "predict_table": "我已采集权威数据并填写油价预测分析表：",
            "report": "月报初稿已生成，您可在报告中心继续编辑：",
            "web_search": "已通过深度研究完成联网查证，结论如下：",
        }.get(skill, "处理完成：")
        return f"{intro}\n\n{core}"

    def _general_chat(
        self,
        prompt: str,
        history: list[dict[str, str]],
        provider: str,
        model: str,
        mode: str = "deep_research",
        evidence: dict[str, Any] | None = None,
        tools_called: list[str] | None = None,
        deep_search: bool = False,
    ) -> str:
        visual_key = self._detect_visual_intent(prompt)
        if visual_key:
            return self._visual_reply(prompt, visual_key)

        safe_history = self._sanitize_history_for_llm(history)
        if evidence is None or tools_called is None:
            tools_called, evidence = self.tools.gather_context(prompt, history=safe_history)

        evidence_text = AgentTools.evidence_brief(evidence)
        tool_note = "、".join(tools_called) if tools_called else "无"
        today = now_beijing_naive().strftime("%Y年%m月%d日")
        stale_note = ""
        platform = evidence.get("query_platform_data", {})
        if isinstance(platform, dict) and platform.get("is_stale"):
            stale_note = (
                f"\n注意：平台数据最新日期为 {platform.get('latest_date')}，"
                f"早于今天（{today}），不可当作今日价格。"
            )

        if llm.is_enabled(provider):
            msgs = [
                {"role": "system", "content": _agent_chat_system(deep_search=deep_search)},
                *safe_history,
                {
                    "role": "user",
                    "content": (
                        f"今天是 {today}。\n"
                        f"用户问题：{prompt}\n\n"
                        f"已调用工具：{tool_note}\n"
                        f"{stale_note}\n\n"
                        f"工具返回证据（请据此回答；证据不足时可结合通用知识，须标注来源性质，严禁编造）：\n{evidence_text}"
                    ),
                },
            ]
            try:
                with llm_context(
                    "agent_chat",
                    prompt=prompt[:200],
                    history_len=len(safe_history),
                    tools=tools_called,
                    mode=mode,
                ):
                    return llm.chat(
                        msgs,
                        provider=provider,
                        model=model,
                        temperature=0.4,
                        mode=mode,
                    )
            except llm.LLMUnavailable:
                pass

        return self._fallback_chat_reply(prompt, evidence, tools_called)

    def _fallback_chat_reply(
        self,
        prompt: str,
        evidence: dict[str, Any],
        tools_called: list[str],
    ) -> str:
        lines = [
            "已为您检索相关信息（大模型暂不可用，以下为工具原始摘要）：",
            f"调用工具：{' · '.join(tools_called)}",
        ]
        platform = evidence.get("query_platform_data", {})
        if platform:
            dash = platform.get("dashboard", {})
            lines.append(f"平台概览：{json.dumps(dash, ensure_ascii=False)[:600]}")
        lines.append(f"\n您的问题是：「{prompt[:100]}{'…' if len(prompt) > 100 else ''}」")
        return "\n".join(lines)

    def revise_selection(
        self,
        report_id: int,
        section_id: str,
        instruction: str,
        provider: str | None = None,
        model: str | None = None,
        mode: str = "deep_research",
    ) -> dict[str, Any]:
        report = self.report.get_report(report_id)
        if not report:
            raise ValueError("Report not found")
        content = json.loads(report.content_json)
        # 兼容结构化（sections 列表）与旧扁平格式
        target = None
        if section_id == "summary":
            old = content.get("summary", "")
        elif "sections" in content:
            for sec in content["sections"]:
                if sec.get("id") == section_id:
                    target = sec
                    break
            old = target.get("content", "") if target else ""
        else:
            old = content.get(section_id, "")

        evidence_meta = json.loads(report.evidence_json or "{}")
        context_text = build_revise_context(
            content=content,
            section_id=section_id,
            target_section=target,
            evidence_meta=evidence_meta,
        )
        revised = self._llm_revise(old, instruction, provider, model, mode, context_text)
        if section_id == "summary":
            content["summary"] = revised
        elif target is not None:
            target["content"] = revised
        else:
            content[section_id] = revised
        self.report.update_content(report_id, content)
        return {"section_id": section_id, "content": revised}

    def _llm_revise(
        self,
        old: str,
        instruction: str,
        provider: str | None,
        model: str | None,
        mode: str = "deep_research",
        context_text: str = "",
    ) -> str:
        prov = provider or settings.default_llm_provider
        resolved_model = self._resolve_model(prov, model)
        if llm.is_enabled(prov):
            try:
                user_content = f"【修改意见】{instruction}\n\n【待修改内容】\n{old}"
                if context_text:
                    user_content += f"\n\n{context_text}"
                with llm_context("agent_revise", instruction=instruction[:200], mode=mode):
                    return llm.chat(
                        [
                            {
                                "role": "system",
                                "content": (
                                    "你是国际油价月报的资深编辑。请根据修改意见改写给定段落，"
                                    "结合提供的章节上下文、关联表格与证据摘要，"
                                    "保留全部数据与来源标注，文风专业严谨，只输出改写后的正文。"
                                ),
                            },
                            {"role": "user", "content": user_content},
                        ],
                        provider=prov,
                        model=resolved_model,
                        temperature=0.4,
                        mode=mode,
                    ).strip()
            except llm.LLMUnavailable:
                pass
        return f"{old}\n\n【Agent修订建议】{instruction}\n（大模型不可用，已保留原文，请专家复核。）".strip()
