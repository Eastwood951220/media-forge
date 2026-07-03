import { getToken } from '@/utils/auth'
import type { RealtimeEvent, RealtimeEventName, RealtimeHandler } from './types'

const EVENT_NAMES: RealtimeEventName[] = [
  'system.connected',
  'system.resync_required',
  'crawler.run.updated',
  'crawler.run.detail.updated',
  'crawler.run.log.appended',
  'crawler.queue.updated',
]

type AnyHandler = RealtimeHandler<Record<string, unknown>>

let source: EventSource | null = null
const handlers = new Map<string, Set<AnyHandler>>()

function eventStreamUrl(token: string) {
  return `/api/events/stream?token=${encodeURIComponent(token)}`
}

function dispatch(eventName: string, message: MessageEvent) {
  let parsed: RealtimeEvent<Record<string, unknown>>
  try {
    parsed = JSON.parse(String(message.data)) as RealtimeEvent<Record<string, unknown>>
  } catch {
    emitLocalResync('malformed_event')
    return
  }

  for (const handler of handlers.get(eventName) ?? []) {
    handler(parsed)
  }
}

function emitLocalResync(reason: string) {
  const event: RealtimeEvent = {
    id: `local-${Date.now()}`,
    event: 'system.resync_required',
    scope: 'system',
    resource_id: null,
    owner_id: '',
    payload: { reason },
    created_at: new Date().toISOString(),
  }
  for (const handler of handlers.get('system.resync_required') ?? []) {
    handler(event)
  }
}

export function connectRealtime() {
  if (source) return source
  const token = getToken()
  if (!token) return null

  source = new EventSource(eventStreamUrl(token))
  for (const eventName of EVENT_NAMES) {
    source.addEventListener(eventName, (message) => dispatch(eventName, message))
  }
  source.onerror = () => {
    emitLocalResync('connection_error')
  }
  return source
}

export function disconnectRealtime() {
  source?.close()
  source = null
  handlers.clear()
}

export function subscribeRealtime<TPayload = Record<string, unknown>>(
  eventName: RealtimeEventName,
  handler: RealtimeHandler<TPayload>,
) {
  const typedHandler = handler as AnyHandler
  const nextHandlers = handlers.get(eventName) ?? new Set<AnyHandler>()
  nextHandlers.add(typedHandler)
  handlers.set(eventName, nextHandlers)

  return () => {
    const currentHandlers = handlers.get(eventName)
    if (!currentHandlers) return
    currentHandlers.delete(typedHandler)
    if (currentHandlers.size === 0) {
      handlers.delete(eventName)
    }
  }
}
