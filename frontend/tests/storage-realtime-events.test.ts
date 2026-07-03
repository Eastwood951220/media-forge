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

describe('storage realtime events', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
    setToken('test-token')
  })

  afterEach(() => {
    disconnectRealtime()
    removeToken()
    vi.unstubAllGlobals()
  })

  it('delivers storage.main.updated events to subscribers', () => {
    const handler = vi.fn()
    subscribeRealtime('storage.main.updated', handler)
    connectRealtime()

    FakeEventSource.instances[0].emit('storage.main.updated', {
      id: 'event-1',
      event: 'storage.main.updated',
      scope: 'storage.main',
      resource_id: 'task-1',
      owner_id: 'user-1',
      payload: {
        id: 'task-1',
        alias: 'test-alias',
        display_name: 'Test Task',
        source: 'single',
        storage_mode: 'single',
        status: 'running',
        total_count: 10,
        success_count: 5,
        failed_count: 0,
        skipped_count: 0,
      },
      created_at: '2026-07-04T00:00:00Z',
    })

    expect(handler).toHaveBeenCalledWith(expect.objectContaining({
      event: 'storage.main.updated',
      payload: expect.objectContaining({
        id: 'task-1',
        status: 'running',
      }),
    }))
  })

  it('delivers storage.sub.updated events to subscribers', () => {
    const handler = vi.fn()
    subscribeRealtime('storage.sub.updated', handler)
    connectRealtime()

    FakeEventSource.instances[0].emit('storage.sub.updated', {
      id: 'event-2',
      event: 'storage.sub.updated',
      scope: 'storage.sub',
      resource_id: 'sub-1',
      owner_id: 'user-1',
      payload: {
        id: 'sub-1',
        main_task_id: 'task-1',
        movie_id: 'movie-1',
        status: 'completed',
        step: 'moving',
      },
      created_at: '2026-07-04T00:00:00Z',
    })

    expect(handler).toHaveBeenCalledWith(expect.objectContaining({
      event: 'storage.sub.updated',
      payload: expect.objectContaining({
        id: 'sub-1',
        movie_id: 'movie-1',
      }),
    }))
  })

  it('delivers movie.storage.updated events to subscribers', () => {
    const handler = vi.fn()
    subscribeRealtime('movie.storage.updated', handler)
    connectRealtime()

    FakeEventSource.instances[0].emit('movie.storage.updated', {
      id: 'event-3',
      event: 'movie.storage.updated',
      scope: 'movie',
      resource_id: 'movie-1',
      owner_id: 'user-1',
      payload: {
        movie_id: 'movie-1',
        storage_summary: { last_status: 'completed' },
      },
      created_at: '2026-07-04T00:00:00Z',
    })

    expect(handler).toHaveBeenCalledWith(expect.objectContaining({
      event: 'movie.storage.updated',
      payload: expect.objectContaining({
        movie_id: 'movie-1',
      }),
    }))
  })
})
