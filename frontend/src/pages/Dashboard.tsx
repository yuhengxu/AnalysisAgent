import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { generatePrediction, getChart, getDashboard } from '../api/client'
import { getDefaultPredictionParams, getDefaultReportParams } from '../constants/agentDefaults'
import ChartPanel from '../components/ChartPanel'
import { startReportGenerate } from '../lib/reportGenerateTask'

function formatDateLabel(iso?: string) {
  if (!iso) return '暂无数据'
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  if (!y || !m || !d) return iso
  return `${m}月${d}日`
}

type ChartRangePreset = '1m' | '3m' | '6m' | 'ytd' | '1y' | 'all' | 'custom'

const RANGE_OPTIONS: { id: ChartRangePreset; label: string }[] = [
  { id: '1m', label: '近1月' },
  { id: '3m', label: '近3月' },
  { id: '6m', label: '近6月' },
  { id: 'ytd', label: '今年以来' },
  { id: '1y', label: '近1年' },
  { id: 'all', label: '全部' },
  { id: 'custom', label: '自定义' },
]

function parseIsoDate(iso: string) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d)
}

function toIsoDate(d: Date) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function shiftMonths(d: Date, months: number) {
  const next = new Date(d)
  next.setMonth(next.getMonth() - months)
  return next
}

function computeChartRange(
  preset: ChartRangePreset,
  latestDate?: string,
  earliestDate?: string,
  customStart?: string,
  customEnd?: string,
): { start_date?: string; end_date?: string } {
  if (!latestDate) return {}
  const end = parseIsoDate(latestDate)
  const earliest = earliestDate ? parseIsoDate(earliestDate) : null

  if (preset === 'custom') {
    return {
      start_date: customStart || earliestDate || toIsoDate(end),
      end_date: customEnd || latestDate,
    }
  }

  let start: Date
  switch (preset) {
    case '1m':
      start = shiftMonths(end, 1)
      break
    case '3m':
      start = shiftMonths(end, 3)
      break
    case '6m':
      start = shiftMonths(end, 6)
      break
    case 'ytd':
      start = new Date(end.getFullYear(), 0, 1)
      break
    case '1y':
      start = shiftMonths(end, 12)
      break
    case 'all':
      start = earliest || shiftMonths(end, 12)
      break
    default:
      start = shiftMonths(end, 3)
  }

  if (earliest && start < earliest) start = earliest
  return { start_date: toIsoDate(start), end_date: toIsoDate(end) }
}

const QUICK_TASKS = [
  { label: '生成预测分析表', desc: '采集权威数据生成油价预测表', action: 'predict_table' as const },
  { label: '生成本月油价月报', desc: '自动生成月报初稿并打开报告中心', action: 'report' as const },
  { label: '分析 Brent 走势', desc: '跳转智能分析，预填 Brent 分析任务', action: 'analyze' as const },
  { label: '比较机构预测', desc: '查看机构供需预测对比图表', action: 'balance' as const },
]

export default function Dashboard() {
  const navigate = useNavigate()
  const [summary, setSummary] = useState<any>(null)
  const [priceMeta, setPriceMeta] = useState<{ latest_date?: string; earliest_date?: string } | null>(null)
  const [priceChart, setPriceChart] = useState<any>(null)
  const [spreadChart, setSpreadChart] = useState<any>(null)
  const [taskLoading, setTaskLoading] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [rangePreset, setRangePreset] = useState<ChartRangePreset>('3m')
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')
  const [metaLoaded, setMetaLoaded] = useState(false)

  const latestDate = priceMeta?.latest_date
  const earliestDate = priceMeta?.earliest_date

  const chartRange = useMemo(
    () => computeChartRange(rangePreset, latestDate, earliestDate, customStart, customEnd),
    [rangePreset, latestDate, earliestDate, customStart, customEnd],
  )

  const loadAll = useCallback(async (range: { start_date?: string; end_date?: string }) => {
    if (!range.start_date || !range.end_date) return
    setLoading(true)
    try {
      const params = { daily_only: 'true', start_date: range.start_date, end_date: range.end_date }
      const [dash, price, spread] = await Promise.all([
        getDashboard({ start_date: range.start_date, end_date: range.end_date }),
        getChart('price_trend', params),
        getChart('spread', params),
      ])
      setSummary(dash)
      setPriceChart(price)
      setSpreadChart(spread)
      setMetaLoaded(true)
    } catch {
      setPriceChart(null)
      setSpreadChart(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    getDashboard()
      .then((dash) => {
        setPriceMeta(dash?.price_meta ?? null)
        const latest = dash?.price_meta?.latest_date as string | undefined
        const earliest = dash?.price_meta?.earliest_date as string | undefined
        if (latest) setCustomEnd(latest)
        if (earliest) setCustomStart(earliest)
      })
      .catch(() => null)
      .finally(() => setMetaLoaded(true))
  }, [])

  useEffect(() => {
    if (!metaLoaded || !chartRange.start_date || !chartRange.end_date) return
    loadAll(chartRange)
  }, [metaLoaded, chartRange, loadAll])

  async function handleQuickTask(action: (typeof QUICK_TASKS)[number]['action'], label: string) {
    setTaskLoading(label)
    try {
      if (action === 'predict_table') {
        const pred = await generatePrediction(getDefaultPredictionParams())
        navigate(`/prediction?id=${pred.id}`)
        return
      }
      if (action === 'report') {
        startReportGenerate(getDefaultReportParams()).catch(() => {})
        navigate('/reports')
        return
      }
      if (action === 'analyze') {
        navigate('/analysis')
        return
      }
      if (action === 'balance') {
        navigate('/analysis?view=balance')
        return
      }
      navigate('/data')
    } finally {
      setTaskLoading(null)
    }
  }

  const symbols = summary?.symbols || {}
  const activeRange = summary?.range || chartRange

  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-2xl font-semibold">专家工作台</h1>
        <p className="mt-1 text-sm text-white/60">国际油价、供需平衡、预测与报告一体化分析</p>
      </section>

      <section className="glass space-y-3 rounded-2xl p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-medium">时间范围</div>
          {latestDate && (
            <div className="text-xs text-white/40">
              数据库最新 {formatDateLabel(latestDate)}
              {activeRange.start_date && activeRange.end_date && (
                <> · 当前 {activeRange.start_date} ~ {activeRange.end_date}</>
              )}
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {RANGE_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => setRangePreset(opt.id)}
              className={`rounded-full px-3 py-1 text-xs ${
                rangePreset === opt.id ? 'bg-brand-blue text-white' : 'bg-white/5 hover:bg-white/10'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        {rangePreset === 'custom' && (
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-white/60">
              起始
              <input
                type="date"
                value={customStart}
                min={earliestDate}
                max={customEnd || latestDate}
                onChange={(e) => setCustomStart(e.target.value)}
                className="ml-2 rounded-lg border border-white/10 bg-black/20 px-2 py-1 text-sm text-white"
              />
            </label>
            <label className="text-xs text-white/60">
              结束
              <input
                type="date"
                value={customEnd}
                min={customStart || earliestDate}
                max={latestDate}
                onChange={(e) => setCustomEnd(e.target.value)}
                className="ml-2 rounded-lg border border-white/10 bg-black/20 px-2 py-1 text-sm text-white"
              />
            </label>
          </div>
        )}
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {['Brent', 'WTI', 'Dubai', 'Oman'].map((sym) => (
          <div key={sym} className="glass card-hover rounded-2xl p-4">
            <div className="text-sm text-white/60">{sym}</div>
            <div className="mt-2 text-2xl font-semibold text-brand-red">
              {loading ? '…' : (symbols[sym]?.period_avg ?? '--')}
            </div>
            <div className="mt-1 text-xs text-white/50">
              区间均价
              {!loading && symbols[sym]?.latest_price != null && (
                <> · 期末 {symbols[sym].latest_price}</>
              )}
            </div>
            <div className="mt-0.5 text-xs text-white/40">
              {loading
                ? '加载中…'
                : symbols[sym]?.latest_date
                  ? `截至 ${formatDateLabel(symbols[sym].latest_date)}`
                  : '区间内无数据'}
            </div>
          </div>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        {loading ? (
          <div className="glass col-span-full rounded-2xl p-8 text-center text-sm text-white/50">
            图表加载中…
          </div>
        ) : (
          <>
            {priceChart && <ChartPanel config={priceChart} />}
            {spreadChart && <ChartPanel config={spreadChart} />}
          </>
        )}
      </section>

      <section className="glass rounded-2xl p-5">
        <h2 className="mb-3 text-lg font-medium">快捷任务</h2>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {QUICK_TASKS.map((task) => (
            <button
              key={task.label}
              type="button"
              onClick={() => handleQuickTask(task.action, task.label)}
              disabled={taskLoading === task.label}
              className="rounded-xl border border-white/10 bg-white/5 p-4 text-left text-sm transition hover:border-brand-red/40 hover:bg-white/10 disabled:opacity-50"
            >
              <div className="font-medium">{task.label}</div>
              <div className="mt-1 text-xs text-white/50">
                {taskLoading === task.label ? '执行中...' : task.desc}
              </div>
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}
