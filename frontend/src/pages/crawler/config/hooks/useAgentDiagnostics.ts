import { useCallback, useEffect, useMemo, useState } from 'react'
import { App } from 'antd'
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import {
  clearOperationalAgentEvents,
  fetchAgentEvents,
  fetchAgentStatus,
} from '@/api/crawler/crawlerAgent'
import type { AgentEvent, AgentStatus } from '@/api/crawler/crawlerAgent/types'
import { queryKeys } from '@/api/queryKeys'
import { subscribeRealtime } from '@/realtime/eventSourceClient'
import { mergeAgentEvents } from '../../shared/agentDiagnostics'

const PAGE_SIZE = 20

export function useAgentDiagnostics() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [levelFilter, setLevelFilter] = useState<string | undefined>()
  const [sourceFilter, setSourceFilter] = useState<string | undefined>()

  const statusQuery = useQuery({
    queryKey: queryKeys.crawlerAgent.status(),
    queryFn: () => fetchAgentStatus(),
    refetchInterval: 30_000,
  })

  const eventsQuery = useInfiniteQuery({
    queryKey: queryKeys.crawlerAgent.events({ level: levelFilter, source: sourceFilter }),
    queryFn: ({ pageParam }) =>
      fetchAgentEvents({
        size: PAGE_SIZE,
        cursor: pageParam ?? undefined,
        level: levelFilter,
        source: sourceFilter,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => (lastPage.has_more ? lastPage.next_cursor : undefined),
  })

  const events = useMemo(
    () => eventsQuery.data?.pages.flatMap((page) => page.rows) ?? [],
    [eventsQuery.data],
  )

  // Append realtime Agent events into the first global event page.
  useEffect(() => {
    const unsubscribe = subscribeRealtime('crawler.agent.event.created', (event) => {
      const payload = event.payload as unknown as AgentEvent | undefined
      if (!payload?.id) return
      queryClient.setQueryData<{ pages: { rows: AgentEvent[] }[]; pageParams: unknown[] }>(
        queryKeys.crawlerAgent.events({ level: levelFilter, source: sourceFilter }),
        (current) => {
          if (!current) return current
          const firstPage = current.pages[0]
          if (!firstPage) return current
          const merged = mergeAgentEvents(firstPage.rows, [payload], { limit: PAGE_SIZE })
          return {
            ...current,
            pages: [{ ...firstPage, rows: merged }, ...current.pages.slice(1)],
          }
        },
      )
      // Keep status counters fresh.
      void queryClient.invalidateQueries({ queryKey: queryKeys.crawlerAgent.status() })
    })
    return unsubscribe
  }, [queryClient, levelFilter, sourceFilter])

  // Re-sync on backend restart / connection loss.
  useEffect(() => {
    const unsubscribe = subscribeRealtime('system.resync_required', () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.crawlerAgent.all() })
    })
    return unsubscribe
  }, [queryClient])

  const clearMutation = useMutation({
    mutationFn: clearOperationalAgentEvents,
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.crawlerAgent.all() })
      message.success(`已清理 ${result.deleted} 条近期诊断日志`)
    },
  })

  const handleClear = useCallback(() => {
    clearMutation.mutate()
  }, [clearMutation])

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.crawlerAgent.all() })
  }, [queryClient])

  return {
    status: statusQuery.data as AgentStatus | undefined,
    statusLoading: statusQuery.isLoading,
    events,
    eventsLoading: eventsQuery.isLoading,
    hasNextPage: eventsQuery.hasNextPage,
    fetchNextPage: eventsQuery.fetchNextPage,
    loadingMore: eventsQuery.isFetchingNextPage,
    levelFilter,
    setLevelFilter,
    sourceFilter,
    setSourceFilter,
    refresh,
    clearLoading: clearMutation.isPending,
    handleClear,
  }
}
