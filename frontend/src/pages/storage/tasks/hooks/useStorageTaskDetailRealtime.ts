import { useEffect } from 'react'
import type { StorageMainTask, StorageSubTask } from '@/api/storage/storageTasks/types'
import { connectRealtime, subscribeRealtime } from '@/realtime/eventSourceClient'
import type { RealtimeEvent, StorageMainUpdatedPayload, StorageSubUpdatedPayload } from '@/realtime/types'
import { mergeSubtaskUpdate } from '../utils/status'

export function useStorageTaskDetailRealtime(args: {
  id: string | undefined
  fetchSubtasks: () => void
  fetchTask: () => void
  setSubtasks: React.Dispatch<React.SetStateAction<StorageSubTask[]>>
  setTask: React.Dispatch<React.SetStateAction<StorageMainTask | null>>
}) {
  const { id, fetchSubtasks, fetchTask, setSubtasks, setTask } = args

  useEffect(() => {
    if (!id) return
    connectRealtime()

    const unsubscribeTask = subscribeRealtime<StorageMainUpdatedPayload>(
      'storage.main.updated',
      (event: RealtimeEvent<StorageMainUpdatedPayload>) => {
        if (event.payload.id !== id) return
        setTask((current) => (current ? { ...current, ...event.payload } : current))
      },
    )

    const unsubscribeSubtask = subscribeRealtime<StorageSubUpdatedPayload>(
      'storage.sub.updated',
      (event: RealtimeEvent<StorageSubUpdatedPayload>) => {
        if (event.payload.main_task_id !== id) return
        setSubtasks((current) => mergeSubtaskUpdate(current, event.payload))
      },
    )

    const unsubscribeResync = subscribeRealtime(
      'system.resync_required',
      () => {
        void fetchTask()
        void fetchSubtasks()
      },
    )

    return () => {
      unsubscribeTask()
      unsubscribeSubtask()
      unsubscribeResync()
    }
  }, [id, fetchTask, fetchSubtasks, setSubtasks, setTask])
}
