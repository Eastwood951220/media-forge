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
  keyword: string
  resyncSnapshot: () => void
  setLogs: React.Dispatch<React.SetStateAction<RunLogEntry[]>>
  setRun: React.Dispatch<React.SetStateAction<CrawlRun | null>>
  setTasks: React.Dispatch<React.SetStateAction<CrawlRunDetailTask[]>>
  statusFilter: string | undefined
}): void {
  const { id, fetchLogs, keyword, resyncSnapshot, setLogs, setRun, setTasks, statusFilter } = args

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
        setTasks((currentTasks) => {
          const byId = new Map(currentTasks.map((task) => [task.id, task]))
          for (const task of event.payload.tasks) {
            const matchesStatus = !statusFilter || task.status === statusFilter
            const normalizedKeyword = keyword.trim().toLowerCase()
            const matchesKeyword = !normalizedKeyword
              || (task.code ?? '').toLowerCase().includes(normalizedKeyword)
              || task.source_name.toLowerCase().includes(normalizedKeyword)
            if (matchesStatus && matchesKeyword) {
              byId.set(task.id, task)
            } else {
              byId.delete(task.id)
            }
          }
          return Array.from(byId.values()).sort((a, b) => (
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          ))
        })
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
  }, [id, fetchLogs, keyword, resyncSnapshot, setLogs, setRun, setTasks, statusFilter])
}
