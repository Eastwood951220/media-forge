import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  cancelScrapingTask,
  getScrapingTask,
  listScrapingTasks,
  retryScrapingTask,
} from '@/api/scraping/scrapingTasks'
import { queryKeys } from '@/api/queryKeys'
import { subscribeRealtime } from '@/realtime/eventSourceClient'
import type { RealtimeEvent, ScrapingTaskUpdatedPayload } from '@/realtime/types'

export function useScrapingTaskList() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(20)
  const params = useMemo(() => ({ page, size }), [page, size])

  const query = useQuery({
    queryKey: queryKeys.scrapingTasks.list(params),
    queryFn: () => listScrapingTasks(params),
    placeholderData: (previous) => previous,
  })

  useEffect(() => {
    const unsubscribe = subscribeRealtime<ScrapingTaskUpdatedPayload>(
      'scraping.task.updated',
      (_event: RealtimeEvent<ScrapingTaskUpdatedPayload>) => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.list(params) })
      },
    )
    return unsubscribe
  }, [params, queryClient])

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.list(params) })
  }, [params, queryClient])

  const cancel = useCallback(async (id: string) => {
    await cancelScrapingTask(id)
    refresh()
  }, [refresh])

  const retry = useCallback(async (id: string) => {
    await retryScrapingTask(id)
    refresh()
  }, [refresh])

  return {
    page,
    size,
    setPage,
    setSize,
    tasks: query.data?.rows ?? [],
    total: query.data?.total ?? 0,
    loading: query.isLoading,
    refresh,
    cancel,
    retry,
  }
}

export function useScrapingTaskDetail(id: string) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: queryKeys.scrapingTasks.detail(id),
    queryFn: () => getScrapingTask(id),
  })

  useEffect(() => {
    const refresh = () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.detail(id) })
    }
    const unsubscribeTask = subscribeRealtime<ScrapingTaskUpdatedPayload>(
      'scraping.task.updated',
      (_event: RealtimeEvent<ScrapingTaskUpdatedPayload>) => refresh(),
    )
    const unsubscribeItem = subscribeRealtime(
      'scraping.item.updated',
      (_event: RealtimeEvent) => refresh(),
    )
    return () => {
      unsubscribeTask()
      unsubscribeItem()
    }
  }, [id, queryClient])

  const cancel = useCallback(async () => {
    await cancelScrapingTask(id)
    void queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.detail(id) })
  }, [id, queryClient])

  const retry = useCallback(async () => {
    const created = await retryScrapingTask(id)
    void queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.detail(id) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.all() })
    return created
  }, [id, queryClient])

  return { task: query.data, loading: query.isLoading, cancel, retry }
}
