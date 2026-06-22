# 这是一个能源行业AI数据分析平台

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
docker compose up --build
```

- 前端：http://localhost:3000
- 后端 API：http://localhost:8000
- 健康检查：http://localhost:8000/health

### 方式二：本地开发

**后端**

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**前端**（需 Node.js 18+）

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173 ，在「数据中心」点击「导入 yuebao 样例数据」即可体验。

### 主要功能

- **数据中心**：CSV/XLSX 上传、字段识别、质量检查、样例数据导入
- **总览/智能分析**：Brent/WTI 价格走势、价差、供需预测图表
- **预测分析表**（新）：采集权威数据 → DeepSeek 逐项研判六大类影响因素（重要性 1-5 / 形势判断 / 促涨持平促跌）+ 布伦特价格预测 → 在线查看、编辑、人工校准 → 导出 Excel（还原样例下划线标注格式）
- **报告中心**（增强）：采集权威数据 → DeepSeek 撰写国际油价月报（封面/摘要/市场回顾/影响因素/油价展望 + 三张数据表）→ 在线编辑、章节级 Agent 校准 → 导出 Word
- **预测模型**：基准/乐观/悲观情景统计预测与回测
- **Agent 入口**：粒子化 Logo 按钮，支持数据分析、预测分析表、月报生成等技能

### 大模型与 Skill 架构

- 统一大模型客户端 `backend/app/core/llm.py`，支持 `volcengine`（豆包，默认）/`deepseek`/`openai`/`mock` 四种 provider。
- **双调用模式**：所有大模型调用支持 `normal`（普通，快速）与 `deep_research`（深度研究）两类模式：
  - DeepSeek + 深度研究 → 开启深度思考（thinking + reasoning_effort）；
  - 豆包 + 深度研究 → 调用 **DeepSearch** 智能体（专为复杂问题设计，集成浏览器使用、联网搜索、知识库、网页解析、ChatPPT、Python 代码执行器等 MCP 服务）。
- **联网查证统一走 DeepSearch**：月报、预测分析表、月报表数据研究与 Agent 实时问答均直接使用方舟 DeepSearch。
- 后端 skill 位于 `backend/app/skills/`：
  - `prediction_skill.py`：生成油价预测分析表
  - `report_skill.py`：生成国际油价月报
  - `sources.py`：**可信数据源注册表**（EIA、IEA、OPEC、美联储、CFTC、S&P Global、Platts、Wood Mackenzie、Rystad、ICE、NYMEX、国家统计局、CNEEI、NOAA 等），两个 skill 均据此口径采集数据并在输出中标注来源。
- 大模型不可用时自动降级到「数据库证据 + 规则兜底」，保证始终可产出初稿。

### 环境变量

参考 `backend/.env.example`。在 `backend/.env` 配置：

```
DEFAULT_LLM_PROVIDER=volcengine
VOLCENGINE_API_KEY=...
VOLCENGINE_MODEL=doubao-seed-2-0-pro-260215
VOLCENGINE_DEEPSEARCH_BOT_ID=bot-xxx     # 豆包深度研究模式（DeepSearch 智能体）
DEEPSEEK_API_KEY=sk-...                  # 可选，兼容保留
DEEPSEEK_REASONING_EFFORT=high           # DeepSeek 深度研究模式思考强度
```

## 1 数据来源

前期会从csv文件加载行业数据

后续会支持将数据保存在轻量级数据库中

也可能会支持从wind等数据服务商api接口获取数据，落库

## 2 功能

将已有数据可视化

提供Agent，可以根据专家指令分析某个方向的数据，实时生成对应的可视化数据

根据专家建议生成周报月报

## 3 实现

### 3.1 前端

前端界面采用轻量化框架

界面风格未来科技简约风、配合毛玻璃效果

可将公司logo拟人化作为Agent入口，logo要做成粒子化的，可以参考[https://hashgraphvc.com/](https://hashgraphvc.com/)这个粒子效果

嵌入doc处理工具，在线实时编辑文本，并可由agent修改

### 3.2 后端

后端要求能处理大数据、实现数据分析，提供机器学习能力，预测未来行情

### 3.3 数据库

轻量型数据库，可保存csv数据，也可以保存图片和doc文件

### 3.4 Agent
可以根据需求选择连接的大模型

skill1：数据预测

skill2：数据分析

skill3：月报周报生成

### 3.5 环境

方便迁移部署

