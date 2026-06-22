import { useEffect, useMemo, useState } from 'react'
import {
  listLlmProviders,
  testLlmConnection,
  type LlmModelGroup,
  type LlmModelOption,
  type LlmProviderInfo,
} from '../api/client'
import ModeSelect from '../components/ModeSelect'
import {
  LLM_MODULES,
  LLM_MODE_LABELS,
  getGlobalLlmMode,
  getUnrestrictedMode,
  setLlmMode,
  setUnrestrictedMode,
  type LlmMode,
  type LlmModule,
} from '../constants/agentDefaults'

const MODE_HINTS: Record<string, { normal: string; deep: string }> = {
  volcengine: {
    normal: '直接调用所选方舟接入点（豆包 / DeepSeek / 千问），响应快，适合日常对话与常规生成。',
    deep: '调用 DeepSearch 智能体：专为复杂问题设计，集成浏览器使用、联网搜索、知识库、网页解析、ChatPPT、Python 代码执行器等 MCP 服务（需后端配置 VOLCENGINE_DEEPSEARCH_BOT_ID）。深度研究模式下将忽略此处所选聊天模型。',
  },
  deepseek: {
    normal: '直接调用 DeepSeek 官方 API，关闭思考链，快速回复。',
    deep: '开启 DeepSeek 深度思考（thinking + reasoning_effort），推理更强但耗时显著更长。',
  },
  openai: {
    normal: '直接调用 OpenAI 兼容接口。',
    deep: '当前提供商不支持深度研究，将按普通模式调用。',
  },
  mock: {
    normal: '本地规则兜底，不调用大模型。',
    deep: '本地规则兜底，不调用大模型。',
  },
}

function ensureModelInList(models: LlmModelOption[], currentId: string): LlmModelOption[] {
  if (!currentId || models.some((m) => m.id === currentId)) return models
  return [
    {
      id: currentId,
      label: `已保存（${currentId}）`,
      family: 'custom',
      hint: '来自浏览器本地存储，若无法连接请在方舟控制台核对接入点 ID',
    },
    ...models,
  ]
}

function buildGroups(models: LlmModelOption[]): LlmModelGroup[] {
  const familyLabels: Record<string, string> = {
    doubao: '豆包',
    deepseek: 'DeepSeek',
    qwen: '通义千问',
    openai: 'OpenAI',
    mock: 'Mock',
    custom: '自定义',
  }
  const groups: LlmModelGroup[] = []
  const seen = new Set<string>()
  for (const m of models) {
    const fam = m.family || 'other'
    if (!seen.has(fam)) {
      seen.add(fam)
      groups.push({ family: fam, label: familyLabels[fam] || fam, models: [] })
    }
    groups.find((g) => g.family === fam)!.models.push(m)
  }
  return groups
}

export default function Settings() {
  const [provider, setProvider] = useState(localStorage.getItem('llm_provider') || 'volcengine')
  const [model, setModel] = useState(localStorage.getItem('llm_model') || 'doubao-seed-2-0-pro-260215')
  const [globalMode, setGlobalMode] = useState<LlmMode>(getGlobalLlmMode())
  const [unrestrictedMode, setUnrestrictedModeState] = useState(getUnrestrictedMode())
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [providers, setProviders] = useState<LlmProviderInfo[]>([])
  const [catalogError, setCatalogError] = useState<string | null>(null)

  useEffect(() => {
    listLlmProviders()
      .then((res) => setProviders(res.providers))
      .catch((e: Error) => setCatalogError(e.message || '加载模型列表失败'))
  }, [])

  const currentProvider = useMemo(
    () => providers.find((p) => p.id === provider),
    [providers, provider],
  )

  const modelGroups = useMemo(() => {
    const base = currentProvider?.model_groups?.length
      ? currentProvider.model_groups
      : buildGroups(currentProvider?.models || [])
    const flat = base.flatMap((g) => g.models)
    const withSaved = ensureModelInList(flat, model)
    return buildGroups(withSaved)
  }, [currentProvider, model])

  const selectedHint = useMemo(
    () => modelGroups.flatMap((g) => g.models).find((m) => m.id === model)?.hint,
    [modelGroups, model],
  )

  function save() {
    localStorage.setItem('llm_provider', provider)
    localStorage.setItem('llm_model', model)
    setLlmMode('global', globalMode)
    setUnrestrictedMode(unrestrictedMode)
    window.dispatchEvent(
      new CustomEvent('llm-mode-change', { detail: { module: 'global', mode: globalMode } }),
    )
    alert('设置已保存到浏览器本地。API Key 与 DeepSearch 应用 ID 由后端环境变量统一管理。')
  }

  function onProviderChange(p: string) {
    setProvider(p)
    setTestResult(null)
    const info = providers.find((x) => x.id === p)
    setModel(info?.default_model || info?.model || 'mock')
  }

  async function handleTestConnection() {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await testLlmConnection(provider, model)
      if (res.ok) {
        setTestResult(`连接成功（${res.duration_ms}ms）：${res.reply || res.message}`)
      } else {
        setTestResult(`连接失败：${res.message}`)
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '网络错误'
      setTestResult(`连接失败：${msg}`)
    } finally {
      setTesting(false)
    }
  }

  const hints = MODE_HINTS[provider] || MODE_HINTS.openai

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">系统设置</h1>
        <p className="text-sm text-white/60">大模型路由、调用模式（普通 / 深度研究）、DeepSearch 与部署配置</p>
      </div>

      <div className="glass max-w-2xl space-y-4 rounded-2xl p-5">
        <div>
          <label className="mb-1 block text-sm text-white/70">模型提供商</label>
          <select
            value={provider}
            onChange={(e) => onProviderChange(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm"
          >
            {(providers.length > 0
              ? providers
              : [
                  { id: 'volcengine', label: '火山方舟（豆包 / DeepSeek / 千问）' },
                  { id: 'deepseek', label: 'DeepSeek 官方 API' },
                  { id: 'openai', label: 'OpenAI 兼容 API' },
                  { id: 'mock', label: 'Mock（本地规则兜底）' },
                ]
            ).map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-sm text-white/70">模型 / 接入点</label>
          <select
            value={model}
            onChange={(e) => {
              setModel(e.target.value)
              setTestResult(null)
            }}
            className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm"
          >
            {modelGroups.length > 0 ? (
              modelGroups.map((group) => (
                <optgroup key={group.family} label={group.label}>
                  {group.models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </optgroup>
              ))
            ) : (
              <option value={model}>{model}</option>
            )}
          </select>
          {selectedHint && <p className="mt-1.5 text-xs text-white/50">{selectedHint}</p>}
          {provider === 'volcengine' && (
            <p className="mt-1 text-xs text-white/40">
              接入点 ID 须与火山方舟控制台一致；可在 backend/.env 通过 VOLCENGINE_MODEL_CATALOG 追加自定义模型。
            </p>
          )}
          {catalogError && <p className="mt-1 text-xs text-amber-300/80">模型列表加载失败：{catalogError}</p>}
        </div>
        <div>
          <label className="mb-1 block text-sm text-white/70">全局默认调用模式</label>
          <div className="flex gap-2">
            {(['deep_research', 'normal'] as const).map((level) => (
              <button
                key={level}
                type="button"
                onClick={() => setGlobalMode(level)}
                className={`flex-1 rounded-xl border px-3 py-2 text-sm transition ${
                  globalMode === level
                    ? 'border-brand-blue bg-brand-blue/30 text-white'
                    : 'border-white/10 bg-black/20 text-white/70 hover:bg-white/5'
                }`}
              >
                {level === 'normal'
                  ? `${LLM_MODE_LABELS.normal}模式（快速回复）`
                  : `${LLM_MODE_LABELS.deep_research}模式（默认，推荐）`}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-white/50">
            {globalMode === 'deep_research' ? hints.deep : hints.normal}
          </p>
          {provider === 'volcengine' && currentProvider && !currentProvider.deep_research_available && globalMode === 'deep_research' && (
            <p className="mt-1 text-xs text-amber-300/80">
              未配置 VOLCENGINE_DEEPSEARCH_BOT_ID，深度研究将降级为普通模式调用所选模型。
            </p>
          )}
        </div>
        <div className="rounded-xl bg-white/5 p-3 text-xs text-white/60">
          API Key 与 DeepSearch 应用 ID 已在后端 <code>.env</code> 中配置
          （VOLCENGINE_API_KEY / VOLCENGINE_DEEPSEARCH_BOT_ID），前端不保存密钥。
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={save} className="rounded-xl bg-brand-blue px-4 py-2 text-sm">
            保存全局设置
          </button>
          {provider !== 'mock' && (
            <button
              onClick={handleTestConnection}
              disabled={testing}
              className="rounded-xl border border-white/20 px-4 py-2 text-sm hover:bg-white/5 disabled:opacity-50"
            >
              {testing ? '测试中…' : '测试连接'}
            </button>
          )}
        </div>
        {testResult && (
          <div
            className={`rounded-xl p-3 text-xs ${
              testResult.startsWith('连接成功')
                ? 'bg-green-500/10 text-green-300'
                : 'bg-red-500/10 text-red-300'
            }`}
          >
            {testResult}
          </div>
        )}
      </div>

      <div className="glass max-w-3xl rounded-2xl p-5">
        <h2 className="mb-1 font-medium text-white">分模块调用模式</h2>
        <p className="mb-4 text-xs text-white/50">
          各业务页面可独立配置普通 / 深度研究模式，覆盖全局默认。在对应页面也可快速切换。
          深度研究模式耗时更长，建议仅在月报、预测分析表等深度任务中开启。
        </p>
        <div className="space-y-3">
          {(Object.entries(LLM_MODULES) as [LlmModule, (typeof LLM_MODULES)[LlmModule]][]).map(
            ([id, meta]) => (
              <div
                key={id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white/5 p-3"
              >
                <div>
                  <div className="text-sm font-medium">{meta.label}</div>
                  <div className="text-xs text-white/50">{meta.hint}</div>
                </div>
                <ModeSelect module={id} compact className="w-44" />
              </div>
            ),
          )}
        </div>
      </div>

      <div className="glass max-w-3xl rounded-2xl p-5">
        <h2 className="mb-3 font-medium text-white">无限制模式（预测 / 月报）</h2>
        <p className="mb-4 text-sm text-white/65">
          开启后，预测分析表与月报生成将切换为无限制 skill：以上一期 yuebao 样例为参照，
          将样例全文交给深度研究模型仿写更新，不做数据真实性或时效性校验，仅保留格式要求。
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setUnrestrictedModeState(false)}
            className={`flex-1 rounded-xl border px-3 py-2 text-sm transition ${
              !unrestrictedMode
                ? 'border-brand-blue bg-brand-blue/30 text-white'
                : 'border-white/10 bg-black/20 text-white/70 hover:bg-white/5'
            }`}
          >
            关闭（权威数据模式）
          </button>
          <button
            type="button"
            onClick={() => setUnrestrictedModeState(true)}
            className={`flex-1 rounded-xl border px-3 py-2 text-sm transition ${
              unrestrictedMode
                ? 'border-brand-blue bg-brand-blue/30 text-white'
                : 'border-white/10 bg-black/20 text-white/70 hover:bg-white/5'
            }`}
          >
            开启（样例仿写模式）
          </button>
        </div>
      </div>

      <div className="glass max-w-3xl rounded-2xl p-5">
        <h2 className="mb-3 font-medium text-white">数据真实性策略</h2>
        <p className="text-sm text-white/65">
          预测分析表、月报和其他联网任务统一使用 DeepSearch，并结合平台已落库数据生成；
          联网结果必须包含来源、URL 与期别，证据不足时会明确标注暂未获取可核验证据。
          开启无限制模式时：跳过上述校验，完全由深度研究模型基于 yuebao 样例推演更新。
        </p>
      </div>

      <div className="glass max-w-2xl rounded-2xl p-5 text-sm text-white/70">
        <h2 className="mb-2 font-medium text-white">部署说明</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>后端默认 SQLite + 本地文件存储，可通过 Docker Compose 一键启动。</li>
          <li>数据目录挂载到 ./data、./db、./yuebao，便于迁移。</li>
          <li>在 backend/.env 配置 VOLCENGINE_API_KEY 与 VOLCENGINE_DEEPSEARCH_BOT_ID 后即可启用方舟模型与联网查证。</li>
          <li>在方舟「应用广场」创建 DeepSearch 应用并配置 VOLCENGINE_DEEPSEARCH_BOT_ID 后，火山方舟即可使用深度研究模式。</li>
          <li>方舟接入点 ID 因账号而异，可在 VOLCENGINE_MODEL_CATALOG 中追加你在控制台创建的接入点。</li>
        </ul>
      </div>
    </div>
  )
}
