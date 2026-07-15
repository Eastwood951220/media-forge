import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { getDashboardOverview } from '@/api/dashboard'
import { useDashboardOverview } from '../hooks/useDashboardOverview'

vi.mock('@/api/dashboard', () => ({
  getDashboardOverview: vi.fn(),
}))

const overview = {
  system_status: 'healthy',
  refreshed_at: '2026-07-15T00:00:00Z',
  crawler: { task_stats: { total: 0, enabled: 0, disabled: 0 }, runtime_stats: { total: 0, running: 0, stopped: 0, idle: 0 }, queue: {} },
  runs: { status_distribution: [], daily_trend: [], recent: [] },
  content: { movie_total: 0, storage_status: { stored: 0, storing: 0, not_stored: 0 } },
  storage: { task_status_distribution: [], recent_tasks: [], index: { status: 'completed', target_folder: '', category_count: 0, code_folder_count: 0, video_count: 0, completed_at: null, errors: [] } },
  alerts: [],
  partial_errors: [],
}

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('useDashboardOverview', () => {
  it('loads dashboard overview through TanStack Query and supports refresh', async () => {
    vi.mocked(getDashboardOverview).mockResolvedValue(overview as any)

    const { result } = renderHook(() => useDashboardOverview(), { wrapper })

    await waitFor(() => expect(result.current.data).toEqual(overview))
    expect(result.current.loading).toBe(false)

    result.current.refresh()
    await waitFor(() => expect(getDashboardOverview).toHaveBeenCalledTimes(2))
  })
})
