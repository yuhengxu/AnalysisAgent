import { useSyncExternalStore } from 'react'
import {
  getPredictionTaskState,
  subscribePredictionTask,
} from '../lib/predictionGenerateTask'

export function usePredictionTask() {
  return useSyncExternalStore(
    subscribePredictionTask,
    getPredictionTaskState,
    getPredictionTaskState,
  )
}
