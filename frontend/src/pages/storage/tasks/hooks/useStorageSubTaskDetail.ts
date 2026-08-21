import { useCallback, useEffect, useState } from 'react'
import { getStorageSubTask, getStorageSubTaskLogs } from '@/api/storage/storageTasks'
import type { StorageSubTask, StorageTaskLog } from '@/api/storage/storageTasks/types'

export function useStorageSubTaskDetail(id: string | undefined) {
  const [subtask, setSubtask] = useState<StorageSubTask | null>(null)
  const [logs, setLogs] = useState<StorageTaskLog[]>([])
  const [loading, setLoading] = useState(false)

  const fetchSubtask = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const data = await getStorageSubTask(id)
      setSubtask(data)
    } finally {
      setLoading(false)
    }
  }, [id])

  const fetchLogs = useCallback(async () => {
    if (!id) return
    try {
      const data = await getStorageSubTaskLogs(id)
      setLogs(data)
    } catch {
      // error handled by request interceptor
    }
  }, [id])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Reset detail state when subtask id changes.
    setSubtask(null)
    setLogs([])
  }, [id])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Initial subtask fetch on mount/id change is intentional.
    void fetchSubtask()
  }, [fetchSubtask])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Initial log fetch on mount/id change is intentional.
    void fetchLogs()
  }, [fetchLogs])

  return { subtask, setSubtask, logs, setLogs, loading, fetchSubtask, fetchLogs }
}
