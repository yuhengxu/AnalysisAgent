import { useSyncExternalStore } from 'react'
import { getReportTaskState, subscribeReportTask } from '../lib/reportGenerateTask'

export function useReportTask() {
  return useSyncExternalStore(subscribeReportTask, getReportTaskState, getReportTaskState)
}
