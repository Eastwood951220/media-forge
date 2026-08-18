import { request } from '@/request'
import type {
  AgentEventPage,
  AgentEventQuery,
  AgentStatus,
  AgentTokenRotateResponse,
} from './types'

const BASE_URL = '/api/crawler/agent'

export function fetchAgentStatus(): Promise<AgentStatus> {
  return request.get<AgentStatus>(`${BASE_URL}/status`)
}

export function fetchAgentEvents(params: AgentEventQuery = {}): Promise<AgentEventPage> {
  return request.get<AgentEventPage>(`${BASE_URL}/events`, params)
}

export function clearOperationalAgentEvents(): Promise<{ deleted: number }> {
  return request.delete<{ deleted: number }>(`${BASE_URL}/events/operational`)
}

export function rotateAgentToken(): Promise<AgentTokenRotateResponse> {
  return request.post<AgentTokenRotateResponse>(`${BASE_URL}/token/rotate`, {})
}

export type {
  AgentEvent,
  AgentEventLevel,
  AgentEventPage,
  AgentEventQuery,
  AgentEventRetentionClass,
  AgentEventSource,
  AgentStatus,
  AgentStatusValue,
  AgentTokenRotateResponse,
  AgentWorkItem,
  AgentWorkItemPage,
  AgentWorkSummary,
} from './types'
