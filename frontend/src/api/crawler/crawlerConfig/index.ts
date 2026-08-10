import { request } from '@/request'
import type { AppConfig, CookiesConfig, CookieTestResponse } from './types.ts'

export type { AppConfig, CookiesConfig, CookieTestResponse, JavdbCookie } from './types.ts'

const BASE_URL = '/api/crawler/config'

export function fetchConfig(): Promise<AppConfig> {
  return request.get<AppConfig>(BASE_URL)
}

export function updateConfig(data: Partial<AppConfig>): Promise<AppConfig> {
  return request.put<AppConfig>(BASE_URL, data)
}

export function fetchCookiesConfig(): Promise<CookiesConfig> {
  return request.get<CookiesConfig>(`${BASE_URL}/cookies`)
}

export function updateCookiesConfig(data: CookiesConfig): Promise<CookiesConfig> {
  return request.put<CookiesConfig>(`${BASE_URL}/cookies`, data)
}

export function testCookiesConfig(url?: string): Promise<CookieTestResponse> {
  return request.post<CookieTestResponse>(`${BASE_URL}/cookies/test`, url ? { url } : {})
}
