export const TASK_STATUS_TEXT: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  success: '成功',
  partial_failed: '部分失败',
  failed: '失败',
  cancelled: '已取消',
}

export const TASK_STATUS_COLOR: Record<string, string> = {
  queued: 'default',
  running: 'processing',
  success: 'success',
  partial_failed: 'warning',
  failed: 'error',
  cancelled: 'default',
}

export const ITEM_STATUS_TEXT: Record<string, string> = {
  pending: '等待中',
  running: '刮削中',
  success: '成功',
  failed: '失败',
  skipped: '跳过',
}

export const ITEM_STATUS_COLOR: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  success: 'success',
  failed: 'error',
  skipped: 'warning',
}
