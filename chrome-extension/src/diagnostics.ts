import type { AgentLocalDiagnostic, AgentLocalStatus } from './protocol'

const DIAGNOSTIC_RING_KEY = 'agentDiagnosticRing'
const STATUS_KEY = 'agentStatus'
const MAX_RING_SIZE = 100

export async function setLocalStatus(status: Omit<AgentLocalStatus, 'updatedAt'>): Promise<void> {
  await chrome.storage.local.set({
    [STATUS_KEY]: {
      ...status,
      updatedAt: new Date().toISOString(),
    },
  })
}

export async function appendLocalDiagnostic(
  level: AgentLocalDiagnostic['level'],
  code: string,
  message: string,
): Promise<void> {
  const entry: AgentLocalDiagnostic = {
    timestamp: new Date().toISOString(),
    level,
    code,
    message,
  }
  const data = await chrome.storage.local.get(DIAGNOSTIC_RING_KEY)
  const ring: AgentLocalDiagnostic[] = Array.isArray(data[DIAGNOSTIC_RING_KEY])
    ? data[DIAGNOSTIC_RING_KEY]
    : []
  ring.push(entry)
  while (ring.length > MAX_RING_SIZE) {
    ring.shift()
  }
  await chrome.storage.local.set({ [DIAGNOSTIC_RING_KEY]: ring })
}

/**
 * Return only stable connection/task dispatch diagnostics that are safe to
 * upload to the backend. The caller must remove them from storage only after
 * the backend acknowledges receipt of the batch.
 */
export async function drainUploadableDiagnostics(): Promise<AgentLocalDiagnostic[]> {
  const data = await chrome.storage.local.get(DIAGNOSTIC_RING_KEY)
  const ring: AgentLocalDiagnostic[] = Array.isArray(data[DIAGNOSTIC_RING_KEY])
    ? data[DIAGNOSTIC_RING_KEY]
    : []
  return ring.filter(
    (entry) => entry.code.startsWith('connection.') || entry.code.startsWith('task.'),
  )
}

export async function removeDiagnostics(entries: AgentLocalDiagnostic[]): Promise<void> {
  if (entries.length === 0) return
  const data = await chrome.storage.local.get(DIAGNOSTIC_RING_KEY)
  const ring: AgentLocalDiagnostic[] = Array.isArray(data[DIAGNOSTIC_RING_KEY])
    ? data[DIAGNOSTIC_RING_KEY]
    : []
  const toRemove = new Set(entries.map((e) => `${e.timestamp}:${e.code}:${e.message}`))
  const filtered = ring.filter(
    (e) => !toRemove.has(`${e.timestamp}:${e.code}:${e.message}`),
  )
  await chrome.storage.local.set({ [DIAGNOSTIC_RING_KEY]: filtered })
}
