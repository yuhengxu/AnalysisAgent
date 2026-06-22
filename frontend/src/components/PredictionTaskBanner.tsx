import { Link } from 'react-router-dom'
import { dismissPredictionTask } from '../lib/predictionGenerateTask'
import { usePredictionTask } from '../hooks/usePredictionTask'

export default function PredictionTaskBanner() {
  const task = usePredictionTask()

  if (task.status === 'idle') return null

  const isRunning = task.status === 'running'
  const isSuccess = task.status === 'success'
  const isError = task.status === 'error'

  return (
    <div
      className={`border-b px-6 py-2 text-sm ${
        isRunning
          ? 'border-cyan-400/30 bg-cyan-500/10 text-cyan-100'
          : isSuccess
            ? 'border-green-400/30 bg-green-500/10 text-green-100'
            : 'border-red-400/30 bg-red-500/10 text-red-100'
      }`}
    >
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {isRunning && (
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-cyan-300" />
          )}
          <span>
            {task.message}
            {isRunning && task.totalSteps > 0 && (
              <span className="ml-2 text-xs opacity-80">
                （{task.step}/{task.totalSteps}
                {task.stepLabel ? ` · ${task.stepLabel}` : ''}）
              </span>
            )}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {isSuccess && task.result?.id != null && (
            <Link
              to={`/prediction?id=${task.result.id}`}
              className="rounded-lg bg-white/10 px-3 py-1 text-xs hover:bg-white/20"
            >
              查看预测分析表
            </Link>
          )}
          {!isRunning && (
            <button
              type="button"
              onClick={dismissPredictionTask}
              className="rounded-lg bg-white/10 px-3 py-1 text-xs hover:bg-white/20"
            >
              关闭
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
