export const AGENT_PROTOCOL_VERSION = 2
export const AGENT_MINIMUM_PROTOCOL_VERSION = 2
export const AGENT_REQUIRED_CAPABILITIES = [
  'task_events',
  'attempt_guard',
  'execution_deadline',
] as const
export type AgentRequiredCapability = (typeof AGENT_REQUIRED_CAPABILITIES)[number]

export type AgentLocalStatus = {
  connected: boolean
  phase: 'idle' | 'connecting' | 'handshaking' | 'connected' | 'busy' | 'error'
  message: string
  updatedAt: string
}

export type AgentLocalDiagnostic = {
  timestamp: string
  level: 'info' | 'warning' | 'error'
  code: string
  message: string
}

export type AssignedTask = {
  agent_task_id: string
  run_id: string
  detail_task_id: string | null
  url_entry_id: string | null
  page_kind: 'list' | 'detail'
  url: string
  attempt: number
  execution_deadline_at: string
}

export type AgentTaskEventPayload = {
  agent_task_id: string
  attempt: number
  phase: string
  level: 'info' | 'warning' | 'error'
  code: string
  message: string
  details: Record<string, unknown>
}

export type AgentTaskFailedCode =
  | 'agent_tab_create_failed'
  | 'agent_page_load_failed'
  | 'agent_content_script_unavailable'
  | 'agent_snapshot_failed'

export type AgentTaskFailedPayload = {
  agent_task_id: string
  attempt: number
  phase: string
  code: AgentTaskFailedCode
  message: string
}

export type PageSnapshot = {
  page_kind: 'list' | 'detail'
  url: string
  source_page?: number
  fragments: Record<string, string>
}

export type AgentCookie = {
  name: string
  value: string
  domain: string
  path: string
  expirationDate?: number | null
  hostOnly: boolean
  httpOnly: boolean
  sameSite?: string | null
  secure: boolean
  session: boolean
  storeId?: string | null
}

export type AgentPageSnapshotPayload = {
  agent_task_id: string
  attempt: number
  snapshot: PageSnapshot
  cookies: AgentCookie[]
}

export type AgentTerminalMessage =
  | { id: string; type: 'agent.page_snapshot'; payload: AgentPageSnapshotPayload }
  | { id: string; type: 'agent.task_failed'; payload: AgentTaskFailedPayload }

export type TaskRunnerDeps = {
  now: () => number
  createTab: (url: string) => Promise<{ id?: number }>
  removeTab: (tabId: number) => Promise<void>
  waitForComplete: (tabId: number, deadlineAt: number) => Promise<void>
  collectSnapshot: (tabId: number) => Promise<{ snapshot?: PageSnapshot }>
  collectCookies: () => Promise<AgentCookie[]>
  emitEvent: (payload: AgentTaskEventPayload) => void
}

export type ServerMessage = {
  id: string
  type: string
  payload: Record<string, unknown>
}
