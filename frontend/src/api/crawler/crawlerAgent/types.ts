export type AgentStatusValue =
  | 'not_configured'
  | 'offline'
  | 'online'
  | 'busy'
  | 'error'
  | 'upgrade_required'

export type AgentEventSource = 'backend' | 'extension'
export type AgentEventLevel = 'info' | 'warning' | 'error'
export type AgentEventRetentionClass = 'operational' | 'run_audit'

export interface AgentEvent {
  id: string
  agent_id: string | null
  run_id: string | null
  work_item_id: string | null
  attempt: number | null
  source: AgentEventSource
  event_type: string
  phase: string | null
  level: AgentEventLevel
  message: string
  details: Record<string, unknown> | null
  retention_class: AgentEventRetentionClass
  created_at: string
}

export interface AgentEventPage {
  rows: AgentEvent[]
  next_cursor: string | null
  has_more: boolean
}

export interface AgentWorkItem {
  id: string
  run_id: string
  task_id: string | null
  detail_task_id: string | null
  url_entry_id: string | null
  page_kind: string
  url: string
  status: string
  attempt: number
  error_reason: string | null
  queued_at: string | null
  assigned_at: string | null
  started_at: string | null
  finished_at: string | null
  assigned_agent_id: string | null
}

export interface AgentWorkSummary {
  pending: number
  active: number
  completed: number
  failed: number
  total: number
}

export interface AgentWorkItemPage {
  rows: AgentWorkItem[]
  summary: AgentWorkSummary
}

export interface AgentStatus {
  status: AgentStatusValue
  agent_id: string | null
  name: string | null
  protocol_version: number | null
  connected_at: string | null
  last_seen_at: string | null
  last_cookie_sync_at: string | null
  version: string | null
  current_work_item: AgentWorkItem | null
  pending_count: number
  active_count: number
}

export interface AgentEventQuery {
  cursor?: string
  size?: number
  level?: string
  source?: string
  phase?: string
  work_item_id?: string
  from_time?: string
  to_time?: string
}

export interface AgentTokenRotateResponse {
  token: string
  status: AgentStatus
}
