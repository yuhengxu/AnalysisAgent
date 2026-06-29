# AnalysisAgent 整体架构图

> 本图基于项目最新文档体系整理，覆盖：用户入口、前端页面、后端 API、服务层、Skill/LLM、数据与文件层、部署运维约束。

```mermaid
flowchart TB
  %% AnalysisAgent 整体架构图

  subgraph U[用户与入口]
    Admin[管理员 admin\n用户管理 / 权限分配 / 系统设置 / LLM 监控]
    User[普通用户 user\n按页面权限访问业务模块]
    AgentUI[右下角粒子化 Agent\n自然语言触发分析 / 预测 / 月报 / 修订]
  end

  subgraph FE[前端层 · React + TypeScript + Vite]
    AuthFE[登录态与权限\nAuthContext / ProtectedRoute / PageRoute / AdminRoute]
    Layout[Layout 导航\ncanAccessPage 过滤业务页面\nadmin 展示管理入口]
    Pages[业务页面\nDashboard / DataCenter / Analysis\nPrediction / Forecast / ReportCenter]
    AdminPages[管理页面\nUserManagement / Settings / LlmMonitor]
    Client[API Client\naxios / Bearer Token / Blob 下载 / 任务轮询]
  end

  subgraph API[后端 API 层 · FastAPI /api/v1]
    AuthAPI[/auth\nlogin / me]
    UsersAPI[/users\n用户 CRUD / 页面权限 / 重置密码]
    DataAPI[/data\n上传 / 样例导入 / 月报表数据]
    AnalyticsAPI[/analytics & /analysis\n统计查询 / 图表配置 / 智能分析]
    ForecastAPI[/forecast\n统计情景预测 / 回测]
    PredictionAPI[/prediction\n预测分析表生成 / 编辑 / 修订 / 导出]
    ReportsAPI[/reports\n月报生成 / 编辑 / 图表 / 导出]
    AgentAPI[/agent\n对话 / skill 编排 / 章节修订]
    OpsAPI[/llm & /llm-logs\n模型设置 / 调用日志]
  end

  subgraph CORE[基础设施与权限]
    Deps[get_current_user\nrequire_page(page)\nrequire_admin]
    Security[JWT + bcrypt\n页面权限不写入 JWT]
    DBCore[SQLAlchemy Session\nSQLite WAL / busy_timeout]
    Logging[统一日志\n请求耗时 / LLM 日志 / agent_runs]
    Config[.env 配置\nLLM / JWT / 数据库 / 图表引擎]
  end

  subgraph SVC[服务层 · Services]
    DataSvc[DataImportService / DataQueryService\n文件保存 / 数据解析 / 质量检查]
    AnalyticsSvc[AnalyticsService\n价格统计 / 价差 / 图表协议 / 月度统计]
    ForecastSvc[ForecastService\nMA3 + 趋势 / 情景预测]
    PredictionSvc[PredictionService\nCRUD / user_id 隔离 / Excel 导出]
    ReportSvc[ReportService\nCRUD / user_id 隔离 / Word/PDF/TeX 导出]
    TableSvc[ReportTableDataService\n6 张系统表 snapshot 同步 / 加载]
    ChartSvc[ChartExportService / chart_render\nmatplotlib 或 ECharts 生成 PNG]
    AgentSvc[AgentService\n技能识别 / 编排 / 视觉状态 / 校准]
    TaskSvc[report_tasks / prediction_tasks\n内存态任务 / task.user_id 校验]
  end

  subgraph SKILL[AI 与 Skill 层]
    PredSkill[PredictionSkill\n证据采集 + LLM 生成 28 项因素 + normalize + fallback]
    ReportSkill[ReportSkill\n证据采集 + LLM 撰写章节\n系统表 rows 只读 snapshot]
    AnalysisSkill[DataAnalysisSkill\n查询 / 分析 / 可选 LLM 总结]
    LLM[统一 LLM Client core/llm.py\nvolcengine / deepseek / openai / mock\nnormal / deep_research]
    Sources[可信数据源提示\nEIA / IEA / OPEC / CFTC / CNEEI 等]
    DeepSearch[DeepSearch 联网\n实时查证 / 来源 / URL / 期别]
  end

  subgraph DATA[数据与文件层]
    Raw[data/raw\n原始上传文件]
    DB[(SQLite db/energy_platform.db\nusers / datasets / price_series\nbalance_forecasts / factor_assessments\nforecast_results / predictions / reports\nreport_table_snapshots / agent_runs / llm_logs)]
    Exports[data/exports\n预测表 xlsx / 月报 docx pdf tex]
    Charts[data/charts\n月报图表 PNG]
    Logs[logs/app.log\n运行日志]
    Samples[yuebao/\n样例数据，只读参考]
  end

  subgraph OPS[部署与运维]
    Local[本地开发\nbackend uvicorn --reload\nfrontend npm run dev]
    Docker[Docker Compose\n前端 Nginx + 后端 Uvicorn]
    Worker[生产约束\n异步任务内存态 → workers=1\n多 worker 需 DB/Redis 任务表]
  end

  Admin --> AuthFE
  User --> AuthFE
  AgentUI --> AgentAPI
  AuthFE --> Layout --> Pages
  AuthFE --> AdminPages
  Pages --> Client
  AdminPages --> Client
  Client --> API

  API --> Deps
  Deps --> Security
  Deps --> DBCore

  AuthAPI --> Security
  UsersAPI --> Deps
  UsersAPI --> DBCore
  DataAPI --> DataSvc
  AnalyticsAPI --> AnalyticsSvc
  ForecastAPI --> ForecastSvc
  PredictionAPI --> PredictionSvc
  ReportsAPI --> ReportSvc
  AgentAPI --> AgentSvc
  OpsAPI --> Logging

  DataSvc --> Raw
  DataSvc --> DB
  DataSvc --> TableSvc
  AnalyticsSvc --> DB
  ForecastSvc --> DB
  PredictionSvc --> PredSkill
  PredictionSvc --> DB
  PredictionSvc --> Exports
  ReportSvc --> ReportSkill
  ReportSvc --> TableSvc
  ReportSvc --> ChartSvc
  ReportSvc --> DB
  ReportSvc --> Exports
  TableSvc --> DB
  ChartSvc --> DB
  ChartSvc --> Charts
  AgentSvc --> PredictionSvc
  AgentSvc --> ReportSvc
  AgentSvc --> ForecastSvc
  AgentSvc --> AnalyticsSvc
  AgentSvc --> DB
  TaskSvc --> PredictionSvc
  TaskSvc --> ReportSvc

  PredSkill --> LLM
  PredSkill --> AnalyticsSvc
  PredSkill --> Sources
  ReportSkill --> LLM
  ReportSkill --> AnalyticsSvc
  ReportSkill --> TableSvc
  ReportSkill --> Sources
  AnalysisSkill --> LLM
  LLM --> DeepSearch

  DBCore --> DB
  Logging --> Logs
  Config --> LLM
  Config --> DBCore
  Samples --> DataSvc
  Local --> FE
  Local --> API
  Docker --> FE
  Docker --> API
  Worker --> TaskSvc
```


## 图中关键约束

1. 前端通过 `AuthContext / PageRoute / AdminRoute` 做页面级拦截，后端通过 `require_page(page)` 与 `require_admin` 做强校验。
2. 月报、预测分析表、异步任务均按 `user_id` 严格隔离，管理员默认也不能跨用户查看业务产物。
3. 月报 6 张系统表由数据中心预置到 `report_table_snapshots`，生成、打开、导出时只读加载，LLM 不直接填写系统表 rows。
4. 两大核心交付物是预测分析表 Excel 与国际油价月报 Word/PDF/TeX。
5. 异步任务状态当前为进程内存态，生产部署应使用单 worker；如需多 worker，需要迁移到数据库或 Redis 任务表。
