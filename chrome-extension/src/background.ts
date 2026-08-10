type AgentSettings = {
  backendUrl: string
  token: string
}

let socket: WebSocket | null = null
let heartbeatInterval: ReturnType<typeof setInterval> | null = null

async function settings(): Promise<AgentSettings | null> {
  const data = await chrome.storage.sync.get(['backendUrl', 'token'])
  if (!data.backendUrl || !data.token) return null
  return { backendUrl: String(data.backendUrl).replace(/\/$/, ''), token: String(data.token) }
}

async function createSession(config: AgentSettings): Promise<string> {
  const response = await fetch(`${config.backendUrl}/api/crawler/agent/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      token: config.token,
      version: chrome.runtime.getManifest().version,
      name: 'Chrome Agent',
    }),
  })
  if (!response.ok) throw new Error(`session_failed:${response.status}`)
  const payload = await response.json()
  return payload.data.session
}

async function javdbCookies() {
  const cookies = await chrome.cookies.getAll({ domain: 'javdb.com' })
  return cookies.map((cookie) => ({
    name: cookie.name,
    value: cookie.value,
    domain: cookie.domain,
    path: cookie.path,
    expirationDate: cookie.expirationDate ?? null,
    hostOnly: cookie.hostOnly,
    httpOnly: cookie.httpOnly,
    sameSite: cookie.sameSite ?? null,
    secure: cookie.secure,
    session: cookie.session,
    storeId: cookie.storeId ?? null,
  }))
}

function wsUrl(backendUrl: string, session: string): string {
  const url = new URL(backendUrl)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = '/api/crawler/agent/ws'
  url.search = `?session=${encodeURIComponent(session)}`
  return url.toString()
}

async function connect() {
  const config = await settings()
  if (!config) return
  const session = await createSession(config)
  socket = new WebSocket(wsUrl(config.backendUrl, session))
  socket.addEventListener('open', async () => {
    send('agent.hello', { version: chrome.runtime.getManifest().version })
    send('agent.cookie_sync', { cookies: await javdbCookies() })
    heartbeatInterval = setInterval(() => send('agent.heartbeat', {}), 20_000)
  })
  socket.addEventListener('message', (event) => {
    void handleServerMessage(JSON.parse(String(event.data)))
  })
}

function send(type: string, payload: Record<string, unknown>) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return
  socket.send(
    JSON.stringify({
      id: `msg_${crypto.randomUUID()}`,
      type,
      sent_at: new Date().toISOString(),
      payload,
    }),
  )
}

async function handleServerMessage(message: { type: string; payload?: Record<string, unknown> }) {
  if (message.type !== 'task.assigned') return
  const payload = message.payload ?? {}
  const url = String(payload.url)
  const tab = await chrome.tabs.create({ url, active: false })
  if (!tab.id) return
  await waitForTabComplete(tab.id)
  const responses = await chrome.tabs.sendMessage(tab.id, { type: 'collect_snapshot' })
  send('agent.page_snapshot', {
    agent_task_id: payload.agent_task_id,
    snapshot: responses.snapshot,
    cookies: await javdbCookies(),
  })
}

function waitForTabComplete(tabId: number): Promise<void> {
  return new Promise((resolve) => {
    const listener = (updatedTabId: number, changeInfo: chrome.tabs.TabChangeInfo) => {
      if (updatedTabId === tabId && changeInfo.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(listener)
        resolve()
      }
    }
    chrome.tabs.onUpdated.addListener(listener)
  })
}

void connect()
