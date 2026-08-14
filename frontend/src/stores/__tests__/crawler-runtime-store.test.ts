import { describe, it, expect, beforeEach } from 'vitest'
import { useCrawlerRuntimeStore } from '../useCrawlerRuntimeStore'

describe('useCrawlerRuntimeStore', () => {
  beforeEach(() => {
    useCrawlerRuntimeStore.getState().reset()
  })

  describe('replaceTaskRuntimeSnapshot', () => {
    it('replaces task map and stats atomically', () => {
      const store = useCrawlerRuntimeStore.getState()
      store.replaceTaskRuntimeSnapshot({
        tasks: [
          { task_id: 't1', runtime_status: 'idle', latest_run_id: null, state_updated_at: '2024-01-01T00:00:00Z', last_run_at: null },
        ],
        stats: { total: 1, idle: 1, running: 0, queued: 0, stopped: 0 },
      })

      const state = useCrawlerRuntimeStore.getState()
      expect(state.taskRuntimeById).toEqual({
        t1: expect.objectContaining({ task_id: 't1', runtime_status: 'idle' }),
      })
      expect(state.taskStats).toEqual({ total: 1, idle: 1, running: 0, queued: 0, stopped: 0 })
      expect(state.taskSnapshotReady).toBe(true)
    })

    it('clears previous task snapshots when payload is smaller', () => {
      const store = useCrawlerRuntimeStore.getState()
      store.replaceTaskRuntimeSnapshot({
        tasks: [
          { task_id: 't1', runtime_status: 'running', latest_run_id: 'r1', state_updated_at: '2024-01-01T00:00:00Z', last_run_at: null },
          { task_id: 't2', runtime_status: 'idle', latest_run_id: null, state_updated_at: '2024-01-01T00:00:00Z', last_run_at: null },
        ],
        stats: { total: 2, idle: 1, running: 1, queued: 0, stopped: 0 },
      })

      store.replaceTaskRuntimeSnapshot({
        tasks: [
          { task_id: 't1', runtime_status: 'running', latest_run_id: 'r1', state_updated_at: '2024-01-01T00:00:00Z', last_run_at: null },
        ],
        stats: { total: 1, idle: 0, running: 1, queued: 0, stopped: 0 },
      })

      const state = useCrawlerRuntimeStore.getState()
      expect(Object.keys(state.taskRuntimeById)).toEqual(['t1'])
      expect(state.taskStats).toEqual({ total: 1, idle: 0, running: 1, queued: 0, stopped: 0 })
    })
  })

  describe('upsertTaskRuntime', () => {
    it('updates a single task and recalculates stats', () => {
      const store = useCrawlerRuntimeStore.getState()
      store.replaceTaskRuntimeSnapshot({
        tasks: [
          { task_id: 't1', runtime_status: 'idle', latest_run_id: null, state_updated_at: '2024-01-01T00:00:00Z', last_run_at: null },
        ],
        stats: { total: 1, idle: 1, running: 0, queued: 0, stopped: 0 },
      })

      store.upsertTaskRuntime({
        task_id: 't1',
        runtime_status: 'running',
        latest_run_id: 'r1',
        state_updated_at: '2024-01-01T00:01:00Z',
        last_run_at: null,
      })

      const state = useCrawlerRuntimeStore.getState()
      expect(state.taskRuntimeById.t1!.runtime_status).toBe('running')
      expect(state.taskStats).toEqual({ total: 1, idle: 0, running: 1, queued: 0, stopped: 0 })
    })
  })

  describe('runRuntime', () => {
    it('stores run runtime with upsertRunRuntime', () => {
      const store = useCrawlerRuntimeStore.getState()
      store.upsertRunRuntime({
        run_id: 'r1',
        status: 'running',
        error: null,
        started_at: null,
        finished_at: null,
        state_updated_at: '2024-01-01T00:02:00Z',
      })

      const state = useCrawlerRuntimeStore.getState()
      expect(state.runRuntimeById.r1).toBeDefined()
      expect(state.runRuntimeById.r1!.status).toBe('running')
    })

    it('rejects older events based on state_updated_at', () => {
      const store = useCrawlerRuntimeStore.getState()
      // Newer event first
      store.upsertRunRuntime({
        run_id: 'r1',
        status: 'running',
        error: null,
        started_at: null,
        finished_at: null,
        state_updated_at: '2024-01-01T00:02:00Z',
      })

      // Older event should be rejected
      store.upsertRunRuntime({
        run_id: 'r1',
        status: 'completed',
        error: null,
        started_at: null,
        finished_at: '2024-01-01T00:03:00Z',
        state_updated_at: '2024-01-01T00:01:00Z',
      })

      const state = useCrawlerRuntimeStore.getState()
      expect(state.runRuntimeById.r1!.status).toBe('running')
    })

    it('hydrateRunRuntime replaces all run runtimes', () => {
      const store = useCrawlerRuntimeStore.getState()
      store.upsertRunRuntime({
        run_id: 'r1',
        status: 'running',
        error: null,
        started_at: null,
        finished_at: null,
        state_updated_at: '2024-01-01T00:02:00Z',
      })

      store.hydrateRunRuntime({
        r2: {
          run_id: 'r2',
          status: 'completed',
          error: null,
          started_at: null,
          finished_at: null,
          state_updated_at: '2024-01-01T00:03:00Z',
        },
      })

      const state = useCrawlerRuntimeStore.getState()
      expect(state.runRuntimeById.r1).toBeUndefined()
      expect(state.runRuntimeById.r2).toBeDefined()
    })

    it('removeRunRuntime removes a run by id', () => {
      const store = useCrawlerRuntimeStore.getState()
      store.upsertRunRuntime({
        run_id: 'r1',
        status: 'running',
        error: null,
        started_at: null,
        finished_at: null,
        state_updated_at: '2024-01-01T00:02:00Z',
      })

      store.removeRunRuntime('r1')
      expect(useCrawlerRuntimeStore.getState().runRuntimeById.r1).toBeUndefined()
    })
  })

  describe('reset', () => {
    it('restores to pristine state', () => {
      const store = useCrawlerRuntimeStore.getState()
      store.replaceTaskRuntimeSnapshot({
        tasks: [
          { task_id: 't1', runtime_status: 'idle', latest_run_id: null, state_updated_at: '2024-01-01T00:00:00Z', last_run_at: null },
        ],
        stats: { total: 1, idle: 1, running: 0, queued: 0, stopped: 0 },
      })

      store.reset()

      const state = useCrawlerRuntimeStore.getState()
      expect(state.taskRuntimeById).toEqual({})
      expect(state.taskStats).toBeNull()
      expect(state.taskSnapshotReady).toBe(false)
      expect(state.runRuntimeById).toEqual({})
    })
  })
})