import {useEffect} from 'react'
import type {CrawlTaskRuntimeSnapshot} from '@/api/crawlTask/types'
import {connectRealtime, subscribeRealtime} from '@/realtime/eventSourceClient'
import type {CrawlerTaskStatusUpdatedPayload} from '@/realtime/types'
import {recomputeStats} from '../utils/runtimeStats'

export function useTaskListRealtime({
  refreshList,
  setRuntimeByTaskId,
  setStats,
}: {
  refreshList: () => void
  setRuntimeByTaskId: React.Dispatch<React.SetStateAction<Record<string, CrawlTaskRuntimeSnapshot>>>
  setStats: React.Dispatch<React.SetStateAction<import('@/api/crawlTask/types').CrawlTaskRuntimeStats>>
}) {
  useEffect(() => {
    connectRealtime()

    const unsubscribeTaskStatus = subscribeRealtime<CrawlerTaskStatusUpdatedPayload>(
      'crawler.task.status.updated',
      (event) => {
        const payload = event.payload
        setRuntimeByTaskId((current) => {
          const next = {...current, [payload.task_id]: payload}
          setStats(recomputeStats(next))
          return next
        })
      },
    )

    const unsubscribeResync = subscribeRealtime('system.resync_required', () => {
      refreshList()
    })

    return () => {
      unsubscribeTaskStatus()
      unsubscribeResync()
    }
  }, [refreshList, setRuntimeByTaskId, setStats])
}
