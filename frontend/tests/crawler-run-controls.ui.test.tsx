import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListPage from '../src/pages/crawler/tasks/TaskListPage'
import { createTemporaryCrawlRun, createTaskUrlRun, getCrawlTasks, getTaskDict } from '@/api/crawler/crawlTask'
import { runCrawlTask } from '@/api/crawler/crawlerRun'
import { useTaskListQueryStore } from '../src/pages/crawler/tasks/useTaskListQueryStore'
import { useCrawlerRuntimeStore } from '../src/stores/useCrawlerRuntimeStore'

vi.mock('@/api/crawler/crawlTask', () => ({
  getCrawlTasks: vi.fn(),
  getTaskDict: vi.fn(),
  createTemporaryCrawlRun: vi.fn(),
  createTaskUrlRun: vi.fn(),
  deleteCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

vi.mock('@/api/crawler/crawlerRun', () => ({
  runCrawlTask: vi.fn(),
  stopCrawlerRun: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  subscribeRealtime: vi.fn(() => vi.fn()),
  connectRealtime: vi.fn(),
  disconnectRealtime: vi.fn(),
}))

vi.mock('keepalive-for-react', () => ({
  useEffectOnActive: (cb: () => void) => cb(),
}))

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute({ component: () => <TaskListPage /> })
  const runsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/crawler/runs', component: () => <div>runs page</div> })
  const router = createRouter({
    routeTree: rootRoute.addChildren([runsRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <AntApp>
        <RouterProvider router={router} />
      </AntApp>
    </QueryClientProvider>,
  )
}

describe('crawler task run controls', () => {
  beforeEach(() => {
    useTaskListQueryStore.getState().reset()
    // Pre-populate the runtime store so taskSnapshotReady is true and tasks have idle runtime
    useCrawlerRuntimeStore.getState().reset()
    useCrawlerRuntimeStore.setState({
      taskSnapshotReady: true,
      taskRuntimeById: {
        'task-1': {
          task_id: 'task-1',
          runtime_status: 'idle',
          latest_run_id: null,
          state_updated_at: '2026-07-02T00:00:00',
          last_run_at: null,
        },
      },
      taskStats: { total: 1, idle: 1, running: 0, queued: 0, stopped: 0 },
    })
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [{
        id: 'task-1',
        name: '任务A',
        storage_location: 'A',
        is_skip: false,
        urls: [{
          id: 'url-1',
          position: 0,
          url: 'https://javdb.com/actors/a',
          url_type: 'actors',
          has_magnet: true,
          has_chinese_sub: false,
          url_name: '演员A',
        }],
      }],
      total: 1,
      page: 1,
      size: 20,
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
    vi.mocked(createTaskUrlRun).mockResolvedValue({
      id: 'run-url-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'queued',
      crawl_mode: 'incremental',
      queued_at: '2026-07-15T00:00:00',
      started_at: null,
      finished_at: null,
      result: { url_subset: true, selected_task_url_ids: ['url-1'], selected_task_url_count: 1 },
      error: null,
      resumed_from: null,
      created_at: '2026-07-15T00:00:00',
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

  it('submits url subset run from a task card', async () => {
    const user = userEvent.setup()
    renderPage()

    const urlRunButton = await screen.findByRole('button', { name: /URL.*爬取/ })
    await user.click(urlRunButton)

    expect(await screen.findByText(/URL 爬取 -/)).toBeInTheDocument()
    await user.click(screen.getByLabelText('选择 URL'))
    const options = await screen.findAllByText('演员A')
    await user.click(options[options.length - 1])
    await user.click(screen.getByRole('button', { name: /开.*始.*爬.*取/ }))

    await waitFor(() => {
      expect(createTaskUrlRun).toHaveBeenCalledWith('task-1', {
        url_ids: ['url-1'],
        crawl_mode: 'incremental',
      })
    })
  })
})
