import { create } from 'zustand'
import type { CrawlTaskRuntimeSnapshot, CrawlTaskRuntimeStats } from '@/api/crawler/crawlTask/types'
import type { CrawlRunRuntime } from '@/realtime/types'

type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'error'

type CrawlerRuntimeState = {
  connectionStatus: ConnectionStatus
  lastConnectedAt: string | null
  lastResyncReason: string | null
  taskRuntimeById: Record<string, CrawlTaskRuntimeSnapshot>
  taskStats: CrawlTaskRuntimeStats | null
  taskSnapshotReady: boolean
  runRuntimeById: Record<string, CrawlRunRuntime>

  setConnectionStatus: (status: ConnectionStatus) => void
  markConnected: () => void
  markResyncRequired: (reason: string) => void
  replaceTaskRuntimeSnapshot: (payload: {
    tasks: CrawlTaskRuntimeSnapshot[]
    stats: CrawlTaskRuntimeStats
  }) => void
  upsertTaskRuntime: (snapshot: CrawlTaskRuntimeSnapshot) => void
  hydrateRunRuntime: (runtimes: Record<string, CrawlRunRuntime>) => void
  upsertRunRuntime: (runtime: CrawlRunRuntime) => void
  removeRunRuntime: (runId: string) => void
  reset: () => void
}

function createInitialState() {
  return {
    connectionStatus: 'idle' as ConnectionStatus,
    lastConnectedAt: null as string | null,
    lastResyncReason: null as string | null,
    taskRuntimeById: {} as Record<string, CrawlTaskRuntimeSnapshot>,
    taskStats: null as CrawlTaskRuntimeStats | null,
    taskSnapshotReady: false,
    runRuntimeById: {} as Record<string, CrawlRunRuntime>,
  }
}

function recalcStats(
  snapshots: Record<string, CrawlTaskRuntimeSnapshot>,
): CrawlTaskRuntimeStats {
  const counts = { idle: 0, running: 0, queued: 0, stopped: 0 }
  for (const s of Object.values(snapshots)) {
    if (counts[s.runtime_status] !== undefined) {
      counts[s.runtime_status]++
    }
  }
  return {
    total: Object.keys(snapshots).length,
    idle: counts.idle,
    running: counts.running,
    queued: counts.queued,
    stopped: counts.stopped,
  }
}

export const useCrawlerRuntimeStore = create<CrawlerRuntimeState>()((set) => ({
  ...createInitialState(),

  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),

  markConnected: () =>
    set({ connectionStatus: 'connected', lastConnectedAt: new Date().toISOString() }),

  markResyncRequired: (reason) =>
    set({
      lastResyncReason: reason,
      taskSnapshotReady: false,
      runRuntimeById: {},
    }),

  replaceTaskRuntimeSnapshot: (payload) =>
    set({
      taskRuntimeById: Object.fromEntries(
        payload.tasks.map((s) => [s.task_id, s]),
      ),
      taskStats: payload.stats,
      taskSnapshotReady: true,
    }),

  upsertTaskRuntime: (snapshot) =>
    set((state) => {
      const next = { ...state.taskRuntimeById, [snapshot.task_id]: snapshot }
      return {
        taskRuntimeById: next,
        taskStats: recalcStats(next),
      }
    }),

  hydrateRunRuntime: (runtimes) =>
    set((state) => ({
      runRuntimeById: {
        ...runtimes,
        ...state.runRuntimeById,
      },
    })),

  upsertRunRuntime: (runtime) =>
    set((state) => {
      const existing = state.runRuntimeById[runtime.run_id]
      // Reject older events
      if (existing && existing.state_updated_at >= runtime.state_updated_at) {
        return state
      }
      return {
        runRuntimeById: {
          ...state.runRuntimeById,
          [runtime.run_id]: runtime,
        },
      }
    }),

  removeRunRuntime: (runId) =>
    set((state) => {
      const { [runId]: _removed, ...rest } = state.runRuntimeById
      return { runRuntimeById: rest }
    }),

  reset: () => set(createInitialState()),
}))
