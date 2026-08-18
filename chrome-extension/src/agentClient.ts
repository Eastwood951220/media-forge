import { runAssignedTask, waitForTabComplete } from './taskRunner'
import type {
  AgentCookie,
  AgentLocalDiagnostic,
  AgentLocalStatus,
  AssignedTask,
  PageSnapshot,
  ServerMessage,
  TaskRunnerDeps,
} from './protocol'

export type AgentSettings = {
  backendUrl: string
  token: string
}

export type AgentClientDeps = {
  fetch: typeof fetch
  WebSocket: typeof WebSocket
  setInterval: (callback: () => void, delay: number) => number
  clearInterval: (id?: number) => void
  setTimeout: (callback: () => void, delay: number) => number
  clearTimeout: (id?: number) => void
  runtimeVersion: () => string
  settings: () => Promise<AgentSettings | null>
  createSession: (config: AgentSettings) => Promise<string>
  javdbCookies: () => Promise<Record<string, unknown>[]>
  createTab: (url: string) => Promise<{ id?: number }>
  removeTab: (tabId: number) => Promise<void>
  waitForTabComplete: (tabId: number, deadlineAt: number) => Promise<void>
  collectSnapshot: (tabId: number) => Promise<{ snapshot?: PageSnapshot }>
  collectCookies: () => Promise<AgentCookie[]>
  setLocalStatus: (status: Omit<AgentLocalStatus, 'updatedAt'>) => Promise<void>
  appendLocalDiagnostic: (
    level: AgentLocalDiagnostic['level'],
    code: string,
    message: string,
  ) => Promise<void>
  drainUploadableDiagnostics: () => Promise<AgentLocalDiagnostic[]>
  removeDiagnostics: (entries: AgentLocalDiagnostic[]) => Promise<void>
}

const RECONNECT_DELAYS_MS = [1000, 2000, 5000, 10000, 30000]
const JITTER_MS = 300
const DEFAULT_HEARTBEAT_INTERVAL_MS = 20_000

export class AgentClient {
  private socket: WebSocket | null = null
  private heartbeatTimer: number | null = null
  private reconnectTimer: number | null = null
  private taskPollTimer: number | null = null
  private requestOutstanding = false
  private activeTask: AssignedTask | null = null
  private terminalMessageId: string | null = null
  private pendingDiagnostics: AgentLocalDiagnostic[] | null = null
  private pendingDiagnosticsMessageId: string | null = null
  private heartbeatIntervalMs = DEFAULT_HEARTBEAT_INTERVAL_MS
  private handshakeComplete = false
  private reconnectAttempt = 0
  private stopping = false

  constructor(private readonly deps: AgentClientDeps) {}

  async start(): Promise<void> {
    if (this.stopping) return
    await this.deps.setLocalStatus({
      connected: false,
      phase: 'connecting',
      message: 'connecting',
    })
    const config = await this.deps.settings()
    if (!config) {
      await this.deps.setLocalStatus({
        connected: false,
        phase: 'idle',
        message: 'missing_settings',
      })
      return
    }
    try {
      const session = await this.deps.createSession(config)
      const url = this.wsUrl(config.backendUrl, session)
      const socket = new this.deps.WebSocket(url)
      this.socket = socket
      socket.addEventListener('open', () => {
        if (this.socket === socket) void this.onOpen()
      })
      socket.addEventListener('message', (event) => {
        if (this.socket === socket) void this.onMessage(event)
      })
      socket.addEventListener('close', () => {
        if (this.socket === socket) void this.onClose()
      })
      socket.addEventListener('error', () => {
        if (this.socket === socket) void this.onError()
      })
    } catch (error) {
      await this.deps.setLocalStatus({
        connected: false,
        phase: 'error',
        message: error instanceof Error ? error.message : 'connect_failed',
      })
      this.scheduleReconnect()
    }
  }

  async stop(): Promise<void> {
    this.stopping = true
    this.clearTimers()
    if (this.socket) {
      this.socket.close()
      this.socket = null
    }
  }

  async settingsChanged(): Promise<void> {
    this.reconnectAttempt = 0
    await this.stop()
    this.stopping = false
    await this.start()
  }

  private wsUrl(backendUrl: string, session: string): string {
    const url = new URL(backendUrl)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.pathname = '/api/crawler/agent/ws'
    url.search = `?session=${encodeURIComponent(session)}`
    return url.toString()
  }

  private async onOpen(): Promise<void> {
    await this.deps.setLocalStatus({
      connected: true,
      phase: 'handshaking',
      message: 'handshaking',
    })
  }

  private async onMessage(event: MessageEvent): Promise<void> {
    let message: ServerMessage
    try {
      message = JSON.parse(String(event.data))
    } catch {
      return
    }

    if (message.type === 'server.hello') {
      const payload = message.payload as Record<string, unknown>
      const intervalSeconds = Number(payload.heartbeat_interval_seconds ?? 20)
      this.heartbeatIntervalMs =
        Number.isFinite(intervalSeconds) && intervalSeconds > 0
          ? intervalSeconds * 1000
          : DEFAULT_HEARTBEAT_INTERVAL_MS
      this.send('agent.hello', {
        protocol_version: 2,
        version: this.deps.runtimeVersion(),
        capabilities: ['task_events', 'attempt_guard', 'execution_deadline'],
      })
      return
    }

    if (message.type === 'server.ack' && !this.handshakeComplete) {
      this.handshakeComplete = true
      this.reconnectAttempt = 0
      await this.deps.setLocalStatus({
        connected: true,
        phase: 'connected',
        message: 'connected',
      })
      this.startHeartbeat()
      await this.sendCookieSync()
      await this.sendDiagnosticsBatch()
      this.requestTask()
      return
    }

    if (!this.handshakeComplete) return

    if (message.type === 'task.none') {
      this.requestOutstanding = false
      if (this.taskPollTimer) {
        this.deps.clearTimeout(this.taskPollTimer)
        this.taskPollTimer = null
      }
      const retryAfter = Number(message.payload?.retry_after_ms ?? 1000)
      this.taskPollTimer = this.deps.setTimeout(() => {
        this.taskPollTimer = null
        this.requestTask()
      }, Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : 1000)
      return
    }

    if (message.type === 'task.assigned') {
      this.requestOutstanding = false
      if (this.taskPollTimer) {
        this.deps.clearTimeout(this.taskPollTimer)
        this.taskPollTimer = null
      }
      if (this.activeTask) return
      const payload = message.payload as Record<string, unknown>
      this.activeTask = {
        agent_task_id: String(payload.agent_task_id),
        run_id: String(payload.run_id),
        detail_task_id: payload.detail_task_id ? String(payload.detail_task_id) : null,
        url_entry_id: payload.url_entry_id ? String(payload.url_entry_id) : null,
        page_kind: payload.page_kind === 'detail' ? 'detail' : 'list',
        url: String(payload.url),
        attempt: Number(payload.attempt),
        execution_deadline_at: String(payload.execution_deadline_at),
      }
      await this.runTask()
      return
    }

    if (message.type === 'server.ack') {
      const ackId = String(message.id)
      if (this.pendingDiagnosticsMessageId && ackId === `ack_${this.pendingDiagnosticsMessageId}`) {
        await this.deps.removeDiagnostics(this.pendingDiagnostics ?? [])
        this.pendingDiagnostics = null
        this.pendingDiagnosticsMessageId = null
      }
      if (this.terminalMessageId && ackId === `ack_${this.terminalMessageId}`) {
        this.terminalMessageId = null
        this.activeTask = null
        this.requestTask()
      }
      return
    }
  }

  private async onClose(): Promise<void> {
    const wasStopping = this.stopping
    this.clearTimers()
    this.socket = null
    this.handshakeComplete = false
    this.activeTask = null
    this.terminalMessageId = null
    this.requestOutstanding = false
    this.pendingDiagnostics = null
    this.pendingDiagnosticsMessageId = null
    await this.deps.appendLocalDiagnostic('error', 'connection.closed', 'WebSocket closed')
    await this.deps.setLocalStatus({
      connected: false,
      phase: 'error',
      message: 'socket_closed',
    })
    if (!wasStopping) {
      this.scheduleReconnect()
    }
  }

  private async onError(): Promise<void> {
    await this.deps.appendLocalDiagnostic('error', 'connection.error', 'WebSocket error')
  }

  private startHeartbeat(): void {
    if (this.heartbeatTimer) {
      this.deps.clearInterval(this.heartbeatTimer)
    }
    this.heartbeatTimer = this.deps.setInterval(() => {
      this.send('agent.heartbeat', {})
    }, this.heartbeatIntervalMs)
  }

  private async sendCookieSync(): Promise<void> {
    const cookies = await this.deps.javdbCookies()
    this.send('agent.cookie_sync', { cookies })
  }

  private async sendDiagnosticsBatch(): Promise<void> {
    const diagnostics = await this.deps.drainUploadableDiagnostics()
    if (diagnostics.length === 0) return
    this.pendingDiagnostics = diagnostics
    this.pendingDiagnosticsMessageId = this.send('agent.diagnostics_batch', {
      events: diagnostics.map((d) => ({
        source: 'extension',
        event_type: d.code,
        level: d.level,
        message: d.message,
        details: {},
      })),
    })
  }

  private requestTask(): void {
    if (this.requestOutstanding || this.activeTask) return
    this.requestOutstanding = true
    this.send('agent.task_request', {})
  }

  private send(type: string, payload: Record<string, unknown>): string | null {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return null
    const id = `msg_${crypto.randomUUID()}`
    this.socket.send(
      JSON.stringify({
        id,
        type,
        sent_at: new Date().toISOString(),
        payload,
      }),
    )
    return id
  }

  private clearTimers(): void {
    if (this.heartbeatTimer) {
      this.deps.clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
    if (this.reconnectTimer) {
      this.deps.clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.taskPollTimer) {
      this.deps.clearTimeout(this.taskPollTimer)
      this.taskPollTimer = null
    }
  }

  private scheduleReconnect(): void {
    if (this.stopping) return
    const delay =
      RECONNECT_DELAYS_MS[Math.min(this.reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)]
    const jitter = Math.floor(Math.random() * JITTER_MS)
    this.reconnectAttempt += 1
    this.reconnectTimer = this.deps.setTimeout(() => {
      this.reconnectTimer = null
      this.stopping = false
      void this.start()
    }, delay + jitter)
  }

  private async runTask(): Promise<void> {
    if (!this.activeTask) return
    await this.deps.setLocalStatus({
      connected: true,
      phase: 'busy',
      message: 'busy',
    })
    const taskRunnerDeps: TaskRunnerDeps = {
      now: Date.now,
      createTab: this.deps.createTab,
      removeTab: this.deps.removeTab,
      waitForComplete: this.deps.waitForTabComplete,
      collectSnapshot: this.deps.collectSnapshot,
      collectCookies: this.deps.collectCookies,
      emitEvent: (payload) => {
        this.send('agent.task_event', payload)
      },
    }
    const result = await runAssignedTask(this.activeTask, taskRunnerDeps)
    const messageId = this.send(result.type, result.payload)
    if (messageId) {
      this.terminalMessageId = messageId
    }
  }
}

export { waitForTabComplete, runAssignedTask }
export type { AssignedTask, ServerMessage }
