# 能源行业 AI 数据分析平台 · 项目工作指引

> **每轮对话入口。** 先读本文档了解当前阶段与核心约束，再根据需要加载 `docs/` 对应文档，确保工作不偏离项目目标。

---

## 1. 项目核心约束（不可偏离）

以下约束来自 [README.MD](./README.MD)（**项目宪法**），所有决策与实现均不得违背：

| 约束 | 说明 |
|---|---|
| 领域定位 | 国际原油数据分析、预测分析表、国际油价月报 |
| 两大交付物 | 预测分析表（Excel）+ 月报（Word），结构化 JSON 存库 |
| Skill 架构 | 证据采集 + LLM + 降级；系统表 snapshot 只读，LLM 不填 rows |
| 分层 | api 编排 / services 业务 / skills 智能产出 |
| 鉴权 | JWT + 页面权限 `require_page` + 用户数据隔离 |
| 多用户 | 月报/预测/异步 task 按 `user_id` 严格隔离 |
| 部署 | Docker Compose；异步任务单 worker；SQLite WAL |
| 文档驱动 | `docs/` 为权威设计；`plans/` 为实施方案；变更须联动文档 |
| LLM 可降级 | 模型不可用时不 500，走规则兜底 |

---

## 2. 文档体系

```
AnalysisAgent/
├── GUIDE.md              ← 本文档（每轮对话入口）
├── README.MD             ← 项目宪法 + 快速开始
├── docs/                 ← 正式设计文档（权威依据）
│   ├── README.md         ← 文档导航
│   ├── 01~17           ← 各模块说明
│   └── 15-开发规范     ← 「改哪个文件」速查表
├── plans/                ← 实施方案（如 edituser.plan.md）
├── backend/              ← FastAPI 后端
└── frontend/             ← React 前端
```

| 目录 | 定位 | 权威性 | 何时读取 |
|---|---|---|---|
| [README.MD](./README.MD) | 项目宪法 + 快速启动 | **最高** | 每轮对话 |
| [docs/](./docs/) | 模块设计、API、规范 | **权威**，开发以此为准 | 按需检索（见 §5） |
| [plans/](./plans/) | 具体改造/实施计划 | 实施依据 | 执行专项任务时 |
| `.cursor/rules/` | AI 对话约束 | 与 README 一致 | Cursor 自动加载 |

**优先级**：`README.MD`（宪法）> `docs/`（正式设计）> `plans/`（实施方案）。

---

## 3. 各阶段工作指引

### 3.1 规划 / 新功能

| 步骤 | 动作 | 读取文档 |
|---|---|---|
| 1 | 确认边界与约束 | README.MD、本文档 §1 |
| 2 | 查架构与模块 | [docs/01-架构总览](./docs/01-架构总览.md) |
| 3 | 查待办与缺口 | [docs/14-待完善功能清单](./docs/14-待完善功能清单.md) |
| 4 | 编写实施计划 | `plans/` 下新建 `.plan.md`（可选） |

### 3.2 设计 / 改接口或表

| 步骤 | 动作 | 读取文档 |
|---|---|---|
| 1 | 定位模块 | [docs/15-开发规范与模块边界](./docs/15-开发规范与模块边界.md) |
| 2 | 数据库 | [docs/02-数据库模块](./docs/02-数据库模块.md) |
| 3 | API | [docs/10-API接口清单](./docs/10-API接口清单.md) |
| 4 | 权限 | [docs/17-用户管理与权限](./docs/17-用户管理与权限.md) |
| 5 | 联动更新 | 对应模块 doc + API 清单 + `client.ts` |

### 3.3 开发

| 步骤 | 动作 | 读取文档 |
|---|---|---|
| 1 | 速查改哪些文件 | [docs/15 §1](./docs/15-开发规范与模块边界.md) |
| 2 | 模块细节 | docs/03~08、16、17 对应章节 |
| 3 | 编码 | 遵循分层；LLM 必降级 |
| 4 | 自检 | [docs/15 §5](./docs/15-开发规范与模块边界.md) |

**完成标准 checklist**：

- [ ] 后端 `python -c "from app.main import app"` 无报错
- [ ] 前端 `npm run build` 通过
- [ ] 权限：前后端均校验（若涉及页面/用户数据）
- [ ] 文档：表/接口/权限变更已同步 `docs/`

### 3.4 部署

| 步骤 | 动作 | 读取文档 |
|---|---|---|
| 1 | 本地/Docker 启动 | [docs/12-启动与部署](./docs/12-启动与部署.md) |
| 2 | 环境变量 | `backend/.env.example` |
| 3 | 生产 worker | **必须 `--workers 1`**（异步任务内存态） |

---

## 4. 工作启动流程（每轮对话）

**原则：轻量入口，按需检索。**

```
□ 1. 读取 GUIDE.md（本文档），确认任务类型
□ 2. 读取 README.MD，确认核心约束
□ 3. 根据 §5 速查表加载 docs/ 对应文档
□ 4. 若执行 plans/ 下方案，先读完整 plan 再编码
□ 5. 完成后：结构性变更同步 docs/；自检清单打勾
```

---

## 5. 按任务类型速查

| 任务类型 | 核心文档 | 补充 |
|---|---|---|
| 架构/总览 | docs/01、README | docs/09 数据流转 |
| 数据导入 | docs/03 | docs/02 |
| 分析/图表 | docs/04、docs/06 | docs/10 analytics |
| 预测分析表 | docs/05 | skills/prediction_skill.py |
| 月报生成 | docs/07、docs/16 | skills/report_skill.py |
| Agent/LLM | docs/08 | core/llm.py |
| API 清单 | docs/10 | frontend/api/client.ts |
| 前端页面 | docs/11 | App.tsx、Layout.tsx |
| 用户/权限 | docs/17 | api/users.py、PageRoute |
| 部署运维 | docs/12 | docker-compose.yml |
| 开发规范 | docs/15 | .cursor/rules/ |
| 待办任务 | docs/14 | plans/ |
| 日志排障 | docs/13 | logs/app.log |

---

## 6. 偏离处理

| 情况 | 处理方式 |
|---|---|
| 新功能不在 docs 中 | 先更新 docs/ 或 plans/，再编码 |
| 新增/变更表或字段 | 更新 docs/02 + migrate.py |
| 新增/变更 API | 更新 docs/10 + client.ts |
| 变更页面权限 | 更新 docs/17 + deps.py + 前端路由 |
| 变更月报/预测 JSON 结构 | 同步模板、导出、前端、skill prompt |

**小偏离**（可先编码、提交时同步文档）须同时满足：

- 不涉及新 API/表/权限
- 不改变 content_json 结构或系统表逻辑
- 变更范围限于 1–2 个文件（bug 修复、样式微调、性能优化）

**不属于小偏离**：新页面、新 skill、新用户权限、跨用户数据访问、异步任务机制变更。

---

## 7. 文档修订

1. **结构性变更**（新模块 doc、权限模型、架构调整）：更新 `docs/README.md` 导航。
2. **单文档内容变更**：Git 自然追踪。
3. 若本文档结构性变更，在下方登记：

| 版本 | 日期 | 变更摘要 |
|---|---|---|
| 1.0.0 | 2026-06-22 | 初版：参照 HIS GUIDE 结构，适配 AnalysisAgent 文档体系 |
