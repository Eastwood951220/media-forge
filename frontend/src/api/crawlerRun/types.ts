export type CrawlMode = 'incremental' | 'full'
export type CrawlRunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'stopped'
export type DetailTaskStatus = 'pending_crawl' | 'crawled' | 'crawl_failed' | 'saved' | 'save_failed' | 'skipped'

export interface RunLogEntry {
  timestamp: string
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | string
  component?: string | null
  event?: string | null
  message: string
  context?: Record<string, unknown>
}

export interface CrawlRun {
  id: string
  task_id: string | null
  task_name: string
  status: CrawlRunStatus
  crawl_mode: CrawlMode
  queued_at: string | null
  started_at: string | null
  finished_at: string | null
  result: Record<string, unknown> | null
  error: string | null
  resumed_from: string | null
  created_at: string
  updated_at: string | null
  logs: RunLogEntry[]
}

export interface CrawlRunDetailTask {
  id: string
  run_id: string
  task_name: string
  code: string | null
  source_url: string
  source_name: string
  source_url_name?: string | null
  task_url?: string | null
  task_final_url?: string | null
  task_url_type?: string | null
  status: DetailTaskStatus
  error: string | null
  item_data: Record<string, unknown> | null
  created_at: string
  crawled_at: string | null
  saved_at: string | null
}

export interface QueueStatus {
  queue_size: number
  is_running: boolean
  current_run_id: string | null
  stop_requested: boolean
}

export interface RetryCrawlerRunTasksRequest {
  detail_ids?: string[]
  retry_all?: boolean
}

export interface RunTaskSummary {
  total: number
  pending_crawl: number
  crawling: number
  saved: number
  skipped: number
  crawl_failed: number
  save_failed: number
  completed: number
  waiting: number
  failed: number
}
