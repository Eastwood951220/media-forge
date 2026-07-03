import type { CrawlTaskRuntimeSnapshot } from '@/api/crawlTask/types'
import type { CrawlRun, CrawlRunDetailTask, RunLogEntry } from '@/api/crawlerRun/types'

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

export type RealtimeEventName =
  | 'system.connected'
  | 'system.resync_required'
  | 'crawler.run.updated'
  | 'crawler.run.detail.updated'
  | 'crawler.run.log.appended'
  | 'crawler.queue.updated'
  | 'crawler.task.status.updated'

export type RealtimeHandler<TPayload = Record<string, unknown>> = (
  event: RealtimeEvent<TPayload>,
) => void
