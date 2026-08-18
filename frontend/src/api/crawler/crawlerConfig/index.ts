import { request } from '@/request'
import type { AppConfig, CookieTestResponse } from './types.ts'

export type { AppConfig, CookieTestResponse } from './types.ts'
export type { JavdbAgentParseMode, JavdbFetchMode } from './types.ts'

const BASE_URL = '/api/crawler/config'

export function fetchConfig(): Promise<AppConfig> {
  return request.get<AppConfig>(BASE_URL)
}

export function updateConfig(data: Partial<AppConfig>): Promise<AppConfig> {
  return request.put<AppConfig>(BASE_URL, data)
}

export function testCookiesConfig(url?: string): Promise<CookieTestResponse> {
  return request.post<CookieTestResponse>(`${BASE_URL}/cookies/test`, url ? { url } : {})
}
