import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { getCrawlTaskRuntimeStatuses, getCrawlTasks } from '@/api/crawlTask'
import { useTaskListData } from '../hooks/useTaskListData'

vi.mock('@/api/crawlTask', () => ({
  deleteCrawlTask: vi.fn(),
  getCrawlTaskRuntimeStatuses: vi.fn(),
  getCrawlTasks: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

vi.mock('@/api/crawlerRun', () => ({
  restartCrawlerRun: vi.fn(),
  runCrawlTask: vi.fn(),
  stopCrawlerRun: vi.fn(),
}))

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('useTaskListData', () => {
  it('loads tasks and runtime statuses through queries', async () => {
    vi.mocked(getCrawlTasks).mockResolvedValue({ rows: [], total: 0 } as any)
    vi.mocked(getCrawlTaskRuntimeStatuses).mockResolvedValue({
      tasks: [],
      stats: { total: 0, running: 0, stopped: 0, idle: 0, queued: 0 },
    } as any)

    const { result } = renderHook(() => useTaskListData(), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.tasks).toEqual([])
    expect(result.current.total).toBe(0)
    expect(getCrawlTasks).toHaveBeenCalledTimes(1)
    expect(getCrawlTaskRuntimeStatuses).toHaveBeenCalledTimes(1)
  })
})
