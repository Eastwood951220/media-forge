import { useCallback, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  countStorageMainTasks,
  deleteStorageMainTask,
  listStorageMainTasks,
  restartStorageMainTask,
  stopStorageMainTask,
} from '@/api/storage/storageTasks'
import type { StorageMainTask } from '@/api/storage/storageTasks/types'
import { queryKeys } from '@/api/queryKeys'

export function useStorageTaskList() {
  const queryClient = useQueryClient()
  const [current, setCurrent] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const listParams = { page: current, size: pageSize }
  const countParams = {}

  const listQuery = useQuery({
    queryKey: queryKeys.storageTasks.list(listParams),
    queryFn: () => listStorageMainTasks(listParams),
    placeholderData: (previousData) => previousData,
  })

  const countQuery = useQuery({
    queryKey: queryKeys.storageTasks.count(countParams),
    queryFn: () => countStorageMainTasks(countParams),
  })

  const tasks = listQuery.data?.rows ?? []
  const total = countQuery.data?.total ?? 0
  const loading = listQuery.isLoading
  const hasMore = listQuery.data?.has_more ?? false
  const countLoading = countQuery.isLoading

  const refreshCurrentPage = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.storageTasks.list(listParams) })
  }, [listParams, queryClient])

  const handleStop = useCallback(async (task: StorageMainTask) => {
    try {
      await stopStorageMainTask(task.id)
      refreshCurrentPage()
    } catch {
      // error handled by request interceptor
    }
  }, [refreshCurrentPage])

  const handleRestart = useCallback(async (task: StorageMainTask) => {
    try {
      await restartStorageMainTask(task.id)
      refreshCurrentPage()
    } catch {
      // error handled by request interceptor
    }
  }, [refreshCurrentPage])

  const handleDelete = useCallback(async (task: StorageMainTask) => {
    try {
      await deleteStorageMainTask(task.id)
      if (tasks.length === 1 && current > 1) {
        setCurrent((page) => page - 1)
        return
      }
      refreshCurrentPage()
      void queryClient.invalidateQueries({ queryKey: queryKeys.storageTasks.count(countParams) })
    } catch {
      // error handled by request interceptor
    }
  }, [current, refreshCurrentPage, queryClient, tasks.length, countParams])

  return {
    current,
    pageSize,
    hasMore,
    total,
    countLoading,
    setCurrent,
    setPageSize,
    handleDelete,
    handleRestart,
    handleStop,
    loading,
    refreshCurrentPage,
    tasks,
  }
}
