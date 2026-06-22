"""油价预测分析表模板（对应 yuebao/prediction/*.xlsx 样例）。

结构：六大类影响因素，每个因素含
- importance：重要性程度 1-5（样例中以"数字下划线"标注被选项）
- judgment：形势判断及支撑指标（正文）
- impact：对国际油价影响，取 促涨 / 持平 / 促跌

末尾为布伦特首行合约价格预测（当月、次月）：区间 + 均价。
"""
from __future__ import annotations

import json
from typing import Any

IMPACT_OPTIONS = ["促涨", "持平", "促跌"]
CONFIDENCE_LEVELS = ["权威数据", "模型推断"]

# (category_id, category_title, [(factor_id, factor_name, source_categories)])
PREDICTION_FACTORS: list[dict[str, Any]] = [
    {
        "id": "macro",
        "title": "1.宏观及金融因素",
        "factors": [
            {"id": "1.1", "name": "全球货币政策", "sources": ["宏观"]},
            {"id": "1.2", "name": "美元汇率", "sources": ["宏观"]},
            {"id": "1.3", "name": "美股走势", "sources": ["宏观"]},
            {"id": "1.4", "name": "美债走势", "sources": ["宏观"]},
            {"id": "1.5", "name": "基金持仓", "sources": ["情绪"]},
            {"id": "1.6", "name": "市场情绪", "sources": ["情绪"]},
        ],
    },
    {
        "id": "demand",
        "title": "2.需求因素",
        "factors": [
            {"id": "2.1", "name": "全球及主要国家经济景气程度", "sources": ["需求", "宏观"]},
            {"id": "2.2", "name": "交通运输业需求状况", "sources": ["需求"]},
            {"id": "2.3", "name": "炼油行业需求状况", "sources": ["需求"]},
            {"id": "2.4", "name": "新技术及能源结构转型重大政策", "sources": ["需求"]},
            {"id": "2.5", "name": "通胀预期带来的投资投机需求", "sources": ["宏观", "情绪"]},
        ],
    },
    {
        "id": "supply",
        "title": "3.供给因素",
        "factors": [
            {"id": "3.1", "name": "OPEC生产情况", "sources": ["供给"]},
            {"id": "3.2", "name": "美国生产情况", "sources": ["供给"]},
            {"id": "3.3", "name": "俄罗斯、加拿大、巴西等重要产油国生产情况", "sources": ["供给"]},
            {"id": "3.4", "name": "石油巨头新油田投产、检修及开支计划等情况", "sources": ["供给"]},
            {"id": "3.5", "name": "运输便利度和成本", "sources": ["航运"]},
            {"id": "3.6", "name": "期初库存情况", "sources": ["库存"]},
            {"id": "3.7", "name": "新技术变革影响", "sources": ["供给"]},
        ],
    },
    {
        "id": "politics",
        "title": "4.政治因素",
        "factors": [
            {"id": "4.1", "name": "中美关系", "sources": ["宏观"]},
            {"id": "4.2", "name": "美俄关系", "sources": ["供给"]},
            {"id": "4.3", "name": "美国中东关系", "sources": ["供给"]},
            {"id": "4.4", "name": "中东内部政治局势", "sources": ["供给"]},
            {"id": "4.5", "name": "其他产油国政局", "sources": ["供给"]},
            {"id": "4.6", "name": "战争等突发事件", "sources": ["供给"]},
        ],
    },
    {
        "id": "climate",
        "title": "5.气候及其他突发事件",
        "factors": [
            {"id": "5.1", "name": "夏季驾驶和冬季取暖等季节性波动因素", "sources": ["气候", "需求"]},
            {"id": "5.2", "name": "极冷极热天气、台风等自然灾害", "sources": ["气候"]},
            {"id": "5.3", "name": "其他突发事件", "sources": ["气候"]},
        ],
    },
    {
        "id": "others",
        "title": "6.其他因素",
        "factors": [
            {"id": "6.1", "name": "可在此填列", "sources": []},
        ],
    },
]

PREDICTION_NOTES = [
    "1.各项因素的分析请偏重于对未来一个月国际油价的影响。",
    "2.重要性程度、对国际油价影响两栏请务必填写、便于汇总统计。",
    "3.若不关注某因素或认为其影响很小，重要性程度、对国际油价影响两栏可按分别填1、持平。",
]


def all_factor_defs() -> list[dict[str, Any]]:
    """展平成 [{category, category_title, id, name, sources}] 列表。"""
    flat = []
    for cat in PREDICTION_FACTORS:
        for f in cat["factors"]:
            flat.append(
                {
                    "category": cat["id"],
                    "category_title": cat["title"],
                    "id": f["id"],
                    "name": f["name"],
                    "sources": f["sources"],
                }
            )
    return flat


def empty_content() -> dict[str, Any]:
    """生成空白预测表骨架（未调用大模型时的兜底结构）。"""
    factors = []
    for f in all_factor_defs():
        factors.append(
            {
                "category": f["category"],
                "category_title": f["category_title"],
                "id": f["id"],
                "name": f["name"],
                "importance": 1,
                "judgment": "",
                "impact": "持平",
                "confidence_level": "模型推断",
            }
        )
    return {
        "factors": factors,
        "price_forecast": {
            "current_month": {"range_low": None, "range_high": None, "avg": None},
            "next_month": {"range_low": None, "range_high": None, "avg": None},
        },
    }


def get_template_json() -> str:
    return json.dumps(
        {"categories": PREDICTION_FACTORS, "impact_options": IMPACT_OPTIONS, "notes": PREDICTION_NOTES},
        ensure_ascii=False,
    )
