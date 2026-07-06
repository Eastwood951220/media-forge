import type { StorageSubTask, StorageTaskLog } from '@/api/storage/storageTasks/types'

export const statusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  skipped: { text: '已跳过', color: 'default' },
}

export const levelColors: Record<string, string> = {
  DEBUG: 'default',
  INFO: 'processing',
  WARNING: 'warning',
  ERROR: 'error',
}

export const stepOrder = [
  'prepare',
  'submit_magnet',
  'waiting_download',
  'scan_files',
  'select_videos',
  'rename_files',
  'move_files',
  'verify_result',
  'cleanup_files',
]

export const stepLabels: Record<string, string> = {
  prepare: '准备任务',
  submit_magnet: '提交磁力',
  waiting_download: '云端下载',
  scan_files: '扫描文件',
  select_videos: '识别主视频',
  rename_files: '重命名',
  move_files: '移动文件',
  verify_result: '校验结果',
  cleanup_files: '清理临时文件',
}

export function logsForStep(logs: StorageTaskLog[], step: string) {
  return logs.filter((log) => log.step === step || log.context?.step === step)
}

export function stepColor(subtask: StorageSubTask, logs: StorageTaskLog[], step: string) {
  if (logs.some((log) => log.level === 'ERROR')) return 'red'
  if (logs.length > 0) return 'green'
  if (subtask.step === step) return 'blue'
  return 'gray'
}

export function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString()
}
