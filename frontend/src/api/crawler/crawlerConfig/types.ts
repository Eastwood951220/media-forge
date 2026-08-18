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
  AGENT_CLAIM_TIMEOUT_SECONDS?: number
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
