export type JavdbFetchMode = 'static' | 'agent'
export type JavdbAgentParseMode = 'backend' | 'extension'

/** Application config stored in env vars. */
export interface AppConfig {
  MAX_LIST_PAGES?: number
  LIST_MAX_WORKERS?: number
  DETAIL_MAX_WORKERS?: number
  LIST_PAGE_DELAY_MIN?: number
  LIST_PAGE_DELAY_MAX?: number
  DETAIL_PAGE_DELAY_MIN?: number
  DETAIL_PAGE_DELAY_MAX?: number
  SECURITY_WAIT_SECONDS?: number
  REQUEST_TIMEOUT?: number
  INCREMENTAL_EXIST_THRESHOLD?: number
  JAVDB_FETCH_MODE?: JavdbFetchMode
  JAVDB_AGENT_PARSE_MODE?: JavdbAgentParseMode
  [key: string]: unknown
}

export interface CookieTestResponse {
  ok: boolean
  status_code: number | null
  reason: string
  message: string
  url: string
  logged_in_detected: boolean
  fetch_mode: string
}

export interface JavdbAgentStatus {
  status: 'not_configured' | 'offline' | 'online' | 'busy' | 'error'
  agent_id?: string | null
  name?: string | null
  last_seen_at?: string | null
  last_cookie_sync_at?: string | null
  version?: string | null
}

export interface JavdbAgentTokenRotateResponse {
  token: string
  status: JavdbAgentStatus
}
