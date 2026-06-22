import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  deletePrediction,
  exportPrediction,
  getPrediction,
  listPredictions,
  revisePredictionFactor,
  updatePrediction,
} from '../api/client'
import ModeSelect from '../components/ModeSelect'
import {
  formatLlmLabel,
  getDefaultPredictionParams,
  getUnrestrictedMode,
} from '../constants/agentDefaults'
import { usePredictionTask } from '../hooks/usePredictionTask'
import { startPredictionGenerate } from '../lib/predictionGenerateTask'

interface Factor {
  category: string
  category_title: string
  id: string
  name: string
  importance: number
  judgment: string
  impact: string
  confidence_level?: string
  source_url?: string
  source_title?: string
}

const confidenceBadge: Record<string, string> = {
  权威数据: 'bg-cyan-500/15 text-cyan-300',
  模型推断: 'bg-amber-500/15 text-amber-300',
}

interface PriceBlock {
  label?: string
  range_low: number | null
  range_high: number | null
  avg: number | null
}

interface PredictionContent {
  factors: Factor[]
  price_forecast: { current_month: PriceBlock; next_month: PriceBlock }
}

const IMPACT_OPTIONS = ['促涨', '持平', '促跌']
const impactColor: Record<string, string> = {
  促涨: 'text-red-300',
  持平: 'text-white/60',
  促跌: 'text-green-300',
}

export default function Prediction() {
  const [searchParams, setSearchParams] = useSearchParams()
  const task = usePredictionTask()
  const resumedRef = useRef(false)
  const [list, setList] = useState<any[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<any>(null)
  const [content, setContent] = useState<PredictionContent | null>(null)
  const [message, setMessage] = useState('')
  const params = getDefaultPredictionParams()
  const [year, setYear] = useState(params.year)
  const [month, setMonth] = useState(params.month)
  const [instruction, setInstruction] = useState('')
  const [unrestrictedMode, setUnrestrictedMode] = useState(getUnrestrictedMode())
  const [reviseOpinions, setReviseOpinions] = useState<Record<string, string>>({})
  const [revising, setRevising] = useState<string | null>(null)

  const loading = task.status === 'running'

  async function refresh() {
    setList(await listPredictions())
  }

  useEffect(() => {
    refresh().catch(() => setList([]))
  }, [])

  useEffect(() => {
    const onChange = () => setUnrestrictedMode(getUnrestrictedMode())
    window.addEventListener('unrestricted-mode-change', onChange)
    return () => window.removeEventListener('unrestricted-mode-change', onChange)
  }, [])

  useEffect(() => {
    const idParam = searchParams.get('id')
    if (idParam && !Number.isNaN(Number(idParam))) open(Number(idParam))
  }, [searchParams])

  // 页面重新进入时，接续进行中的生成任务或展示已完成结果
  useEffect(() => {
    if (resumedRef.current) return
    resumedRef.current = true

    if (task.status === 'idle') return

    if (task.params) {
      setYear(task.params.year)
      setMonth(task.params.month)
      setInstruction(task.params.extra_instruction || '')
    }
    setMessage(task.message)

    if (task.status === 'running' && task.params) {
      startPredictionGenerate(task.params)
        .then(async (res) => {
          await refresh()
          await open(res.id)
        })
        .catch(() => {})
      return
    }

    if (task.status === 'success' && task.result?.id) {
      refresh()
        .then(() => open(task.result!.id))
        .catch(() => {})
    }
  }, [])

  useEffect(() => {
    if (task.message) setMessage(task.message)
  }, [task.message])

  useEffect(() => {
    if (task.status === 'success' && task.result?.id && selectedId !== task.result.id) {
      refresh()
        .then(() => open(task.result!.id))
        .catch(() => {})
    }
  }, [task.status, task.result?.id])

  async function open(id: number) {
    const d = await getPrediction(id)
    setSelectedId(id)
    setDetail(d)
    setContent(d.content)
    setSearchParams({ id: String(id) })
  }

  async function handleGenerate() {
    const genParams = { year, month, extra_instruction: instruction }
    setMessage('正在采集权威数据并调用大模型生成预测分析表…')
    try {
      const res = await startPredictionGenerate(genParams)
      await refresh()
      await open(res.id)
    } catch {
      // 错误信息由全局 task 状态同步到 message
    }
  }

  function updateFactor(idx: number, patch: Partial<Factor>) {
    if (!content) return
    const factors = content.factors.map((f, i) => (i === idx ? { ...f, ...patch } : f))
    setContent({ ...content, factors })
  }

  function updatePrice(block: 'current_month' | 'next_month', patch: Partial<PriceBlock>) {
    if (!content) return
    setContent({
      ...content,
      price_forecast: {
        ...content.price_forecast,
        [block]: { ...content.price_forecast[block], ...patch },
      },
    })
  }

  /** 保存时剔除专家修改意见；意见仅存于前端状态，不写入数据库、不导出 Excel。 */
  function contentForSave(): Record<string, unknown> | null {
    if (!content) return null
    const payload = JSON.parse(JSON.stringify(content)) as PredictionContent
    for (const factor of payload.factors) {
      const extra = factor as Factor & Record<string, unknown>
      delete extra.revise_opinions
      delete extra.expert_opinion
      delete extra.expert_opinions
      delete extra.importance_opinion
      delete extra.judgment_opinion
      delete extra.impact_opinion
    }
    return payload as unknown as Record<string, unknown>
  }

  async function save() {
    if (!selectedId || !content) return
    const payload = contentForSave()
    if (!payload) return
    await updatePrediction(selectedId, payload)
    setMessage('预测分析表已保存（人工校准已记录）')
    await refresh()
  }

  function setReviseOpinion(key: string, value: string) {
    setReviseOpinions((prev) => ({ ...prev, [key]: value }))
  }

  async function handleReviseFactor(idx: number) {
    if (!selectedId || !content) return
    const key = `${idx}-judgment`
    const opinion = (reviseOpinions[key] || '').trim()
    if (!opinion) {
      setMessage('请先填写修改意见')
      return
    }
    setRevising(key)
    try {
      const result = await revisePredictionFactor(selectedId, idx, 'judgment', opinion)
      const factors = content.factors.map((f, i) =>
        i === idx ? { ...f, judgment: String(result.value) } : f,
      )
      setContent({ ...content, factors })
      setReviseOpinions((prev) => ({ ...prev, [key]: '' }))
      setMessage('大模型已根据专家意见完成修改')
    } catch {
      setMessage('修改失败，请确认后端已启动后重试')
    } finally {
      setRevising(null)
    }
  }

  async function handleExport() {
    if (!selectedId) return
    await save()
    const blob = await exportPrediction(selectedId)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${detail?.title || 'prediction'}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleDelete(id: number, e: React.MouseEvent) {
    e.stopPropagation()
    if (!window.confirm('确定删除该预测分析表？')) return
    await deletePrediction(id)
    if (selectedId === id) {
      setSelectedId(null)
      setContent(null)
      setDetail(null)
      setSearchParams({})
    }
    await refresh()
  }

  const groups = content
    ? Array.from(new Set(content.factors.map((f) => f.category_title)))
    : []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">预测分析表</h1>
          <p className="text-sm text-white/60">
            采集权威数据 · 大模型逐项研判 · 人工校准 · 导出 Excel
          </p>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[300px_1fr]">
        {/* 左侧：生成表单 + 列表 */}
        <div className="space-y-4">
          <div className="glass space-y-3 rounded-2xl p-4">
            <h2 className="text-sm font-medium text-white/70">生成新预测表</h2>
            <div className="flex gap-2">
              <input
                type="number"
                value={year}
                onChange={(e) => setYear(Number(e.target.value))}
                className="w-1/2 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm outline-none"
                placeholder="年"
              />
              <select
                value={month}
                onChange={(e) => setMonth(Number(e.target.value))}
                className="w-1/2 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm outline-none"
              >
                {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                  <option key={m} value={m}>
                    {m} 月
                  </option>
                ))}
              </select>
            </div>
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="可补充重点关注的因素或情景假设（可选）"
              className="h-16 w-full resize-none rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm outline-none"
            />
            <ModeSelect module="prediction" compact />
            {unrestrictedMode && (
              <p className="text-xs text-amber-300/80">
                无限制模式已开启：将基于 yuebao/prediction 上一期样例，由深度研究模型仿写生成。
              </p>
            )}
            <button
              onClick={handleGenerate}
              disabled={loading}
              className="w-full rounded-xl bg-brand-red px-4 py-2 text-sm disabled:opacity-50"
            >
              {loading ? '生成中…' : '生成预测分析表'}
            </button>
          </div>

          <div className="glass rounded-2xl p-4">
            <h2 className="mb-3 text-sm font-medium text-white/70">历史记录</h2>
            <div className="space-y-2">
              {list.map((p) => (
                <div
                  key={p.id}
                  className={`flex items-start gap-1 rounded-xl ${
                    selectedId === p.id ? 'bg-brand-blue/40' : 'bg-white/5 hover:bg-white/10'
                  }`}
                >
                  <button
                    onClick={() => open(p.id)}
                    className="min-w-0 flex-1 px-3 py-2 text-left text-sm"
                  >
                    <div className="truncate">{p.title}</div>
                    <div className="text-xs text-white/50">
                      {formatLlmLabel(p.llm_used, p.model_name)} · {p.status}
                    </div>
                  </button>
                  <button
                    onClick={(e) => handleDelete(p.id, e)}
                    className="shrink-0 px-2 py-2 text-xs text-red-400 hover:text-red-300"
                  >
                    删除
                  </button>
                </div>
              ))}
              {list.length === 0 && <div className="text-sm text-white/50">暂无记录</div>}
            </div>
          </div>
        </div>

        {/* 右侧：编辑器 */}
        <div className="glass rounded-2xl p-5">
          {content ? (
            <>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm text-white/70">
                  {detail?.title}
                  {detail?.llm_used && (
                    <span className="ml-2 text-xs text-white/40">
                      · {formatLlmLabel(detail.llm_used, detail.model_name)}
                    </span>
                  )}
                </div>
                <div className="flex gap-2">
                  <button onClick={save} className="rounded-xl bg-brand-blue px-4 py-2 text-sm">
                    保存校准
                  </button>
                  <button
                    onClick={handleExport}
                    className="rounded-xl bg-white/10 px-4 py-2 text-sm"
                  >
                    导出 Excel
                  </button>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full table-fixed border-collapse text-sm">
                  <thead>
                    <tr className="bg-white/10 text-left text-xs text-white/70">
                      <th className="w-[14%] px-2 py-2">影响因素</th>
                      <th className="w-[8%] px-2 py-2">重要性(1-5)</th>
                      <th className="w-[38%] px-2 py-2">形势判断及支撑指标</th>
                      <th className="w-[8%] px-2 py-2">影响</th>
                      <th className="w-[12%] px-2 py-2">致信水平</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groups.map((g) => (
                      <FactorGroup
                        key={g}
                        title={g}
                        content={content}
                        onChange={updateFactor}
                        reviseOpinions={reviseOpinions}
                        onReviseOpinionChange={setReviseOpinion}
                        onRevise={handleReviseFactor}
                        revising={revising}
                      />
                    ))}
                  </tbody>
                </table>
              </div>

              {/* 价格预测 */}
              <div className="mt-5 grid gap-3 md:grid-cols-2">
                {(['current_month', 'next_month'] as const).map((blk) => {
                  const b = content.price_forecast[blk]
                  return (
                    <div key={blk} className="rounded-xl bg-white/5 p-4">
                      <div className="mb-2 text-sm font-medium">
                        {b.label || (blk === 'current_month' ? '当月价格预测' : '次月价格预测')}
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <span className="text-white/60">区间</span>
                        <input
                          type="number"
                          value={b.range_low ?? ''}
                          onChange={(e) =>
                            updatePrice(blk, {
                              range_low: e.target.value === '' ? null : Number(e.target.value),
                            })
                          }
                          className="w-20 rounded-lg border border-white/10 bg-black/20 px-2 py-1"
                        />
                        <span>-</span>
                        <input
                          type="number"
                          value={b.range_high ?? ''}
                          onChange={(e) =>
                            updatePrice(blk, {
                              range_high: e.target.value === '' ? null : Number(e.target.value),
                            })
                          }
                          className="w-20 rounded-lg border border-white/10 bg-black/20 px-2 py-1"
                        />
                        <span className="ml-2 text-white/60">均价</span>
                        <input
                          type="number"
                          value={b.avg ?? ''}
                          onChange={(e) =>
                            updatePrice(blk, {
                              avg: e.target.value === '' ? null : Number(e.target.value),
                            })
                          }
                          className="w-20 rounded-lg border border-white/10 bg-black/20 px-2 py-1"
                        />
                        <span className="text-white/50">美元/桶</span>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* 数据来源 */}
              {detail?.sources?.length > 0 && (
                <div className="mt-4 rounded-xl bg-white/5 p-4 text-xs text-white/60">
                  <div className="mb-1 font-medium text-white/70">
                    可信数据源（共 {detail.sources.length} 个）
                  </div>
                  <div className="flex flex-wrap gap-x-3 gap-y-1">
                    {detail.sources.map((s: any) => (
                      <a
                        key={s.name}
                        href={s.url}
                        target="_blank"
                        rel="noreferrer"
                        className="hover:text-cyan-300"
                      >
                        {s.name}
                      </a>
                    ))}
                  </div>
                </div>
              )}

              {/* 联网检索来源 */}
              {detail?.evidence?.web_references?.length > 0 && (
                <div className="mt-4 rounded-xl border border-cyan-400/20 bg-cyan-500/5 p-4 text-xs text-white/60">
                  <div className="mb-2 flex items-center gap-2 font-medium text-white/70">
                    <span className="rounded bg-cyan-500/20 px-1.5 py-0.5 text-[10px] text-cyan-200">
                      联网查询
                    </span>
                    实时检索来源（共 {detail.evidence.web_references.length} 条，供时效性参考）
                  </div>
                  <ol className="list-decimal space-y-1 pl-5">
                    {detail.evidence.web_references.map((s: any, i: number) => (
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
            </>
          ) : (
            <div className="py-20 text-center text-white/50">
              请在左侧生成预测分析表，或选择历史记录
            </div>
          )}
        </div>
      </div>

      {message && <div className="rounded-xl bg-black/30 p-3 text-sm">{message}</div>}
    </div>
  )
}

function AutoResizeTextarea({
  value,
  onChange,
  className = '',
}: {
  value: string
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void
  className?: string
}) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const resize = useCallback(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.max(el.scrollHeight, 48)}px`
  }, [])

  useEffect(() => {
    resize()
  }, [value, resize])

  return (
    <textarea
      ref={ref}
      value={value}
      onChange={(e) => {
        onChange(e)
        resize()
      }}
      rows={1}
      className={className}
    />
  )
}

function FactorReviseBox({
  factorIdx,
  opinion,
  revisingKey,
  onOpinionChange,
  onRevise,
}: {
  factorIdx: number
  opinion: string
  revisingKey: string | null
  onOpinionChange: (key: string, value: string) => void
  onRevise: (idx: number) => void
}) {
  const key = `${factorIdx}-judgment`
  const busy = revisingKey === key
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-white/5 pt-2">
      <input
        value={opinion}
        onChange={(e) => onOpinionChange(key, e.target.value)}
        placeholder="修改意见"
        className="min-w-[200px] flex-1 rounded-lg border border-white/10 bg-black/20 px-3 py-1.5 text-xs outline-none placeholder:text-white/30 focus:border-cyan-400/40"
      />
      <button
        type="button"
        onClick={() => onRevise(factorIdx)}
        disabled={busy || !opinion.trim()}
        className="rounded-lg bg-white/10 px-3 py-1.5 text-xs disabled:opacity-50"
      >
        {busy ? '修订中…' : 'Agent 修订'}
      </button>
    </div>
  )
}

function FactorGroup({
  title,
  content,
  onChange,
  reviseOpinions,
  onReviseOpinionChange,
  onRevise,
  revising,
}: {
  title: string
  content: PredictionContent
  onChange: (idx: number, patch: Partial<Factor>) => void
  reviseOpinions: Record<string, string>
  onReviseOpinionChange: (key: string, value: string) => void
  onRevise: (idx: number) => void
  revising: string | null
}) {
  return (
    <>
      <tr>
        <td colSpan={5} className="bg-brand-blue/20 px-2 py-1.5 text-xs font-semibold text-cyan-200">
          {title}
        </td>
      </tr>
      {content.factors.map((f, idx) =>
        f.category_title === title ? (
          <tr key={f.id} className="border-t border-white/5">
            <td className="px-2 py-2 align-top text-white/80">
              <span className="text-white/40">{f.id}</span> {f.name}
            </td>
            <td className="px-2 py-2 align-top">
              <select
                value={f.importance}
                onChange={(e) => onChange(idx, { importance: Number(e.target.value) })}
                className="w-full max-w-16 rounded-lg border border-white/10 bg-black/20 px-2 py-1 text-sm"
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </td>
            <td className="px-2 py-2 align-top">
              <AutoResizeTextarea
                value={f.judgment}
                onChange={(e) => onChange(idx, { judgment: e.target.value })}
                className="box-border w-full resize-none overflow-hidden rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs leading-relaxed outline-none focus:border-cyan-400/40"
              />
              <FactorReviseBox
                factorIdx={idx}
                opinion={reviseOpinions[`${idx}-judgment`] || ''}
                revisingKey={revising}
                onOpinionChange={onReviseOpinionChange}
                onRevise={onRevise}
              />
            </td>
            <td className="px-2 py-2 align-top">
              <select
                value={f.impact}
                onChange={(e) => onChange(idx, { impact: e.target.value })}
                className={`w-full rounded-lg border border-white/10 bg-black/20 px-2 py-1 text-sm ${impactColor[f.impact] || ''}`}
              >
                {IMPACT_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            </td>
            <td className="px-2 py-2 align-top">
              <div className="flex min-h-[48px] flex-col justify-center gap-1.5">
                <span
                  className={`inline-flex w-fit rounded-md px-2 py-1 text-xs ${
                    confidenceBadge[f.confidence_level || '模型推断'] || 'bg-white/10 text-white/60'
                  }`}
                >
                  {f.confidence_level || '模型推断'}
                </span>
                {f.confidence_level === '权威数据' && f.source_url ? (
                  <a
                    href={f.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="break-words text-xs text-cyan-300/90 hover:text-cyan-200 hover:underline"
                  >
                    {f.source_title || f.source_url}
                  </a>
                ) : null}
              </div>
            </td>
          </tr>
        ) : null,
      )}
    </>
  )
}
