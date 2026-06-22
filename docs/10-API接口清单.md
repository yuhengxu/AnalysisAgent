# 10 · API 接口清单与调用关系

- **基址**：`/api/v1`（前端通过 Vite 代理到 `http://localhost:8000`）。
- **健康检查**：`GET /health`（不带前缀，公开）。
- **鉴权**：除 `/auth/login` 外，所有业务 API 需 `Authorization: Bearer <token>`。
  - **页面权限**：各业务模块 router 使用 `require_page(key)`（见 [17-用户管理与权限](./17-用户管理与权限.md)）。
  - **管理员**：`/users/*`、`/llm`、`/llm-logs` 需 admin 角色。
- 前端调用层：`frontend/src/api/client.ts`（所有请求集中于此）。

## 0. auth（登录）
| 方法 | 路径 | 前端调用 | 说明 |
|------|------|----------|------|
| POST | `/auth/login` | `login` | 返回 `access_token` + `user.allowed_pages`；停用账号 403 |
| GET | `/auth/me` | `getMe` | 刷新当前用户与页面权限 |

## 0.1 users（用户管理 · admin）
| 方法 | 路径 | 前端调用 | 说明 |
|------|------|----------|------|
| GET | `/users/page-options` | `getUserPageOptions` | 可勾选业务页面 |
| GET | `/users` | `listUsers` | 用户列表 |
| POST | `/users` | `createUser` | 创建普通用户，初始密码 `qwer1234` |
| PUT | `/users/{id}` | `updateUser` | 修改页面权限 / 启停 |
| DELETE | `/users/{id}` | `deleteUser` | 删除普通用户 |
| POST | `/users/{id}/reset-password` | `resetUserPassword` | 重置为 `qwer1234` |

## 1. data（数据中心）
| 方法 | 路径 | 请求 | 返回 | 前端调用 |
|------|------|------|------|----------|
| POST | `/data/upload` | multipart file + `?category` | `{import, quality}` | `uploadFile` |
| POST | `/data/seed` | — | `{results[]}` | `seedSampleData` |
| GET | `/data/datasets` | — | `Dataset[]` | `listDatasets` |
| GET | `/data/quality/{id}` | — | `{issues, passed}` | — |
| GET | `/data/report-tables/schema` | — | `{tables[]}` | `getReportTablesSchema` |
| GET | `/data/report-tables/list` | — | 已录入回顾月列表 | `listReportTablePeriods` |
| GET | `/data/report-tables` | `review_year`, `review_month` | 6 表 snapshot 状态 | `getReportTables` |
| POST | `/data/report-tables/sync-derived` | `{review_year, review_month, ...}` | `{synced, errors}` | `syncReportDerivedTables` |
| POST | `/data/report-tables/fetch-web` | `{review_year, review_month, table_keys?}` | `{fetched, skipped, errors}` | `fetchReportWebTables` |
| PUT | `/data/report-tables/{table_key}` | `{review_year, review_month, rows}` | snapshot | `saveReportTable` |
| GET | `/data/agency-forecasts/schema` | — | 表3-2 模板（兼容） | `getAgencyForecastSchema` |
| GET | `/data/agency-forecasts` | `year`, `month`（展望月） | 表3-2 数据 | `getAgencyForecast` |
| PUT | `/data/agency-forecasts` | `{year, month, rows}` | 写入 table_agency snapshot | `saveAgencyForecast` |

## 2. analytics（分析/可视化）
| 方法 | 路径 | 关键参数 | 前端调用 |
|------|------|----------|----------|
| GET | `/analytics/dashboard` | — | `getDashboard` |
| GET | `/analytics/prices` | `symbols,start_date,end_date` | `getPrices` |
| GET | `/analytics/spread` | `symbol_a,symbol_b` | — |
| GET | `/analytics/balance` | `agency` | — |
| GET | `/analytics/factors` | `report_month` | — |
| GET | `/analytics/charts/{type}` | type∈price_trend/spread/balance | `getChart` |
| GET | `/analytics/monthly-stats` | `symbol,year,month` | — |

## 3. forecast（统计模型）
| 方法 | 路径 | 前端调用 |
|------|------|----------|
| POST | `/forecast/run?symbol=` | `runForecast` |
| GET | `/forecast?symbol=` | `listForecasts` |
| GET | `/forecast/backtest?symbol=` | `getBacktest` |

## 4. prediction（预测分析表）★
| 方法 | 路径 | 前端调用 |
|------|------|----------|
| POST | `/prediction/generate` | `generatePrediction` |
| POST | `/prediction/generate/async` | 异步生成 |
| GET | `/prediction/generate/tasks/{task_id}` | 轮询进度（校验 task.user_id） |
| GET | `/prediction` | `listPredictions` |
| GET | `/prediction/{id}` | `getPrediction` |
| PUT | `/prediction/{id}` | `updatePrediction` |
| POST | `/prediction/{id}/revise` | `revisePredictionFactor` |
| GET | `/prediction/{id}/export` | `exportPrediction`（blob） |
| DELETE | `/prediction/{id}` | `deletePrediction` |
| GET | `/prediction/sources` | `getTrustedSources` |

## 5. reports（月报）★
| 方法 | 路径 | 前端调用 |
|------|------|----------|
| POST | `/reports/generate` | `generateReport` |
| POST | `/reports/generate/async` | 异步生成 |
| GET | `/reports/generate/tasks/{task_id}` | 轮询进度（校验 task.user_id） |
| GET | `/reports` | `listReports` |
| GET | `/reports/template` | — |
| GET | `/reports/{id}` | `getReport` |
| PUT | `/reports/{id}` | `updateReport` |
| GET | `/reports/{id}/export` | `exportReport`（blob，`?format=docx\|pdf\|tex`） |
| GET | `/reports/export-tools` | `getReportExportTools`（xelatex/pandoc 可用性） |
| GET | `/reports/{id}/charts/{chart_id}` | 图表 PNG（`<img src>`） |
| DELETE | `/reports/{id}` | `deleteReport` |

## 6. agent
| 方法 | 路径 | 前端调用 |
|------|------|----------|
| POST | `/agent/run` | `runAgent` |
| POST | `/agent/chat` | `chatAgent` |
| GET | `/agent/skills` | — |
| POST | `/agent/revise/{report_id}` | `reviseSection` |

## 7. 调用关系图（API → 服务 → skill → DB/LLM）
```
data       → DataImportService → DB
analytics  → AnalyticsService  → DB
forecast   → ForecastService   → AnalyticsService → DB
prediction → PredictionService → PredictionSkill → AnalyticsService(DB) + llm(豆包/DeepSeek)
reports    → ReportService     → ReportSkill     → AnalyticsService(DB) + llm(豆包/DeepSeek)
agent      → AgentService      → {Prediction/Report/Forecast/Analytics}Service + llm
```

## 8. 约定
- 错误：服务抛 `ValueError("... not found")` → 路由转 `HTTPException(404)`。
- 大模型相关参数：`model_provider` 传 `null`/不传则用后端默认（deepseek）；传 `mock` 走兜底。
- 二进制下载（Excel/Word）：前端用 `responseType:'blob'` + `URL.createObjectURL`。
