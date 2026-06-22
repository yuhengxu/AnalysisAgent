import { useEffect, useState } from 'react'
import { getLlmLog, listLlmLogSources, listLlmLogs } from '../api/client'
import { formatBeijingTime } from '../lib/formatTime'

const SOURCE_LABELS: Record<string, string> = {
  prediction_skill: '预测分析表',
  prediction_unrestricted_skill: '预测分析表（无限制）',
  report_skill: '月报生成',
  report_unrestricted_skill: '月报生成（无限制）',
  agent_chat: 'Agent 对话',
  agent_analyze: 'Agent 分析',
  agent_revise: '月报修订',
  web_search_plan: '联网·规划判断',
  web_search_query: '联网·检索执行',
  web_search_direct: '联网·直接作答',
  web_search_skill: '联网·结果归纳',
  unknown: '未知',
}

function sourceLabel(source: string) {
  return SOURCE_LABELS[source] || source
}

export default function LlmMonitor() {
  const [items, setItems] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [source, setSource] = useState('')
  const [status, setStatus] = useState('')
  const [sources, setSources] = useState<string[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  async function refresh(p = page) {
    setLoading(true)
    try {
      const res = await listLlmLogs({
        page: p,
        page_size: 15,
        source: source || undefined,
        status: status || undefined,
      })
      setItems(res.items)
      setTotal(res.total)
      setPage(res.page)
      setPages(res.pages)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    listLlmLogSources().then(setSources).catch(() => setSources([]))
  }, [])

  useEffect(() => {
    refresh(1).catch(() => setItems([]))
  }, [source, status])

  async function open(id: number) {
    setSelectedId(id)
    setDetail(await getLlmLog(id))
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">大模型监控日志</h1>
        <p className="text-sm text-white/60">
          查看每轮大模型调用的客户请求与模型应答，数据同步写入 logs/llm_dialogue.log
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1.1fr]">
        <div className="glass rounded-2xl p-4">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <select
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm"
            >
              <option value="">全部来源</option>
              {sources.map((s) => (
                <option key={s} value={s}>
                  {sourceLabel(s)}
                </option>
              ))}
            </select>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm"
            >
              <option value="">全部状态</option>
              <option value="success">成功</option>
              <option value="error">失败</option>
            </select>
            <button
              onClick={() => refresh(page)}
              className="rounded-lg bg-white/10 px-3 py-2 text-sm hover:bg-white/15"
            >
              刷新
            </button>
            <span className="text-xs text-white/50">共 {total} 条</span>
          </div>

          <div className="space-y-2">
            {items.map((item) => (
              <button
                key={item.id}
                onClick={() => open(item.id)}
                className={`w-full rounded-xl px-3 py-3 text-left text-sm transition ${
                  selectedId === item.id ? 'bg-brand-blue/40' : 'bg-white/5 hover:bg-white/10'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{sourceLabel(item.source)}</span>
                  <span
                    className={`text-xs ${item.status === 'success' ? 'text-green-300' : 'text-red-300'}`}
                  >
                    {item.status === 'success' ? '成功' : '失败'}
                  </span>
                </div>
                <div className="mt-1 text-xs text-white/50">
                  {item.provider}/{item.model_name} · {item.duration_ms.toFixed(0)}ms ·{' '}
                  {formatBeijingTime(item.created_at)}
                </div>
                <div className="mt-1 line-clamp-2 text-xs text-white/70">{item.request_preview}</div>
              </button>
            ))}
            {items.length === 0 && !loading && (
              <div className="py-12 text-center text-sm text-white/50">暂无对话记录</div>
            )}
          </div>

          {pages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-2">
              <button
                disabled={page <= 1}
                onClick={() => refresh(page - 1)}
                className="rounded-lg bg-white/10 px-3 py-1 text-sm disabled:opacity-40"
              >
                上一页
              </button>
              <span className="text-xs text-white/50">
                {page} / {pages}
              </span>
              <button
                disabled={page >= pages}
                onClick={() => refresh(page + 1)}
                className="rounded-lg bg-white/10 px-3 py-1 text-sm disabled:opacity-40"
              >
                下一页
              </button>
            </div>
          )}
        </div>

        <div className="glass rounded-2xl p-5">
          {detail ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-lg font-medium">对话 #{detail.id}</div>
                  <div className="text-xs text-white/50">{formatBeijingTime(detail.created_at)}</div>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-xs ${
                    detail.status === 'success'
                      ? 'bg-green-500/20 text-green-300'
                      : 'bg-red-500/20 text-red-300'
                  }`}
                >
                  {detail.status === 'success' ? '成功' : '失败'}
                </span>
              </div>

              <div className="grid gap-2 text-sm md:grid-cols-2">
                <div className="rounded-xl bg-white/5 p-3">
                  <div className="text-xs text-white/50">来源</div>
                  <div>{sourceLabel(detail.source)}</div>
                </div>
                <div className="rounded-xl bg-white/5 p-3">
                  <div className="text-xs text-white/50">模型</div>
                  <div>
                    {detail.provider} / {detail.model_name}
                  </div>
                </div>
                <div className="rounded-xl bg-white/5 p-3">
                  <div className="text-xs text-white/50">耗时</div>
                  <div>{detail.duration_ms.toFixed(1)} ms</div>
                </div>
                {Object.keys(detail.meta || {}).length > 0 && (
                  <div className="rounded-xl bg-white/5 p-3 md:col-span-2">
                    <div className="text-xs text-white/50">上下文</div>
                    <pre className="mt-1 overflow-x-auto text-xs text-white/70">
                      {JSON.stringify(detail.meta, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              <div>
                <div className="mb-2 text-sm font-medium text-cyan-200">客户请求（Messages）</div>
                <div className="max-h-72 space-y-3 overflow-y-auto rounded-xl bg-black/30 p-4">
                  {detail.request_messages.map((m: any, i: number) => (
                    <div key={i}>
                      <div className="mb-1 text-xs uppercase text-white/40">{m.role}</div>
                      <pre className="whitespace-pre-wrap break-words text-xs leading-relaxed text-white/85">
                        {m.content}
                      </pre>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-2 text-sm font-medium text-green-200">大模型应答</div>
                <div className="max-h-96 overflow-y-auto rounded-xl bg-black/30 p-4">
                  {detail.status === 'error' ? (
                    <pre className="whitespace-pre-wrap text-xs text-red-300">{detail.error_message}</pre>
                  ) : (
                    <pre className="whitespace-pre-wrap break-words text-xs leading-relaxed text-white/85">
                      {detail.response_content}
                    </pre>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="py-24 text-center text-white/50">选择左侧记录查看完整对话</div>
          )}
        </div>
      </div>
    </div>
  )
}
