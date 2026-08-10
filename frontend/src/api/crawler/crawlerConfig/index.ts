import { request } from '@/request'
import type { AppConfig, CookieTestResponse } from './types.ts'
import type { JavdbAgentStatus, JavdbAgentTokenRotateResponse } from './types.ts'

export type {
  AppConfig,
  CookieTestResponse,
  JavdbAgentStatus,
  JavdbAgentTokenRotateResponse,
  JavdbAgentParseMode,
  JavdbFetchMode,
} from './types.ts'

const BASE_URL = '/api/crawler/config'
const AGENT_BASE_URL = '/api/crawler/agent'

export function fetchConfig(): Promise<AppConfig> {
  return request.get<AppConfig>(BASE_URL)
}

export function updateConfig(data: Partial<AppConfig>): Promise<AppConfig> {
  return request.put<AppConfig>(BASE_URL, data)
}

export function testCookiesConfig(url?: string): Promise<CookieTestResponse> {
  return request.post<CookieTestResponse>(`${BASE_URL}/cookies/test`, url ? { url } : {})
}

export function fetchAgentStatus(): Promise<JavdbAgentStatus> {
  return request.get<JavdbAgentStatus>(`${AGENT_BASE_URL}/status`)
}

export function rotateAgentToken(): Promise<JavdbAgentTokenRotateResponse> {
  return request.post<JavdbAgentTokenRotateResponse>(`${AGENT_BASE_URL}/token/rotate`, {})
}
