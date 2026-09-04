export type ScheduleType = 'daily' | 'weekly'
export type StorageMode = 'single' | 'multiple'

export interface CrawlerSchedule {
  id: string
  name: string
  enabled: boolean
  schedule_type: ScheduleType
  time_of_day: string
  weekdays: number[]
  auto_storage_enabled: boolean
  storage_mode: StorageMode
  selected_storage_location: string | null
  task_count: number
  tasks: Array<{ id: string; name: string; is_skip: boolean }>
  last_triggered_at: string | null
  next_run_at: string | null
  latest_run_status: string | null
  created_at: string
  updated_at: string | null
}

export interface CrawlerSchedulePayload {
  name: string
  enabled: boolean
  task_ids: string[]
  schedule_type: ScheduleType
  time_of_day: string
  weekdays: number[]
  auto_storage_enabled: boolean
  storage_mode: StorageMode
  selected_storage_location: string | null
}

export interface CrawlerSchedulePage {
  rows: CrawlerSchedule[]
  total: number
  page: number
  size: number
}

export interface CrawlerScheduleRunTaskResult {
  task_id?: string
  run_id?: string
  reason?: string
}

export interface CrawlerScheduleRunResult {
  reason?: string
  accepted?: CrawlerScheduleRunTaskResult[]
  skipped?: CrawlerScheduleRunTaskResult[]
  failed?: CrawlerScheduleRunTaskResult[]
}

export interface CrawlerScheduleRun {
  id: string
  schedule_id: string
  status: string
  trigger_type: string
  triggered_at: string
  finished_at: string | null
  result: CrawlerScheduleRunResult
  storage_status: string
  storage_task_id: string | null
  storage_error: string | null
  crawl_run_ids: string[]
}

export interface CrawlerScheduleRunPage {
  rows: CrawlerScheduleRun[]
  total: number
  page: number
  size: number
}
