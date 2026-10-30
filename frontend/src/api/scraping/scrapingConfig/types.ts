export interface ScrapingConfig {
  base_url: string
  api_key: string
  api_key_configured: boolean
  directory_id: number | null
  trigger_delay_seconds: number
  scrape_root: string
  media_root: string
  metadata_sources: string[]
  metatube_url: string
  metatube_token: string
  metatube_token_configured: boolean
  jellyfin_base_url: string
  jellyfin_api_key: string
  jellyfin_api_key_configured: boolean
  jellyfin_auto_refresh_enabled: boolean
  jellyfin_watch_sync_enabled: boolean
  jellyfin_watch_sync_schedule_type: 'daily' | 'weekly'
  jellyfin_watch_sync_time_of_day: string
  jellyfin_watch_sync_weekdays: number[]
}

export interface ScrapingConfigUpdate {
  base_url?: string
  api_key?: string
  directory_id?: number | null
  trigger_delay_seconds?: number
  scrape_root?: string
  media_root?: string
  metadata_sources?: string[]
  metatube_url?: string
  metatube_token?: string
  jellyfin_base_url?: string
  jellyfin_api_key?: string
  jellyfin_auto_refresh_enabled?: boolean
  jellyfin_watch_sync_enabled?: boolean
  jellyfin_watch_sync_schedule_type?: 'daily' | 'weekly'
  jellyfin_watch_sync_time_of_day?: string
  jellyfin_watch_sync_weekdays?: number[]
}

export interface ScrapingRunResult {
  success: boolean
  status_code: number | null
  message: string
}

export interface ScrapingDirectoryEntry {
  name: string
  path: string
}

export interface ScrapingDirectoryListing {
  path: string
  parent: string | null
  entries: ScrapingDirectoryEntry[]
  roots: ScrapingDirectoryEntry[]
  truncated: boolean
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
