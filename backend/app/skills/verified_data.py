"""宏观数据引用与致信水平判定。

预测/月报生成时：
- 从互联网搜集到的真实数据 → 权威数据（须提供 source_url 超链接）
- 大模型自行推导的数据 → 模型推断

平台数据库证据仅供分析参考，不作为权威数据核验依据。
"""
from __future__ import annotations

import re
from typing import Any, Callable

from app.core.timezone import now_beijing_naive

CONFIDENCE_AUTHORITATIVE = "权威数据"
CONFIDENCE_INFERRED = "模型推断"
CONFIDENCE_LEVELS = (CONFIDENCE_AUTHORITATIVE, CONFIDENCE_INFERRED)

_URL_PATTERN = re.compile(r"https?://[^\s\])>\"'，。；]+")

# 常见宏观指标检索模板：(检索词后缀, 指标名, source_id, page_key)
_MACRO_QUERY_SPECS: list[tuple[str, str, str, str]] = [
    ("中国 官方制造业PMI 国家统计局", "中国官方制造业PMI", "nbs", "data"),
    ("中国 规模以上工业增加值 同比 国家统计局", "中国规模以上工业增加值同比", "nbs", "data"),
    ("美国 CPI 同比", "美国CPI同比", "bls", "cpi"),
    ("美国 非农就业", "美国非农就业", "bls", "employment"),
    ("全球 制造业 PMI S&P Global", "全球制造业PMI", "spglobal_pmi", "pmi"),
    ("美联储 联邦基金利率 FOMC", "美联储联邦基金利率", "fed", "fomc"),
]

# 从文本提取「指标 + 数值」的常见模式
_VALUE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?:PMI|制造业采购经理指数|采购经理指数)"
        r"[^0-9]{0,20}(\d{1,2}(?:\.\d+)?)",
        re.I,
    ),
    re.compile(r"CPI[^0-9]{0,30}(?:同比)?[^0-9]{0,10}(\d{1,2}(?:\.\d+)?)\s*%", re.I),
    re.compile(r"非农就业[^0-9]{0,20}(?:新增)?[^0-9]{0,10}(\d{1,3}(?:\.\d+)?)\s*万", re.I),
    re.compile(r"失业率[^0-9]{0,20}(\d{1,2}(?:\.\d+)?)\s*%", re.I),
    re.compile(r"工业增加值[^0-9]{0,20}(?:同比)?[^0-9]{0,10}(\d{1,2}(?:\.\d+)?)\s*%", re.I),
    re.compile(
        r"联邦基金利率[^0-9]{0,30}(\d{1,2}(?:\.\d+)?)\s*%\s*[-–~至]\s*(\d{1,2}(?:\.\d+)?)\s*%",
        re.I,
    ),
]

_PERIOD_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(\d{4})年(\d{1,2})月"),
    re.compile(r"(\d{4})[-/.](\d{1,2})(?:[-/.]\d{1,2})?"),
]

_BARE_MONTH_PATTERN = re.compile(r"(?<!\d)(\d{1,2})月(?!\d)")


def period_key(year: int, month: int) -> int:
    return year * 12 + month


def period_label(year: int, month: int) -> str:
    return f"{year}年{month}月"


def prev_period(year: int, month: int) -> tuple[int, int]:
    if month > 1:
        return year, month - 1
    return year - 1, 12


def today_iso() -> str:
    return now_beijing_naive().strftime("%Y-%m-%d")


def extract_periods(text: str) -> list[tuple[int, int]]:
    """从文本中提取所有显式年-月期别。"""
    if not text:
        return []
    found: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for pat in _PERIOD_PATTERNS:
        for m in pat.finditer(text):
            y, mo = int(m.group(1)), int(m.group(2))
            if 1 <= mo <= 12 and (y, mo) not in seen:
                seen.add((y, mo))
                found.append((y, mo))
    return found


def infer_period_from_text(
    text: str,
    *,
    review_year: int,
    review_month: int,
) -> tuple[int, int] | None:
    """推断文本所属期别；优先显式年份，否则在回顾月语境下解析裸「N月」。"""
    periods = extract_periods(text)
    if periods:
        return max(periods, key=lambda p: period_key(p[0], p[1]))
    bare = _BARE_MONTH_PATTERN.search(text)
    if bare:
        mo = int(bare.group(1))
        if 1 <= mo <= 12:
            y = review_year if mo <= review_month else review_year - 1
            return y, mo
    return None


def build_macro_search_queries(review_year: int, review_month: int) -> list[str]:
    """构造带完整期别的宏观检索词。"""
    label = period_label(review_year, review_month)
    return [f"{label} {suffix}" for suffix, *_ in _MACRO_QUERY_SPECS]


def _extract_value(indicator: str, text: str) -> str | None:
    blob = f"{indicator} {text}"
    for pat in _VALUE_PATTERNS:
        m = pat.search(blob)
        if not m:
            continue
        if m.lastindex and m.lastindex >= 2:
            return f"{m.group(1)}%-{m.group(2)}%"
        return m.group(1)
    return None


def _parse_search_hit(
    indicator: str,
    source_id: str,
    page_key: str,
    title: str,
    snippet: str,
    url: str,
    review_year: int,
    review_month: int,
) -> dict[str, Any] | None:
    blob = f"{title} {snippet}"
    period = infer_period_from_text(blob, review_year=review_year, review_month=review_month)
    if not period:
        return None
    dy, dm = period
    value = _extract_value(indicator, blob)
    if not value:
        return None
    return {
        "indicator": indicator,
        "value": value,
        "period": period_label(dy, dm),
        "period_year": dy,
        "period_month": dm,
        "source_id": source_id,
        "page_key": page_key,
        "source_title": title.strip(),
        "source_url": url,
        "verified": True,
    }


def gather_macro_evidence(
    search_fn: Callable[[str, int], list[dict[str, str]]],
    review_year: int,
    review_month: int,
    *,
    per_query: int = 3,
) -> dict[str, Any]:
    """联网检索并解析宏观数据点。"""
    data_points: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, int, int]] = set()

    for suffix, indicator, source_id, page_key in _MACRO_QUERY_SPECS:
        query = f"{period_label(review_year, review_month)} {suffix}"
        results = search_fn(query, per_query)
        for hit in results:
            title = hit.get("title", "")
            snippet = hit.get("snippet", "")
            url = hit.get("url", "")
            parsed = _parse_search_hit(
                indicator, source_id, page_key, title, snippet, url,
                review_year, review_month,
            )
            if not parsed:
                continue
            dedupe_key = (indicator, parsed["period_year"], parsed["period_month"])
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            data_points.append(parsed)

    return {
        "review_period": period_label(review_year, review_month),
        "today": today_iso(),
        "data_points": data_points,
        "query_count": len(_MACRO_QUERY_SPECS),
    }


def data_points_brief(evidence: dict[str, Any]) -> str:
    """生成写入 prompt 的互联网检索数据摘要。"""
    points = evidence.get("data_points") or []
    if not points:
        return (
            f"回顾月：{evidence.get('review_period', '')}；今日：{evidence.get('today', '')}\n"
            "【提示】暂未从互联网检索到可引用的宏观数值；可结合【DeepSearch 查证】与历史走势"
            "合理推断，confidence_level 标注为「模型推断」。"
        )

    lines = [
        f"回顾月：{evidence.get('review_period', '')}；今日：{evidence.get('today', '')}",
        "以下数据点来自互联网检索；引用时 confidence_level 为「权威数据」，并填写对应 source_url：",
    ]
    for i, p in enumerate(points, start=1):
        lines.append(
            f"[{i}] {p['period']} {p['indicator']}={p['value']} "
            f"source_url={p.get('source_url', '')}"
        )
    return "\n".join(lines)


def data_period_rules(
    target_year: int,
    target_month: int,
    review_year: int,
    review_month: int,
    *,
    strict: bool = True,
) -> str:
    """生成写入 prompt 的数据引用规则。"""
    rules = (
        f"【数据引用规则】\n"
        f"- 目标预测月：{period_label(target_year, target_month)}；"
        f"主要依据回顾月 {period_label(review_year, review_month)} 前后已发布数据。\n"
        f"- 引用数值须写完整期别（如「{period_label(review_year, review_month)}」），"
        f"禁止只写「5月」省略年份。\n"
        f"- 每项须给出 confidence_level（致信水平），只能取「权威数据」或「模型推断」。\n"
        f"- 从互联网搜集到的真实数据：confidence_level 为「权威数据」，"
        f"并须提供 source_url（来源网页超链接，可附 source_title）。\n"
        f"- 大模型自行推导、无互联网来源支撑的数据：confidence_level 为「模型推断」，不填 source_url。\n"
        f"- 【平台数据库证据】仅供分析参考，不可替代互联网来源作为权威数据依据。"
    )
    if strict:
        rules += "\n- 标注为「权威数据」时 source_url 必填且须为可访问的网页链接。"
    return rules


def normalize_source_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith(("http://", "https://")):
        return text.rstrip(".,;)")
    return None


def extract_url_from_text(text: str) -> str | None:
    match = _URL_PATTERN.search(text or "")
    if not match:
        return None
    return normalize_source_url(match.group(0))


def append_data_gap_notice(judgment: str, factor_name: str) -> str:
    """当 judgment 为空时，给出可基于历史合理推断的占位说明。"""
    if judgment.strip():
        return judgment
    return (
        f"{factor_name}：暂未从互联网获取到可引用的宏观数据，"
        f"可结合历史走势进行合理推断（致信水平：模型推断）。"
    )


def infer_confidence_level(
    judgment: str,
    *,
    source_url: str | None = None,
    llm_value: str | None = None,
) -> str:
    """根据来源链接与 LLM 标注推断致信水平。"""
    url = normalize_source_url(source_url) or extract_url_from_text(judgment)
    if url:
        return CONFIDENCE_AUTHORITATIVE
    normalized = normalize_confidence_level(llm_value)
    if normalized == CONFIDENCE_AUTHORITATIVE:
        return CONFIDENCE_INFERRED
    if normalized:
        return normalized
    return CONFIDENCE_INFERRED


def normalize_confidence_level(value: Any) -> str | None:
    text = str(value or "").strip()
    if text in CONFIDENCE_LEVELS:
        return text
    if text in ("权威", "已核验", "verified", "authoritative"):
        return CONFIDENCE_AUTHORITATIVE
    if text in ("推断", "推理", "inferred", "inference"):
        return CONFIDENCE_INFERRED
    return None


def apply_authoritative_source(
    entry: dict[str, Any],
    *,
    source_url: str | None = None,
    source_title: str | None = None,
    judgment: str = "",
) -> None:
    """写入致信水平与来源链接（仅权威数据保留链接）。"""
    url = normalize_source_url(source_url) or extract_url_from_text(judgment)
    confidence = infer_confidence_level(judgment, source_url=url)
    entry["confidence_level"] = confidence
    entry.pop("source_url", None)
    entry.pop("source_title", None)
    if confidence == CONFIDENCE_AUTHORITATIVE and url:
        entry["source_url"] = url
        title = str(source_title or "").strip()
        if title:
            entry["source_title"] = title


def sanitize_judgment(
    judgment: str,
    factor_name: str,
    *,
    review_year: int,
    review_month: int,
    verified_points: list[dict[str, Any]] | None = None,
    strict: bool = True,
) -> str:
    """规范化 judgment 文本。"""
    del review_year, review_month, verified_points, strict
    text = (judgment or "").strip()
    if not text:
        return append_data_gap_notice("", factor_name)
    return text
