export interface ScrapingConfig {
  base_url: string
  api_key: string
  api_key_configured: boolean
  directory_id: number | null
  trigger_delay_seconds: number
  scrape_root: string
  media_root: string
  metadata_sources: string[]
}

export interface ScrapingConfigUpdate {
  base_url?: string
  api_key?: string
  directory_id?: number | null
  trigger_delay_seconds?: number
  scrape_root?: string
  media_root?: string
  metadata_sources?: string[]
}

export interface ScrapingRunResult {
  success: boolean
  status_code: number | null
  message: string
}

export interface ScrapingScanSummary {
  folders_scanned: number
  folders_with_strm: number
  scraped_folders: number
  not_scraped_folders: number
  matched_movies: number
  updated_movies: number
  unmatched_folders: string[]
  duration_ms: number
}
