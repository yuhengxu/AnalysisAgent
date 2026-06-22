# 能源行业 AI 数据分析平台 · 项目宪法

> 本文档是项目的**初心与宪法**，并包含**快速开始**指引。  
> 工作方法见 [GUIDE.md](./GUIDE.md)；模块设计见 [docs/](./docs/)。

---

## 序言

本平台面向能源行业（国际原油），将权威数据、统计分析与大模型能力结合，产出两类核心交付物：**油价预测分析表**（Excel）与 **国际油价月报**（Word）。Agent 作为统一入口，而非事后外挂。

---

## 一、使命

**以数据为基、以 Skill 为脑、以 Agent 为入口，让能源分析从导入到预测、从月报撰写到导出形成可复用的 AI 原生工作流。**

---

## 二、核心目标

| # | 目标 | 要义 |
|---|---|---|
| 1 | **数据管理与分析** | 导入价格/供需/因素数据，统计、图表、查询 |
| 2 | **油价预测分析表** | 六大类因素逐项研判 + 价格预测 → 在线编辑 → 导出 Excel |
| 3 | **国际油价月报** | 完整研究报告自动生成 → 章节编辑/Agent 修订 → 导出 Word |
| 4 | **拟人化 Agent** | 粒子化 Logo 入口，自然语言驱动上述能力 |

---

## 三、宪法级约束

以下条款为项目**不可偏离的底线**。若需变更，须先修订本文档并联动更新 `docs/` 相关文档。

### 3.1 系统边界

| 约束 | 说明 |
|---|---|
| **领域** | 能源行业（国际原油）数据分析与报告 |
| **两大交付物** | 预测分析表 + 月报，结构化 JSON 存库、文件导出 |
| **Agent** | 统一 skill 编排入口，与业务模块同源数据 |

### 3.2 部署与环境

| 约束 | 说明 |
|---|---|
| **跨平台** | Windows / Linux 本地开发；Docker Compose 部署 |
| **轻量存储** | SQLite + 本地文件（`data/`、`db/`、`logs/`） |
| **单 worker** | 月报/预测异步任务为进程内存态，生产 `uvicorn --workers 1` |

### 3.3 安全与权限

| 约束 | 说明 |
|---|---|
| **JWT 鉴权** | 除登录外，业务 API 须 Bearer Token |
| **页面权限** | 后端 `require_page` + 前端 `PageRoute`，禁止仅隐藏导航 |
| **数据隔离** | 月报/预测按 `user_id` 严格隔离（admin 亦不例外） |
| **任务隔离** | 异步 task 校验 `task.user_id` |

### 3.4 大模型与 Skill

| 约束 | 说明 |
|---|---|
| **统一客户端** | `core/llm.py`；provider 可切换，须支持降级 |
| **必可降级** | LLM 不可用时规则兜底，接口不 500 |
| **系统表 snapshot** | 月报 6 张系统表只读 snapshot，LLM 不得填 rows |
| **可信数据源** | skill 引用 `skills/sources.py` 权威机构口径 |

### 3.5 工程治理

| 约束 | 说明 |
|---|---|
| **文档驱动** | `docs/` 为权威设计；`plans/` 为实施方案；变更联动文档 |
| **分层架构** | api 编排 / services 业务 / skills 智能产出 |
| **最小 diff** | 只改任务相关代码，不顺手重构无关模块 |

---

## 四、文档层级

```
README.MD（本文档）  ← 宪法 + 快速开始
       ↓
GUIDE.md             ← 工作指引：每轮对话如何读文档
       ↓
docs/                ← 模块设计（01~17）
       ↓
plans/               ← 实施方案（如用户管理改造）
       ↓
.cursor/rules/       ← Cursor AI 约束（自动加载）
```

**冲突处理**：`docs/` 不得违背本文档；冲突时以本文档为准并修订 `docs/`。

---

## 五、快速开始

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

**统一管理脚本**（可选）：`./scripts/manage.sh start`

### 主要功能

- **数据中心**：CSV/XLSX 上传、字段识别、质量检查、样例数据导入、月报表数据预置
- **总览/智能分析**：Brent/WTI 价格走势、价差、供需预测图表
- **预测分析表**：权威数据 + 大模型研判 → 在线编辑 → 导出 Excel
- **报告中心**：大模型撰写月报 → 章节编辑/Agent 校准 → 导出 Word/PDF
- **预测模型**：基准/乐观/悲观情景统计预测与回测
- **用户管理**（admin）：新增用户、页面权限、重置密码
- **Agent 入口**：粒子化 Logo，支持数据分析、预测表、月报等技能

### 大模型与 Skill 架构

- 统一客户端 `backend/app/core/llm.py`，支持 `volcengine`（豆包，默认）/`deepseek`/`openai`/`mock`。
- **双调用模式**：`normal`（普通）与 `deep_research`（深度研究 / DeepSearch）。
- 后端 skill 位于 `backend/app/skills/`：`prediction_skill.py`、`report_skill.py`、`sources.py` 等。
- 大模型不可用时自动降级到「数据库证据 + 规则兜底」。

### 环境变量

参考 `backend/.env.example`。关键项：

```
DEFAULT_LLM_PROVIDER=volcengine
VOLCENGINE_API_KEY=...
VOLCENGINE_DEEPSEARCH_BOT_ID=bot-xxx
JWT_SECRET_KEY=change-me-in-production
ADMIN_USERNAME=admin
ADMIN_PASSWORD=...
```

详见 [docs/12-启动与部署.md](./docs/12-启动与部署.md) 与 [docs/17-用户管理与权限.md](./docs/17-用户管理与权限.md)。

---

## 六、修订

| 版本 | 日期 | 变更摘要 | 联动更新 |
|---|---|---|---|
| 2.0.0 | 2026-06-22 | 升格为项目宪法结构；新增 GUIDE 与 .cursor/rules | GUIDE.md、.cursor/rules/ |
