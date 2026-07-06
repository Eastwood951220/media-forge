import { useCallback, useEffect, useState } from 'react'
import {
  deleteStorageMainTask,
  listStorageMainTasks,
  restartStorageMainTask,
  stopStorageMainTask,
} from '@/api/storage/storageTasks'
import type { StorageMainTask } from '@/api/storage/storageTasks/types'

export function useStorageTaskList() {
  const [tasks, setTasks] = useState<StorageMainTask[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [current, setCurrent] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const fetchTasks = useCallback(async (page: number, size: number) => {
    setLoading(true)
    try {
      const data = await listStorageMainTasks({ page, limit: size })
      setTasks(data.rows)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchTasks(current, pageSize)
  }, [current, pageSize, fetchTasks])

  const refreshCurrentPage = useCallback(() => {
    void fetchTasks(current, pageSize)
  }, [current, pageSize, fetchTasks])

  const handleStop = useCallback(async (task: StorageMainTask) => {
    try {
      await stopStorageMainTask(task.id)
      void fetchTasks(current, pageSize)
    } catch {
      // error handled by request interceptor
    }
  }, [current, pageSize, fetchTasks])

  const handleRestart = useCallback(async (task: StorageMainTask) => {
    try {
      await restartStorageMainTask(task.id)
      void fetchTasks(current, pageSize)
    } catch {
      // error handled by request interceptor
    }
  }, [current, pageSize, fetchTasks])

  const handleDelete = useCallback(async (task: StorageMainTask) => {
    try {
      await deleteStorageMainTask(task.id)
      if (tasks.length === 1 && current > 1) {
        setCurrent((page) => page - 1)
        return
      }
      void fetchTasks(current, pageSize)
    } catch {
      // error handled by request interceptor
    }
  }, [current, fetchTasks, pageSize, tasks.length])

  return {
    current,
    fetchTasks,
    handleDelete,
    handleRestart,
    handleStop,
    loading,
    pageSize,
    refreshCurrentPage,
    setCurrent,
    setPageSize,
    setTasks,
    setTotal,
    tasks,
    total,
  }
}
