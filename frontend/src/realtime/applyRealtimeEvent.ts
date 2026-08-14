import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import type {
  CrawlerTaskRuntimeSnapshotPayload,
  CrawlerTaskStatusUpdatedPayload,
  CrawlRunRuntime,
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

  if (event.event === 'crawler.task.runtime.snapshot') {
    const payload = event.payload as unknown as CrawlerTaskRuntimeSnapshotPayload
    store.replaceTaskRuntimeSnapshot({
      tasks: payload.tasks,
      stats: payload.stats,
    })
    return
  }

  if (event.event === 'crawler.task.status.updated') {
    const payload = event.payload as unknown as CrawlerTaskStatusUpdatedPayload
    store.upsertTaskRuntime(payload)
    return
  }

  if (event.event === 'crawler.run.status.updated') {
    const payload = event.payload as unknown as CrawlRunRuntime
    store.upsertRunRuntime(payload)
    return
  }

  // crawler.run.detail.updated and crawler.run.log.appended are handled
  // locally by page-level subscribers — not stored in the global store.
}