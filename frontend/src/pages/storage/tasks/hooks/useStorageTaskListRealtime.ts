import { useEffect } from 'react'
import type { StorageMainTask } from '@/api/storage/storageTasks/types'
import { connectRealtime, subscribeRealtime } from '@/realtime/eventSourceClient'
import type { RealtimeEvent, StorageMainDeletedPayload } from '@/realtime/types'

export function useStorageTaskListRealtime(args: {
  setTasks: React.Dispatch<React.SetStateAction<StorageMainTask[]>>
  setTotal?: React.Dispatch<React.SetStateAction<number>>
}) {
  const { setTasks, setTotal } = args

  useEffect(() => {
    connectRealtime()

    const unsubscribeUpdated = subscribeRealtime<StorageMainTask>(
      'storage.main.updated',
      (event: RealtimeEvent<StorageMainTask>) => {
        const updatedTask = event.payload
        setTasks((prev) =>
          prev.map((task) =>
            task.id === updatedTask.id ? { ...task, ...updatedTask } : task,
          ),
        )
      },
    )

    const unsubscribeDeleted = subscribeRealtime<StorageMainDeletedPayload>(
      'storage.main.deleted',
      (event: RealtimeEvent<StorageMainDeletedPayload>) => {
        setTasks((prev) => prev.filter((task) => task.id !== event.payload.id))
        if (setTotal) {
          setTotal((count) => Math.max(0, count - 1))
        }
      },
    )

    return () => {
      unsubscribeUpdated()
      unsubscribeDeleted()
    }
  }, [setTasks, setTotal])
}
