import type { QueryClient } from '@tanstack/react-query'
import { queryKeys } from './queryKeys'

export function invalidateCrawlerRunLists(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.crawlerRuns.all() })
}

export function invalidateCrawlerTaskLists(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.crawlerTasks.all() })
}
