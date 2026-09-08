import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { message } from 'antd'
import type { PropsWithChildren } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { deleteCrawlerRun, getCrawlerRuns } from '@/api/crawler/crawlerRun'
import type { RunListResponse } from '@/api/crawler/crawlerRun/types'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import RunListPage from '../RunListPage'

const realtimeMock = vi.hoisted(() => ({
  handlers: {} as Record<string, (event: unknown) => void>,
}))

vi.mock('@/api/crawler/crawlerRun', () => ({
  deleteCrawlerRun: vi.fn(),
  getCrawlerRuns: vi.fn(),
  restartCrawlerRun: vi.fn(),
  stopCrawlerRun: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  subscribeRealtime: vi.fn((eventName: string, handler: (event: unknown) => void) => {
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
    sessionStorage.clear()
    realtimeMock.handlers = {}
    useCrawlerRuntimeStore.getState().reset()
  })

  it('loads static run rows with one list request', async () => {
    vi.mocked(getCrawlerRuns).mockResolvedValue({
      rows: [buildRun()],
      page: 1,
      size: 20,
      has_more: false,
    } as never)

    render(<RunListPage />, { wrapper })

    await waitFor(() => expect(getCrawlerRuns).toHaveBeenCalledWith({ page: 1, size: 20 }))
    expect(getCrawlerRuns).toHaveBeenCalledTimes(1)
  })

  it('renders run task name and scope tag in one line', async () => {
    vi.mocked(getCrawlerRuns).mockResolvedValue({
      rows: [{ ...buildRun(), run_scope_label: '部分 URL', run_scope: 'task_url_subset' }],
      page: 1,
      size: 20,
      has_more: false,
    } as never)

    render(<RunListPage />, { wrapper })

    const taskName = await screen.findByText('Run Task')
    const nameLine = taskName.closest('[data-testid="run-task-name-line"]')

    expect(nameLine).toBeInTheDocument()
    expect(nameLine).toHaveTextContent('Run Task')
    expect(nameLine).toHaveTextContent('部分 URL')
  })

  it('renders crawler progress summary in the run list', async () => {
    vi.mocked(getCrawlerRuns).mockResolvedValue({
      rows: [{
        ...buildRun('completed'),
        summary: {
          total: 4,
          pending_crawl: 0,
          crawling: 0,
          saved: 1,
          skipped: 1,
          crawl_failed: 2,
          save_failed: 0,
          completed: 2,
          waiting: 0,
          failed: 2,
        },
      }],
      total: 1,
    } as unknown as RunListResponse)

    render(<RunListPage />, { wrapper })

    expect(await screen.findByRole('columnheader', { name: '爬虫进度' })).toBeInTheDocument()
    expect(await screen.findByText('Run Task')).toBeInTheDocument()
    expect(screen.getByText('总 4')).toBeInTheDocument()
    expect(screen.getByText('成功 2')).toBeInTheDocument()
    expect(screen.getByText('失败 2').className).toContain('runProgressErrorMeta')
    expect(screen.getByText('跳过 1')).toBeInTheDocument()
  })

  it('hydrates baseline run status from the store on mount', async () => {
    vi.mocked(getCrawlerRuns).mockResolvedValue({
      rows: [buildRun('running')],
      page: 1,
      size: 20,
      has_more: false,
    } as never)

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
    } as never)

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

  it('keeps delete confirmation pending until the refreshed list arrives', async () => {
    let resolveRefresh!: (value: RunListResponse) => void
    const refreshResult = new Promise<RunListResponse>((resolve) => {
      resolveRefresh = resolve
    })

    vi.mocked(deleteCrawlerRun).mockResolvedValue(undefined)
    vi.mocked(getCrawlerRuns)
      .mockResolvedValueOnce({
        rows: [buildRun('failed')],
        total: 1,
      } as unknown as RunListResponse)
      .mockImplementationOnce(() => refreshResult)

    render(<RunListPage />, { wrapper })

    await screen.findByText('Run Task')
    await waitFor(() => expect(useCrawlerRuntimeStore.getState().runRuntimeById['run-1']).toBeDefined())
    let refreshResolved = false
    let runtimeRemovedBeforeRefresh = false
    const unsubscribe = useCrawlerRuntimeStore.subscribe((state) => {
      if (!refreshResolved && !state.runRuntimeById['run-1']) {
        runtimeRemovedBeforeRefresh = true
      }
    })

    fireEvent.click(screen.getByRole('button', { name: /删除/ }))
    await screen.findByText('删除运行记录')
    fireEvent.click(screen.getByRole('button', { name: /确\s*定/ }))

    await waitFor(() => expect(deleteCrawlerRun).toHaveBeenCalledWith('run-1'))
    await waitFor(() => expect(getCrawlerRuns).toHaveBeenCalledTimes(2))
    expect(screen.getByText('删除运行记录')).toBeInTheDocument()
    expect(runtimeRemovedBeforeRefresh).toBe(false)

    refreshResolved = true
    resolveRefresh({
      rows: [],
      total: 0,
    })

    await waitFor(() => expect(screen.queryByText('Run Task')).not.toBeInTheDocument())
    expect(useCrawlerRuntimeStore.getState().runRuntimeById['run-1']).toBeUndefined()
    unsubscribe()
  })

  it('keeps realtime state when the post-delete list refresh fails', async () => {
    const warningSpy = vi.spyOn(message, 'warning').mockReturnValue({} as ReturnType<typeof message.warning>)
    const successSpy = vi.spyOn(message, 'success').mockReturnValue({} as ReturnType<typeof message.success>)

    vi.mocked(deleteCrawlerRun).mockResolvedValue(undefined)
    vi.mocked(getCrawlerRuns)
      .mockResolvedValueOnce({
        rows: [buildRun('failed')],
        total: 1,
      } as unknown as RunListResponse)
      .mockRejectedValueOnce(new Error('refresh failed'))
    useCrawlerRuntimeStore.getState().hydrateRunRuntime({
      'run-1': {
        run_id: 'run-1',
        status: 'failed',
        error: 'live failure',
        started_at: null,
        finished_at: null,
        state_updated_at: '2026-08-01T00:01:00Z',
      },
    })

    render(<RunListPage />, { wrapper })

    await screen.findByText('Run Task')
    fireEvent.click(screen.getByRole('button', { name: /删除/ }))
    await screen.findByText('删除运行记录')
    fireEvent.click(screen.getByRole('button', { name: /确\s*定/ }))

    await waitFor(() => {
      expect(warningSpy).toHaveBeenCalledWith('运行记录已删除，但列表刷新失败，请手动刷新')
    })
    expect(successSpy).not.toHaveBeenCalled()
    expect(useCrawlerRuntimeStore.getState().runRuntimeById['run-1']?.error).toBe('live failure')

    warningSpy.mockRestore()
    successSpy.mockRestore()
  })

  it('keeps pagination and refreshes that page when the run list is mounted again', async () => {
    vi.mocked(getCrawlerRuns).mockResolvedValue({
      rows: [buildRun('completed')],
      total: 120,
      page: 1,
      size: 20,
      has_more: true,
    } as never)

    const { unmount } = render(<RunListPage />, { wrapper })

    await screen.findByText('Run Task')
    fireEvent.click(screen.getByTitle('2'))
    await waitFor(() => expect(getCrawlerRuns).toHaveBeenCalledWith({ page: 2, size: 20 }))

    unmount()
    render(<RunListPage />, { wrapper })

    await waitFor(() => expect(getCrawlerRuns).toHaveBeenLastCalledWith({ page: 2, size: 20 }))
  })
})
