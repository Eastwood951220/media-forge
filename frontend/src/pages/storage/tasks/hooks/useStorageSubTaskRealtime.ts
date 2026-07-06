import { useEffect } from 'react'
import type { StorageSubTask, StorageTaskLog } from '@/api/storage/storageTasks/types'
import { connectRealtime, subscribeRealtime } from '@/realtime/eventSourceClient'
import type { RealtimeEvent } from '@/realtime/types'

interface UseStorageSubTaskRealtimeOptions {
  id: string | undefined
  setSubtask: React.Dispatch<React.SetStateAction<StorageSubTask | null>>
  setLogs: React.Dispatch<React.SetStateAction<StorageTaskLog[]>>
  fetchSubtask: () => Promise<void>
  fetchLogs: () => Promise<void>
}

export function useStorageSubTaskRealtime({
  id,
  setSubtask,
  setLogs,
  fetchSubtask,
  fetchLogs,
}: UseStorageSubTaskRealtimeOptions) {
  useEffect(() => {
    if (!id) return
    connectRealtime()

    const unsubscribeSubtask = subscribeRealtime<StorageSubTask>(
      'storage.sub.updated',
      (event: RealtimeEvent<StorageSubTask>) => {
        if (event.payload.id !== id) return
        setSubtask((current) => (current ? { ...current, ...event.payload } : event.payload))
      },
    )

    const unsubscribeLog = subscribeRealtime<StorageTaskLog>(
      'storage.sub.log.appended',
      (event: RealtimeEvent<StorageTaskLog>) => {
        if (event.resource_id !== id) return
        setLogs((current) => current.concat(event.payload))
      },
    )

    const unsubscribeResync = subscribeRealtime(
      'system.resync_required',
      () => {
        void fetchSubtask()
        void fetchLogs()
      },
    )

    return () => {
      unsubscribeSubtask()
      unsubscribeLog()
      unsubscribeResync()
    }
  }, [id, setSubtask, setLogs, fetchSubtask, fetchLogs])
}
