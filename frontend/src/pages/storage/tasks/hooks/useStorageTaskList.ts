import { useCallback, useMemo, type SetStateAction } from 'react'
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
import { useRouteActivationRefresh } from '@/hooks/useRouteActivationRefresh'
import { useSessionListState } from '@/hooks/useSessionListState'

const STORAGE_TASK_LIST_STATE_CACHE_KEY = 'media-forge:storage-task-list-state'

export function useStorageTaskList() {
  const queryClient = useQueryClient()
  const [listState, setListState] = useSessionListState(STORAGE_TASK_LIST_STATE_CACHE_KEY, {
    current: 1,
    pageSize: 20,
  })
  const current = listState.current
  const pageSize = listState.pageSize
  const setCurrent = useCallback((value: SetStateAction<number>) => {
    setListState((previous) => ({
      ...previous,
      current: typeof value === 'function' ? value(previous.current) : value,
    }))
  }, [setListState])
  const setPageSize = useCallback((value: SetStateAction<number>) => {
    setListState((previous) => ({
      ...previous,
      pageSize: typeof value === 'function' ? value(previous.pageSize) : value,
    }))
  }, [setListState])

  const listParams = useMemo(() => ({ page: current, size: pageSize }), [current, pageSize])
  const countParams = useMemo(() => ({}), [])

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

  useRouteActivationRefresh(refreshCurrentPage)

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
  }, [current, refreshCurrentPage, queryClient, tasks.length, countParams, setCurrent])

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
