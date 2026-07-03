import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RunDetailPage from '../src/pages/crawler/runs/RunDetailPage'
import { getCrawlerRun, getCrawlerRunLogs, getCrawlerRunTasks } from '../src/api/crawlerRun'
import type { RealtimeEventName, RealtimeHandler } from '../src/realtime/types'

const realtimeHandlers = new Map<string, Set<RealtimeHandler>>()

vi.mock('../src/api/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunLogs: vi.fn(),
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
  })

  it('renders run details and loads logs from API', async () => {
    renderPage()

    expect(await screen.findByText('运行详情 - 任务A')).toBeInTheDocument()
    expect(getCrawlerRun).toHaveBeenCalledWith('run-1')
    expect(getCrawlerRunLogs).toHaveBeenCalledWith('run-1')
    expect(getCrawlerRunTasks).toHaveBeenCalledWith('run-1', {
      limit: 200,
      status: undefined,
      keyword: undefined,
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

    expect(await screen.findByText('已完成')).toBeInTheDocument()
    expect(screen.getByText('详情 53/53 跳过')).toBeInTheDocument()
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

    const initialCallCount = vi.mocked(getCrawlerRunLogs).mock.calls.length

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
      expect(getCrawlerRunLogs.mock.calls.length).toBeGreaterThan(initialCallCount)
    })
    expect(await screen.findByText('详情处理完成: 总计=54 已完成=0 失败=0 跳过=54')).toBeInTheDocument()
  })

  it('resyncs snapshots when system resync is required', async () => {
    renderPage()

    await screen.findByText('运行详情 - 任务A')

    const initialRunCalls = vi.mocked(getCrawlerRun).mock.calls.length
    const initialLogsCalls = vi.mocked(getCrawlerRunLogs).mock.calls.length
    const initialTasksCalls = vi.mocked(getCrawlerRunTasks).mock.calls.length

    emit('system.resync_required', { reason: 'connection_error' }, null)

    await waitFor(() => {
      expect(getCrawlerRun.mock.calls.length).toBeGreaterThan(initialRunCalls)
      expect(getCrawlerRunLogs.mock.calls.length).toBeGreaterThan(initialLogsCalls)
      expect(getCrawlerRunTasks.mock.calls.length).toBeGreaterThan(initialTasksCalls)
    })
  })
})
