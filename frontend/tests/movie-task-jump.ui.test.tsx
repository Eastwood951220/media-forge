import { App as AntApp } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListPage from '../src/pages/crawler/tasks/TaskListPage'
import MovieListPage from '../src/pages/content/movies/MovieListPage'
import { RouteKeepAliveProvider, RouteKeepAliveOutlet } from '../src/layout/routeCache'
import { useCrawlerRuntimeStore } from '../src/stores/useCrawlerRuntimeStore'
import { getCrawlTasks, getTaskDict } from '@/api/crawler/crawlTask'
import { fetchMovies } from '@/api/movie'

vi.mock('@/api/crawler/crawlTask', () => ({
  getCrawlTasks: vi.fn(),
  getTaskDict: vi.fn(),
  getCrawlTaskTags: vi.fn(),
  deleteCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
  batchRunCrawlTasks: vi.fn(),
  batchCreateCrawlTasks: vi.fn(),
  createTemporaryCrawlRun: vi.fn(),
  createTaskUrlRun: vi.fn(),
}))

vi.mock('@/api/crawler/crawlerRun', () => ({
  runCrawlTask: vi.fn(),
  stopCrawlerRun: vi.fn(),
  restartCrawlerRun: vi.fn(),
}))

vi.mock('@/api/movie', () => ({
  fetchMovieFilterConfig: vi.fn().mockResolvedValue({ filters: {} }),
  fetchFilters: vi.fn().mockResolvedValue([]),
  fetchMovies: vi.fn(),
  syncMovieStorageStatus: vi.fn(),
  deleteMovies: vi.fn(),
  refreshMovieMagnets: vi.fn(),
  fetchMovieDetail: vi.fn(),
}))

vi.mock('@/api/storage/storageIndex', () => ({
  refreshStorageIndex: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  subscribeRealtime: vi.fn(() => vi.fn()),
  connectRealtime: vi.fn(),
  disconnectRealtime: vi.fn(),
}))

function TestShell() {
  return (
    <AntApp>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouteKeepAliveProvider>
          <RouteKeepAliveOutlet />
        </RouteKeepAliveProvider>
      </QueryClientProvider>
    </AntApp>
  )
}

function renderRoutes() {
  const rootRoute = createRootRoute({ component: TestShell })
  const taskRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks',
    component: TaskListPage,
  })
  const movieRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/content/movies',
    component: MovieListPage,
    validateSearch: (search: Record<string, unknown>) => ({
      task_id: typeof search.task_id === 'string' ? search.task_id : undefined,
    }),
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([taskRoute, movieRoute]),
    history: createBrowserHistory(),
  })

  void router.navigate({ to: '/crawler/tasks' })
  return render(<RouterProvider router={router} />)
}

const TASK_ID = '11111111-2222-3333-4444-555555555555'

const idleTask = {
  id: TASK_ID,
  name: '任务一',
  storage_location: 'P1',
  tags: [],
  urls: [],
  is_skip: false,
  status: 'idle',
  task_id: null,
  error_message: null,
  total_found: 0,
  total_qualified: 0,
  owner_id: 'owner-1',
  created_at: '2026-08-01T00:00:00Z',
  updated_at: null,
  last_run_at: null,
  last_run_status: null,
}

function lastFetchTaskId(): string | undefined {
  const calls = vi.mocked(fetchMovies).mock.calls
  return (calls.at(-1)?.[0] as { source_task_id?: string } | undefined)?.source_task_id
}

describe('task card to movie list jump', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useCrawlerRuntimeStore.getState().reset()
    useCrawlerRuntimeStore.setState({
      taskSnapshotReady: true,
      taskRuntimeById: { [TASK_ID]: { task_id: TASK_ID, runtime_status: 'idle', latest_run_id: null, state_updated_at: '2026-09-04T00:00:00Z', last_run_at: null } },
      taskStats: { total: 1, idle: 1, running: 0, queued: 0, stopped: 0 },
    })
    vi.mocked(getCrawlTasks).mockResolvedValue({ rows: [idleTask], total: 1, page: 1, size: 20 } as never)
    vi.mocked(getTaskDict).mockResolvedValue([{ id: TASK_ID, name: idleTask.name }] as never)
    vi.mocked(fetchMovies).mockResolvedValue({ items: [], total: 0, page: 1, limit: 20, total_pages: 1 } as never)
  })

  it('keeps the task preset applied across keep-alive remounts', async () => {
    renderRoutes()

    const user = userEvent.setup()
    await screen.findByText('任务一')
    await user.click(screen.getByRole('button', { name: /查看 任务一 的影片/ }))

    await vi.waitFor(() => {
      expect(lastFetchTaskId()).toBe(TASK_ID)
    })

    // keep-alive may remount the page several times; the preset must survive
    // every remount instead of being lost after the first mount.
    await new Promise((resolve) => setTimeout(resolve, 400))

    expect(lastFetchTaskId()).toBe(TASK_ID)
    expect(window.location.search).toContain(`task_id=${TASK_ID}`)
  })
})
