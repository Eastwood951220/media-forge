export interface CrawlTask {
  id: string
  name: string
  description: string | null
  keywords: string[]
  target_websites: string[]
  schedule: string | null
  max_pages: number
  crawl_depth: number
  status: string
  task_id: string | null
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  total_found: number
  total_qualified: number
  owner_id: string
  created_at: string
  updated_at: string | null
}

export interface PaginatedResponse<T> {
  rows: T[]
  total: number
  page: number
  page_size: number
}

export interface CrawlTaskCreateParams {
  name: string
  description?: string
  keywords: string[]
  target_websites: string[]
  schedule?: string
  max_pages?: number
  crawl_depth?: number
}

export interface CrawlTaskUpdateParams {
  name?: string
  description?: string
  keywords?: string[]
  target_websites?: string[]
  schedule?: string
  max_pages?: number
  crawl_depth?: number
}

export interface CrawlTaskStats {
  total: number
}
