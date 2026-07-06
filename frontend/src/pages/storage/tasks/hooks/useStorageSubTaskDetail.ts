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
    setSubtask(null)
    setLogs([])
  }, [id])

  useEffect(() => {
    void fetchSubtask()
  }, [fetchSubtask])

  useEffect(() => {
    void fetchLogs()
  }, [fetchLogs])

  return { subtask, setSubtask, logs, setLogs, loading, fetchSubtask, fetchLogs }
}
