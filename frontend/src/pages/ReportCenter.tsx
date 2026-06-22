import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  deleteReport,
  exportReport,
  getReportExportTools,
  getReport,
  getReportTables,
  listReports,
  reviseSection,
  updateReport,
} from '../api/client'
import ModeSelect from '../components/ModeSelect'
import ReportChartImage from '../components/ReportChartImage'
import {
  buildReportParams,
  formatReportPeriodLabel,
  getDefaultReportParams,
  getUnrestrictedMode,
} from '../constants/agentDefaults'
import {
  chartsForSection,
  DEFAULT_REVISE_INSTRUCTION,
} from '../constants/reportCharts'
import { useReportTask } from '../hooks/useReportTask'
import { startReportGenerate } from '../lib/reportGenerateTask'

interface Section {
  id: string
  title: string
  level: number
  content?: string
  hint?: string
  confidence_level?: string
  source_url?: string
  source_title?: string
}

const confidenceBadge: Record<string, string> = {
  权威数据: 'bg-cyan-500/15 text-cyan-300',
  模型推断: 'bg-amber-500/15 text-amber-300',
}
interface TableData {
  title: string
  source: string
  headers: string[]
  rows: string[][]
}
interface ReportContent {
  cover: Record<string, string>
  summary: string
  sections: Section[]
  tables: Record<string, TableData>
  approval: Record<string, string>
}

const TABLE_ANCHOR: Record<string, string> = {
  review_futures: 'table_price_change',
  outlook_scenario: 'table_scenario',
  outlook_agency: 'table_agency',
}

const TABLE_KEY_LABEL: Record<string, string> = {
  table_price_change: '表1-1 价格月度变化',
  table_macro_pmi: '表2-1 PMI',
  table_demand_forecast: '表2-2 GDP',
  table_supply_balance: '表2-3 供需差',
  table_scenario: '表3-1 情景预测',
  table_agency: '表3-2 咨询机构预测',
}

function formatMissingTablesNote(missing: string[]): string {
  if (!missing.length) return ''
  const labels = missing.map((k) => TABLE_KEY_LABEL[k] || k)
  return `\n⚠ 以下系统表尚未预置：${labels.join('、')}（可在数据中心「月报表数据」补全）`
}

export default function ReportCenter() {
  const [searchParams, setSearchParams] = useSearchParams()
  const task = useReportTask()
  const resumedRef = useRef(false)
  const defaults = getDefaultReportParams()
  const [outlookYear, setOutlookYear] = useState(defaults.outlook_year)
  const [outlookMonth, setOutlookMonth] = useState(defaults.outlook_month)
  const reportParams = useMemo(
    () => buildReportParams(outlookYear, outlookMonth),
    [outlookYear, outlookMonth],
  )

  const [reports, setReports] = useState<any[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<any>(null)
  const [content, setContent] = useState<ReportContent | null>(null)
  const [message, setMessage] = useState('')
  const [unrestrictedMode, setUnrestrictedMode] = useState(getUnrestrictedMode)
  const [revising, setRevising] = useState<string | null>(null)
  const [reviseTexts, setReviseTexts] = useState<Record<string, string>>({
    summary: DEFAULT_REVISE_INSTRUCTION,
  })
  const [exportTools, setExportTools] = useState<{ xelatex: boolean; pandoc: boolean } | null>(null)

  const loading = task.status === 'running'

  function getReviseText(sectionId: string) {
    return reviseTexts[sectionId] ?? DEFAULT_REVISE_INSTRUCTION
  }

  function setReviseText(sectionId: string, value: string) {
    setReviseTexts((prev) => ({ ...prev, [sectionId]: value }))
  }

  async function refresh() {
    setReports(await listReports())
  }

  useEffect(() => {
    refresh().catch(() => setReports([]))
  }, [])

  useEffect(() => {
    getReportExportTools()
      .then(setExportTools)
      .catch(() => setExportTools({ xelatex: false, pandoc: false }))
  }, [])

  useEffect(() => {
    const onChange = () => setUnrestrictedMode(getUnrestrictedMode())
    window.addEventListener('unrestricted-mode-change', onChange)
    return () => window.removeEventListener('unrestricted-mode-change', onChange)
  }, [])

  useEffect(() => {
    const idParam = searchParams.get('id')
    if (idParam && !Number.isNaN(Number(idParam))) openReport(Number(idParam))
  }, [searchParams])

  useEffect(() => {
    if (resumedRef.current) return
    resumedRef.current = true

    if (task.status === 'idle') return

    if (task.params) {
      setOutlookYear(task.params.outlook_year)
      setOutlookMonth(task.params.outlook_month)
    }
    setMessage(task.message)

    if (task.status === 'running' && task.params) {
      startReportGenerate(task.params)
        .then(async (res) => {
          const refs = res.references || {}
          const refNote = [
            refs.forecast_model ? '已引用预测模型' : '未找到预测模型（已尝试自动运行）',
            refs.prediction_table ? `已引用预测分析表 #${refs.prediction_id}` : '未找到同期预测分析表',
          ].join(' · ')
          setMessage(`已生成：${res.title}（${formatReportPeriodLabel(task.params!)}）\n${refNote}`)
          await refresh()
          await openReport(res.id)
        })
        .catch(() => {})
      return
    }

    if (task.status === 'success' && task.result?.id) {
      refresh()
        .then(() => openReport(task.result!.id))
        .catch(() => {})
    }
  }, [])

  useEffect(() => {
    if (task.message) setMessage(task.message)
  }, [task.message])

  useEffect(() => {
    if (task.status === 'success' && task.result?.id && selectedId !== task.result.id) {
      refresh()
        .then(() => openReport(task.result!.id))
        .catch(() => {})
    }
  }, [task.status, task.result?.id])

  async function handleGenerate() {
    try {
      const tablesStatus = await getReportTables(reportParams.review_year, reportParams.review_month)
      const missing = (tablesStatus.missing_tables as string[]) || []
      if (missing.length > 0) {
        const note = formatMissingTablesNote(missing)
        if (!window.confirm(`${note.replace('\n', '')}\n\n仍要继续生成吗？`)) return
      }
    } catch {
      // 预检失败不阻断生成
    }

    setMessage(`正在生成《国际油价月报》${formatReportPeriodLabel(reportParams)}…`)
    try {
      const result = await startReportGenerate(reportParams)
      const refs = result.references || {}
      const refNote = [
        refs.forecast_model ? '已引用预测模型' : '未找到预测模型（已尝试自动运行）',
        refs.prediction_table ? `已引用预测分析表 #${refs.prediction_id}` : '未找到同期预测分析表',
      ].join(' · ')
      const snap = (result.table_snapshots || {}) as { missing_tables?: string[] }
      const missingNote = formatMissingTablesNote(snap.missing_tables || [])
      setMessage(`已生成：${result.title}（${formatReportPeriodLabel(reportParams)}）\n${refNote}${missingNote}`)
      await refresh()
      await openReport(result.id)
    } catch {
      // 错误信息由全局 task 状态同步到 message
    }
  }

  async function openReport(id: number) {
    const d = await getReport(id)
    setSelectedId(id)
    setDetail(d)
    setContent(d.content)
    setSearchParams({ id: String(id) })
  }

  async function handleDelete(id: number, e: React.MouseEvent) {
    e.stopPropagation()
    if (!window.confirm('确定删除该报告？')) return
    await deleteReport(id)
    if (selectedId === id) {
      setSelectedId(null)
      setContent(null)
      setDetail(null)
      setSearchParams({})
    }
    setMessage('报告已删除')
    await refresh()
  }

  async function saveReport() {
    if (!selectedId || !content) return
    await updateReport(selectedId, content as unknown as Record<string, unknown>)
    setMessage('报告已保存（人工校准已记录）')
    await refresh()
  }

  async function downloadExport(format: 'docx' | 'pdf' | 'tex') {
    if (!selectedId) return
    await saveReport()
    const ext = format === 'tex' ? 'tex' : format
    const blob = await exportReport(selectedId, format)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${detail?.title || 'report'}.${ext}`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleExportWord() {
    try {
      await downloadExport('docx')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '导出失败'
      setMessage(`Word 导出失败：${msg}`)
    }
  }

  async function handleExportPdf() {
    try {
      await downloadExport('pdf')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '导出失败'
      setMessage(`PDF 导出失败：${msg}（需安装 xelatex）`)
    }
  }

  async function handleRevise(sectionId: string) {
    if (!selectedId || !content) return
    setRevising(sectionId)
    try {
      const result = await reviseSection(selectedId, sectionId, getReviseText(sectionId))
      if (sectionId === 'summary') {
        setContent({ ...content, summary: result.content })
      } else {
        setContent({
          ...content,
          sections: content.sections.map((s) =>
            s.id === sectionId ? { ...s, content: result.content } : s,
          ),
        })
      }
      setMessage('Agent 已修订该章节')
    } finally {
      setRevising(null)
    }
  }

  function updateSection(id: string, patch: Partial<Section>) {
    if (!content) return
    setContent({
      ...content,
      sections: content.sections.map((s) => (s.id === id ? { ...s, ...patch } : s)),
    })
  }

  function updateTableCell(key: string, r: number, c: number, value: string) {
    if (!content) return
    const tbl = content.tables[key]
    const rows = tbl.rows.map((row, ri) =>
      ri === r ? row.map((cell, ci) => (ci === c ? value : cell)) : row,
    )
    setContent({ ...content, tables: { ...content.tables, [key]: { ...tbl, rows } } })
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">报告中心</h1>
        <p className="text-sm text-white/60">
          采集权威数据 · 引用预测模型与预测分析表 · DeepSeek 撰写 · 导出 Word / PDF
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-[300px_1fr]">
        <div className="space-y-4">
          <div className="glass space-y-3 rounded-2xl p-4">
            <h2 className="text-sm font-medium text-white/70">生成月报初稿</h2>
            <div>
              <label className="mb-1 block text-xs text-white/50">本期月份（展望月）</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  value={outlookYear}
                  onChange={(e) => setOutlookYear(Number(e.target.value))}
                  className="w-1/2 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm outline-none"
                />
                <select
                  value={outlookMonth}
                  onChange={(e) => setOutlookMonth(Number(e.target.value))}
                  className="w-1/2 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm outline-none"
                >
                  {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                    <option key={m} value={m}>
                      {m} 月
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="rounded-xl bg-white/5 p-3 text-xs leading-relaxed text-white/70">
              <div className="font-medium text-white/90">
                {formatReportPeriodLabel(reportParams)}
              </div>
              <div className="mt-1">期号：{reportParams.issue_no}</div>
              <div>回顾：{reportParams.review_year}年{reportParams.review_month}月</div>
              <div>展望：{reportParams.outlook_year}年{reportParams.outlook_month}月</div>
            </div>
            {unrestrictedMode ? null : (
              <p className="text-xs text-white/50">
                生成时将自动引用
                <Link to="/forecast" className="mx-0.5 text-brand-blue underline">预测模型</Link>
                情景结果；若存在同期
                <Link to="/prediction" className="mx-0.5 text-brand-blue underline">预测分析表</Link>
                将一并纳入第三章展望。
              </p>
            )}
            <ModeSelect module="report" compact />
            {loading && task.stepLabel && (
              <p className="text-xs text-white/50">
                第 {task.step}/{task.totalSteps} 步：{task.stepLabel}
              </p>
            )}
            <button
              type="button"
              onClick={handleGenerate}
              disabled={loading}
              className="w-full rounded-xl bg-brand-red px-4 py-2 text-sm disabled:opacity-50"
            >
              {loading ? '生成中…' : `生成 ${reportParams.outlook_year}年${reportParams.outlook_month}月 月报`}
            </button>
            {message && (
              <div className="whitespace-pre-wrap rounded-xl bg-black/30 p-3 text-xs text-white/70">
                {message}
              </div>
            )}
          </div>

          <div className="glass rounded-2xl p-4">
            <h2 className="mb-3 text-sm font-medium text-white/70">报告列表</h2>
            <div className="space-y-2">
              {reports.map((r) => (
                <div
                  key={r.id}
                  className={`flex items-start gap-1 rounded-xl ${
                    selectedId === r.id ? 'bg-brand-blue/40' : 'bg-white/5 hover:bg-white/10'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => openReport(r.id)}
                    className="min-w-0 flex-1 px-3 py-2 text-left text-sm"
                  >
                    <div className="truncate">{r.title}</div>
                    <div className="text-xs text-white/50">
                      {r.issue_no || r.report_date} · {r.status}
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={(e) => handleDelete(r.id, e)}
                    className="shrink-0 px-2 py-2 text-xs text-red-400 hover:text-red-300"
                  >
                    删除
                  </button>
                </div>
              ))}
              {reports.length === 0 && <div className="text-sm text-white/50">暂无报告</div>}
            </div>
          </div>
        </div>

        <div className="glass rounded-2xl p-5">
          {content ? (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-medium text-white/90">{detail?.title}</div>
                  {(detail?.outlook_year || detail?.review_year) && (
                    <div className="text-xs text-white/50">
                      {detail.outlook_year && detail.outlook_month
                        ? `展望 ${detail.outlook_year}年${detail.outlook_month}月`
                        : ''}
                      {detail.review_year && detail.review_month
                        ? ` · 回顾 ${detail.review_year}年${detail.review_month}月`
                        : ''}
                    </div>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={saveReport} className="rounded-xl bg-brand-blue px-4 py-2 text-sm">
                    保存校准
                  </button>
                  <button type="button" onClick={handleExportWord} className="rounded-xl bg-white/10 px-4 py-2 text-sm">
                    导出 Word
                  </button>
                  <button
                    type="button"
                    onClick={handleExportPdf}
                    disabled={exportTools !== null && !exportTools.xelatex}
                    title={
                      exportTools && !exportTools.xelatex
                        ? '服务器未安装 xelatex，无法导出 PDF'
                        : '通过 LaTeX 排版导出 PDF'
                    }
                    className="rounded-xl bg-white/10 px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    导出 PDF
                  </button>
                </div>
              </div>

              {message && (
                <div className="whitespace-pre-wrap rounded-xl bg-black/30 p-3 text-sm text-white/80">
                  {message}
                </div>
              )}

              <div>
                <h3 className="mb-2 text-sm font-medium text-white/70">内容摘要</h3>
                <textarea
                  value={content.summary}
                  onChange={(e) => setContent({ ...content, summary: e.target.value })}
                  className="min-h-[100px] w-full rounded-xl border border-white/10 bg-black/20 p-3 text-sm outline-none"
                />
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <input
                    value={getReviseText('summary')}
                    onChange={(e) => setReviseText('summary', e.target.value)}
                    className="min-w-[200px] flex-1 rounded-lg border border-white/10 bg-black/20 px-3 py-1.5 text-xs outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => handleRevise('summary')}
                    disabled={revising === 'summary'}
                    className="rounded-lg bg-white/10 px-3 py-1.5 text-xs disabled:opacity-50"
                  >
                    {revising === 'summary' ? '修订中…' : 'Agent 修订'}
                  </button>
                </div>
              </div>

              {content.sections.map((sec) => (
                <div key={sec.id} className="space-y-2 border-t border-white/10 pt-4">
                  <h3 className="text-sm font-medium">{sec.title}</h3>
                  {sec.level === 2 && (
                    <>
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="text-white/50">致信水平</span>
                        <span
                          className={`inline-flex rounded-md px-2 py-0.5 ${
                            confidenceBadge[sec.confidence_level || '模型推断'] ||
                            'bg-white/10 text-white/60'
                          }`}
                        >
                          {sec.confidence_level || '模型推断'}
                        </span>
                        {sec.confidence_level === '权威数据' && sec.source_url ? (
                          <a
                            href={sec.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="break-words text-cyan-300/90 hover:text-cyan-200 hover:underline"
                          >
                            {sec.source_title || sec.source_url}
                          </a>
                        ) : null}
                      </div>
                      <textarea
                        value={sec.content || ''}
                        onChange={(e) => updateSection(sec.id, { content: e.target.value })}
                        className="min-h-[120px] w-full rounded-xl border border-white/10 bg-black/20 p-3 text-sm outline-none"
                      />
                      {TABLE_ANCHOR[sec.id] && content.tables[TABLE_ANCHOR[sec.id]] && (
                        <div className="overflow-x-auto rounded-xl bg-white/5 p-3">
                          <div className="mb-2 text-xs font-medium">
                            {content.tables[TABLE_ANCHOR[sec.id]].title}
                          </div>
                          <table className="min-w-full text-xs">
                            <thead>
                              <tr>
                                {content.tables[TABLE_ANCHOR[sec.id]].headers.map((h) => (
                                  <th key={h} className="px-2 py-1 text-left text-white/60">
                                    {h}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {content.tables[TABLE_ANCHOR[sec.id]].rows.map((row, ri) => (
                                <tr key={ri} className="border-t border-white/5">
                                  {row.map((cell, ci) => (
                                    <td key={ci} className="px-2 py-1">
                                      <input
                                        value={cell}
                                        onChange={(e) =>
                                          updateTableCell(TABLE_ANCHOR[sec.id], ri, ci, e.target.value)
                                        }
                                        className="w-full bg-transparent outline-none"
                                      />
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                      {selectedId &&
                        chartsForSection(sec.id).map((chart) => (
                          <div key={chart.id} className="rounded-xl bg-white/5 p-3">
                            <ReportChartImage
                              reportId={selectedId}
                              chartId={chart.id}
                              title={chart.title}
                              className="mx-auto max-h-64 w-full max-w-2xl rounded-lg object-contain"
                            />
                            <div className="mt-2 text-center text-xs font-medium text-white/80">
                              {chart.title}
                            </div>
                          </div>
                        ))}
                      <div className="flex flex-wrap items-center gap-2">
                        <input
                          value={getReviseText(sec.id)}
                          onChange={(e) => setReviseText(sec.id, e.target.value)}
                          className="min-w-[200px] flex-1 rounded-lg border border-white/10 bg-black/20 px-3 py-1.5 text-xs outline-none"
                        />
                        <button
                          type="button"
                          onClick={() => handleRevise(sec.id)}
                          disabled={revising === sec.id}
                          className="rounded-lg bg-white/10 px-3 py-1.5 text-xs disabled:opacity-50"
                        >
                          {revising === sec.id ? '修订中…' : 'Agent 修订'}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ))}

              {detail?.web_references?.length > 0 && (
                <div className="rounded-xl border border-cyan-400/20 bg-cyan-500/5 p-4 text-xs text-white/60">
                  <div className="mb-2 flex items-center gap-2 font-medium text-white/70">
                    <span className="rounded bg-cyan-500/20 px-1.5 py-0.5 text-[10px] text-cyan-200">
                      联网查询
                    </span>
                    实时检索来源（共 {detail.web_references.length} 条，供时效性参考）
                  </div>
                  <ol className="list-decimal space-y-1 pl-5">
                    {detail.web_references.map((s: any, i: number) => (
                      <li key={`${s.url}-${i}`}>
                        <a
                          href={s.url}
                          target="_blank"
                          rel="noreferrer"
                          className="break-words text-cyan-300/90 hover:text-cyan-200 hover:underline"
                        >
                          {s.title || s.url}
                        </a>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          ) : (
            <div className="py-16 text-center text-sm text-white/50">
              在左侧选择月份并生成月报，或从列表打开已有报告
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
