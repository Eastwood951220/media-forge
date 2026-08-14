import { useEffect } from 'react'
import { subscribeRealtime } from '@/realtime/eventSourceClient'
import type { CrawlerTaskStatusUpdatedPayload } from '@/realtime/types'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'

export function useTaskListRealtime() {
  const upsertTaskRuntime = useCrawlerRuntimeStore((state) => state.upsertTaskRuntime)
  const markResyncRequired = useCrawlerRuntimeStore((state) => state.markResyncRequired)

  useEffect(() => {
    const unsubscribeTaskStatus = subscribeRealtime<CrawlerTaskStatusUpdatedPayload>(
      'crawler.task.status.updated',
      (event) => {
        upsertTaskRuntime(event.payload)
      },
    )

    const unsubscribeResync = subscribeRealtime('system.resync_required', (event) => {
      markResyncRequired(event.payload?.reason as string ?? 'unknown')
    })

    return () => {
      unsubscribeTaskStatus()
      unsubscribeResync()
    }
  }, [upsertTaskRuntime, markResyncRequired])
}
