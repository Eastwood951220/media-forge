import { create } from 'zustand'
import type { CrawlTaskRuntimeSnapshot } from '@/api/crawlTask/types'
import type { CrawlRun, CrawlRunDetailTask, RunLogEntry, RunTaskSummary } from '@/api/crawlerRun/types'

type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'error'

type CrawlerRuntimeState = {
  connectionStatus: ConnectionStatus
  lastConnectedAt: string | null
  lastResyncReason: string | null
  runtimeByTaskId: Record<string, CrawlTaskRuntimeSnapshot>
  runsById: Record<string, CrawlRun>
  detailsByRunId: Record<string, Record<string, CrawlRunDetailTask>>
  logsByRunId: Record<string, RunLogEntry[]>
  summaryByRunId: Record<string, RunTaskSummary>
  setConnectionStatus: (status: ConnectionStatus) => void
  markConnected: () => void
  markResyncRequired: (reason: string) => void
  hydrateTaskRuntime: (snapshots: CrawlTaskRuntimeSnapshot[]) => void
  hydrateRun: (run: CrawlRun) => void
  hydrateRunDetails: (runId: string, tasks: CrawlRunDetailTask[], summary?: RunTaskSummary) => void
  mergeRunDetails: (runId: string, tasks: CrawlRunDetailTask[]) => void
  hydrateRunLogs: (runId: string, logs: RunLogEntry[]) => void
  appendRunLog: (runId: string, log: RunLogEntry) => void
  clearRun: (runId: string) => void
  reset: () => void
}

const initialState = {
  connectionStatus: 'idle' as ConnectionStatus,
  lastConnectedAt: null,
  lastResyncReason: null,
  runtimeByTaskId: {},
  runsById: {},
  detailsByRunId: {},
  logsByRunId: {},
  summaryByRunId: {},
}

export const useCrawlerRuntimeStore = create<CrawlerRuntimeState>()((set) => ({
  ...initialState,
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  markConnected: () => set({ connectionStatus: 'connected', lastConnectedAt: new Date().toISOString() }),
  markResyncRequired: (reason) => set({ lastResyncReason: reason }),
  hydrateTaskRuntime: (snapshots) =>
    set({
      runtimeByTaskId: Object.fromEntries(snapshots.map((snapshot) => [snapshot.task_id, snapshot])),
    }),
  hydrateRun: (run) => set((state) => ({ runsById: { ...state.runsById, [run.id]: run } })),
  hydrateRunDetails: (runId, tasks, summary) =>
    set((state) => ({
      detailsByRunId: {
        ...state.detailsByRunId,
        [runId]: Object.fromEntries(tasks.map((task) => [task.id, task])),
      },
      summaryByRunId: summary ? { ...state.summaryByRunId, [runId]: summary } : state.summaryByRunId,
    })),
  mergeRunDetails: (runId, tasks) =>
    set((state) => ({
      detailsByRunId: {
        ...state.detailsByRunId,
        [runId]: {
          ...(state.detailsByRunId[runId] ?? {}),
          ...Object.fromEntries(tasks.map((task) => [task.id, task])),
        },
      },
    })),
  hydrateRunLogs: (runId, logs) =>
    set((state) => ({
      logsByRunId: { ...state.logsByRunId, [runId]: logs },
    })),
  appendRunLog: (runId, log) =>
    set((state) => ({
      logsByRunId: { ...state.logsByRunId, [runId]: [...(state.logsByRunId[runId] ?? []), log] },
    })),
  clearRun: (runId) =>
    set((state) => {
      const { [runId]: _run, ...runsById } = state.runsById
      const { [runId]: _details, ...detailsByRunId } = state.detailsByRunId
      const { [runId]: _logs, ...logsByRunId } = state.logsByRunId
      const { [runId]: _summary, ...summaryByRunId } = state.summaryByRunId
      return { runsById, detailsByRunId, logsByRunId, summaryByRunId }
    }),
  reset: () => set(initialState),
}))
