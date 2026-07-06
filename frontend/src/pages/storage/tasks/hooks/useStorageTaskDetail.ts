import { useCallback, useEffect, useState } from 'react'
import {
  getStorageMainTask,
  listStorageSubTasks,
  restartStorageMainTask,
  stopStorageMainTask,
} from '@/api/storage/storageTasks'
import type { StorageMainTask, StorageSubTask } from '@/api/storage/storageTasks/types'

export function useStorageTaskDetail(id: string | undefined) {
  const [task, setTask] = useState<StorageMainTask | null>(null)
  const [subtasks, setSubtasks] = useState<StorageSubTask[]>([])
  const [loading, setLoading] = useState(false)
  const [subtasksLoading, setSubtasksLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState<'stop' | 'restart' | null>(null)

  const fetchTask = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const data = await getStorageMainTask(id)
      setTask(data)
    } finally {
      setLoading(false)
    }
  }, [id])

  const fetchSubtasks = useCallback(async () => {
    if (!id) return
    setSubtasksLoading(true)
    try {
      const data = await listStorageSubTasks(id, { limit: 200 })
      setSubtasks(data.rows)
    } finally {
      setSubtasksLoading(false)
    }
  }, [id])

  useEffect(() => {
    setTask(null)
    setSubtasks([])
  }, [id])

  useEffect(() => {
    void fetchTask()
  }, [fetchTask])

  useEffect(() => {
    void fetchSubtasks()
  }, [fetchSubtasks])

  const handleStop = useCallback(async () => {
    if (!id) return
    setActionLoading('stop')
    try {
      const stoppedTask = await stopStorageMainTask(id)
      setTask(stoppedTask)
      void fetchSubtasks()
    } catch {
      // error handled by request interceptor
    } finally {
      setActionLoading(null)
    }
  }, [id, fetchSubtasks])

  const handleRestart = useCallback(async () => {
    if (!id) return
    setActionLoading('restart')
    try {
      const restartedTask = await restartStorageMainTask(id)
      setTask(restartedTask)
      void fetchSubtasks()
    } catch {
      // error handled by request interceptor
    } finally {
      setActionLoading(null)
    }
  }, [id, fetchSubtasks])

  return {
    actionLoading,
    fetchSubtasks,
    fetchTask,
    handleRestart,
    handleStop,
    loading,
    setSubtasks,
    setTask,
    subtasks,
    subtasksLoading,
    task,
  }
}
