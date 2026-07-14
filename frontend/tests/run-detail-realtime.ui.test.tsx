import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RunDetailPage from '../src/pages/crawler/runs/RunDetailPage'
import { getCrawlerRun, getCrawlerRunLogs, getCrawlerRunTaskSummary, getCrawlerRunTasks } from '../src/api/crawlerRun'
import type { RealtimeEventName, RealtimeHandler } from '../src/realtime/types'

const realtimeHandlers = new Map<string, Set<RealtimeHandler>>()

vi.mock('../src/api/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunLogs: vi.fn(),
  getCrawlerRunTaskSummary: vi.fn(),
  getCrawlerRunTasks: vi.fn(),
}))

vi.mock('../src/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(() => null),
  subscribeRealtime: vi.fn((eventName: RealtimeEventName, handler: RealtimeHandler) => {
    const handlers = realtimeHandlers.get(eventName) ?? new Set()
    handlers.add(handler)
    realtimeHandlers.set(eventName, handlers)
    return () => handlers.delete(handler)
  }),
}))

vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: (options: { count: number; estimateSize?: (index: number) => number }) => ({
    getVirtualItems: () => {
      const items = []
      for (let i = 0; i < options.count; i++) {
        const size = options.estimateSize?.(i) ?? 48
        items.push({ index: i, start: i * size, size, end: (i + 1) * size })
      }
      return items
    },
    getTotalSize: () => options.count * (options.estimateSize?.(0) ?? 48),
    measureElement: () => {},
  }),
}))

function emit(eventName: RealtimeEventName, payload: Record<string, unknown>, resourceId: string | null = 'run-1') {
  for (const handler of realtimeHandlers.get(eventName) ?? []) {
    handler({
      id: `event-${Date.now()}`,
      event: eventName,
      scope: eventName.startsWith('crawler') ? 'crawler.run' : 'system',
      resource_id: resourceId,
      owner_id: 'user-1',
      payload,
      created_at: '2026-07-03T00:00:00Z',
    })
  }
}

function renderPage(initialPath = '/crawler/runs/run-1') {
  const rootRoute = createRootRoute({ component: () => <RunDetailPage /> })
  const detailRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/runs/$id',
    component: RunDetailPage,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([detailRoute]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })

  return render(<RouterProvider router={router} />)
}

describe('RunDetailPage realtime events', () => {
  beforeEach(() => {
    realtimeHandlers.clear()
    vi.mocked(getCrawlerRun).mockResolvedValue({
      id: 'run-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'running',
      crawl_mode: 'incremental',
      queued_at: null,
      started_at: null,
      finished_at: null,
      result: null,
      error: null,
      resumed_from: null,
      created_at: '2026-07-03T00:00:00Z',
      updated_at: null,
      logs: [],
    })
    vi.mocked(getCrawlerRunLogs).mockResolvedValue([])
    vi.mocked(getCrawlerRunTasks).mockResolvedValue({
      rows: [],
      total: 0,
    })
    vi.mocked(getCrawlerRunTaskSummary).mockResolvedValue({
      total: 0,
      pending_crawl: 0,
      crawling: 0,
      saved: 0,
      skipped: 0,
      crawl_failed: 0,
      save_failed: 0,
      completed: 0,
      waiting: 0,
      failed: 0,
    })
  })

  it('renders run details and loads logs from API', async () => {
    renderPage()

    expect(await screen.findByText('运行详情 - 任务A')).toBeInTheDocument()
    expect(getCrawlerRun).toHaveBeenCalledWith('run-1')
    expect(getCrawlerRunLogs).toHaveBeenCalledWith('run-1')
    expect(getCrawlerRunTasks).toHaveBeenCalledWith('run-1', {
      page: 1,
      size: 50,
      status: undefined,
      keyword: undefined,
    })
    expect(getCrawlerRunTaskSummary).toHaveBeenCalledWith('run-1')
  })

  it('does not expect summary from the paginated tasks response', async () => {
    vi.mocked(getCrawlerRunTaskSummary).mockResolvedValue({
      total: 2,
      pending_crawl: 1,
      crawling: 0,
      saved: 1,
      skipped: 0,
      crawl_failed: 0,
      save_failed: 0,
      completed: 1,
      waiting: 1,
      failed: 0,
    })
    vi.mocked(getCrawlerRunTasks).mockResolvedValue({
      rows: [],
      total: 2,
    })

    renderPage()

    expect(await screen.findByText('运行详情 - 任务A')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('总数').parentElement?.textContent).toContain('2')
      expect(screen.getByText('完成').parentElement?.textContent).toContain('1')
      expect(screen.getByText('等待').parentElement?.textContent).toContain('1')
    })
  })

  it('keeps existing logs when completion run updates contain empty logs', async () => {
    vi.mocked(getCrawlerRunLogs).mockResolvedValue([
      {
        timestamp: '2026-07-03T00:03:00Z',
        level: 'INFO',
        component: 'crawler.run',
        event: 'run_log',
        message: '详情 53/53 跳过',
        context: { reason: 'already_exists' },
      },
    ])
    vi.mocked(getCrawlerRun)
      .mockResolvedValueOnce({
        id: 'run-1',
        task_id: 'task-1',
        task_name: '任务A',
        status: 'running',
        crawl_mode: 'incremental',
        queued_at: null,
        started_at: null,
        finished_at: null,
        result: null,
        error: null,
        resumed_from: null,
        created_at: '2026-07-03T00:00:00Z',
        updated_at: null,
        logs: [],
      })
      .mockResolvedValueOnce({
        id: 'run-1',
        task_id: 'task-1',
        task_name: '任务A',
        status: 'completed',
        crawl_mode: 'incremental',
        queued_at: null,
        started_at: '2026-07-03T00:01:00Z',
        finished_at: '2026-07-03T00:10:00Z',
        result: { skipped_tasks: 54 },
        error: null,
        resumed_from: null,
        created_at: '2026-07-03T00:00:00Z',
        updated_at: null,
        logs: [],
      })

    renderPage()

    expect(await screen.findByText('详情 53/53 跳过')).toBeInTheDocument()

    emit('crawler.run.updated', {
      id: 'run-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'completed',
      crawl_mode: 'incremental',
      queued_at: null,
      started_at: null,
      finished_at: '2026-07-03T00:10:00Z',
      result: { skipped_tasks: 54 },
      error: null,
      resumed_from: null,
      created_at: '2026-07-03T00:00:00Z',
      updated_at: null,
      logs: [],
    })

    await waitFor(() => {
      expect(screen.getByText('已完成')).toBeInTheDocument()
    })
    expect(screen.getByText('详情 53/53 跳过')).toBeInTheDocument()
  })

  it('refetches tasks for each url completion refresh event', async () => {
    renderPage()
    await screen.findByText('运行详情 - 任务A')

    const initialTasksCalls = vi.mocked(getCrawlerRunTasks).mock.calls.length

    emit('crawler.run.detail.updated', {
      run_id: 'run-1',
      tasks: [],
      refresh_tasks: true,
      reason: 'url_completed',
    })
    emit('crawler.run.detail.updated', {
      run_id: 'run-1',
      tasks: [],
      refresh_tasks: true,
      reason: 'url_completed',
    })

    await waitFor(() => {
      expect(vi.mocked(getCrawlerRunTasks).mock.calls.length).toBeGreaterThanOrEqual(initialTasksCalls + 2)
    })
  })

  it('reloads final logs from the logs endpoint when a run completes', async () => {
    vi.mocked(getCrawlerRunLogs)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          timestamp: '2026-07-03T00:10:00Z',
          level: 'INFO',
          component: 'crawler.run',
          event: 'run_log',
          message: '详情处理完成: 总计=54 已完成=0 失败=0 跳过=54',
          context: {},
        },
      ])

    renderPage()
    await screen.findByText('运行详情 - 任务A')

    const initialCallCount = vi.mocked(getCrawlerRunLogs).mock.calls.length as number
    const initialTasksCalls = vi.mocked(getCrawlerRunTasks).mock.calls.length as number
    const initialSummaryCalls = vi.mocked(getCrawlerRunTaskSummary).mock.calls.length as number

    emit('crawler.run.updated', {
      id: 'run-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'completed',
      crawl_mode: 'incremental',
      queued_at: null,
      started_at: null,
      finished_at: '2026-07-03T00:10:00Z',
      result: { skipped_tasks: 54 },
      error: null,
      resumed_from: null,
      created_at: '2026-07-03T00:00:00Z',
      updated_at: null,
      logs: [],
    })

    await waitFor(() => {
      expect(vi.mocked(getCrawlerRunLogs).mock.calls.length).toBeGreaterThan(initialCallCount)
      expect(vi.mocked(getCrawlerRunTasks).mock.calls.length).toBeGreaterThan(initialTasksCalls)
      expect(vi.mocked(getCrawlerRunTaskSummary).mock.calls.length).toBeGreaterThan(initialSummaryCalls)
    })
    expect(await screen.findByText('详情处理完成: 总计=54 已完成=0 失败=0 跳过=54')).toBeInTheDocument()
  })

  it('resyncs snapshots when system resync is required', async () => {
    renderPage()

    await screen.findByText('运行详情 - 任务A')

    const initialRunCalls = vi.mocked(getCrawlerRun).mock.calls.length
    const initialLogsCalls = vi.mocked(getCrawlerRunLogs).mock.calls.length
    const initialTasksCalls = vi.mocked(getCrawlerRunTasks).mock.calls.length
    const initialSummaryCalls = vi.mocked(getCrawlerRunTaskSummary).mock.calls.length

    emit('system.resync_required', { reason: 'connection_error' }, null)

    await waitFor(() => {
      expect(vi.mocked(getCrawlerRun).mock.calls.length).toBeGreaterThan(initialRunCalls)
      expect(vi.mocked(getCrawlerRunLogs).mock.calls.length).toBeGreaterThan(initialLogsCalls)
      expect(vi.mocked(getCrawlerRunTasks).mock.calls.length).toBeGreaterThan(initialTasksCalls)
      expect(vi.mocked(getCrawlerRunTaskSummary).mock.calls.length).toBeGreaterThan(initialSummaryCalls)
    })
  })

  it('reloads the run snapshot when a terminal run event arrives', async () => {
    vi.mocked(getCrawlerRun)
      .mockResolvedValueOnce({
        id: 'run-1',
        task_id: 'task-1',
        task_name: '任务A',
        status: 'running',
        crawl_mode: 'incremental',
        queued_at: null,
        started_at: null,
        finished_at: null,
        result: null,
        error: null,
        resumed_from: null,
        created_at: '2026-07-03T00:00:00Z',
        updated_at: null,
        logs: [],
      })
      .mockResolvedValueOnce({
        id: 'run-1',
        task_id: 'task-1',
        task_name: '任务A',
        status: 'completed',
        crawl_mode: 'incremental',
        queued_at: null,
        started_at: '2026-07-03T00:01:00Z',
        finished_at: '2026-07-03T00:10:00Z',
        result: { total_tasks: 1, saved: 1 },
        error: null,
        resumed_from: null,
        created_at: '2026-07-03T00:00:00Z',
        updated_at: null,
        logs: [],
      })

    renderPage()
    await screen.findByText('运行详情 - 任务A')

    const initialRunCalls = vi.mocked(getCrawlerRun).mock.calls.length

    emit('crawler.run.updated', {
      id: 'run-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'completed',
      crawl_mode: 'incremental',
      queued_at: null,
      started_at: null,
      finished_at: '2026-07-03T00:10:00Z',
      result: {},
      error: null,
      resumed_from: null,
      created_at: '2026-07-03T00:00:00Z',
      updated_at: null,
      logs: [],
    })

    await waitFor(() => {
      expect(vi.mocked(getCrawlerRun).mock.calls.length).toBeGreaterThan(initialRunCalls)
    })
    expect(await screen.findByText('已完成')).toBeInTheDocument()
  })

  it('updates summary metrics from realtime detail event summary payload', async () => {
    vi.mocked(getCrawlerRunTaskSummary).mockResolvedValue({
      total: 1,
      pending_crawl: 1,
      crawling: 0,
      saved: 0,
      skipped: 0,
      crawl_failed: 0,
      save_failed: 0,
      completed: 0,
      waiting: 1,
      failed: 0,
    })
    vi.mocked(getCrawlerRunTasks).mockResolvedValue({
      rows: [],
      total: 1,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('等待').parentElement?.textContent).toContain('1')
    })

    emit('crawler.run.detail.updated', {
      run_id: 'run-1',
      tasks: [],
      summary: {
        total: 1,
        pending_crawl: 0,
        crawling: 0,
        saved: 1,
        skipped: 0,
        crawl_failed: 0,
        save_failed: 0,
        completed: 1,
        waiting: 0,
        failed: 0,
      },
    })

    await waitFor(() => {
      expect(screen.getByText('完成').parentElement?.textContent).toContain('1')
      expect(screen.getByText('等待').parentElement?.textContent).toContain('0')
    })
  })

  it('refetches summary for old detail events without summary payload', async () => {
    vi.mocked(getCrawlerRunTaskSummary)
      .mockResolvedValueOnce({
        total: 1,
        pending_crawl: 1,
        crawling: 0,
        saved: 0,
        skipped: 0,
        crawl_failed: 0,
        save_failed: 0,
        completed: 0,
        waiting: 1,
        failed: 0,
      })
      .mockResolvedValueOnce({
        total: 1,
        pending_crawl: 0,
        crawling: 0,
        saved: 1,
        skipped: 0,
        crawl_failed: 0,
        save_failed: 0,
        completed: 1,
        waiting: 0,
        failed: 0,
      })

    renderPage()
    await screen.findByText('运行详情 - 任务A')

    const initialSummaryCalls = vi.mocked(getCrawlerRunTaskSummary).mock.calls.length

    emit('crawler.run.detail.updated', {
      run_id: 'run-1',
      tasks: [],
    })

    await waitFor(() => {
      expect(vi.mocked(getCrawlerRunTaskSummary).mock.calls.length).toBeGreaterThan(initialSummaryCalls)
      expect(screen.getByText('完成').parentElement?.textContent).toContain('1')
    })
  })
})
