import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RunDetailPage from '../src/pages/crawler/runs/RunDetailPage'
import { getCrawlerRun, getCrawlerRunLogs, getCrawlerRunTaskSummary, getCrawlerRunTasks } from '../src/api/crawlerRun'

vi.mock('../src/api/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunLogs: vi.fn(),
  getCrawlerRunTaskSummary: vi.fn(),
  getCrawlerRunTasks: vi.fn(),
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

function renderDetailPage() {
  const rootRoute = createRootRoute({ component: () => <RunDetailPage /> })
  const detailRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/runs/$id',
    component: RunDetailPage,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([detailRoute]),
    history: createMemoryHistory({ initialEntries: ['/crawler/runs/run-1'] }),
  })
  return render(<RouterProvider router={router} />)
}

describe('RunDetailPage logs', () => {
  beforeEach(() => {
    vi.mocked(getCrawlerRun).mockResolvedValue({
      id: 'run-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'completed',
      crawl_mode: 'incremental',
      queued_at: '2026-07-02T00:00:00Z',
      started_at: '2026-07-02T00:00:01Z',
      finished_at: '2026-07-02T00:00:02Z',
      result: { saved: 1 },
      error: null,
      resumed_from: null,
      created_at: '2026-07-02T00:00:00Z',
      updated_at: null,
      logs: [],
    })
    vi.mocked(getCrawlerRunLogs).mockResolvedValue([
      { timestamp: '2026-07-02T00:00:01Z', level: 'INFO', message: '任务开始执行' },
      { timestamp: '2026-07-02T00:00:02Z', level: 'ERROR', message: '入库失败: AAA-001' },
    ])
    vi.mocked(getCrawlerRunTasks).mockResolvedValue({
      rows: [],
      total: 0,
    })
    vi.mocked(getCrawlerRunTaskSummary).mockResolvedValue({
      total: 6,
      pending_crawl: 1,
      crawling: 1,
      saved: 1,
      skipped: 1,
      crawl_failed: 1,
      save_failed: 1,
      completed: 2,
      waiting: 2,
      failed: 2,
    })
  })

  it('renders run logs on the detail page', async () => {
    renderDetailPage()

    expect(await screen.findByText('运行日志')).toBeInTheDocument()
    expect(await screen.findByText('入库失败: AAA-001')).toBeInTheDocument()
    expect(screen.getByText('任务开始执行')).toBeInTheDocument()
  })

  it('passes the route id to run detail APIs', async () => {
    renderDetailPage()

    await screen.findByText('运行日志')
    expect(getCrawlerRun).toHaveBeenCalledWith('run-1')
    expect(getCrawlerRunLogs).toHaveBeenCalledWith('run-1')
    expect(getCrawlerRunTasks).toHaveBeenCalledWith('run-1', {
      page: 1,
      size: 50,
      status: undefined,
      keyword: undefined,
    })
  })

  it('renders full-run child task summary from API', async () => {
    renderDetailPage()

    expect(await screen.findByText('总数')).toBeInTheDocument()
    expect(screen.getByText('6')).toBeInTheDocument()
    expect(screen.getByText('完成')).toBeInTheDocument()
    expect(screen.getByText('等待')).toBeInTheDocument()
    expect(screen.getByText('失败')).toBeInTheDocument()
  })
})
