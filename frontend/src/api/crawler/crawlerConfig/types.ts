/** A single cookie entry matching the browser-export format. */
export interface JavdbCookie {
  domain: string
  expirationDate: number | null
  hostOnly: boolean
  httpOnly: boolean
  name: string
  path: string
  sameSite: string | null
  secure: boolean
  session: boolean
  storeId: string | null
  value: string
}

/** Wrapper for the cookie array stored in the JSON file. */
export interface CookiesConfig {
  cookies: JavdbCookie[]
}

export type JavdbFetchMode = 'static' | 'browser'

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

export interface JavDBSessionStatus {
  profile_exists: boolean
  storage_state_exists: boolean
  verification_browser_open: boolean
  last_check_at?: string | null
  last_check_url?: string | null
  last_status_code?: number | null
  last_reason: string
  last_message: string
  logged_in_detected: boolean
  runtime_environment: string
}

export interface JavDBSessionCheck {
  ok: boolean
  status_code: number | null
  reason: string
  message: string
  url: string
  logged_in_detected: boolean
  checked_at?: string | null
  runtime_environment: string
}

export interface JavDBSessionExportResponse {
  path: string
}
