"""国际油价月报模板（对应 yuebao/yuebao/*.docx 样例）。

报告内容采用结构化 JSON：
- cover：封面信息
- summary：内容摘要（可多段，用 \n 分隔）
- sections：章节列表（level=1 为大标题无正文，level=2 为子节含正文）
- tables：命名表格（期货价格月变化、情景预测、机构预测）
- approval：审核签发信息
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ----------------------------------------------------------------------- #
# 默认章节大纲（标题可由大模型按当月主题微调）
DEFAULT_SECTIONS: list[dict[str, Any]] = [
    {"id": "review", "title": "一、原油市场回顾", "level": 1},
    {"id": "review_futures", "title": "（一）期货市场回顾", "level": 2,
     "hint": "Brent/WTI 期货结算均价、环比同比、月差结构、持仓"},
    {"id": "review_spot", "title": "（二）现货市场回顾", "level": 2,
     "hint": "Brent/Dubai/ESPO 现货价格与价差"},
    {"id": "factors", "title": "二、国际油价影响因素", "level": 1},
    {"id": "factor_macro", "title": "（一）全球经济与宏观金融", "level": 2,
     "hint": "全球经济、PMI、通胀、美联储、美元"},
    {"id": "factor_demand", "title": "（二）全球石油需求", "level": 2,
     "hint": "炼厂开工、交通出行、季节性需求"},
    {"id": "factor_supply", "title": "（三）全球石油供应", "level": 2,
     "hint": "OPEC+ 产量、美国页岩、非OPEC增量"},
    {"id": "factor_inventory", "title": "（四）库存变化", "level": 2,
     "hint": "OECD 商业库存、战略储备、浮仓"},
    {"id": "factor_dollar", "title": "（五）美元与美联储政策", "level": 2,
     "hint": "FOMC、点阵图、美元指数"},
    {"id": "factor_geo", "title": "（六）地缘局势", "level": 2,
     "hint": "中东、俄乌、霍尔木兹海峡等地缘风险"},
    {"id": "factor_position", "title": "（七）期货持仓与市场情绪", "level": 2,
     "hint": "CFTC 基金净多/净空、市场情绪"},
    {"id": "outlook", "title": "三、国际油价展望", "level": 1},
    {"id": "outlook_scenario", "title": "（一）情景分析与预测", "level": 2,
     "hint": "基准/低油价/高油价三情景"},
    {"id": "outlook_seminar", "title": "（二）研讨会预测结果", "level": 2,
     "hint": "1+7+N 国际油价研讨会预测均价与区间"},
    {"id": "outlook_model", "title": "（三）模型预测结果", "level": 2,
     "hint": "国际油价预测模型结果"},
    {"id": "outlook_agency", "title": "（四）有关机构预测结果", "level": 2,
     "hint": "S&P、Wood Mackenzie、Rystad 预测"},
    {"id": "outlook_conclusion", "title": "（五）预测结论", "level": 2,
     "hint": "综合预测结论：月度均价与区间、季度均价"},
]

DEFAULT_TABLES: dict[str, dict[str, Any]] = {
    "table_price_change": {
        "title": "表1-1 国际原油期货价格月度变化表（单位：美元/桶）",
        "source": "CNEEI",
        "headers": ["项目", "Brent", "WTI"],
        "rows": [["月均值", "", ""], ["环比", "", ""], ["同比", "", ""]],
    },
    "table_macro_pmi": {
        "title": "表2-1 全球主要经济体PMI",
        "source": "S&P Global、Eurostat、国家统计局",
        "headers": ["PMI", "PMI", "美国", "欧元区", "中国"],
        "rows": [
            ["综合", "初值", "", "", ""],
            ["综合", "环比变化", "", "", ""],
            ["制造业", "终值", "", "", ""],
            ["制造业", "环比变化", "", "", ""],
            ["服务业", "初值", "", "", ""],
            ["服务业", "环比变化", "", "", ""],
        ],
    },
    "table_demand_forecast": {
        "title": "表2-2 全球主要经济体GDP增速预测，%",
        "source": "IMF、世界银行",
        "headers": ["国家/地区", "2026", "较2026.1预测变化"],
        "rows": [
            ["全球", "", ""],
            ["美国", "", ""],
            ["欧元区", "", ""],
            ["东盟", "", ""],
            ["沙特阿拉伯", "", ""],
            ["俄罗斯", "", ""],
        ],
    },
    "table_supply_balance": {
        "title": "表2-3 机构对全球石油供应过剩量的预测（单位：百万桶/天）",
        "source": "IEA、EIA、S&P、Wood Mackenzie、Rystad",
        "headers": ["机构", "2026Q1", "2026Q2", "2026Q3", "2026Q4"],
        "rows": [
            ["IEA", "", "", "", ""],
            ["EIA", "", "", "", ""],
            ["S&P", "", "", "", ""],
            ["WM", "", "", "", ""],
            ["Rystad", "", "", "", ""],
        ],
    },
    "table_scenario": {
        "title": "表3-1 Brent油价走势情景预测（单位：美元/桶）",
        "source": "CNEEI",
        "headers": ["", "基准情景", "低油价情景", "高油价情景"],
        "rows": [["当月", "", "", ""], ["本季度", "", "", ""], ["全年", "", "", ""]],
    },
    "table_agency": {
        "title": "表3-2 咨询机构Brent油价预测（单位：美元/桶）",
        "source": "S&P、Wood Mackenzie、Rystad Energy",
        "headers": ["", "S&P", "Wood Mackenzie", "Rystad Energy"],
        "rows": [["当月", "", "", ""], ["本季度", "", "", ""], ["全年", "", "", ""]],
    },
    "table_distribution": {
        "title": "",
        "source": "",
        "headers": ["报送"],
        "rows": [["报送：集团公司领导、集团办公室、规划计划部、财务资金部、质量健康安全环保部、法律部、科技信息部。"]],
    },
}


def default_content(issue_no: str, report_date: str, dept: str = "") -> dict[str, Any]:
    return {
        "cover": {
            "org": "中国海油集团能源经济研究院",
            "title": "国际油价月报",
            "issue": issue_no,
            "dept": dept or "能源经济与政策研究中心石油经济研究室",
            "date": report_date,
        },
        "summary": "",
        "sections": [
            dict(s, content="", confidence_level="") if s["level"] == 2 else dict(s)
            for s in DEFAULT_SECTIONS
        ],
        "tables": json.loads(json.dumps(DEFAULT_TABLES, ensure_ascii=False)),
        "approval": {
            "author": "执笔：",
            "reviewer": "初审：",
            "approver": "审核：",
            "signer": "签发：",
        },
    }


# 兼容旧引用 ------------------------------------------------------------- #
MONTHLY_REPORT_TEMPLATE = {
    "name": "国际油价月报",
    "report_type": "monthly",
    "sections": DEFAULT_SECTIONS,
    "tables": list(DEFAULT_TABLES.keys()),
}

DAILY_PRICE_SOURCE = "CNEEI"
MONTHLY_PRICE_SOURCE = "CNEEI_MONTHLY"

PRICE_SYMBOL_MAP = {
    "WTI(期)": "WTI",
    "布伦特(期)": "Brent",
    "布伦特": "Brent",
    "阿曼(期)": "Oman",
    "沪原油(期)": "SC",
    "迪拜": "Dubai",
    "阿曼": "Oman",
    "DTD": "DTD",
    "米纳斯": "Minas",
    "塔皮斯": "Tapis",
    "杜里": "Duri",
    "辛塔": "Cinta",
    "ESPO": "ESPO",
}


def get_template_json() -> str:
    return json.dumps(MONTHLY_REPORT_TEMPLATE, ensure_ascii=False)


def save_template_to_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(get_template_json(), encoding="utf-8")
