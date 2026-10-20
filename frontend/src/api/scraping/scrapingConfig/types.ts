export interface ScrapingConfig {
  base_url: string
  api_key: string
  api_key_configured: boolean
  directory_id: number | null
  trigger_delay_seconds: number
}

export interface ScrapingConfigUpdate {
  base_url?: string
  api_key?: string
  directory_id?: number | null
  trigger_delay_seconds?: number
}

export interface ScrapingRunResult {
  success: boolean
  status_code: number | null
  message: string
}
