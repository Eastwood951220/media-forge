import { act, render, screen } from '@testing-library/react'
import { createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { createMemoryHistory } from '@tanstack/react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AppLayout from '../src/layout'
import headerStyles from '../src/layout/Header/Header.module.less'
import { useAuthStore } from '../src/stores/useAuthStore'
import { useTagsViewStore } from '../src/stores/useTagsViewStore'
import { useThemeStore } from '../src/stores/useThemeStore'

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

function renderLayout(initialPath = '/') {
  const rootRoute = createRootRoute({ component: AppLayout })
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => <div>console outlet</div>,
  })
  const crawlerTasksRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks',
    component: () => <div>console outlet</div>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute, crawlerTasksRoute]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })

  return render(<RouterProvider router={router} />)
}

describe('modern console layout', () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: 'test-token',
      isAuthenticated: true,
      userInfo: {
        username: 'admin',
        displayName: 'Admin',
      },
    })
    useThemeStore.setState({
      mode: 'light',
      darkMode: false,
      primaryColor: '#006AFF',
    })
    useTagsViewStore.getState().resetViews()
    useTagsViewStore.setState({
      visitedViews: [
        { path: '/', fullPath: '/', cacheKey: '/', title: '仪表盘', closable: false },
        { path: '/crawler/tasks', fullPath: '/crawler/tasks', cacheKey: '/crawler/tasks', title: '任务列表', closable: true },
      ],
    })
  })

  it('renders console shell landmarks, crawler navigation, and tags view', async () => {
    renderLayout('/crawler/tasks')

    expect(await screen.findByText('Media Forge')).toBeInTheDocument()
    expect(screen.getByText('Operations Console')).toBeInTheDocument()
    expect(screen.getAllByRole('menu').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('仪表盘').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('爬虫')).toBeInTheDocument()
    expect(screen.getAllByText('任务列表').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('爬虫配置')).toBeInTheDocument()
    expect(screen.getByText('console outlet')).toBeInTheDocument()
    expect(screen.queryByLabelText('Open settings')).not.toBeInTheDocument()
  })

  it('keeps the top header theme-aware in dark mode', async () => {
    act(() => {
      useThemeStore.setState({
        mode: 'dark',
        darkMode: true,
        primaryColor: '#006AFF',
      })
    })

    renderLayout()

    const header = await screen.findByRole('banner')
    expect(header).toHaveClass(headerStyles.header)
    expect(header).toHaveClass(headerStyles.dark)
  })
})
