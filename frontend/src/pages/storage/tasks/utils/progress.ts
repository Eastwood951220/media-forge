import type { StorageMainTask } from '@/api/storage/storageTasks/types'

/**
 * Softened progress status: a task only shows the exception bar when it ended
 * in 'failed' without any successful or skipped work. Mixed results with some
 * successes keep the normal (blue) progress style.
 */
export function getProgressStatus(task: StorageMainTask): 'exception' | undefined {
  const hasAnySuccess = task.success_count + task.skipped_count > 0
  if (task.status === 'failed' && !hasAnySuccess) return 'exception'
  return undefined
}
