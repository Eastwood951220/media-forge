import { Outlet, createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider, useNavigate } from '@tanstack/react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListPage from '../src/pages/crawler/tasks/TaskListPage'
import { useCrawlerRuntimeStore } from '../src/stores/useCrawlerRuntimeStore'
import { getCrawlTasks } from '@/api/crawler/crawlTask'

vi.mock('@/api/crawler/crawlTask', () => ({
  getCrawlTasks: vi.fn(),
  deleteCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
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
  useEffectOnActive: (cb: () => void) => cb(),
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
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
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

  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

describe('TaskListPage routing', () => {
  beforeEach(() => {
    useCrawlerRuntimeStore.getState().reset()
    useCrawlerRuntimeStore.setState({
      taskSnapshotReady: true,
      taskRuntimeById: {},
      taskStats: { total: 0, idle: 0, running: 0, queued: 0, stopped: 0 },
    })
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [],
      total: 0,
      page: 1,
      size: 20,
    })
  })

  it('renders task list page with toolbar', async () => {
    renderTaskRoutes()

    expect(await screen.findByText('临时任务')).toBeInTheDocument()
    expect(await screen.findByText('新建任务')).toBeInTheDocument()
  })

  it('navigates to config and back', async () => {
    renderTaskRoutes()

    await screen.findByText('临时任务')

    await userEvent.click(screen.getByRole('button', { name: 'config' }))
    expect(await screen.findByText('config page')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'tasks' }))
    expect(await screen.findByText('临时任务')).toBeInTheDocument()
  })
})
