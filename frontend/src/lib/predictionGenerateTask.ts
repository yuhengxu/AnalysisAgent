import {
  getPredictionGenerateTask,
  startPredictionGenerateAsync,
  type PredictionTaskStatus,
} from '../api/client'
import { formatLlmLabel, getUnrestrictedMode } from '../constants/agentDefaults'

export interface GenerateParams {
  year: number
  month: number
  extra_instruction?: string
  symbol?: string
}

export interface GenerateResult {
  id: number
  title: string
  llm_used?: boolean
  model_name?: string
  [key: string]: unknown
}

export type TaskStatus = 'idle' | 'running' | 'success' | 'error'

export interface PredictionTaskState {
  status: TaskStatus
  params: GenerateParams | null
  message: string
  step: number
  totalSteps: number
  stepLabel: string
  result: GenerateResult | null
  error: string | null
  startedAt: number | null
}

type Listener = () => void

const IDLE: PredictionTaskState = {
  status: 'idle',
  params: null,
  message: '',
  step: 0,
  totalSteps: 7,
  stepLabel: '',
  result: null,
  error: null,
  startedAt: null,
}

let state: PredictionTaskState = { ...IDLE }
let activePromise: Promise<GenerateResult> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null
const listeners = new Set<Listener>()

function emit() {
  listeners.forEach((l) => l())
}

function clearPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function applyTaskStatus(task: PredictionTaskStatus, params: GenerateParams) {
  state = {
    ...state,
    status: task.status === 'success' ? 'success' : task.status === 'error' ? 'error' : 'running',
    params,
    message: task.message || state.message,
    step: task.step,
    totalSteps: task.total_steps,
    stepLabel: task.step_label,
    result: (task.result as GenerateResult | null) ?? null,
    error: task.error,
  }
  emit()
}

function waitForTask(taskId: string, params: GenerateParams): Promise<GenerateResult> {
  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const task = await getPredictionGenerateTask(taskId)
        applyTaskStatus(task, params)
        if (task.status === 'success' && task.result) {
          clearPoll()
          resolve(task.result as GenerateResult)
        } else if (task.status === 'error') {
          clearPoll()
          reject(new Error(task.error || '生成失败'))
        }
      } catch (err) {
        clearPoll()
        reject(err)
      }
    }

    void poll()
    pollTimer = setInterval(() => {
      void poll()
    }, 2000)
  })
}

/** 启动或复用进行中的生成任务（异步多轮，切换页面不中断）。 */
export function startPredictionGenerate(params: GenerateParams): Promise<GenerateResult> {
  if (activePromise && state.status === 'running') {
    return activePromise
  }

  clearPoll()
  const unrestricted = getUnrestrictedMode()
  state = {
    status: 'running',
    params,
    message: unrestricted
      ? `正在基于 yuebao 样例仿写 ${params.year}年${params.month}月 预测分析表（深度研究）…`
      : `正在生成 ${params.year}年${params.month}月 预测分析表（分 ${IDLE.totalSteps} 步多轮调用）…`,
    step: 0,
    totalSteps: unrestricted ? 1 : 7,
    stepLabel: '初始化',
    result: null,
    error: null,
    startedAt: Date.now(),
  }
  emit()

  activePromise = startPredictionGenerateAsync(params)
    .then((task) => waitForTask(task.task_id, params))
    .then((res) => {
      state = {
        ...state,
        status: 'success',
        message: `已生成：${res.title}（${formatLlmLabel(!!res.llm_used, res.model_name)}）`,
        result: res,
        error: null,
      }
      emit()
      return res
    })
    .catch((err: unknown) => {
      const detail = err instanceof Error ? err.message : '未知错误'
      state = {
        ...state,
        status: 'error',
        message: `生成失败：${detail}`,
        error: detail,
        result: null,
      }
      emit()
      throw err
    })
    .finally(() => {
      clearPoll()
      activePromise = null
    })

  return activePromise
}

export function getPredictionTaskState(): PredictionTaskState {
  return state
}

export function subscribePredictionTask(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function isPredictionGenerating(): boolean {
  return state.status === 'running'
}

export function dismissPredictionTask(): void {
  if (state.status === 'running') return
  clearPoll()
  state = { ...IDLE }
  emit()
}
