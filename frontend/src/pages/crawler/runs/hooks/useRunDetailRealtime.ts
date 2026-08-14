import { useEffect } from 'react'
import { subscribeRealtime } from '@/realtime/eventSourceClient'
import type { CrawlRun, CrawlRunDetailTask, RunLogEntry, RunTaskSummary } from '@/api/crawler/crawlerRun/types'
import type {
  CrawlerRunDetailUpdatedPayload,
  CrawlerRunLogAppendedPayload,
  CrawlerRunStatusUpdatedPayload,
} from '@/realtime/types'

export function useRunDetailRealtime(args: {
  id: string | undefined
  fetchLogs: () => Promise<void>
  fetchRun: () => Promise<void>
  fetchTasks: () => Promise<void>
  keyword: string
  resyncSnapshot: () => void
  setLogs: React.Dispatch<React.SetStateAction<RunLogEntry[]>>
  setRun: React.Dispatch<React.SetStateAction<CrawlRun | null>>
  setTaskSummary: React.Dispatch<React.SetStateAction<RunTaskSummary>>
  setTaskTotal: React.Dispatch<React.SetStateAction<number>>
  setTasks: React.Dispatch<React.SetStateAction<CrawlRunDetailTask[]>>
  statusFilter: string | undefined
}): void {
  const {
    id,
    fetchLogs,
    fetchRun,
    fetchTasks,
    keyword,
    resyncSnapshot,
    setLogs,
    setRun,
    setTaskSummary,
    setTaskTotal,
    setTasks,
    statusFilter,
  } = args

  useEffect(() => {
    if (!id) return

    const unsubscribeRun = subscribeRealtime<CrawlerRunStatusUpdatedPayload>(
      'crawler.run.status.updated',
      (event) => {
        if (event.resource_id !== id) return
        const { status, error, started_at, finished_at } = event.payload
        setRun((currentRun) => ({
          ...currentRun,
          status,
          error,
          started_at,
          finished_at,
          logs: currentRun?.logs ?? [],
        } as CrawlRun))
        if (['completed', 'failed', 'stopped'].includes(status)) {
          void fetchRun()
          void fetchLogs()
          void fetchTasks()
        }
      },
    )

    const unsubscribeDetails = subscribeRealtime<CrawlerRunDetailUpdatedPayload>(
      'crawler.run.detail.updated',
      (event) => {
        if (event.owner_id !== id || event.payload.run_id !== id) return
        if (event.payload.summary) {
          setTaskSummary(event.payload.summary)
        }
        if (event.payload.refresh_tasks) {
          void fetchTasks()
          return
        }
        let needsRefresh = false
        setTasks((currentTasks) => {
          const byId = new Map(currentTasks.map((task) => [task.id, task]))
          const normalizedKeyword = keyword.trim().toLowerCase()
          for (const task of event.payload.tasks) {
            const wasPresent = byId.has(task.id)
            const matchesStatus = !statusFilter || task.status === statusFilter
            const matchesKeyword = !normalizedKeyword
              || (task.code ?? '').toLowerCase().includes(normalizedKeyword)
              || task.source_name.toLowerCase().includes(normalizedKeyword)
              || (task.source_url_name ?? '').toLowerCase().includes(normalizedKeyword)
            if (wasPresent && matchesStatus && matchesKeyword) {
              byId.set(task.id, task as CrawlRunDetailTask)
            } else if (wasPresent) {
              byId.delete(task.id)
              needsRefresh = true
            } else if (matchesStatus && matchesKeyword) {
              needsRefresh = true
            }
          }
          const nextTasks = Array.from(byId.values()).sort((a, b) => (
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          ))
          setTaskTotal((currentTotal) => Math.max(currentTotal, nextTasks.length))
          return nextTasks
        })
        if (needsRefresh) {
          void fetchTasks()
        }
      },
    )

    const unsubscribeLogs = subscribeRealtime<CrawlerRunLogAppendedPayload>(
      'crawler.run.log.appended',
      (event) => {
        if (event.owner_id !== id || event.payload.run_id !== id) return
        setLogs((currentLogs) => {
          const log = event.payload.log
          const key = [log.timestamp, log.component ?? '', log.event ?? '', log.message].join('|')
          // Deduplicate: skip if an entry with the same key already exists
          if (currentLogs.some((existing) => {
            const existingKey = [existing.timestamp, existing.component ?? '', existing.event ?? '', existing.message].join('|')
            return existingKey === key
          })) {
            return currentLogs
          }
          return [...currentLogs, log]
        })
      },
    )

    const unsubscribeResync = subscribeRealtime(
      'system.resync_required',
      () => {
        resyncSnapshot()
      },
    )

    return () => {
      unsubscribeRun()
      unsubscribeDetails()
      unsubscribeLogs()
      unsubscribeResync()
    }
  }, [id, fetchLogs, fetchRun, fetchTasks, keyword, resyncSnapshot, setLogs, setRun, setTaskSummary, setTaskTotal, setTasks, statusFilter])
}