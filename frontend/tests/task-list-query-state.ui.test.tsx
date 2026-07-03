import { Outlet, createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider, useNavigate } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListPage from '../src/pages/crawler/tasks/TaskListPage'
import { useTaskListQueryStore } from '../src/pages/crawler/tasks/useTaskListQueryStore'
import { getCrawlTasks } from '../src/api/crawlTask'

vi.mock('../src/api/crawlTask', () => ({
  getCrawlTasks: vi.fn(),
  getCrawlTaskRuntimeStatuses: vi.fn().mockResolvedValue({ tasks: [] }),
  getCrawlTaskStats: vi.fn().mockResolvedValue({ total: 0, enabled: 0, disabled: 0 }),
  deleteCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

vi.mock('../src/realtime/eventSourceClient', () => ({
  subscribeRealtime: vi.fn(() => vi.fn()),
  connectRealtime: vi.fn(),
  disconnectRealtime: vi.fn(),
}))

vi.mock('keepalive-for-react', () => ({
  KeepAlive: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useKeepAliveRef: () => ({
    current: {
      destroy: vi.fn(),
      destroyAll: vi.fn(),
      destroyOther: vi.fn(),
      refresh: vi.fn(),
      getCacheNodes: vi.fn(() => []),
    },
  }),
}))

function TestShell() {
  const navigate = useNavigate()
  return (
    <div>
      <button type="button" onClick={() => void navigate({ to: '/crawler/tasks' })}>
        tasks
      </button>
      <button type="button" onClick={() => void navigate({ to: '/crawler/config' })}>
        config
      </button>
      <Outlet />
    </div>
  )
}

function renderTaskRoutes() {
  const rootRoute = createRootRoute({ component: TestShell })
  const taskRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks',
    component: TaskListPage,
  })
  const configRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/config',
    component: () => <div>config page</div>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([taskRoute, configRoute]),
    history: createMemoryHistory({ initialEntries: ['/crawler/tasks'] }),
  })

  return render(<RouterProvider router={router} />)
}

describe('TaskListPage query state', () => {
  beforeEach(() => {
    useTaskListQueryStore.getState().reset()
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [],
      total: 0,
      page: 1,
      page_size: 20,
    })
  })

  it('keeps the search condition after switching away and back', async () => {
    renderTaskRoutes()

    const searchInput = await screen.findByPlaceholderText('搜索任务名称')
    await userEvent.type(searchInput, '每日')

    await waitFor(() => {
      expect(getCrawlTasks).toHaveBeenLastCalledWith({
        skip: 0,
        limit: 20,
        keyword: '每日',
      })
    })

    await userEvent.click(screen.getByRole('button', { name: 'config' }))
    expect(await screen.findByText('config page')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'tasks' }))
    expect(await screen.findByPlaceholderText('搜索任务名称')).toHaveValue('每日')
  })
})
