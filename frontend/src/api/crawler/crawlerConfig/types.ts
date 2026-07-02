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

/** Application config stored in env vars. */
export interface AppConfig {
  MAX_LIST_PAGES?: number
  LIST_PAGE_DELAY_MIN?: number
  LIST_PAGE_DELAY_MAX?: number
  DETAIL_PAGE_DELAY_MIN?: number
  DETAIL_PAGE_DELAY_MAX?: number
  SECURITY_WAIT_SECONDS?: number
  REQUEST_TIMEOUT?: number
  INCREMENTAL_EXIST_THRESHOLD?: number
  [key: string]: unknown
}
