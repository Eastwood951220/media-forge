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
}
