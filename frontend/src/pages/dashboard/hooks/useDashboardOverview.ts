import { useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getDashboardOverview } from '@/api/dashboard'
import { queryKeys } from '@/api/queryKeys'
import type { DashboardOverview } from '@/api/dashboard/types'

export function useDashboardOverview() {
  const queryClient = useQueryClient()
  const query = useQuery<DashboardOverview, Error>({
    queryKey: queryKeys.dashboard.overview(),
    queryFn: getDashboardOverview,
  })

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.overview() })
  }, [queryClient])

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error,
    refreshing: query.isFetching && !query.isLoading,
    fetchOverview: refresh,
    refresh,
  }
}
