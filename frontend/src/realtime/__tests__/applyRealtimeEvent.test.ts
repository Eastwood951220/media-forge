import { describe, it, expect, beforeEach } from 'vitest'
import { applyRealtimeEvent } from '../applyRealtimeEvent'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'

function makeEvent(event: string, payload: Record<string, unknown> = {}) {
  return {
    id: 'e1',
    event,
    scope: 'crawler.task',
    resource_id: null,
    owner_id: 'user1',
    payload,
    created_at: '2024-01-01T00:00:00Z',
  }
}

describe('applyRealtimeEvent', () => {
  beforeEach(() => {
    useCrawlerRuntimeStore.getState().reset()
  })

  it('system.connected marks connected', () => {
    applyRealtimeEvent(makeEvent('system.connected'))
    const state = useCrawlerRuntimeStore.getState()
    expect(state.connectionStatus).toBe('connected')
    expect(state.lastConnectedAt).toBeTruthy()
  })

  it('system.resync_required sets resync reason and clears run runtimes', () => {
    // Seed some run runtime state
    const store = useCrawlerRuntimeStore.getState()
    store.upsertRunRuntime({
      run_id: 'r1',
      status: 'running',
      error: null,
      started_at: null,
      finished_at: null,
      state_updated_at: '2024-01-01T00:02:00Z',
    })

    applyRealtimeEvent(makeEvent('system.resync_required', { reason: 'token_expired' }))

    const state = useCrawlerRuntimeStore.getState()
    expect(state.lastResyncReason).toBe('token_expired')
    expect(state.taskSnapshotReady).toBe(false)
    expect(state.runRuntimeById).toEqual({})
  })

  it('crawler.task.runtime.snapshot replaces full task state', () => {
    applyRealtimeEvent(makeEvent('crawler.task.runtime.snapshot', {
      tasks: [
        { task_id: 't1', runtime_status: 'idle', latest_run_id: null, state_updated_at: '2024-01-01T00:00:00Z', last_run_at: null },
      ],
      stats: { total: 1, idle: 1, running: 0, queued: 0, stopped: 0 },
    }))

    const state = useCrawlerRuntimeStore.getState()
    expect(Object.keys(state.taskRuntimeById)).toEqual(['t1'])
    expect(state.taskStats).toEqual({ total: 1, idle: 1, running: 0, queued: 0, stopped: 0 })
    expect(state.taskSnapshotReady).toBe(true)
  })

  it('crawler.task.status.updated upserts single task', () => {
    // Seed initial snapshot
    applyRealtimeEvent(makeEvent('crawler.task.runtime.snapshot', {
      tasks: [
        { task_id: 't1', runtime_status: 'idle', latest_run_id: null, state_updated_at: '2024-01-01T00:00:00Z', last_run_at: null },
        { task_id: 't2', runtime_status: 'queued', latest_run_id: 'r2', state_updated_at: '2024-01-01T00:00:00Z', last_run_at: null },
      ],
      stats: { total: 2, idle: 1, running: 0, queued: 1, stopped: 0 },
    }))

    applyRealtimeEvent(makeEvent('crawler.task.status.updated', {
      task_id: 't1',
      runtime_status: 'running',
      latest_run_id: 'r1',
      state_updated_at: '2024-01-01T00:01:00Z',
      last_run_at: null,
    }))

    const state = useCrawlerRuntimeStore.getState()
    expect(state.taskRuntimeById.t1!.runtime_status).toBe('running')
    // t2 should be preserved
    expect(state.taskRuntimeById.t2!.runtime_status).toBe('queued')
    // Stats recalculated
    expect(state.taskStats).toEqual({ total: 2, idle: 0, running: 1, queued: 1, stopped: 0 })
  })

  it('crawler.run.status.updated stores minimal run runtime', () => {
    applyRealtimeEvent(makeEvent('crawler.run.status.updated', {
      run_id: 'r1',
      status: 'completed',
      error: null,
      started_at: null,
      finished_at: null,
      state_updated_at: '2024-01-01T00:01:00Z',
    }))

    const state = useCrawlerRuntimeStore.getState()
    expect(state.runRuntimeById.r1).toBeDefined()
    expect(state.runRuntimeById.r1!.status).toBe('completed')
    // Should NOT contain full run object fields
    expect((state.runRuntimeById.r1 as Record<string, unknown>).task_name).toBeUndefined()
    expect((state.runRuntimeById.r1 as Record<string, unknown>).crawl_mode).toBeUndefined()
    expect((state.runRuntimeById.r1 as Record<string, unknown>).created_at).toBeUndefined()
  })

  it('crawler.run.detail.updated and crawler.run.log.appended are ignored (not stored globally)', () => {
    // These should be no-ops for the global store
    applyRealtimeEvent(makeEvent('crawler.run.detail.updated', {
      run_id: 'r1',
      tasks: [],
    }))

    applyRealtimeEvent(makeEvent('crawler.run.log.appended', {
      run_id: 'r1',
      log: { timestamp: '2024-01-01T00:00:00Z', level: 'INFO', message: 'test' },
    }))

    // No errors, and no run runtime stored
    expect(useCrawlerRuntimeStore.getState().runRuntimeById).toEqual({})
  })
})