import axios from 'axios'
import {
  buildForecastChart,
  extractSymbol,
  formatForecastResponse,
  getDefaultPredictionParams,
  getDefaultReportParams,
  formatLlmLabel,
  getLlmProvider,
  getLlmModel,
  getLlmRequestParams,
  getTrustedSourcesPayload,
  getUnrestrictedModePayload,
  type ReportGenerateParams,
} from '../constants/agentDefaults'
import { getStoredToken, setStoredToken } from '../lib/authStorage'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 600_000,
})

api.interceptors.request.use((config) => {
  const token = getStoredToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401 && !error.config?.url?.includes('/auth/login')) {
      setStoredToken(null)
      localStorage.removeItem('auth_user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

const pollApi = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
})

pollApi.interceptors.request.use((config) => {
  const token = getStoredToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export default api

export async function getDashboard(params?: { start_date?: string; end_date?: string }) {
  const { data } = await api.get('/analytics/dashboard', { params })
  return data
}

export async function getPrices(symbols = 'Brent,WTI') {
  const { data } = await api.get('/analytics/prices', { params: { symbols } })
  return data
}

export async function getChart(chartType: string, params?: Record<string, string | number | undefined>) {
  const { data } = await api.get(`/analytics/charts/${chartType}`, { params })
  return data
}

export async function getDataCatalog() {
  const { data } = await api.get('/data/catalog')
  return data
}

export async function queryData(params: Record<string, unknown>) {
  const { data } = await api.post('/data/query', params)
  return data
}

export async function exportQueryData(params: Record<string, unknown>) {
  const resp = await api.post('/data/query/export', params, { responseType: 'blob' })
  return resp.data
}

export async function runAnalysis(params: Record<string, unknown>) {
  const { data } = await api.post('/analysis/run', {
    include_charts: true,
    ...getLlmRequestParams('analysis'),
    ...params,
  })
  return data
}

export async function queryAnalysis(params: Record<string, unknown>) {
  const { data } = await api.post('/analysis/query', params)
  return data
}

export async function uploadFile(file: File, category?: string) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/data/upload', form, {
    params: category ? { category } : undefined,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function seedSampleData() {
  const { data } = await api.post('/data/seed')
  return data
}

export async function listDatasets() {
  const { data } = await api.get('/data/datasets')
  return data
}

export async function getAgencyForecastSchema() {
  const { data } = await api.get('/data/agency-forecasts/schema')
  return data
}

export async function getAgencyForecast(year: number, month: number) {
  const { data } = await api.get('/data/agency-forecasts', { params: { year, month } })
  return data
}

export async function listAgencyForecasts() {
  const { data } = await api.get('/data/agency-forecasts/list')
  return data
}

export async function saveAgencyForecast(payload: { year: number; month: number; rows: string[][] }) {
  const { data } = await api.put('/data/agency-forecasts', payload)
  return data
}

export async function getReportTablesSchema() {
  const { data } = await api.get('/data/report-tables/schema')
  return data
}

export async function getReportTables(reviewYear: number, reviewMonth: number) {
  const { data } = await api.get('/data/report-tables', {
    params: { review_year: reviewYear, review_month: reviewMonth },
  })
  return data
}

export async function listReportTablePeriods() {
  const { data } = await api.get('/data/report-tables/list')
  return data
}

export async function syncReportDerivedTables(payload: {
  review_year: number
  review_month: number
  outlook_year?: number
  outlook_month?: number
  table_keys?: string[]
}) {
  const { data } = await api.post('/data/report-tables/sync-derived', payload)
  return data
}

export async function fetchReportWebTables(payload: {
  review_year: number
  review_month: number
  outlook_year?: number
  outlook_month?: number
  enable_gdp_llm_predict?: boolean
  table_keys?: string[]
}) {
  const { data } = await api.post('/data/report-tables/fetch-web', payload)
  return data
}

export async function saveReportTable(payload: {
  review_year: number
  review_month: number
  table_key: string
  rows: string[][]
}) {
  const { table_key, ...body } = payload
  const { data } = await api.put(`/data/report-tables/${table_key}`, body)
  return data
}

export async function runAgent(
  prompt: string,
  skill: string,
  modelProvider = getLlmProvider(),
  modelName?: string,
) {
  const { data } = await api.post('/agent/run', {
    prompt,
    skill,
    model_provider: modelProvider,
    model_name: modelName ?? getLlmModel(),
    mode: getLlmRequestParams('analysis').mode,
    ...getTrustedSourcesPayload(),
  })
  return data
}

export async function waitForPredictionTask(
  taskId: string,
  onProgress?: (task: PredictionTaskStatus) => void,
): Promise<Record<string, unknown>> {
  for (;;) {
    const task = await getPredictionGenerateTask(taskId)
    onProgress?.(task)
    if (task.status === 'success' && task.result) return task.result
    if (task.status === 'error') throw new Error(task.error || '生成失败')
    await new Promise((r) => setTimeout(r, 2000))
  }
}

export async function chatAgent(
  messages: { role: string; content: string }[],
  skillHint?: string,
  onProgress?: (text: string) => void,
) {
  // 对话可能触发 DeepSearch 联网查证，须使用长超时 api，不能用 pollApi(30s)
  const { data } = await api.post('/agent/chat', {
    messages,
    skill_hint: skillHint,
    ...getTrustedSourcesPayload(),
    ...getLlmRequestParams('agent'),
  })
  const res = data as {
    message: string
    visual: Record<string, unknown>
    charts: unknown[]
    tools_called: string[]
    skill: string | null
    report_id: number | null
    prediction_id: number | null
    duration_ms: number
    async_task?: PredictionTaskStatus & { type?: string; skill?: string }
  }

  if (res.async_task?.task_id) {
    onProgress?.(res.async_task.message || '任务已启动…')
    const result = await waitForPredictionTask(res.async_task.task_id, (task) => {
      onProgress?.(
        task.step_label
          ? `第 ${task.step}/${task.total_steps} 步：${task.step_label}`
          : task.message,
      )
    })
    const title = typeof result.title === 'string' ? result.title : '预测分析表'
    return {
      ...res,
      message: `${res.message}\n\n已完成《${title}》，可在预测分析表页查看、校准并导出 Excel。`,
      prediction_id: typeof result.id === 'number' ? result.id : null,
      tools_called: res.tools_called?.length
        ? res.tools_called
        : ['collect_authoritative_data', 'llm_fill_prediction_table'],
    }
  }
  return res
}

export async function executeSkill(
  prompt: string,
  skill: string,
  onProgress?: (text: string) => void,
) {
  if (skill === 'predict') {
    const symbol = extractSymbol(prompt)
    const forecast = await runForecast(symbol)
    const priceChart = await getChart('price_trend').catch(() => null)
    const charts = [buildForecastChart(forecast)]
    if (priceChart) charts.push(priceChart)
    return {
      skill,
      response: formatForecastResponse(forecast),
      tools_called: ['run_forecast_model', 'generate_chart'],
      charts,
      evidence: { forecast },
      duration_ms: 0,
    }
  }
  if (skill === 'report') {
    const params = getDefaultReportParams()
    onProgress?.('正在启动月报生成任务…')
    const started = await startReportGenerateAsync(params)
    const report = await waitForReportTask(started.task_id, (task) => {
      onProgress?.(
        task.step_label
          ? `第 ${task.step}/${task.total_steps} 步：${task.step_label}`
          : task.message,
      )
    })
    const title = typeof report.title === 'string' ? report.title : '月报'
    const llmUsed = Boolean(report.llm_used)
    const modelName = typeof report.model_name === 'string' ? report.model_name : undefined
    const reportId = typeof report.id === 'number' ? report.id : undefined
    return {
      skill,
      response: `已生成月报初稿：${title}${llmUsed ? `（${formatLlmLabel(true, modelName)}）` : ''}。可在报告中心查看、校准并导出 Word。`,
      tools_called: ['collect_authoritative_data', 'llm_draft_report_section'],
      charts: [],
      evidence: { report_id: reportId },
      report_id: reportId,
      duration_ms: 0,
    }
  }
  if (skill === 'predict_table') {
    const p = getDefaultPredictionParams()
    onProgress?.('正在启动预测分析表生成任务…')
    const started = await startPredictionGenerateAsync({ ...p, extra_instruction: prompt })
    const pred = await waitForPredictionTask(started.task_id, (task) => {
      onProgress?.(
        task.step_label
          ? `第 ${task.step}/${task.total_steps} 步：${task.step_label}`
          : task.message,
      )
    })
    const title = typeof pred.title === 'string' ? pred.title : '预测分析表'
    const llmUsed = Boolean(pred.llm_used)
    const modelName = typeof pred.model_name === 'string' ? pred.model_name : undefined
    const predId = typeof pred.id === 'number' ? pred.id : undefined
    return {
      skill,
      response: `已生成《${title}》${llmUsed ? `（${formatLlmLabel(true, modelName)}）` : ''}，含 28 项影响因素与价格预测。可在预测分析表页校准并导出 Excel。`,
      tools_called: ['collect_authoritative_data', 'llm_fill_prediction_table'],
      charts: [],
      evidence: { prediction_id: predId },
      prediction_id: predId,
      duration_ms: 0,
    }
  }
  return runAgent(prompt, skill)
}

export async function clearData(category?: string) {
  const { data } = await api.delete('/data/clear', { params: category ? { category } : undefined })
  return data as { status: string; category: string; counts: Record<string, number> }
}

export async function listReports() {
  const { data } = await api.get('/reports')
  return data
}

export async function getReport(id: number) {
  const { data } = await api.get(`/reports/${id}`)
  return data
}

export async function updateReport(id: number, content: Record<string, unknown>, title?: string) {
  const { data } = await api.put(`/reports/${id}`, { content, title })
  return data
}

export async function generateReport(payload: ReportGenerateParams) {
  const { data } = await api.post('/reports/generate', {
    ...payload,
    ...getTrustedSourcesPayload(),
    ...getUnrestrictedModePayload(),
    ...getLlmRequestParams('report'),
  })
  return data
}

export interface ReportTaskStatus {
  task_id: string
  status: 'pending' | 'running' | 'success' | 'error'
  step: number
  total_steps: number
  step_label: string
  message: string
  result: Record<string, unknown> | null
  error: string | null
  elapsed_ms: number
}

export async function startReportGenerateAsync(payload: ReportGenerateParams) {
  const { data } = await pollApi.post<ReportTaskStatus>('/reports/generate/async', {
    ...payload,
    ...getTrustedSourcesPayload(),
    ...getUnrestrictedModePayload(),
    ...getLlmRequestParams('report'),
  })
  return data
}

export async function getReportGenerateTask(taskId: string) {
  const { data } = await pollApi.get<ReportTaskStatus>(`/reports/generate/tasks/${taskId}`)
  return data
}

export async function waitForReportTask(
  taskId: string,
  onProgress?: (task: ReportTaskStatus) => void,
): Promise<Record<string, unknown>> {
  for (;;) {
    const task = await getReportGenerateTask(taskId)
    onProgress?.(task)
    if (task.status === 'success' && task.result) return task.result
    if (task.status === 'error') throw new Error(task.error || '生成失败')
    await new Promise((r) => setTimeout(r, 2000))
  }
}

export async function getReportExportTools() {
  const { data } = await api.get('/reports/export-tools')
  return data as { xelatex: boolean; pandoc: boolean }
}

export async function exportReport(id: number, format: 'docx' | 'pdf' | 'tex' = 'docx') {
  const resp = await api.get(`/reports/${id}/export`, {
    params: { format },
    responseType: 'blob',
  })
  return resp.data
}

export async function getReportChartBlob(reportId: number, chartId: string) {
  const resp = await api.get(`/reports/${reportId}/charts/${chartId}`, { responseType: 'blob' })
  return resp.data as Blob
}

export async function runForecast(symbol = 'Brent') {
  const { data } = await api.post('/forecast/run', null, { params: { symbol } })
  return data
}

export async function listForecasts() {
  const { data } = await api.get('/forecast')
  return data
}

export async function getBacktest(symbol = 'Brent') {
  const { data } = await api.get('/forecast/backtest', { params: { symbol } })
  return data
}

export async function reviseSection(reportId: number, sectionId: string, instruction: string) {
  const { data } = await api.post(`/agent/revise/${reportId}`, {
    section_id: sectionId,
    instruction,
    ...getLlmRequestParams('report'),
  })
  return data
}

export async function deleteReport(id: number) {
  const { data } = await api.delete(`/reports/${id}`)
  return data
}

// ---- 预测分析表 ----
export async function listPredictions() {
  const { data } = await api.get('/prediction')
  return data
}

export async function getPrediction(id: number) {
  const { data } = await api.get(`/prediction/${id}`)
  return data
}

export async function generatePrediction(payload: {
  symbol?: string
  year: number
  month: number
  extra_instruction?: string
}) {
  const { data } = await api.post('/prediction/generate', {
    ...payload,
    ...getTrustedSourcesPayload(),
    ...getUnrestrictedModePayload(),
    ...getLlmRequestParams('prediction'),
  })
  return data
}

export interface PredictionTaskStatus {
  task_id: string
  status: 'pending' | 'running' | 'success' | 'error'
  step: number
  total_steps: number
  step_label: string
  message: string
  result: Record<string, unknown> | null
  error: string | null
  elapsed_ms: number
}

export async function startPredictionGenerateAsync(payload: {
  symbol?: string
  year: number
  month: number
  extra_instruction?: string
}) {
  const { data } = await pollApi.post<PredictionTaskStatus>('/prediction/generate/async', {
    ...payload,
    ...getTrustedSourcesPayload(),
    ...getUnrestrictedModePayload(),
    ...getLlmRequestParams('prediction'),
  })
  return data
}

export async function getPredictionGenerateTask(taskId: string) {
  const { data } = await pollApi.get<PredictionTaskStatus>(
    `/prediction/generate/tasks/${taskId}`,
  )
  return data
}

export async function updatePrediction(id: number, content: Record<string, unknown>, title?: string) {
  const { data } = await api.put(`/prediction/${id}`, { content, title })
  return data
}

export async function revisePredictionFactor(
  id: number,
  factorIdx: number,
  field: 'judgment',
  instruction: string,
) {
  const { data } = await api.post(`/prediction/${id}/revise`, {
    factor_idx: factorIdx,
    field,
    instruction,
    ...getLlmRequestParams('prediction'),
  })
  return data as { factor_idx: number; field: string; value: string | number }
}

export async function exportPrediction(id: number) {
  const resp = await api.get(`/prediction/${id}/export`, { responseType: 'blob' })
  return resp.data
}

export async function deletePrediction(id: number) {
  const { data } = await api.delete(`/prediction/${id}`)
  return data
}

export async function getTrustedSources() {
  const { data } = await api.get('/prediction/sources')
  return data
}

export async function listLlmLogs(params?: {
  page?: number
  page_size?: number
  source?: string
  status?: string
}) {
  const { data } = await api.get('/llm-logs', { params })
  return data as {
    items: Array<{
      id: number
      source: string
      provider: string
      model_name: string
      status: string
      duration_ms: number
      request_preview: string
      response_preview: string
      created_at: string
    }>
    total: number
    page: number
    page_size: number
    pages: number
  }
}

export async function getLlmLog(id: number) {
  const { data } = await api.get(`/llm-logs/${id}`)
  return data as {
    id: number
    source: string
    provider: string
    model_name: string
    status: string
    error_message: string
    duration_ms: number
    request_messages: Array<{ role: string; content: string }>
    response_content: string
    meta: Record<string, unknown>
    created_at: string
  }
}

export async function listLlmLogSources() {
  const { data } = await api.get('/llm-logs/sources')
  return data as string[]
}

export interface LlmModelOption {
  id: string
  label: string
  family: string
  hint: string
}

export interface LlmModelGroup {
  family: string
  label: string
  models: LlmModelOption[]
}

export interface LlmProviderInfo {
  id: string
  label: string
  model: string
  default_model: string
  models: LlmModelOption[]
  model_groups: LlmModelGroup[]
  enabled: boolean
  deep_research_available: boolean
  deep_research_label: string
}

export async function listLlmProviders() {
  const { data } = await api.get('/llm/providers')
  return data as {
    default: string
    providers: LlmProviderInfo[]
  }
}

export async function listLlmModels(provider: string) {
  const { data } = await api.get('/llm/models', { params: { provider } })
  return data as {
    provider: string
    default_model: string
    models: LlmModelOption[]
    groups: LlmModelGroup[]
  }
}

export async function testLlmConnection(provider: string, model?: string) {
  const { data } = await api.post('/llm/test', null, {
    params: { provider, model: model || undefined },
  })
  return data as {
    ok: boolean
    provider: string
    model: string
    message: string
    reply?: string
    duration_ms?: number
  }
}

export async function login(username: string, password: string) {
  const { data } = await api.post('/auth/login', { username, password })
  return data as {
    access_token: string
    token_type: string
    user: { id: number; username: string; role: 'admin' | 'user'; allowed_pages: string[] }
  }
}

export async function getMe() {
  const { data } = await api.get('/auth/me')
  return data as { id: number; username: string; role: 'admin' | 'user'; allowed_pages: string[] }
}

export interface UserPageOption {
  key: string
  label: string
}

export interface ManagedUser {
  id: number
  username: string
  role: 'admin' | 'user'
  allowed_pages: string[]
  is_active: boolean
  created_at?: string
  updated_at?: string
}

export async function getUserPageOptions() {
  const { data } = await api.get<UserPageOption[]>('/users/page-options')
  return data
}

export async function listUsers() {
  const { data } = await api.get<ManagedUser[]>('/users')
  return data
}

export async function createUser(payload: { username: string; allowed_pages: string[] }) {
  const { data } = await api.post<ManagedUser>('/users', payload)
  return data
}

export async function updateUser(
  id: number,
  payload: { allowed_pages?: string[]; is_active?: boolean },
) {
  const { data } = await api.put<ManagedUser>(`/users/${id}`, payload)
  return data
}

export async function deleteUser(id: number) {
  const { data } = await api.delete(`/users/${id}`)
  return data
}

export async function resetUserPassword(id: number) {
  const { data } = await api.post(`/users/${id}/reset-password`)
  return data as { id: number; status: string; initial_password: string }
}
