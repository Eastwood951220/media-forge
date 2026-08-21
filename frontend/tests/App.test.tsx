import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { createMemoryHistory } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import * as React from 'react'
import { router as baseRouter } from '../src/routes'
import { queryClient } from '../src/lib/query-client'
import App from '../src/App'
import { useAuthStore } from '../src/stores/useAuthStore'
import { useThemeStore } from '../src/stores/useThemeStore'
import { setToken, removeToken } from '../src/utils/auth'

vi.mock('@/api/init', () => ({
  getInitConfig: vi.fn().mockResolvedValue({ initialized: true, databaseConfigured: true, redisConfigured: true }),
  saveInitConfig: vi.fn(),
  testPostgres: vi.fn(),
  testRedis: vi.fn(),
}))

vi.mock('@theme-toggles/react/styles/classic.css', () => ({}))

vi.mock('@theme-toggles/react', () => {
  const Classic = ({ className, 'aria-label': ariaLabel, onClick, ...props }: Record<string, unknown>) =>
    React.createElement('button', { className, 'aria-label': ariaLabel, onClick, type: 'button', ...props })
  return { Classic }
})

vi.mock('@/api/crawler/crawlTask', () => ({
  getCrawlTasks: vi.fn().mockResolvedValue({ rows: [], total: 0 }),
  getTaskDict: vi.fn().mockResolvedValue([]),
  createTemporaryCrawlRun: vi.fn().mockResolvedValue({ run_id: 'run-1', accepted: true }),
  createTaskUrlRun: vi.fn().mockResolvedValue({ run_id: 'run-1', accepted: true }),
  deleteCrawlTask: vi.fn().mockResolvedValue(undefined),
  updateCrawlTask: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/api/dashboard', () => ({
  getDashboardOverview: vi.fn().mockResolvedValue({
    system_status: 'healthy',
    refreshed_at: '2026-07-14T00:00:00Z',
    crawler: {
      task_stats: { total: 0, enabled: 0, disabled: 0 },
      runtime_stats: { total: 0, idle: 0, running: 0, queued: 0, stopped: 0 },
      queue: { queue_size: 0, is_running: false, current_run_id: null, stop_requested: false },
    },
    runs: { status_distribution: [], daily_trend: [], recent: [] },
    content: { movie_total: 0, storage_status: { stored: 0, storing: 0, not_stored: 0 } },
    storage: {
      task_status_distribution: [],
      recent_tasks: [],
      index: {
        target_folder: '',
        status: 'idle',
        category_count: 0,
        code_folder_count: 0,
        video_count: 0,
        completed_at: null,
        errors: [],
      },
    },
    alerts: [],
    partial_errors: [],
  }),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  subscribeRealtime: vi.fn(() => vi.fn()),
  connectRealtime: vi.fn(),
  disconnectRealtime: vi.fn(),
}))

vi.mock('@/api/crawler/crawlerConfig', () => ({
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
  fetchAgentStatus: vi.fn().mockResolvedValue({ status: 'not_configured' }),
  rotateAgentToken: vi.fn().mockResolvedValue({ token: 'agent-token', status: { status: 'offline' } }),
  testCookiesConfig: vi.fn().mockResolvedValue({
    ok: true,
    status_code: 200,
    reason: 'OK',
    message: 'ok',
    url: 'https://javdb.com',
    logged_in_detected: true,
    fetch_mode: 'static',
  }),
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
    document.documentElement.dataset.theme = 'light'
    document.documentElement.className = ''
    document.documentElement.style.removeProperty('--app-primary-color')
    useThemeStore.setState({
      mode: 'light',
      darkMode: false,
      primaryColor: '#006AFF',
    })
  })

  it('syncs root dark class with dark theme state', async () => {
    setToken('test-token')
    useAuthStore.setState({ token: 'test-token', isAuthenticated: true })
    useThemeStore.setState({
      mode: 'dark',
      darkMode: true,
      primaryColor: '#006AFF',
    })

    const { rerender } = render(<App />)

    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe('dark')
      expect(document.documentElement).toHaveClass('dark')
    })

    useThemeStore.setState({
      mode: 'light',
      darkMode: false,
      primaryColor: '#006AFF',
    })
    rerender(<App />)

    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe('light')
      expect(document.documentElement).not.toHaveClass('dark')
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
      expect(screen.getByRole('heading', { name: '运行态总览' })).toBeInTheDocument()
      expect(screen.getAllByText(/Media Forge/i).length).toBeGreaterThanOrEqual(1)
    })
  })

  it('shows crawler task page with a task list tag for authenticated user', async () => {
    setToken('test-token')
    useAuthStore.setState({ token: 'test-token', isAuthenticated: true })

    renderApp('/crawler/tasks')

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '临时任务' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /新建任务/ })).toBeInTheDocument()
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
