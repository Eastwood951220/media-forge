import type { CrawlTaskRuntimeSnapshot } from '@/api/crawler/crawlTask/types'
import type { RunLogEntry, RunTaskSummary } from '@/api/crawler/crawlerRun/types'
import type { AgentEvent } from '@/api/crawler/crawlerAgent/types'
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

/** Minimal run runtime payload — status-only, no full CrawlRun object. */
export type CrawlRunRuntime = {
  run_id: string
  status: string
  error: string | null
  started_at: string | null
  finished_at: string | null
  state_updated_at: string
}

/** Snapshot payload containing all task runtimes and aggregate stats. */
export type CrawlerTaskRuntimeSnapshotPayload = {
  tasks: CrawlTaskRuntimeSnapshot[]
  stats: {
    total: number
    idle: number
    running: number
    queued: number
    stopped: number
  }
  reason?: string
  generated_at?: string
}

/** Minimal detail task patch for realtime updates (no timestamps, no full object). */
export type CrawlRunDetailTaskPatch = {
  id: string
  status: string
  error: string | null
  code: string | null
  source_name: string
  source_url_name: string | null
  task_url_type: string | null
  display_code: string | null
  display_source_name: string | null
}

export type CrawlerRunStatusUpdatedPayload = CrawlRunRuntime

export type CrawlerRunDetailUpdatedPayload = {
  run_id: string
  tasks: CrawlRunDetailTaskPatch[]
  refresh_tasks?: boolean
  reason?: string
  summary?: RunTaskSummary
}

export type CrawlerRunLogAppendedPayload = {
  run_id: string
  log: RunLogEntry
}

export type CrawlerTaskStatusUpdatedPayload = CrawlTaskRuntimeSnapshot

export type CrawlerTaskRuntimeSnapshotPayloadEvent = {
  reason?: string
  generated_at?: string
  tasks: CrawlTaskRuntimeSnapshot[]
  stats: {
    total: number
    idle: number
    running: number
    queued: number
    stopped: number
  }
}

export type StorageMainUpdatedPayload = Pick<
  StorageMainTask,
  'id' | 'status' | 'total_count' | 'success_count' | 'failed_count' | 'skipped_count'
> & Partial<StorageMainTask>

export type StorageMainDeletedPayload = {
  id: string
}

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

/** Real-time Agent diagnostic event payload matches the REST AgentEvent contract. */
export type CrawlerAgentEventCreatedPayload = AgentEvent

export type RealtimeEventName =
  | 'system.connected'
  | 'system.resync_required'
  | 'crawler.agent.event.created'
  | 'crawler.run.status.updated'
  | 'crawler.run.detail.updated'
  | 'crawler.run.log.appended'
  | 'crawler.task.runtime.snapshot'
  | 'crawler.task.status.updated'
  | 'storage.main.updated'
  | 'storage.main.deleted'
  | 'storage.sub.updated'
  | 'storage.sub.log.appended'
  | 'storage.queue.updated'
  | 'movie.storage.updated'

export type RealtimeHandler<TPayload = Record<string, unknown>> = (
  event: RealtimeEvent<TPayload>,
) => void