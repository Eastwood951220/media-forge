export type ScrapingTaskStatus =
  | 'queued'
  | 'running'
  | 'success'
  | 'partial_failed'
  | 'failed'
  | 'cancelled'

export type ScrapingItemStatus = 'pending' | 'running' | 'success' | 'failed' | 'skipped'

export interface ScrapingTask {
  id: string
  status: ScrapingTaskStatus
  total_count: number
  success_count: number
  failed_count: number
  skipped_count: number
  cancel_requested: boolean
  created_by: string
  created_at?: string | null
  queued_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  error_message?: string | null
}

export interface ScrapingTaskItem {
  id: string
  task_id: string
  movie_id: string
  movie_code: string
  movie_title: string
  status: ScrapingItemStatus
  source: string
  folder: string
  duration_ms: number
  error_message?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ScrapingTaskDetail extends ScrapingTask {
  items: ScrapingTaskItem[]
}

export interface ScrapingTaskListResponse {
  rows: ScrapingTask[]
  total: number
  page: number
  size: number
}
