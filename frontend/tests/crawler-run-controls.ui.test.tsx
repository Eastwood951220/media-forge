import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListPage from '../src/pages/crawler/tasks/TaskListPage'
import { createTemporaryCrawlRun, getCrawlTaskStats, getCrawlTasks, getTaskDict } from '../src/api/crawlTask'
import { runCrawlTask } from '../src/api/crawlerRun'
import { useTaskListQueryStore } from '../src/pages/crawler/tasks/useTaskListQueryStore'

vi.mock('../src/api/crawlTask', () => ({
  getCrawlTasks: vi.fn(),
  getCrawlTaskStats: vi.fn(),
  getCrawlTaskRuntimeStatuses: vi.fn().mockResolvedValue({ tasks: [], stats: { total: 1, idle: 1, running: 0, queued: 0, stopped: 0 } }),
  getTaskDict: vi.fn(),
  createTemporaryCrawlRun: vi.fn(),
  deleteCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

vi.mock('../src/api/crawlerRun', () => ({
  runCrawlTask: vi.fn(),
  stopCrawlerRun: vi.fn(),
}))

vi.mock('../src/realtime/eventSourceClient', () => ({
  subscribeRealtime: vi.fn(() => vi.fn()),
  connectRealtime: vi.fn(),
  disconnectRealtime: vi.fn(),
}))

function renderPage() {
  const rootRoute = createRootRoute({ component: () => <TaskListPage /> })
  const runsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/crawler/runs', component: () => <div>runs page</div> })
  const router = createRouter({
    routeTree: rootRoute.addChildren([runsRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(<RouterProvider router={router} />)
}

describe('crawler task run controls', () => {
  beforeEach(() => {
    useTaskListQueryStore.getState().reset()
    vi.mocked(getCrawlTaskStats).mockResolvedValue({ total: 1, enabled: 1, disabled: 0 })
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [{
        id: 'task-1',
        name: '任务A',
        storage_location: 'A',
        urls: [],
        is_skip: false,
        status: 'pending',
        task_id: null,
        error_message: null,
        total_found: 0,
        total_qualified: 0,
        owner_id: 'user-1',
        created_at: '2026-07-02T00:00:00',
        updated_at: null,
        last_run_at: null,
        last_run_status: null,
      }],
      total: 1,
    })
    vi.mocked(runCrawlTask).mockResolvedValue({ id: 'run-1' } as never)
    vi.mocked(getTaskDict).mockResolvedValue([{ id: 'task-1', name: '任务A' }])
    vi.mocked(createTemporaryCrawlRun).mockResolvedValue({
      id: 'run-temp-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'queued',
      crawl_mode: 'temporary',
      queued_at: '2026-07-13T00:00:00',
      started_at: null,
      finished_at: null,
      result: { temporary: true, detail_url_count: 1 },
      error: null,
      resumed_from: null,
      created_at: '2026-07-13T00:00:00',
      updated_at: null,
      logs: [],
    })
  })

  it('starts an incremental run from the crawl dropdown', async () => {
    renderPage()

    const crawlButton = await screen.findByText('爬取')
    await userEvent.click(crawlButton)
    await userEvent.click(await screen.findByText('增量爬取'))

    await waitFor(() => {
      expect(runCrawlTask).toHaveBeenCalledWith('task-1', 'incremental')
    })
  })

  it('creates a temporary run from the task list modal', async () => {
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: '临时任务' }))

    const select = await screen.findByLabelText('归属任务')
    await userEvent.click(select)

    const dropdownOption = await screen.findAllByText('任务A')
    await userEvent.click(dropdownOption[dropdownOption.length - 1])

    await userEvent.type(screen.getByPlaceholderText(/请输入 JavDB 详情页 URL/), 'https://javdb.com/v/temp001')
    await userEvent.click(screen.getByRole('button', { name: '创建临时任务' }))

    await waitFor(() => {
      expect(createTemporaryCrawlRun).toHaveBeenCalledWith({
        task_id: 'task-1',
        detail_urls: ['https://javdb.com/v/temp001'],
      })
    })
  })
})
