// @ts-nocheck — test file, router types are complex; functionality is what matters
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { createMemoryHistory } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { router as baseRouter } from '../src/routes'
import { queryClient } from '../src/lib/query-client'
import { useAuthStore } from '../src/stores/useAuthStore'
import { setToken, removeToken } from '../src/utils/auth'

vi.mock('@/api/init', () => ({
  getInitConfig: vi.fn().mockResolvedValue({ initialized: true, databaseConfigured: true, redisConfigured: true }),
  saveInitConfig: vi.fn(),
  testPostgres: vi.fn(),
  testRedis: vi.fn(),
}))

vi.mock('@/api/crawlTask', () => ({
  getCrawlTasks: vi.fn().mockResolvedValue({ rows: [], total: 0 }),
  deleteCrawlTask: vi.fn().mockResolvedValue(undefined),
  updateCrawlTask: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/api/crawlerConfig', () => ({
  fetchConfig: vi.fn().mockResolvedValue({
    MAX_LIST_PAGES: 50,
    LIST_PAGE_DELAY_MIN: 1,
    LIST_PAGE_DELAY_MAX: 3,
    DETAIL_PAGE_DELAY_MIN: 2,
    DETAIL_PAGE_DELAY_MAX: 5,
    SECURITY_WAIT_SECONDS: 60,
    REQUEST_TIMEOUT: 30,
    INCREMENTAL_EXIST_THRESHOLD: 10,
  }),
  fetchCookiesConfig: vi.fn().mockResolvedValue({ cookies: [] }),
  updateConfig: vi.fn(),
  updateCookiesConfig: vi.fn(),
}))

function renderApp(initialPath = '/') {
  const history = createMemoryHistory({ initialEntries: [initialPath] })
  const testRouter = createRouter({
    routeTree: baseRouter.routeTree,
    history,
    defaultPreload: 'intent',
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={testRouter} />
    </QueryClientProvider>,
  )
}

describe('App auth routing', () => {
  beforeEach(() => {
    removeToken()
    useAuthStore.setState({
      token: '',
      isAuthenticated: false,
      userInfo: null,
    })
  })

  it('redirects unauthenticated user to login page', async () => {
    renderApp('/')

    await waitFor(() => {
      expect(screen.getByText(/欢迎回来/i)).toBeInTheDocument()
      expect(screen.getByText(/请登录您的账户以继续/i)).toBeInTheDocument()
    })
  })

  it('shows dashboard for authenticated user', async () => {
    setToken('test-token')
    useAuthStore.setState({ token: 'test-token', isAuthenticated: true })

    renderApp('/')

    await waitFor(() => {
      expect(screen.getAllByText('Operations Console').length).toBeGreaterThanOrEqual(2)
      expect(screen.getByText(/Media Forge/i)).toBeInTheDocument()
    })
  })

  it('shows crawler task page with a task list tag for authenticated user', async () => {
    setToken('test-token')
    useAuthStore.setState({ token: 'test-token', isAuthenticated: true })

    renderApp('/crawler/tasks')

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '爬取任务' })).toBeInTheDocument()
      expect(screen.getAllByText('任务列表').length).toBeGreaterThanOrEqual(2)
    })
  })

  it('shows crawler config page for authenticated user', async () => {
    setToken('test-token')
    useAuthStore.setState({ token: 'test-token', isAuthenticated: true })

    renderApp('/crawler/config')

    await waitFor(() => {
      expect(screen.getByText('爬取参数')).toBeInTheDocument()
      expect(screen.getAllByText('爬虫配置').length).toBeGreaterThanOrEqual(1)
    })
  })
})
