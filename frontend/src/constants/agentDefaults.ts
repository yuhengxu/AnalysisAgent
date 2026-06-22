import { beijingDateParts } from '../lib/formatTime'

export const SKILL_LABELS: Record<string, string> = {
  analyze: '数据分析',
  predict_table: '预测分析表',
  report: '月报生成',
  predict: '情景模型',
  web_search: '深度研究查证',
}

/** 智能分析 / 数据库解读：避免「近期」等表述，强制模型绑定 evidence */
export const ANALYSIS_EVIDENCE_PROMPT =
  '请仅根据 evidence 中已查询的平台数据库结果，解读关键数值变化、差异及业务含义。'

export const SKILL_PROMPTS: Record<string, string> = {
  analyze: ANALYSIS_EVIDENCE_PROMPT,
  predict_table: '采集权威数据，生成本月布伦特油价预测分析表，逐项填写影响因素与价格预测',
  report: '生成本月国际油价月报初稿，包含市场回顾、影响因素分析与价格展望',
  predict: '基于历史数据预测 Brent 下月价格走势，给出基准/乐观/悲观三种情景',
  web_search: '使用豆包 DeepSearch 查证国际油价最新权威数据',
  research: '检索 OPEC 最新产量政策与 EIA 库存数据，结合互联网资讯分析对布伦特油价的影响',
}

export const RESEARCH_PROMPT =
  '检索近期国际油价市场动态（OPEC/EIA/美联储），结合平台数据给出简要研判'

/** 各业务模块可独立配置调用模式（普通 / 深度研究） */
export const LLM_MODULES = {
  agent: { label: 'Agent 对话', hint: '悬浮助手与资讯检索' },
  prediction: { label: '预测分析表', hint: '多轮生成 28 项因素' },
  report: { label: '报告中心', hint: '月报生成与段落修订' },
  analysis: { label: '智能分析', hint: '平台数据解读与图表分析' },
} as const

export type LlmModule = keyof typeof LLM_MODULES
/**
 * 调用模式：
 * - normal        普通模式：直接调用对话模型，响应快
 * - deep_research 深度研究模式：DeepSeek 开启深度思考；豆包调用 DeepSearch 智能体
 *                 （集成浏览器使用、联网搜索、知识库、网页解析、ChatPPT、Python 代码执行器等 MCP 服务）
 */
export type LlmMode = 'normal' | 'deep_research'

export const LLM_MODE_LABELS: Record<LlmMode, string> = {
  normal: '普通',
  deep_research: '深度研究',
}

export function getDefaultPredictionParams() {
  const now = new Date()
  return { symbol: 'Brent', year: now.getFullYear(), month: now.getMonth() + 1 }
}

export function getLlmProvider(): string {
  return localStorage.getItem('llm_provider') || 'volcengine'
}

export function getLlmModel(): string {
  return localStorage.getItem('llm_model') || 'doubao-seed-2-0-pro-260215'
}

function normalizeMode(stored: string | null): LlmMode | null {
  if (stored === 'normal' || stored === 'deep_research') return stored
  // 兼容旧版思考强度存储：high/max/off → 深度研究（系统默认）
  if (stored === 'high' || stored === 'max' || stored === 'off') return 'deep_research'
  return null
}

export function getGlobalLlmMode(): LlmMode {
  return (
    normalizeMode(localStorage.getItem('llm_mode')) ??
    normalizeMode(localStorage.getItem('llm_reasoning_effort')) ??
    'deep_research'
  )
}

export function getLlmMode(module?: LlmModule): LlmMode {
  if (module) {
    const stored =
      normalizeMode(localStorage.getItem(`llm_mode_${module}`)) ??
      normalizeMode(localStorage.getItem(`llm_reasoning_effort_${module}`))
    if (stored) return stored
  }
  return getGlobalLlmMode()
}

export function setLlmMode(target: LlmModule | 'global', mode: LlmMode) {
  const key = target === 'global' ? 'llm_mode' : `llm_mode_${target}`
  localStorage.setItem(key, mode)
}

export function getLlmRequestParams(module?: LlmModule) {
  return {
    model_provider: getLlmProvider(),
    model_name: getLlmModel(),
    mode: getLlmMode(module),
  }
}

const TRUSTED_SOURCES_ONLY_KEY = 'trusted_sources_only'
const LEGACY_TRUSTED_SOURCES_ONLY_KEY = 'agent_trusted_sources_only'

export function getTrustedSourcesOnly(): boolean {
  const stored =
    localStorage.getItem(TRUSTED_SOURCES_ONLY_KEY) ??
    localStorage.getItem(LEGACY_TRUSTED_SOURCES_ONLY_KEY)
  if (stored === 'false') return false
  return true
}

export function setTrustedSourcesOnly(enabled: boolean) {
  localStorage.setItem(TRUSTED_SOURCES_ONLY_KEY, enabled ? 'true' : 'false')
  window.dispatchEvent(
    new CustomEvent('trusted-sources-change', { detail: { enabled } }),
  )
}

/** @deprecated 使用 getTrustedSourcesOnly */
export const getAgentTrustedSourcesOnly = getTrustedSourcesOnly

/** @deprecated 使用 setTrustedSourcesOnly */
export const setAgentTrustedSourcesOnly = setTrustedSourcesOnly

export function getTrustedSourcesPayload() {
  return { trusted_sources_only: false }
}

const UNRESTRICTED_MODE_KEY = 'unrestricted_mode'

export function getUnrestrictedMode(): boolean {
  return localStorage.getItem(UNRESTRICTED_MODE_KEY) === 'true'
}

export function setUnrestrictedMode(enabled: boolean) {
  localStorage.setItem(UNRESTRICTED_MODE_KEY, enabled ? 'true' : 'false')
  window.dispatchEvent(
    new CustomEvent('unrestricted-mode-change', { detail: { enabled } }),
  )
}

export function getUnrestrictedModePayload() {
  return { unrestricted_mode: getUnrestrictedMode() }
}

const MODEL_DISPLAY_LABELS: Record<string, string> = {
  'deepseek-v4-pro': 'DeepSeek-V4-pro',
  'deepseek-v4-flash': 'DeepSeek-V4-flash',
  'deepseek-chat': 'DeepSeek Chat',
  'deepseek-reasoner': 'DeepSeek Reasoner',
  'doubao-seed-2-0-pro-260215': 'Doubao-Seed-2.0-pro',
  'doubao-seed-2-0-lite-260215': 'Doubao-Seed-2.0-lite',
  'gpt-4o-mini': 'GPT-4o mini',
  'gpt-4o': 'GPT-4o',
}

/** 根据模型名生成展示标签（历史记录、生成完成提示等）。 */
export function formatLlmLabel(llmUsed: boolean, modelName?: string | null): string {
  if (!llmUsed) return '规则'
  if (!modelName) return '大模型'
  if (MODEL_DISPLAY_LABELS[modelName]) return MODEL_DISPLAY_LABELS[modelName]
  if (/doubao|seed-2-0-pro/i.test(modelName)) return '豆包'
  if (/deepseek/i.test(modelName)) return 'DeepSeek'
  if (/qwen/i.test(modelName)) return '通义千问'
  if (/gpt/i.test(modelName)) return 'OpenAI'
  return modelName
}

export interface ReportGenerateParams {
  issue_no: string
  report_date: string
  review_year: number
  review_month: number
  outlook_year: number
  outlook_month: number
}

/** 展望月 → 回顾月（含跨年：1 月展望 → 上年 12 月回顾） */
export function reviewFromOutlook(outlookYear: number, outlookMonth: number) {
  if (outlookMonth === 1) {
    return { review_year: outlookYear - 1, review_month: 12 }
  }
  return { review_year: outlookYear, review_month: outlookMonth - 1 }
}

/** 回顾月 → 展望月（含跨年：12 月回顾 → 次年 1 月展望） */
export function outlookFromReview(reviewYear: number, reviewMonth: number) {
  if (reviewMonth === 12) {
    return { outlook_year: reviewYear + 1, outlook_month: 1 }
  }
  return { outlook_year: reviewYear, outlook_month: reviewMonth + 1 }
}

/** 表2-1 PMI 查证期别：与回顾月一致 */
export function pmiFromReview(reviewYear: number, reviewMonth: number) {
  return { pmi_year: reviewYear, pmi_month: reviewMonth }
}

export function formatDataCenterPeriodNote(reviewYear: number, reviewMonth: number) {
  const outlook = outlookFromReview(reviewYear, reviewMonth)
  const pmi = pmiFromReview(reviewYear, reviewMonth)
  return [
    `回顾月：${reviewYear}年${reviewMonth}月`,
    `PMI 查证：${pmi.pmi_year}年${pmi.pmi_month}月`,
    `对应展望月报：${outlook.outlook_year}年${outlook.outlook_month}月（第${outlook.outlook_month}期）`,
  ].join('\n')
}

export function buildReportParams(outlookYear: number, outlookMonth: number): ReportGenerateParams {
  const { review_year: reviewYear, review_month: reviewMonth } = reviewFromOutlook(
    outlookYear,
    outlookMonth,
  )
  const { day } = beijingDateParts()
  const reportDate = `${outlookYear}年${outlookMonth}月${day}日`
  const issueNo = `${outlookYear}年第${outlookMonth}期`
  return {
    issue_no: issueNo,
    report_date: reportDate,
    review_year: reviewYear,
    review_month: reviewMonth,
    outlook_year: outlookYear,
    outlook_month: outlookMonth,
  }
}

export function formatReportPeriodLabel(params: ReportGenerateParams): string {
  return `${params.outlook_year}年${params.outlook_month}月期（回顾${params.review_year}年${params.review_month}月）`
}

export function getDefaultReportParams(): ReportGenerateParams {
  const { year, month } = beijingDateParts()
  return buildReportParams(year, month)
}

/** 数据中心默认回顾月：对应当前月报展望月的上一自然月 */
export function getDefaultReviewPeriod() {
  const { year, month } = beijingDateParts()
  return reviewFromOutlook(year, month)
}

export function extractSymbol(prompt: string): string {
  const match = prompt.match(/\b(Brent|WTI|Dubai|Oman)\b/i)
  return match ? match[1].charAt(0).toUpperCase() + match[1].slice(1).toLowerCase() : 'Brent'
}

export function formatForecastResponse(forecast: {
  symbol: string
  period: string
  scenarios: Array<{ scenario: string; point: number; low: number; high: number }>
  evidence: Record<string, unknown>
}): string {
  const lines = [`【${forecast.symbol} ${forecast.period} 预测结果】`]
  for (const s of forecast.scenarios) {
    const label =
      s.scenario === 'baseline' ? '基准' : s.scenario === 'optimistic' ? '乐观' : '悲观'
    lines.push(`- ${label}：${s.point} USD/bbl（区间 ${s.low}–${s.high}）`)
  }
  lines.push(`依据：${JSON.stringify(forecast.evidence)}`)
  return lines.join('\n')
}

export function buildForecastChart(forecast: {
  symbol: string
  period: string
  scenarios: Array<{ scenario: string; point: number; low: number; high: number }>
}) {
  const labelMap: Record<string, string> = {
    baseline: '基准',
    optimistic: '乐观',
    pessimistic: '悲观',
  }
  return {
    title: `${forecast.symbol} ${forecast.period} 情景预测`,
    xAxis: '情景',
    yAxis: '价格 (USD/bbl)',
    source: '平台预测模型',
    series: [
      {
        name: forecast.symbol,
        data: forecast.scenarios.map((s) => [labelMap[s.scenario] || s.scenario, s.point]),
      },
    ],
  }
}
