import type { CrawlTaskRuntimeSnapshot } from '@/api/crawlTask/types'
import type { CrawlRun, CrawlRunDetailTask, RunLogEntry } from '@/api/crawlerRun/types'
import type { StorageMainTask, StorageTaskLog } from '@/api/storage/storageTasks/types'

export type RealtimeEvent<TPayload = Record<string, unknown>> = {
  id: string
  event: string
  scope: string
  resource_id: string | null
  owner_id: string
  payload: TPayload
  created_at: string
}

export type CrawlerRunUpdatedPayload = CrawlRun

export type CrawlerRunDetailUpdatedPayload = {
  run_id: string
  tasks: CrawlRunDetailTask[]
}

export type CrawlerRunLogAppendedPayload = {
  run_id: string
  log: RunLogEntry
}

export type CrawlerTaskStatusUpdatedPayload = CrawlTaskRuntimeSnapshot

export type StorageMainUpdatedPayload = Pick<
  StorageMainTask,
  'id' | 'status' | 'total_count' | 'success_count' | 'failed_count' | 'skipped_count'
> & Partial<StorageMainTask>

export type StorageSubUpdatedPayload = {
  id: string
  main_task_id: string
  movie_id: string
  status: string
  step: string
  error_message?: string | null
}

export type StorageSubLogAppendedPayload = StorageTaskLog

export type MovieStorageUpdatedPayload = {
  movie_id: string
  storage_summary: Record<string, unknown>
}

export type RealtimeEventName =
  | 'system.connected'
  | 'system.resync_required'
  | 'crawler.run.updated'
  | 'crawler.run.detail.updated'
  | 'crawler.run.log.appended'
  | 'crawler.queue.updated'
  | 'crawler.task.status.updated'
  | 'storage.main.updated'
  | 'storage.sub.updated'
  | 'storage.sub.log.appended'
  | 'storage.queue.updated'
  | 'movie.storage.updated'

export type RealtimeHandler<TPayload = Record<string, unknown>> = (
  event: RealtimeEvent<TPayload>,
) => void
