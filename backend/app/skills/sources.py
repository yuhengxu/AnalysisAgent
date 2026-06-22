"""可信数据源注册表。

两个 skill（油价预测分析表、国际油价月报）在采集数据与撰写分析时，
必须以下列权威机构发布的口径为准，并在输出中标注来源，确保数据可追溯。
分类对应预测分析表的影响因素维度：宏观/需求/供给/政治/库存/价格/航运/气候。
"""
from __future__ import annotations

from typing import Any

TRUSTED_SOURCES: list[dict[str, Any]] = [
    # —— 供需与基本面 ——
    {
        "id": "eia",
        "name": "美国能源信息署 EIA",
        "name_en": "U.S. Energy Information Administration",
        "url": "https://www.eia.gov",
        "categories": ["供给", "需求", "库存", "价格"],
        "desc": "短期能源展望(STEO)、周度库存、美国产量/钻机等官方统计。",
    },
    {
        "id": "iea",
        "name": "国际能源署 IEA",
        "name_en": "International Energy Agency",
        "url": "https://www.iea.org/topics/oil-market-report",
        "categories": ["供给", "需求", "库存"],
        "desc": "月度石油市场报告(OMR)、全球供需平衡与 OECD 库存。",
    },
    {
        "id": "opec",
        "name": "石油输出国组织 OPEC",
        "name_en": "OPEC",
        "url": "https://www.opec.org/opec_web/en/publications/338.htm",
        "categories": ["供给"],
        "desc": "月度石油市场报告(MOMR)、OPEC+ 产量与配额政策。",
    },
    # —— 宏观与金融 ——
    {
        "id": "fed",
        "name": "美联储 / FOMC",
        "name_en": "Federal Reserve",
        "url": "https://www.federalreserve.gov/monetarypolicy.htm",
        "categories": ["宏观"],
        "desc": "联邦基金利率决议、点阵图、货币政策声明。",
    },
    {
        "id": "cme_fedwatch",
        "name": "CME FedWatch",
        "name_en": "CME FedWatch Tool",
        "url": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html",
        "categories": ["宏观"],
        "desc": "利率期货隐含的降/加息概率。",
    },
    {
        "id": "bls",
        "name": "美国劳工统计局 BLS",
        "name_en": "U.S. Bureau of Labor Statistics",
        "url": "https://www.bls.gov",
        "categories": ["宏观"],
        "desc": "CPI 通胀、非农就业、失业率。",
    },
    {
        "id": "nbs",
        "name": "国家统计局",
        "name_en": "National Bureau of Statistics of China",
        "url": "https://www.stats.gov.cn",
        "categories": ["宏观", "需求"],
        "desc": "中国 GDP、PMI、工业增加值、原油加工量。",
    },
    {
        "id": "spglobal_pmi",
        "name": "S&P Global PMI",
        "name_en": "S&P Global PMI",
        "url": "https://www.pmi.spglobal.com",
        "categories": ["宏观", "需求"],
        "desc": "全球主要经济体制造业/服务业/综合 PMI。",
    },
    # —— 价格与持仓 ——
    {
        "id": "ice",
        "name": "洲际交易所 ICE",
        "name_en": "Intercontinental Exchange",
        "url": "https://www.ice.com",
        "categories": ["价格"],
        "desc": "Brent 原油期货结算价、月差与持仓结构。",
    },
    {
        "id": "cme_nymex",
        "name": "芝加哥商品交易所 NYMEX",
        "name_en": "CME Group / NYMEX",
        "url": "https://www.cmegroup.com/markets/energy/crude-oil/light-sweet-crude.html",
        "categories": ["价格"],
        "desc": "WTI 原油期货结算价与合约结构。",
    },
    {
        "id": "platts",
        "name": "标普全球普氏 Platts",
        "name_en": "S&P Global Commodity Insights (Platts)",
        "url": "https://www.spglobal.com/commodityinsights",
        "categories": ["价格"],
        "desc": "Brent/Dubai/ESPO 等现货评估与价差。",
    },
    {
        "id": "cftc",
        "name": "美国商品期货交易委员会 CFTC",
        "name_en": "U.S. CFTC",
        "url": "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm",
        "categories": ["宏观", "情绪"],
        "desc": "基金净多/净空持仓(COT)报告。",
    },
    # —— 航运与机构预测 ——
    {
        "id": "baltic",
        "name": "波罗的海交易所",
        "name_en": "Baltic Exchange",
        "url": "https://www.balticexchange.com",
        "categories": ["航运"],
        "desc": "BDTI 原油运价指数。",
    },
    {
        "id": "woodmac",
        "name": "伍德麦肯兹 Wood Mackenzie",
        "name_en": "Wood Mackenzie",
        "url": "https://www.woodmac.com",
        "categories": ["供给", "价格"],
        "desc": "上游供给与油价机构预测。",
    },
    {
        "id": "rystad",
        "name": "雷斯塔能源 Rystad Energy",
        "name_en": "Rystad Energy",
        "url": "https://www.rystadenergy.com",
        "categories": ["供给", "价格"],
        "desc": "全球油气供给与油价机构预测。",
    },
    {
        "id": "cneei",
        "name": "中国海油集团能源经济研究院 CNEEI",
        "name_en": "CNOOC Energy Economics Institute",
        "url": "https://www.cnooc.com.cn",
        "categories": ["价格", "供给", "需求"],
        "desc": "国际油价月报、油价预测模型与研讨会结论（平台口径基准）。",
    },
    # —— 气候 ——
    {
        "id": "noaa",
        "name": "美国国家海洋和大气管理局 NOAA",
        "name_en": "NOAA",
        "url": "https://www.cpc.ncep.noaa.gov",
        "categories": ["气候"],
        "desc": "厄尔尼诺/拉尼娜、飓风季与极端天气预报。",
    },
]

# 经核验的数据页面白名单（大模型只能引用 source_id + page_key，禁止自行编造 URL）
SOURCE_PAGE_CATALOG: list[dict[str, str]] = [
    {"source_id": "eia", "page_key": "steo", "name": "EIA STEO", "page": "短期能源展望", "url": "https://www.eia.gov/outlooks/steo/"},
    {"source_id": "eia", "page_key": "petroleum", "name": "EIA 石油数据", "page": "石油周报与库存", "url": "https://www.eia.gov/petroleum/"},
    {"source_id": "eia", "page_key": "weekly", "name": "EIA 周度石油", "page": "周度石油状况报告", "url": "https://www.eia.gov/petroleum/supply/weekly/"},
    {"source_id": "iea", "page_key": "omr", "name": "IEA OMR", "page": "石油市场月报", "url": "https://www.iea.org/reports/oil-market-report"},
    {"source_id": "opec", "page_key": "momr", "name": "OPEC MOMR", "page": "月度石油市场报告", "url": "https://www.opec.org/opec_web/en/publications/338.htm"},
    {"source_id": "fed", "page_key": "h10", "name": "美联储 H.10", "page": "美元汇率统计", "url": "https://www.federalreserve.gov/releases/h10/current/"},
    {"source_id": "fed", "page_key": "fomc", "name": "美联储 FOMC", "page": "货币政策与利率决议", "url": "https://www.federalreserve.gov/monetarypolicy.htm"},
    {"source_id": "cme_fedwatch", "page_key": "tool", "name": "CME FedWatch", "page": "利率概率工具", "url": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"},
    {"source_id": "bls", "page_key": "cpi", "name": "BLS CPI", "page": "消费者物价指数", "url": "https://www.bls.gov/cpi/"},
    {"source_id": "bls", "page_key": "employment", "name": "BLS 就业", "page": "非农就业与失业率", "url": "https://www.bls.gov/news.release/empsit.nr0.htm"},
    {"source_id": "nbs", "page_key": "data", "name": "国家统计局", "page": "宏观经济数据发布", "url": "https://www.stats.gov.cn/sj/"},
    {"source_id": "spglobal_pmi", "page_key": "pmi", "name": "S&P Global PMI", "page": "全球 PMI 指数", "url": "https://www.pmi.spglobal.com/Public/Release/PressReleases"},
    {"source_id": "ice", "page_key": "brent", "name": "ICE Brent", "page": "布伦特原油期货", "url": "https://www.ice.com/products/219/Brent-Crude-Futures"},
    {"source_id": "cme_nymex", "page_key": "wti", "name": "NYMEX WTI", "page": "WTI 原油期货", "url": "https://www.cmegroup.com/markets/energy/crude-oil/light-sweet-crude.html"},
    {"source_id": "platts", "page_key": "oil", "name": "Platts 原油", "page": "原油现货评估", "url": "https://www.spglobal.com/commodityinsights/en/products-solutions/products/oil"},
    {"source_id": "cftc", "page_key": "cot", "name": "CFTC COT", "page": "持仓周报", "url": "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm"},
    {"source_id": "baltic", "page_key": "bdti", "name": "波罗的海交易所", "page": "BDTI 原油运价", "url": "https://www.balticexchange.com/en/index.html"},
    {"source_id": "woodmac", "page_key": "oil", "name": "Wood Mackenzie", "page": "油气市场研究", "url": "https://www.woodmac.com/industry/oil-and-gas/"},
    {"source_id": "rystad", "page_key": "oil", "name": "Rystad Energy", "page": "油气市场分析", "url": "https://www.rystadenergy.com/"},
    {"source_id": "cneei", "page_key": "report", "name": "CNEEI", "page": "国际油价月报与预测", "url": "https://www.cnooc.com.cn"},
    {"source_id": "noaa", "page_key": "enso", "name": "NOAA CPC", "page": "ENSO 与气候展望", "url": "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/"},
]


def sources_for(*categories: str) -> list[dict[str, Any]]:
    """按因素分类筛选相关数据源。无参数返回全部。"""
    if not categories:
        return TRUSTED_SOURCES
    cats = set(categories)
    return [s for s in TRUSTED_SOURCES if cats & set(s["categories"])]


def categories_from_items(
    items: list[dict[str, Any]], *, key: str = "sources"
) -> list[str]:
    """从因素/章节定义中汇总涉及的数据源分类（去重排序）。"""
    cats: set[str] = set()
    for item in items:
        for c in item.get(key, []):
            if c:
                cats.add(c)
    return sorted(cats)


def source_refs_for(*categories: str) -> list[dict[str, str]]:
    """返回前端展示用的数据源引用（name + url，可渲染超链接）。"""
    return [{"name": s["name"], "url": s["url"]} for s in sources_for(*categories)]


def _allowed_source_ids(*categories: str) -> set[str]:
    return {s["id"] for s in sources_for(*categories)}


def source_pages_for(*categories: str) -> list[dict[str, str]]:
    """按因素分类返回可用的已核验数据页面。"""
    allowed = _allowed_source_ids(*categories)
    return [p for p in SOURCE_PAGE_CATALOG if p["source_id"] in allowed]


def source_pages_brief(*categories: str) -> str:
    """生成写入 prompt 的页面白名单（禁止模型自行编造 URL）。"""
    lines = []
    for p in source_pages_for(*categories):
        lines.append(
            f"- source_id={p['source_id']} page_key={p['page_key']} "
            f"「{p['name']} · {p['page']}」"
        )
    return "\n".join(lines)


def source_pages_payload(*categories: str) -> list[dict[str, str]]:
    return [
        {
            "source_id": p["source_id"],
            "page_key": p["page_key"],
            "name": p["name"],
            "page": p["page"],
            "url": p["url"],
        }
        for p in source_pages_for(*categories)
    ]


def normalize_llm_source_refs(
    raw: Any,
    *,
    allowed_categories: list[str] | None = None,
    max_items: int = 6,
    strict: bool = True,
) -> list[dict[str, str]]:
    """将大模型返回的 source 引用规范化。strict=True 时仅接受白名单 source_id+page_key。"""
    if not isinstance(raw, list):
        return []
    pages = source_pages_for(*(allowed_categories or ()))
    by_key = {(p["source_id"], p["page_key"]): p for p in pages}
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    seen_urls: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("source_id", "")).strip()
        pkey = str(item.get("page_key", "")).strip()
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        data_point = str(item.get("data_point", "")).strip()

        if sid and pkey:
            key = (sid, pkey)
            if key in seen:
                continue
            entry = by_key.get(key)
            if entry:
                seen.add(key)
                ref: dict[str, str] = {
                    "name": entry["name"],
                    "url": entry["url"],
                    "page": entry["page"],
                    "source_id": sid,
                    "page_key": pkey,
                }
                if data_point:
                    ref["data_point"] = data_point
                out.append(ref)
            elif not strict and (name or url):
                seen.add(key)
                ref = {"name": name or sid, "source_id": sid, "page_key": pkey}
                if url:
                    ref["url"] = url
                if data_point:
                    ref["data_point"] = data_point
                out.append(ref)
            continue

        if not strict and (name or url):
            dedupe = url or name
            if dedupe in seen_urls:
                continue
            seen_urls.add(dedupe)
            ref = {"name": name or url}
            if url:
                ref["url"] = url
            if data_point:
                ref["data_point"] = data_point
            out.append(ref)

        if len(out) >= max_items:
            break
    return out


def sources_payload(*categories: str) -> list[dict[str, Any]]:
    """生成供大模型 JSON 入参使用的结构化数据源列表。"""
    return [
        {
            "id": s["id"],
            "name": s["name"],
            "name_en": s["name_en"],
            "url": s["url"],
            "categories": s["categories"],
            "desc": s["desc"],
        }
        for s in sources_for(*categories)
    ]


def sources_brief(*categories: str) -> str:
    """生成供大模型 prompt 使用的可信数据源清单文本。"""
    lines = []
    for s in sources_for(*categories):
        lines.append(f"- {s['name']}（{s['name_en']}, {s['url']}）：{s['desc']}")
    return "\n".join(lines)


def sources_brief_by_item(
    items: list[dict[str, Any]],
    *,
    id_key: str = "id",
    name_key: str = "name",
    sources_key: str = "sources",
) -> str:
    """按条目列出允许引用的数据源，限制大模型逐条查询范围。"""
    lines: list[str] = []
    for item in items:
        label = f"{item.get(id_key, '')} {item.get(name_key, '')}".strip()
        cats = item.get(sources_key, [])
        if not cats:
            lines.append(f"- {label}：不限定专用数据源，可参考通用清单")
            continue
        lines.append(
            f"- {label}（限定分类：{', '.join(cats)}）\n"
            f"{sources_brief(*cats)}"
        )
    return "\n".join(lines)


# 月报各子章节对应的数据源分类（与预测分析表 factors.sources 口径一致）
REPORT_SECTION_SOURCES: dict[str, list[str]] = {
    "review_futures": ["价格"],
    "review_spot": ["价格"],
    "factor_macro": ["宏观", "需求"],
    "factor_demand": ["需求"],
    "factor_supply": ["供给"],
    "factor_inventory": ["库存"],
    "factor_dollar": ["宏观"],
    "factor_geo": ["供给"],
    "factor_position": ["情绪", "宏观"],
    "outlook_scenario": ["价格"],
    "outlook_seminar": ["价格", "供给", "需求"],
    "outlook_model": ["价格"],
    "outlook_agency": ["价格", "供给"],
    "outlook_conclusion": ["价格"],
}


def report_sections_with_sources(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """为月报子章节附加 sources 分类，供大模型入参使用。"""
    out: list[dict[str, Any]] = []
    for sec in sections:
        if sec.get("level") != 2:
            continue
        out.append({**sec, "sources": REPORT_SECTION_SOURCES.get(sec["id"], [])})
    return out
