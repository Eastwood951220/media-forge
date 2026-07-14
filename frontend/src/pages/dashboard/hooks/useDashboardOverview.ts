import { useCallback, useEffect, useState } from 'react'
import { getDashboardOverview } from '@/api/dashboard'
import type { DashboardOverview } from '@/api/dashboard/types'

export function useDashboardOverview() {
  const [data, setData] = useState<DashboardOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const fetchOverview = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    if (mode === 'initial') {
      setLoading(true)
    } else {
      setRefreshing(true)
    }
    try {
      const overview = await getDashboardOverview()
      setData(overview)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err : new Error('首页数据加载失败'))
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void fetchOverview('initial')
  }, [fetchOverview])

  const refresh = useCallback(() => {
    void fetchOverview(data ? 'refresh' : 'initial')
  }, [data, fetchOverview])

  return {
    data,
    loading,
    error,
    refreshing,
    fetchOverview,
    refresh,
  }
}
