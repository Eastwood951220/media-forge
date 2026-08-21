import type { AgentLocalDiagnostic, AgentLocalStatus } from './protocol'

const version = document.querySelector<HTMLElement>('#version')
const statusDot = document.querySelector<HTMLElement>('#statusDot')
const statusLabel = document.querySelector<HTMLElement>('#statusLabel')
const statusMessage = document.querySelector<HTMLElement>('#statusMessage')
const updatedAt = document.querySelector<HTMLElement>('#updatedAt')
const backendUrl = document.querySelector<HTMLElement>('#backendUrl')
const tokenState = document.querySelector<HTMLElement>('#tokenState')
const latestError = document.querySelector<HTMLElement>('#latestError')
const diagnostics = document.querySelector<HTMLElement>('#diagnostics')
const reconnect = document.querySelector<HTMLButtonElement>('#reconnect')
const openOptions = document.querySelector<HTMLButtonElement>('#openOptions')
const copyDiagnostics = document.querySelector<HTMLButtonElement>('#copyDiagnostics')
const clearDiagnostics = document.querySelector<HTMLButtonElement>('#clearDiagnostics')

const statusLabels: Record<AgentLocalStatus['phase'], string> = {
  idle: 'Idle',
  connecting: 'Connecting',
  handshaking: 'Handshaking',
  connected: 'Connected',
  busy: 'Busy',
  error: 'Error',
}

let cachedStatus: AgentLocalStatus | null = null
let cachedDiagnostics: AgentLocalDiagnostic[] = []

function formatRelative(value: string | null | undefined): string {
  if (!value) return '-'
  const timestamp = Date.parse(value)
  if (Number.isNaN(timestamp)) return '-'
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ago`
}

function formatTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString()
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function renderStatus(status: AgentLocalStatus | null) {
  cachedStatus = status
  if (!status) {
    if (statusLabel) statusLabel.textContent = 'Not configured'
    if (statusMessage) statusMessage.textContent = 'No local agent status is available.'
    if (updatedAt) updatedAt.textContent = '-'
    statusDot?.classList.remove(
      'status-idle',
      'status-connected',
      'status-busy',
      'status-connecting',
      'status-handshaking',
      'status-error',
    )
    return
  }

  if (statusLabel) statusLabel.textContent = statusLabels[status.phase] ?? status.phase
  if (statusMessage) statusMessage.textContent = status.message
  if (updatedAt) updatedAt.textContent = formatRelative(status.updatedAt)
  if (statusDot) {
    statusDot.className = `dot status-${status.phase}`
  }
}

function renderDiagnostics(ring: AgentLocalDiagnostic[]) {
  cachedDiagnostics = ring
  const recent = ring.slice(-5).reverse()
  const error = [...ring].reverse().find((entry) => entry.level === 'error')
  if (latestError) {
    latestError.textContent = error ? error.message : '-'
    latestError.classList.toggle('error-text', Boolean(error))
  }
  if (!diagnostics) return
  if (recent.length === 0) {
    diagnostics.innerHTML = '<div class="muted">No diagnostics yet.</div>'
    return
  }
  diagnostics.innerHTML = recent.map((entry) => {
    const messageClass = entry.level === 'error' ? 'diagnostic-message error-text' : 'diagnostic-message'
    return `
      <div class="diagnostic">
        <div class="diagnostic-meta">${escapeHtml(formatTime(entry.timestamp))} · ${escapeHtml(entry.level)} · ${escapeHtml(entry.code)}</div>
        <div class="${messageClass}">${escapeHtml(entry.message)}</div>
      </div>
    `
  }).join('')
}

async function renderSettings() {
  const data = await chrome.storage.sync.get(['backendUrl', 'token'])
  if (backendUrl) backendUrl.textContent = data.backendUrl ? String(data.backendUrl) : 'Not set'
  if (tokenState) tokenState.textContent = data.token ? 'Configured' : 'Missing'
}

async function load() {
  if (version) version.textContent = `v${chrome.runtime.getManifest().version}`
  const data = await chrome.storage.local.get(['agentStatus', 'agentDiagnosticRing'])
  renderStatus((data.agentStatus as AgentLocalStatus | undefined) ?? null)
  renderDiagnostics(
    Array.isArray(data.agentDiagnosticRing)
      ? data.agentDiagnosticRing as AgentLocalDiagnostic[]
      : [],
  )
  await renderSettings()
}

async function requestReconnect() {
  if (statusMessage) statusMessage.textContent = 'Reconnect requested...'
  try {
    await chrome.runtime.sendMessage({ type: 'agent_reconnect_requested' })
    if (statusMessage) statusMessage.textContent = 'Reconnect request sent.'
  } catch (error) {
    if (statusMessage) {
      statusMessage.textContent = error instanceof Error
        ? error.message
        : 'Reconnect failed. Reload extension if needed.'
    }
  }
}

async function copyCurrentDiagnostics() {
  const payload = {
    status: cachedStatus,
    diagnostics: cachedDiagnostics.slice(-20),
  }
  await navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
  if (statusMessage) statusMessage.textContent = 'Diagnostics copied.'
}

async function clearLocalDiagnostics() {
  await chrome.storage.local.set({ agentDiagnosticRing: [] })
  renderDiagnostics([])
  if (statusMessage) statusMessage.textContent = 'Local diagnostics cleared.'
}

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === 'local') {
    if (changes.agentStatus) {
      renderStatus((changes.agentStatus.newValue as AgentLocalStatus | undefined) ?? null)
    }
    if (changes.agentDiagnosticRing) {
      renderDiagnostics(
        Array.isArray(changes.agentDiagnosticRing.newValue)
          ? changes.agentDiagnosticRing.newValue as AgentLocalDiagnostic[]
          : [],
      )
    }
  }
  if (areaName === 'sync' && (changes.backendUrl || changes.token)) {
    void renderSettings()
  }
})

reconnect?.addEventListener('click', () => {
  void requestReconnect()
})

openOptions?.addEventListener('click', () => {
  chrome.runtime.openOptionsPage()
})

copyDiagnostics?.addEventListener('click', () => {
  void copyCurrentDiagnostics()
})

clearDiagnostics?.addEventListener('click', () => {
  void clearLocalDiagnostics()
})

void load()
