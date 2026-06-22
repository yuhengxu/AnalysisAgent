# 08 · Agent 与大模型模块

## 1. 组成
| 文件 | 职责 |
|------|------|
| `core/llm.py` | **统一大模型客户端**：provider 路由、JSON 模式、降级 |
| `core/config.py` | LLM 相关配置项 |
| `services/agent.py` | Agent 编排：对话、技能识别与调用、视觉外观、章节校准 |
| `api/agent.py` | REST 路由 |
| `skills/prediction_skill.py` / `report_skill.py` | 两个核心 skill |
| `skills/sources.py` | 可信数据源注册表 |

## 2. 统一大模型客户端（llm.py）

### 2.1 provider 路由
| provider | base_url | model | 说明 |
|----------|----------|-------|------|
| `volcengine`（默认） | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-2-0-pro-260215` | 火山方舟豆包，OpenAI 兼容 |
| `deepseek` | `https://api.deepseek.com` | `deepseek-v4-pro` | 兼容保留 |
| `openai` | `https://api.openai.com/v1` | `gpt-4o-mini` | 任意 OpenAI 兼容服务 |
| `mock` | — | — | 不联网，触发各 skill 规则兜底 |

### 2.2 调用模式（mode）
所有大模型调用统一支持两类模式（请求体 `mode` 字段，默认 `normal`）：

| mode | DeepSeek | 豆包（volcengine） | 其他 |
|------|----------|--------------------|------|
| `normal` | 直接调用，关闭思考链 | 直接调用 Seed 2.0 Pro | 直接调用 |
| `deep_research` | 开启**深度思考**（`thinking` + `reasoning_effort`，强度由 `DEEPSEEK_REASONING_EFFORT` 控制） | 调用 **DeepSearch 智能体**（`/bots/chat/completions`，model=`VOLCENGINE_DEEPSEARCH_BOT_ID`）。DeepSearch 专为复杂问题设计，集成浏览器使用、联网搜索、知识库、网页解析、ChatPPT、Python 代码执行器等 MCP 服务 | 等同普通模式 |

- 豆包未配置 `VOLCENGINE_DEEPSEARCH_BOT_ID` 时，深度研究模式自动降级为普通模式（日志告警）。
- 深度研究模式使用更长的超时 `LLM_DEEP_TIMEOUT`（默认 900s）。
- 兼容旧入参：`mode` 收到旧版思考强度取值时自动映射（`off`→`normal`，`high`/`max`→`deep_research`）。
- 豆包 DeepSearch 是项目唯一联网通道；不再调用独立浏览器服务。

### 2.3 关键函数
- `is_enabled(provider)` → provider≠mock 且配置了 key。
- `deep_search_available()` → 是否已配置 DeepSearch 应用 ID。
- `normalize_mode(mode)` → 归一化为 `normal` / `deep_research`。
- `chat(messages, provider, model, temperature, json_mode, max_tokens, mode)` → 文本；失败抛 `LLMUnavailable`。
- `chat_json(system, user, ..., mode)` → dict；内置 `_parse_json` 容错（去 ```json 围栏、截取首尾大括号）。
- **降级约定**：任何调用失败抛 `LLMUnavailable`，调用方 `except` 后走规则兜底，**绝不让请求失败**。

### 2.4 配置项（core/config.py / .env）
```
DEFAULT_LLM_PROVIDER=volcengine
VOLCENGINE_API_KEY=...
VOLCENGINE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
VOLCENGINE_MODEL=doubao-seed-2-0-pro-260215
VOLCENGINE_DEEPSEARCH_BOT_ID=bot-xxx     # 深度研究模式（方舟应用广场创建 DeepSearch 应用）
DEEPSEEK_REASONING_EFFORT=high           # DeepSeek 深度研究模式思考强度 high|max
LLM_TIMEOUT=600
LLM_DEEP_TIMEOUT=900
```

## 3. Agent 服务（agent.py）

### 3.1 技能（SKILLS）
| skill | 含义 | 落地 |
|-------|------|------|
| `predict_table` | 油价预测分析表 | PredictionService.generate |
| `report` | 国际油价月报 | ReportService.generate_monthly_draft |
| `predict` | 情景统计模型 | ForecastService.run_forecast |
| `analyze` | 数据分析 | AnalyticsService + 可选 LLM 润色 |
| `web_search` | DeepSearch 联网查证 | 方舟 DeepSearch 智能体 |

### 3.2 两个入口
- `run(prompt, skill, provider, model)`：直接执行某 skill，落 `agent_runs`，返回 response/tools_called/evidence/charts，含 `prediction_id`/`report_id`。
- `chat(messages, skill_hint, provider, model)`：对话式。先判**视觉意图**（改粒子外观）→ 否则 `_detect_skill` 识别技能 → 调 `run` → 包装回复 + 下发 `visual` 视觉状态。

### 3.3 技能识别（_detect_skill）
关键词命中：预测分析表/分析表→`predict_table`；月报/报告→`report`；预测/forecast→`predict`；分析/走势/价差→`analyze`。

### 3.4 视觉外观
`VISUAL_PRESETS` 定义 idle/listening/thinking/analyzing/predicting/reporting/success/futuristic 等；`_detect_visual_intent` 支持"科技感/红色警示/舒缓/加快"等自然语言微调，前端 `AgentAvatar` 据此渲染。

### 3.5 REST 接口
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/agent/run` | 执行单个 skill |
| POST | `/agent/chat` | 对话（返回 message/visual/charts/report_id/prediction_id） |
| GET | `/agent/skills` | 技能清单 |
| POST | `/agent/revise/{report_id}` | 章节级校准（见 07） |

## 4. DeepSearch 联网

项目不再使用独立浏览器服务。所有实时联网需求统一调用方舟 DeepSearch 智能体（`/bots/chat/completions`）：

- 月报和预测分析表强制使用 DeepSearch 获取最新数据与来源。
- `web_search` skill 和普通对话中的实时问题自动切换到 DeepSearch。
- 月报表 PMI 等联网数据只允许通过 DeepSearch 获取，不设置其他联网降级路径。
- 联网结果必须包含来源名称、URL 与数据期别；缺失时只能说明“暂未获取可核验证据”，不得补写数字。

`skills/sources.py` 仍作为内部权威机构说明保留，用于提示模型优先采用 EIA/IEA/OPEC/CFTC/CNEEI 等机构口径，但不作为用户可配置功能。

## 5. 扩展点
- 新增 provider（如通义/文心）：在 `_resolve()` 加分支 + config 加 key。
- 新增 skill：在 `skills/` 写类（gather_evidence + generate + 降级）→ 在 agent `SKILLS`/`run`/`_detect_skill` 注册（见 15）。
- 流式输出：当前为一次性返回，SSE 流式见 14-TODO-AGENT-1。
