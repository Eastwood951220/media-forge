import type { AgentLocalDiagnostic, AgentLocalStatus } from './protocol'

const backendUrl = document.querySelector<HTMLInputElement>('#backendUrl')
const token = document.querySelector<HTMLInputElement>('#token')
const save = document.querySelector<HTMLButtonElement>('#save')
const connectionStatus = document.querySelector<HTMLElement>('#connectionStatus')
const statusUpdatedAt = document.querySelector<HTMLElement>('#statusUpdatedAt')
const latestError = document.querySelector<HTMLElement>('#latestError')

function renderStatus(status: AgentLocalStatus) {
  if (connectionStatus) {
    connectionStatus.textContent = `${status.phase}: ${status.message}`
  }
  if (statusUpdatedAt) {
    statusUpdatedAt.textContent = status.updatedAt ? `updated at ${status.updatedAt}` : '-'
  }
}

function renderLatestError(ring: AgentLocalDiagnostic[]) {
  if (!latestError) return
  const error = [...ring].reverse().find((d) => d.level === 'error')
  latestError.textContent = error ? `[${error.code}] ${error.message}` : ''
}

async function load() {
  const data = await chrome.storage.local.get(['agentStatus', 'agentDiagnosticRing'])
  if (data.agentStatus) renderStatus(data.agentStatus as AgentLocalStatus)
  if (data.agentDiagnosticRing) renderLatestError(data.agentDiagnosticRing as AgentLocalDiagnostic[])
}

chrome.storage.onChanged.addListener((changes) => {
  if (changes.agentStatus) renderStatus(changes.agentStatus.newValue as AgentLocalStatus)
  if (changes.agentDiagnosticRing) renderLatestError(changes.agentDiagnosticRing.newValue as AgentLocalDiagnostic[])
})

chrome.storage.sync.get(['backendUrl', 'token']).then((data) => {
  if (backendUrl) backendUrl.value = String(data.backendUrl ?? '')
  if (token) token.value = String(data.token ?? '')
})

load()

save?.addEventListener('click', async () => {
  await chrome.storage.sync.set({
    backendUrl: backendUrl?.value ?? '',
    token: token?.value ?? '',
  })
  try {
    await chrome.runtime.sendMessage({ type: 'agent_settings_saved' })
    if (connectionStatus) connectionStatus.textContent = 'Saved. Agent is reconnecting.'
  } catch (error) {
    if (connectionStatus) {
      connectionStatus.textContent = error instanceof Error ? error.message : 'Saved. Reload extension if needed.'
    }
  }
})
