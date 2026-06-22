import {
  getReportGenerateTask,
  startReportGenerateAsync,
  type ReportTaskStatus,
} from '../api/client'
import {
  formatLlmLabel,
  formatReportPeriodLabel,
  getUnrestrictedMode,
  type ReportGenerateParams,
} from '../constants/agentDefaults'

export interface GenerateResult {
  id: number
  title: string
  llm_used?: boolean
  model_name?: string
  references?: Record<string, unknown>
  [key: string]: unknown
}

export type TaskStatus = 'idle' | 'running' | 'success' | 'error'

export interface ReportTaskState {
  status: TaskStatus
  params: ReportGenerateParams | null
  message: string
  step: number
  totalSteps: number
  stepLabel: string
  result: GenerateResult | null
  error: string | null
  startedAt: number | null
}

type Listener = () => void

const IDLE: ReportTaskState = {
  status: 'idle',
  params: null,
  message: '',
  step: 0,
  totalSteps: 3,
  stepLabel: '',
  result: null,
  error: null,
  startedAt: null,
}

let state: ReportTaskState = { ...IDLE }
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

function applyTaskStatus(task: ReportTaskStatus, params: ReportGenerateParams) {
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

function waitForTask(taskId: string, params: ReportGenerateParams): Promise<GenerateResult> {
  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const task = await getReportGenerateTask(taskId)
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

/** 启动或复用进行中的月报生成任务（切换页面不中断）。 */
export function startReportGenerate(params: ReportGenerateParams): Promise<GenerateResult> {
  if (activePromise && state.status === 'running') {
    return activePromise
  }

  clearPoll()
  const unrestricted = getUnrestrictedMode()
  const label = formatReportPeriodLabel(params)
  state = {
    status: 'running',
    params,
    message: unrestricted
      ? `正在生成《国际油价月报》${label}（深度研究）…`
      : `正在生成《国际油价月报》${label}（分 3 步）…`,
    step: 0,
    totalSteps: unrestricted ? 1 : 3,
    stepLabel: '初始化',
    result: null,
    error: null,
    startedAt: Date.now(),
  }
  emit()

  activePromise = startReportGenerateAsync(params)
    .then((task) => waitForTask(task.task_id, params))
    .then((res) => {
      state = {
        ...state,
        status: 'success',
        message: `已生成：${res.title}（${formatLlmLabel(!!res.llm_used, res.model_name as string | undefined)}）`,
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

export function getReportTaskState(): ReportTaskState {
  return state
}

export function subscribeReportTask(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function isReportGenerating(): boolean {
  return state.status === 'running'
}

export function dismissReportTask(): void {
  if (state.status === 'running') return
  clearPoll()
  state = { ...IDLE }
  emit()
}
