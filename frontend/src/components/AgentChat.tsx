import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { chatAgent } from '../api/client'
import { RESEARCH_PROMPT, SKILL_LABELS } from '../constants/agentDefaults'
import {
  clearChatHistory,
  loadChatHistory,
  saveChatHistory,
  trimChatHistory,
  type ChatMsg,
} from '../lib/agentChatStorage'
import type { AgentVisualState } from '../types/agentVisual'
import { DEFAULT_VISUAL, type AgentMood } from '../types/agentVisual'

function normalizeVisual(raw: Record<string, unknown> | undefined): AgentVisualState {
  if (!raw) return DEFAULT_VISUAL
  return {
    mood: (raw.mood as AgentMood) || 'idle',
    colors: Array.isArray(raw.colors) ? (raw.colors as string[]) : DEFAULT_VISUAL.colors,
    particle_speed: Number(raw.particle_speed) || DEFAULT_VISUAL.particle_speed,
    glow_intensity: Number(raw.glow_intensity) || DEFAULT_VISUAL.glow_intensity,
    pulse_rate: Number(raw.pulse_rate) || DEFAULT_VISUAL.pulse_rate,
    status_text: typeof raw.status_text === 'string' ? raw.status_text : DEFAULT_VISUAL.status_text,
  }
}
import AgentAvatar from './AgentAvatar'
import ChartPanel from './ChartPanel'

interface Props {
  onClose: () => void
  visual: AgentVisualState
  onVisualChange: (v: AgentVisualState) => void
  onThinkingChange: (thinking: boolean) => void
}

export default function AgentChat({ onClose, visual, onVisualChange, onThinkingChange }: Props) {
  const navigate = useNavigate()
  const [messages, setMessages] = useState<ChatMsg[]>(() => loadChatHistory())
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [charts, setCharts] = useState<any[]>([])
  const [reportId, setReportId] = useState<number | null>(null)
  const [predictionId, setPredictionId] = useState<number | null>(null)
  const [toolsCalled, setToolsCalled] = useState<string[]>([])
  const [progressText, setProgressText] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, charts, loading])

  useEffect(() => {
    onThinkingChange(loading)
  }, [loading, onThinkingChange])

  useEffect(() => {
    saveChatHistory(messages)
  }, [messages])

  function handleClearHistory() {
    if (loading) return
    if (messages.length > 1 && !window.confirm('确定清空对话记录？')) return
    setMessages(clearChatHistory())
    setCharts([])
    setReportId(null)
    setPredictionId(null)
    setToolsCalled([])
    setProgressText('')
    onVisualChange(DEFAULT_VISUAL)
  }

  async function sendMessage(text: string, skillHint?: string) {
    const trimmed = text.trim()
    if (!trimmed || loading) return

    const nextMessages: ChatMsg[] = trimChatHistory([
      ...messages,
      { role: 'user', content: trimmed },
    ])
    setMessages(nextMessages)
    setInput('')
    setLoading(true)
    setProgressText('')
    onVisualChange({ ...visual, mood: 'thinking', status_text: '思考与编排工具中…' })

    try {
      const res = await chatAgent(
        trimChatHistory(nextMessages).map((m) => ({ role: m.role, content: m.content })),
        skillHint,
        (text) => {
          setProgressText(text)
          onVisualChange({ ...visual, mood: 'predicting', status_text: text })
        },
      )
      setMessages((prev) => [...prev, { role: 'assistant', content: res.message }])
      if (res.visual) onVisualChange(normalizeVisual(res.visual))
      setCharts(res.charts || [])
      setToolsCalled(res.tools_called || [])
      setReportId(res.report_id ?? null)
      setPredictionId(res.prediction_id ?? null)
    } catch (err: unknown) {
      const msg =
        (err as { code?: string; message?: string })?.code === 'ECONNABORTED'
          ? '请求超时：查证或深度研究耗时较长，请稍后重试，或在设置中开启「深度研究」模式以加快联网查询。'
          : (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data
                ?.detail ||
            (err as { message?: string })?.message ||
            '请求失败，请确认后端已启动后重试。'
      setMessages((prev) => [...prev, { role: 'assistant', content: msg }])
      onVisualChange({ ...DEFAULT_VISUAL, mood: 'error', status_text: '请求异常' })
    } finally {
      setLoading(false)
    }
  }

  function sendResearch(text: string) {
    sendMessage(text, 'web_search')
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    sendMessage(input)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-end bg-black/50 p-4 md:p-6">
      <div className="agent-chat-panel glass flex h-[min(85vh,720px)] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-white/15 shadow-2xl md:max-w-lg">
        <div className="flex items-center gap-3 border-b border-white/10 px-4 py-3">
          <div className="relative h-12 w-12 shrink-0">
            <AgentAvatar size={48} visual={visual} active={loading} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-base font-semibold">能源分析助手</div>
            <div className="truncate text-xs text-cyan-200/70">
              {visual.status_text || '在线 · 随时为您服务'}
            </div>
          </div>
          <button
            type="button"
            onClick={handleClearHistory}
            disabled={loading}
            className="shrink-0 rounded-lg px-2 py-1 text-xs text-white/50 hover:bg-white/10 disabled:opacity-50"
          >
            清空
          </button>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-lg px-3 py-1 text-sm text-white/70 hover:bg-white/10"
          >
            关闭
          </button>
        </div>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
          {messages.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[88%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                  m.role === 'user'
                    ? 'bg-brand-red/25 text-white'
                    : 'bg-white/8 text-white/90'
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="rounded-2xl bg-white/8 px-3 py-2 text-sm text-white/60">
                <span className="agent-typing">{progressText || '正在思考与检索…'}</span>
              </div>
            </div>
          )}
          {toolsCalled.length > 0 && (
            <div className="text-xs text-white/45">工具：{toolsCalled.join(' · ')}</div>
          )}
          {charts.map((chart, idx) => (
            <ChartPanel key={idx} config={chart} height={200} />
          ))}
          {reportId && (
            <button
              type="button"
              onClick={() => {
                onClose()
                navigate(`/reports?id=${reportId}`)
              }}
              className="rounded-lg bg-brand-blue px-3 py-1.5 text-xs"
            >
              打开报告中心
            </button>
          )}
          {predictionId && (
            <button
              type="button"
              onClick={() => {
                onClose()
                navigate(`/prediction?id=${predictionId}`)
              }}
              className="rounded-lg bg-brand-blue px-3 py-1.5 text-xs"
            >
              打开预测分析表
            </button>
          )}
        </div>

        <div className="border-t border-white/10 px-3 py-2">
          <div className="mb-2 flex flex-wrap gap-1.5">
            {Object.entries(SKILL_LABELS).map(([id, label]) => (
              <button
                key={id}
                type="button"
                disabled={loading}
                onClick={() =>
                  sendMessage(
                    id === 'analyze'
                      ? '请根据平台数据库 evidence 解读已查询的价格与供需数据'
                      : id === 'predict'
                        ? '预测 Brent 下月价格情景'
                        : id === 'predict_table'
                          ? '生成本月布伦特油价预测分析表'
                          : '生成本月国际油价月报',
                  )
                }
                className="rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-[10px] text-white/70 hover:border-cyan-400/40 disabled:opacity-50"
              >
                {label}
              </button>
            ))}
            <button
              type="button"
              disabled={loading}
              onClick={() => sendResearch(RESEARCH_PROMPT)}
              className="rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-[10px] text-white/70 hover:border-cyan-400/40 disabled:opacity-50"
            >
              资讯检索
            </button>
            <button
              type="button"
              disabled={loading}
              onClick={() => sendMessage('更科技感、更有未来感的粒子外观')}
              className="rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-[10px] text-white/70 hover:border-cyan-400/40 disabled:opacity-50"
            >
              科技感外观
            </button>
          </div>
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="输入问题或业务指令…"
              disabled={loading}
              className="flex-1 rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm outline-none placeholder:text-white/35 focus:border-cyan-400/50"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="shrink-0 rounded-xl bg-brand-red px-4 py-2 text-sm font-medium disabled:opacity-50"
            >
              发送
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
