import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getCrawlerRunCount, getCrawlerRuns } from '@/api/crawler/crawlerRun'
import RunListPage from '../RunListPage'

const realtimeMock = vi.hoisted(() => ({
  handlers: {} as Record<string, (event: any) => void>,
}))

vi.mock('@/api/crawler/crawlerRun', () => ({
  deleteCrawlerRun: vi.fn(),
  getCrawlerRunCount: vi.fn(),
  getCrawlerRuns: vi.fn(),
  restartCrawlerRun: vi.fn(),
  stopCrawlerRun: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  subscribeRealtime: vi.fn((eventName: string, handler: (event: any) => void) => {
    realtimeMock.handlers[eventName] = handler
    return vi.fn()
  }),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: vi.fn().mockReturnValue(vi.fn()),
}))

function buildRun(status: 'queued' | 'running' | 'completed' | 'failed' | 'stopped' = 'running') {
  return {
    id: 'run-1',
    task_id: 'task-1',
    task_name: 'Run Task',
    status,
    crawl_mode: 'incremental' as const,
    queued_at: null,
    started_at: null,
    finished_at: null,
    result: null,
    error: null,
    resumed_from: null,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: null,
    logs: [],
  }
}

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('RunListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    realtimeMock.handlers = {}
  })

  it('loads runs with page and size before count is required', async () => {
    vi.mocked(getCrawlerRuns).mockResolvedValue({
      rows: [buildRun()],
      page: 1,
      size: 20,
      has_more: false,
    })
    vi.mocked(getCrawlerRunCount).mockResolvedValue({ total: 1 })

    render(<RunListPage />, { wrapper })

    await waitFor(() => expect(getCrawlerRuns).toHaveBeenCalledWith({ page: 1, size: 20 }))
    await waitFor(() => expect(getCrawlerRunCount).toHaveBeenCalledWith({}))

    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(getCrawlerRuns).toHaveBeenCalledTimes(1)
    expect(getCrawlerRunCount).toHaveBeenCalledTimes(1)
  })

  it('updates the current row from realtime without refetching the list', async () => {
    vi.mocked(getCrawlerRuns).mockResolvedValue({
      rows: [buildRun('running')],
      page: 1,
      size: 20,
      has_more: false,
    })
    vi.mocked(getCrawlerRunCount).mockResolvedValue({ total: 1 })

    const { findByText } = render(<RunListPage />, { wrapper })

    await findByText('Run Task')
    await waitFor(() => expect(realtimeMock.handlers['crawler.run.updated']).toBeTruthy())

    realtimeMock.handlers['crawler.run.updated']({
      id: 'event-1',
      event: 'crawler.run.updated',
      scope: 'crawler',
      resource_id: 'run-1',
      owner_id: 'owner-1',
      payload: {
        id: 'run-1',
        task_id: 'task-1',
        task_name: 'Run Task',
        status: 'failed',
        crawl_mode: 'incremental' as const,
        queued_at: null,
        started_at: null,
        finished_at: null,
        result: null,
        error: 'network error',
        resumed_from: null,
        created_at: '2026-08-01T00:00:00Z',
        updated_at: '2026-08-01T00:01:00Z',
        logs: [],
      },
      created_at: '2026-08-01T00:01:00Z',
    })

    await findByText('失败')
    expect(getCrawlerRuns).toHaveBeenCalledTimes(1)
  })
})