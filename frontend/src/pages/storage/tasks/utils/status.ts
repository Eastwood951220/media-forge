import type { StorageMainTaskStatus, StorageMode, StorageSubTask } from '@/api/storage/storageTasks/types'
import type { StorageSubUpdatedPayload } from '@/realtime/types'

export const statusLabels: Record<StorageMainTaskStatus, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  stopping: { text: '停止中', color: 'warning' },
  stopped: { text: '已停止', color: 'warning' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
}

export const subTaskStatusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  skipped: { text: '已跳过', color: 'default' },
}

export const modeLabels: Record<StorageMode, string> = {
  single: '单盘',
  multiple: '多盘',
}

export const PAGE_SIZE_OPTIONS = ['10', '20', '50']

export function mergeSubtaskUpdate(current: StorageSubTask[], update: StorageSubUpdatedPayload): StorageSubTask[] {
  let matched = false
  const next = current.map((subtask) => {
    if (subtask.id !== update.id) return subtask
    matched = true
    return { ...subtask, ...update }
  })
  return matched ? next : current
}
