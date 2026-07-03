export interface TaskUrlEntry {
  id?: string
  position?: number
  url: string
  url_type: string
  has_magnet?: boolean
  has_chinese_sub?: boolean
  sort_type?: number
  source?: string
  final_url?: string
  url_name?: string | null
}

export interface CrawlTask {
  id: string
  _id?: string
  name: string
  storage_location: string
  urls: TaskUrlEntry[]
  is_skip: boolean
  status: string
  task_id: string | null
  error_message: string | null
  total_found: number
  total_qualified: number
  owner_id: string
  created_at: string
  updated_at: string | null
  last_run_at: string | null
  last_run_status: string | null
}

export interface PaginatedResponse<T> {
  rows: T[]
  total: number
  page?: number
  page_size?: number
  code?: number
  msg?: string
}

export interface CrawlTaskCreateParams {
  name: string
  storage_location: string
  urls: TaskUrlEntry[]
  is_skip?: boolean
}

export interface CrawlTaskUpdateParams {
  name?: string
  urls?: TaskUrlEntry[]
  is_skip?: boolean
}

export interface CrawlTaskStats {
  total: number
  enabled: number
  disabled: number
}

export type DeleteMode = 'task_only' | 'task_and_movies' | 'task_movies_and_cloud'

export interface DeleteTaskResult {
  deleted_task: boolean
  deleted_runs: number
  deleted_detail_tasks: number
  updated_movies: number
  deleted_movies: number
  deleted_magnets: number
  cloud_delete: string
}

export interface TaskDictItem {
  id: string
  name: string
}

export interface TaskRuntimeStatus {
  task_id: string
  name: string
  is_skip: boolean
  status: 'pending' | 'running' | 'success' | 'failed'
  latest_run_id: string | null
  latest_run_status: string | null
}

export interface TaskRuntimeStatusResponse {
  tasks: TaskRuntimeStatus[]
}
