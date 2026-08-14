import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getCrawlerRuns } from '@/api/crawler/crawlerRun'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import RunListPage from '../RunListPage'

const realtimeMock = vi.hoisted(() => ({
  handlers: {} as Record<string, (event: any) => void>,
}))

vi.mock('@/api/crawler/crawlerRun', () => ({
  deleteCrawlerRun: vi.fn(),
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
    task_name: 'Run Task',
    status,
    crawl_mode: 'incremental' as const,
    created_at: '2026-08-01T00:00:00Z',
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
    useCrawlerRuntimeStore.getState().reset()
  })

  it('loads static run rows with one list request', async () => {
    vi.mocked(getCrawlerRuns).mockResolvedValue({
      rows: [buildRun()],
      page: 1,
      size: 20,
      has_more: false,
    } as any)

    render(<RunListPage />, { wrapper })

    await waitFor(() => expect(getCrawlerRuns).toHaveBeenCalledWith({ page: 1, size: 20 }))
    expect(getCrawlerRuns).toHaveBeenCalledTimes(1)
  })

  it('hydrates baseline run status from the store on mount', async () => {
    vi.mocked(getCrawlerRuns).mockResolvedValue({
      rows: [buildRun('running')],
      page: 1,
      size: 20,
      has_more: false,
    } as any)

    useCrawlerRuntimeStore.getState().hydrateRunRuntime({
      'run-1': {
        run_id: 'run-1',
        status: 'failed',
        error: 'network error',
        started_at: null,
        finished_at: null,
        state_updated_at: '2026-08-01T00:01:00Z',
      },
    })

    render(<RunListPage />, { wrapper })

    await waitFor(() => {
      expect(getCrawlerRuns).toHaveBeenCalledTimes(1)
    })
  })

  it('updates run status from realtime via the store without refetching', async () => {
    vi.mocked(getCrawlerRuns).mockResolvedValue({
      rows: [buildRun('running')],
      page: 1,
      size: 20,
      has_more: false,
    } as any)

    const { findByText } = render(<RunListPage />, { wrapper })

    await findByText('Run Task')
    await waitFor(() => expect(realtimeMock.handlers['crawler.run.status.updated']).toBeTruthy())

    realtimeMock.handlers['crawler.run.status.updated']({
      id: 'event-1',
      event: 'crawler.run.status.updated',
      scope: 'crawler.run',
      resource_id: 'run-1',
      owner_id: 'owner-1',
      payload: {
        run_id: 'run-1',
        status: 'failed',
        error: 'network error',
        started_at: null,
        finished_at: null,
        state_updated_at: '2026-08-01T00:01:00Z',
      },
      created_at: '2026-08-01T00:01:00Z',
    })

    await findByText('失败')
    expect(getCrawlerRuns).toHaveBeenCalledTimes(1)
  })
})