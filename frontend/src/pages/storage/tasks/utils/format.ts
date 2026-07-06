import dayjs from 'dayjs'
import type { StorageSubTask, StorageTaskLog } from '@/api/storage/storageTasks/types'

export function formatTime(value: string) {
  if (!value) return '-'
  return dayjs(value).format('YYYY-MM-DD HH:mm:ss')
}

export function logsForStep(logs: StorageTaskLog[], step: string): StorageTaskLog[] {
  return logs.filter((log) => log.step === step)
}

export function stepColor(subtask: StorageSubTask, logs: StorageTaskLog[], step: string): 'red' | 'green' | 'blue' | 'gray' {
  const stepLogs = logsForStep(logs, step)
  if (stepLogs.some((log) => log.level === 'error')) return 'red'
  if (step === subtask.step && subtask.status === 'running') return 'blue'
  if (stepLogs.length > 0) return 'green'
  return 'gray'
}
