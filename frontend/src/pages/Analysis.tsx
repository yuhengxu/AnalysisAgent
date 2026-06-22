import { useState } from 'react'
import { Link } from 'react-router-dom'
import { queryAnalysis, runAnalysis } from '../api/client'
import ChartPanel from '../components/ChartPanel'
import DataFilterPanel from '../components/DataFilterPanel'
import DataResultTable from '../components/DataResultTable'
import ModeSelect from '../components/ModeSelect'
import { useDataFilters } from '../hooks/useDataFilters'
import { ANALYSIS_EVIDENCE_PROMPT } from '../constants/agentDefaults'

const PRESETS = [
  {
    label: '价格走势',
    patch: { category: 'price' as const, symbols: ['Brent', 'WTI'] },
    question: '解读 evidence 中各品种月度均价、环比与同比变化',
  },
  {
    label: '机构供需',
    patch: { category: 'balance' as const, agencies: ['IEA', 'EIA'] },
    question: '对比 evidence 中 IEA、EIA 各周期供/需数值差异及含义',
  },
  {
    label: '价差解读',
    patch: { category: 'price' as const, symbols: ['Brent', 'WTI'] },
    question: '基于 evidence 日度序列，解读 Brent 与 WTI 价差在所选时间范围内的变化',
  },
]

export default function Analysis() {
  const { params, setParams, catalog, monthOptions } = useDataFilters({ category: 'mixed' })
  const [question, setQuestion] = useState(ANALYSIS_EVIDENCE_PROMPT)
  const [queryResult, setQueryResult] = useState<any>(null)
  const [runResult, setRunResult] = useState<any>(null)
  const [queryLoading, setQueryLoading] = useState(false)
  const [runLoading, setRunLoading] = useState(false)
  const [analysisStale, setAnalysisStale] = useState(false)

  async function handleQuery() {
    setQueryLoading(true)
    setAnalysisStale(true)
    try {
      setQueryResult(await queryAnalysis(params))
    } finally {
      setQueryLoading(false)
    }
  }

  async function handleRun() {
    setRunLoading(true)
    try {
      setRunResult(await runAnalysis({ ...params, question }))
      setAnalysisStale(false)
    } finally {
      setRunLoading(false)
    }
  }

  const charts = queryResult?.charts || runResult?.charts || []
  const tableData = queryResult?.data || runResult?.data
  const hasData = Boolean(queryResult || runResult)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">智能分析</h1>
        <p className="text-sm text-white/60">
          左侧查数与图表，右侧提问与解读。筛选器与数据中心完全一致。
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            onClick={() => {
              setParams(p.patch)
              setQuestion(p.question)
              setAnalysisStale(true)
            }}
            className="rounded-full bg-white/5 px-4 py-1 text-sm hover:bg-white/10"
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-2 xl:items-start">
        {/* 左侧：数据查询 + 结果 */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-medium">数据查询</h2>
            <span className="text-xs text-white/40">筛选 · 表格 · 图表</span>
          </div>

          <DataFilterPanel
            params={params}
            catalog={catalog}
            monthOptions={monthOptions}
            onChange={(patch) => {
              setParams(patch)
              setAnalysisStale(true)
            }}
            showMixed
          />

          <button
            type="button"
            onClick={handleQuery}
            disabled={queryLoading}
            className="rounded-xl bg-brand-blue px-5 py-2 text-sm font-medium disabled:opacity-50"
          >
            {queryLoading ? '查询中…' : '查询数据'}
          </button>

          {hasData ? (
            <div className="space-y-4">
              {charts.length > 0 && (
                <div className="glass space-y-4 rounded-2xl p-5">
                  <h3 className="text-sm font-medium text-white/80">图表</h3>
                  <div className="space-y-4">
                    {charts.map((chart: any, idx: number) => (
                      <ChartPanel key={idx} config={chart} height={260} />
                    ))}
                  </div>
                </div>
              )}

              <div className="glass space-y-4 rounded-2xl p-5">
                <h3 className="text-sm font-medium text-white/80">数据结果</h3>
                <DataResultTable result={tableData} />
              </div>
            </div>
          ) : (
            <div className="glass relative z-0 rounded-2xl p-5 text-sm text-white/60">
              <p>
                设置筛选条件后点击「查询数据」。导入数据请前往
                <Link to="/data" className="mx-1 text-brand-blue underline">
                  数据中心
                </Link>
                。
              </p>
            </div>
          )}
        </div>

        {/* 右侧：研究提问 + 解读结果 */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-medium">智能解读</h2>
            <span className="text-xs text-white/40">基于左侧数据</span>
          </div>

          <div className="glass space-y-4 rounded-2xl p-5">
            <label className="block text-sm text-white/70">研究问题</label>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              className="min-h-[140px] w-full rounded-xl border border-white/10 bg-black/20 p-4 text-sm outline-none"
              placeholder="请围绕左侧已查询的数据库结果提问，避免使用「近期」「最新」等未在筛选条件中定义的时间表述…"
            />
            <div className="flex flex-wrap items-end gap-4">
              <ModeSelect module="analysis" className="min-w-[200px]" />
              <button
                type="button"
                onClick={handleRun}
                disabled={runLoading}
                className="rounded-xl bg-brand-red px-5 py-2 text-sm font-medium disabled:opacity-50"
              >
                {runLoading ? '分析中…' : '查询并解读'}
              </button>
            </div>
            {!queryResult && (
              <p className="text-xs text-white/40">建议先在左侧查询数据，再发起解读。</p>
            )}
          </div>

          <div
            className={`glass rounded-2xl p-5 transition-opacity ${
              analysisStale && runResult ? 'opacity-40' : 'opacity-100'
            }`}
          >
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-medium text-white/80">分析结论</h3>
              {analysisStale && runResult && (
                <span className="text-xs text-amber-300/80">数据已更新，请重新解读</span>
              )}
            </div>

            {runLoading ? (
              <p className="text-sm text-white/50">正在生成解读…</p>
            ) : runResult?.response ? (
              <>
                <pre className="whitespace-pre-wrap text-sm text-white/90">{runResult.response}</pre>
                <div className="mt-3 text-xs text-white/50">
                  工具：{runResult.tools_called?.join(' · ')}
                  {runResult.duration_ms ? ` · 耗时 ${Math.round(runResult.duration_ms)} ms` : ''}
                </div>
              </>
            ) : (
              <p className="text-sm text-white/50">
                填写研究问题后点击「查询并解读」，结论将显示在此处。
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
