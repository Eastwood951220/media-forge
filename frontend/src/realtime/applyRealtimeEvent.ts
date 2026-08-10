import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import type {
  CrawlerRunDetailUpdatedPayload,
  CrawlerRunLogAppendedPayload,
  CrawlerRunUpdatedPayload,
  CrawlerTaskStatusUpdatedPayload,
  RealtimeEvent,
} from './types'

export function applyRealtimeEvent(event: RealtimeEvent): void {
  const store = useCrawlerRuntimeStore.getState()

  if (event.event === 'system.connected') {
    store.markConnected()
    return
  }

  if (event.event === 'system.resync_required') {
    const reason = String((event.payload as { reason?: unknown }).reason ?? 'unknown')
    store.markResyncRequired(reason)
    return
  }

  if (event.event === 'crawler.task.status.updated') {
    const payload = event.payload as unknown as CrawlerTaskStatusUpdatedPayload
    store.hydrateTaskRuntime([
      ...Object.values(useCrawlerRuntimeStore.getState().runtimeByTaskId).filter(
        (item) => item.task_id !== payload.task_id,
      ),
      payload,
    ])
    return
  }

  if (event.event === 'crawler.run.updated') {
    store.hydrateRun(event.payload as unknown as CrawlerRunUpdatedPayload)
    return
  }

  if (event.event === 'crawler.run.detail.updated') {
    const payload = event.payload as unknown as CrawlerRunDetailUpdatedPayload
    store.mergeRunDetails(payload.run_id, payload.tasks)
    if (payload.summary) {
      const existing = Object.values(
        useCrawlerRuntimeStore.getState().detailsByRunId[payload.run_id] ?? {},
      )
      store.hydrateRunDetails(payload.run_id, existing, payload.summary)
    }
    return
  }

  if (event.event === 'crawler.run.log.appended') {
    const payload = event.payload as unknown as CrawlerRunLogAppendedPayload
    store.appendRunLog(payload.run_id, payload.log)
  }
}
