import { AgentClient } from './agentClient'
import {
  appendLocalDiagnostic,
  drainUploadableDiagnostics,
  removeDiagnostics,
  setLocalStatus,
} from './diagnostics'
import type { AgentClientDeps, AgentSettings } from './agentClient'

const AGENT_WAKE_ALARM = 'media_forge_agent_wake'
const AGENT_WAKE_PERIOD_MINUTES = 10

async function settings(): Promise<AgentSettings | null> {
  const data = await chrome.storage.sync.get(['backendUrl', 'token'])
  if (!data.backendUrl || !data.token) return null
  return {
    backendUrl: String(data.backendUrl).replace(/\/$/, ''),
    token: String(data.token),
  }
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

async function createTab(url: string) {
  return chrome.tabs.create({ url, active: false })
}

async function removeTab(tabId: number) {
  await chrome.tabs.remove(tabId)
}

function waitForTabComplete(tabId: number, deadlineAt: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const remaining = deadlineAt - Date.now()
    if (remaining <= 0) {
      reject(new Error('deadline_exceeded'))
      return
    }
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener)
      reject(new Error('deadline_exceeded'))
    }, remaining)
    const listener = (updatedTabId: number, changeInfo: chrome.tabs.TabChangeInfo) => {
      if (updatedTabId === tabId && changeInfo.status === 'complete') {
        clearTimeout(timer)
        chrome.tabs.onUpdated.removeListener(listener)
        resolve()
      }
    }
    chrome.tabs.onUpdated.addListener(listener)
  })
}

async function collectSnapshot(tabId: number) {
  const responses = await chrome.tabs.sendMessage(tabId, { type: 'collect_snapshot' })
  return { snapshot: responses?.snapshot }
}

async function collectCookies() {
  return javdbCookies()
}

const deps: AgentClientDeps = {
  fetch: globalThis.fetch,
  WebSocket: WebSocket,
  setInterval,
  clearInterval,
  setTimeout,
  clearTimeout,
  runtimeVersion: () => chrome.runtime.getManifest().version,
  settings,
  createSession,
  javdbCookies,
  createTab,
  removeTab,
  waitForTabComplete,
  collectSnapshot,
  collectCookies,
  setLocalStatus,
  appendLocalDiagnostic,
  drainUploadableDiagnostics,
  removeDiagnostics,
}

const client = new AgentClient(deps)

async function ensureWakeAlarm() {
  const existing = await chrome.alarms.get(AGENT_WAKE_ALARM)
  if (existing) return
  await chrome.alarms.create(AGENT_WAKE_ALARM, {
    periodInMinutes: AGENT_WAKE_PERIOD_MINUTES,
  })
}

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== 'sync') return
  if (!changes.backendUrl && !changes.token) return
  void client.settingsChanged()
})

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== 'agent_settings_saved' && message?.type !== 'agent_reconnect_requested') {
    return false
  }
  void client.settingsChanged().then(() => sendResponse({ ok: true }))
  return true
})

chrome.runtime.onInstalled.addListener(() => {
  void ensureWakeAlarm()
  void client.start()
})

chrome.runtime.onStartup.addListener(() => {
  void ensureWakeAlarm()
  void client.start()
})

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== AGENT_WAKE_ALARM) return
  void client.wake()
})

void ensureWakeAlarm()
void client.start()
