import { useEffect, useMemo } from 'react'
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import {
  getCrawlerRunAgentEvents,
  getCrawlerRunAgentWorkItems,
} from '@/api/crawler/crawlerRun'
import type {
  AgentEvent,
  AgentWorkSummary,
} from '@/api/crawler/crawlerAgent/types'
import { queryKeys } from '@/api/queryKeys'
import { subscribeRealtime } from '@/realtime/eventSourceClient'
import {
  groupAgentEvents,
  mergeAgentEvents,
  type AgentWorkTimeline,
} from '../../shared/agentDiagnostics'

const PAGE_SIZE = 100

const emptyAgentWorkSummary: AgentWorkSummary = {
  pending: 0,
  active: 0,
  completed: 0,
  failed: 0,
  total: 0,
}

export function useRunAgentDiagnostics(runId: string | undefined) {
  const queryClient = useQueryClient()

  const workQuery = useQuery({
    queryKey: queryKeys.crawlerRunAgent.workItems(runId ?? ''),
    queryFn: () => getCrawlerRunAgentWorkItems(runId!),
    enabled: Boolean(runId),
  })

  const eventQuery = useInfiniteQuery({
    queryKey: queryKeys.crawlerRunAgent.events(runId ?? ''),
    queryFn: ({ pageParam }) =>
      getCrawlerRunAgentEvents(runId!, {
        size: PAGE_SIZE,
        cursor: pageParam ?? undefined,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => (lastPage.has_more ? lastPage.next_cursor : undefined),
    enabled: Boolean(runId),
  })

  const workItems = useMemo(() => workQuery.data?.rows ?? [], [workQuery.data])
  const events = useMemo(
    () => eventQuery.data?.pages.flatMap((page) => page.rows) ?? [],
    [eventQuery.data],
  )

  // Append realtime Agent events for this run into the first event page.
  useEffect(() => {
    if (!runId) return undefined
    const unsubscribe = subscribeRealtime('crawler.agent.event.created', (event) => {
      const payload = event.payload as unknown as AgentEvent | undefined
      if (!payload?.id || payload.run_id !== runId) return
      queryClient.setQueryData<{ pages: { rows: AgentEvent[] }[]; pageParams: unknown[] }>(
        queryKeys.crawlerRunAgent.events(runId),
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
    })
    return unsubscribe
  }, [queryClient, runId])

  // Re-sync on backend restart / connection loss.
  useEffect(() => {
    if (!runId) return undefined
    const unsubscribe = subscribeRealtime('system.resync_required', () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.crawlerRunAgent.all(runId) })
    })
    return unsubscribe
  }, [queryClient, runId])

  const timelines: AgentWorkTimeline[] = useMemo(
    () => groupAgentEvents(workItems, events),
    [workItems, events],
  )

  return {
    workItems,
    summary: workQuery.data?.summary ?? emptyAgentWorkSummary,
    events,
    timelines,
    loading: workQuery.isLoading || eventQuery.isLoading,
    hasNextPage: eventQuery.hasNextPage,
    fetchNextPage: eventQuery.fetchNextPage,
    loadingMore: eventQuery.isFetchingNextPage,
    hasDiagnostics: Boolean(workItems.length || events.length),
  }
}
