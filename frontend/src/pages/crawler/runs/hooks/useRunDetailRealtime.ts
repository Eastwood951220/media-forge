import { useEffect } from 'react'
import { connectRealtime, subscribeRealtime } from '@/realtime/eventSourceClient'
import type { CrawlRun, CrawlRunDetailTask, RunLogEntry } from '@/api/crawlerRun/types'
import type {
  CrawlerRunDetailUpdatedPayload,
  CrawlerRunLogAppendedPayload,
  CrawlerRunUpdatedPayload,
} from '@/realtime/types'

export function useRunDetailRealtime(args: {
  id: string | undefined
  fetchLogs: () => Promise<void>
  fetchTasks: () => Promise<void>
  keyword: string
  resyncSnapshot: () => void
  setLogs: React.Dispatch<React.SetStateAction<RunLogEntry[]>>
  setRun: React.Dispatch<React.SetStateAction<CrawlRun | null>>
  setTasks: React.Dispatch<React.SetStateAction<CrawlRunDetailTask[]>>
  statusFilter: string | undefined
}): void {
  const { id, fetchLogs, fetchTasks, keyword, resyncSnapshot, setLogs, setRun, setTasks, statusFilter } = args

  useEffect(() => {
    if (!id) return
    connectRealtime()

    const unsubscribeRun = subscribeRealtime<CrawlerRunUpdatedPayload>(
      'crawler.run.updated',
      (event) => {
        if (event.resource_id !== id) return
        setRun((currentRun) => ({
          ...event.payload,
          logs: currentRun?.logs ?? [],
        }))
        if (['completed', 'failed', 'stopped'].includes(event.payload.status)) {
          void fetchLogs()
        }
      },
    )

    const unsubscribeDetails = subscribeRealtime<CrawlerRunDetailUpdatedPayload>(
      'crawler.run.detail.updated',
      (event) => {
        if (event.resource_id !== id || event.payload.run_id !== id) return
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
              byId.set(task.id, task)
            } else if (wasPresent) {
              byId.delete(task.id)
              needsRefresh = true
            } else if (matchesStatus && matchesKeyword) {
              needsRefresh = true
            }
          }
          return Array.from(byId.values()).sort((a, b) => (
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          ))
        })
        if (needsRefresh) {
          void fetchTasks()
        }
      },
    )

    const unsubscribeLogs = subscribeRealtime<CrawlerRunLogAppendedPayload>(
      'crawler.run.log.appended',
      (event) => {
        if (event.resource_id !== id || event.payload.run_id !== id) return
        setLogs((currentLogs) => [...currentLogs, event.payload.log])
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
  }, [id, fetchLogs, fetchTasks, keyword, resyncSnapshot, setLogs, setRun, setTasks, statusFilter])
}
