import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { connectRealtime, disconnectRealtime, subscribeRealtime } from '../src/realtime/eventSourceClient'
import { setToken, removeToken } from '../src/utils/auth'

type ListenerMap = Record<string, Array<(event: MessageEvent) => void>>

class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  listeners: ListenerMap = {}
  close = vi.fn()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(eventName: string, handler: (event: MessageEvent) => void) {
    this.listeners[eventName] = [...(this.listeners[eventName] ?? []), handler]
  }

  removeEventListener(eventName: string, handler: (event: MessageEvent) => void) {
    this.listeners[eventName] = (this.listeners[eventName] ?? []).filter((item) => item !== handler)
  }

  emit(eventName: string, data: unknown) {
    for (const handler of this.listeners[eventName] ?? []) {
      handler(new MessageEvent(eventName, { data: JSON.stringify(data) }))
    }
  }
}

describe('eventSourceClient', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
    setToken('token with space')
  })

  afterEach(() => {
    disconnectRealtime()
    removeToken()
    vi.unstubAllGlobals()
  })

  it('connects with encoded query token', () => {
    connectRealtime()

    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.instances[0].url).toBe('/api/events/stream?token=token%20with%20space')
  })

  it('does not connect without a token', () => {
    removeToken()

    connectRealtime()

    expect(FakeEventSource.instances).toHaveLength(0)
  })

  it('delivers parsed realtime events to subscribers', () => {
    const handler = vi.fn()
    subscribeRealtime('crawler.run.updated', handler)
    connectRealtime()

    FakeEventSource.instances[0].emit('crawler.run.updated', {
      id: 'event-1',
      event: 'crawler.run.updated',
      scope: 'crawler.run',
      resource_id: 'run-1',
      owner_id: 'user-1',
      payload: { status: 'running' },
      created_at: '2026-07-03T00:00:00Z',
    })

    expect(handler).toHaveBeenCalledWith(expect.objectContaining({
      event: 'crawler.run.updated',
      payload: { status: 'running' },
    }))
  })

  it('unsubscribes handlers', () => {
    const handler = vi.fn()
    const unsubscribe = subscribeRealtime('crawler.run.updated', handler)
    connectRealtime()

    unsubscribe()
    FakeEventSource.instances[0].emit('crawler.run.updated', {
      id: 'event-1',
      event: 'crawler.run.updated',
      scope: 'crawler.run',
      resource_id: 'run-1',
      owner_id: 'user-1',
      payload: { status: 'running' },
      created_at: '2026-07-03T00:00:00Z',
    })

    expect(handler).not.toHaveBeenCalled()
  })
})
