import { request } from '@/request'
import type {
  AppConfig,
  CookiesConfig,
  CookieTestResponse,
  JavDBSessionCheck,
  JavDBSessionExportResponse,
  JavDBSessionStatus,
} from './types.ts'

export type {
  AppConfig,
  CookiesConfig,
  CookieTestResponse,
  JavdbCookie,
  JavDBSessionCheck,
  JavDBSessionExportResponse,
  JavDBSessionStatus,
} from './types.ts'

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

export function fetchJavdbSessionStatus(): Promise<JavDBSessionStatus> {
  return request.get<JavDBSessionStatus>(`${BASE_URL}/javdb-session`)
}

export function openJavdbSession(url?: string): Promise<JavDBSessionStatus> {
  return request.post<JavDBSessionStatus>(`${BASE_URL}/javdb-session/open`, url ? { url } : {})
}

export function closeJavdbSession(): Promise<JavDBSessionStatus> {
  return request.post<JavDBSessionStatus>(`${BASE_URL}/javdb-session/close`, {})
}

export function checkJavdbSession(url?: string): Promise<JavDBSessionCheck> {
  return request.post<JavDBSessionCheck>(`${BASE_URL}/javdb-session/check`, url ? { url } : {})
}

export function exportJavdbSession(): Promise<JavDBSessionExportResponse> {
  return request.post<JavDBSessionExportResponse>(`${BASE_URL}/javdb-session/export`, {})
}

export function resetJavdbSession(): Promise<JavDBSessionStatus> {
  return request.delete<JavDBSessionStatus>(`${BASE_URL}/javdb-session`)
}
