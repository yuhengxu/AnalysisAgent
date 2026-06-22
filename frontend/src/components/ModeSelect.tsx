import { useEffect, useState } from 'react'
import {
  LLM_MODE_LABELS,
  getLlmMode,
  getLlmProvider,
  setLlmMode,
  type LlmMode,
  type LlmModule,
} from '../constants/agentDefaults'

interface Props {
  module: LlmModule
  label?: string
  compact?: boolean
  className?: string
}

/** 深度研究模式说明（按当前 provider 区分） */
export function deepResearchHint(): string {
  const provider = getLlmProvider()
  if (provider === 'deepseek') return '深度研究：开启 DeepSeek 深度思考，推理更强但耗时更长'
  if (provider === 'volcengine')
    return '深度研究：调用豆包 DeepSearch 智能体（联网搜索、浏览器使用、网页解析、Python 代码执行等 MCP 服务）'
  return '深度研究：当前提供商不支持，将按普通模式调用'
}

export default function ModeSelect({
  module,
  label = '调用模式',
  compact = false,
  className = '',
}: Props) {
  const mode = useLlmMode(module)

  function onChange(next: LlmMode) {
    setLlmMode(module, next)
    window.dispatchEvent(new CustomEvent('llm-mode-change', { detail: { module, mode: next } }))
  }

  return (
    <div className={className}>
      {!compact && <label className="mb-1 block text-sm text-white/70">{label}</label>}
      <div className="flex gap-2">
        {(['deep_research', 'normal'] as const).map((level) => (
          <button
            key={level}
            type="button"
            onClick={() => onChange(level)}
            title={level === 'deep_research' ? deepResearchHint() : '普通模式：直接调用对话模型，响应快'}
            className={`rounded-xl border px-3 text-xs transition ${
              compact ? 'flex-1 py-1.5' : 'flex-1 py-2 text-sm'
            } ${
              mode === level
                ? 'border-brand-blue bg-brand-blue/30 text-white'
                : 'border-white/10 bg-black/20 text-white/70 hover:bg-white/5'
            }`}
          >
            {LLM_MODE_LABELS[level]}
          </button>
        ))}
      </div>
    </div>
  )
}

/** 订阅模块调用模式变更 */
export function useLlmMode(module: LlmModule): LlmMode {
  const [, tick] = useState(0)
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { module?: LlmModule }
      if (!detail?.module || detail.module === module) tick((n) => n + 1)
    }
    window.addEventListener('llm-mode-change', handler)
    return () => window.removeEventListener('llm-mode-change', handler)
  }, [module])
  return getLlmMode(module)
}
