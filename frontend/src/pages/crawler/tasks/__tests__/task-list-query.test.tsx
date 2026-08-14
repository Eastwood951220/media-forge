import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { getCrawlTasks } from '@/api/crawler/crawlTask'
import { useTaskListData } from '../hooks/useTaskListData'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'

vi.mock('@/api/crawler/crawlTask', () => ({
  deleteCrawlTask: vi.fn(),
  getCrawlTasks: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

vi.mock('@/api/crawler/crawlerRun', () => ({
  restartCrawlerRun: vi.fn(),
  runCrawlTask: vi.fn(),
  stopCrawlerRun: vi.fn(),
}))

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const taskRow = {
  id: 'task-1',
  name: 'Test Task',
  storage_location: '/storage',
  is_skip: false,
  urls: [{ id: 'url-1', position: 1, url: 'https://example.com', url_type: 'actors', has_magnet: false, has_chinese_sub: false, url_name: null }],
}

describe('useTaskListData', () => {
  beforeEach(() => {
    useCrawlerRuntimeStore.getState().reset()
  })

  it('loads static task rows with one list request and reads runtime from the store', async () => {
    vi.mocked(getCrawlTasks).mockResolvedValue({ rows: [taskRow], total: 1, page: 1, size: 20 } as any)
    useCrawlerRuntimeStore.getState().replaceTaskRuntimeSnapshot({
      tasks: [{ task_id: taskRow.id, runtime_status: 'running', latest_run_id: 'run-1', last_run_at: null, state_updated_at: '2026-08-13T09:00:00Z' }],
      stats: { total: 1, idle: 0, running: 1, queued: 0, stopped: 0 },
    })

    const { result } = renderHook(() => useTaskListData(), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.total).toBe(1)
    expect(result.current.runtimeByTaskId[taskRow.id].runtime_status).toBe('running')
    expect(getCrawlTasks).toHaveBeenCalledTimes(1)
  })
})