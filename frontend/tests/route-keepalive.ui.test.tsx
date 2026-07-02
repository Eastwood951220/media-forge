import { useState, type PropsWithChildren } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  Link as RouterLink,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import {
  isRouteCacheExcluded,
  ROUTE_CACHE_EXCLUDE_PATHS,
  RouteKeepAliveOutlet,
  RouteKeepAliveProvider,
} from '../src/layout/routeCache'

vi.mock('keepalive-for-react', () => ({
  KeepAlive: ({
    activeCacheKey,
    exclude,
    children,
  }: PropsWithChildren<{ activeCacheKey: string; exclude: string[] }>) => (
    <div
      data-testid="keep-alive"
      data-active-cache-key={activeCacheKey}
      data-exclude={exclude.join('|')}
    >
      {children}
    </div>
  ),
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

function renderCachedOutlet(initialPath: string) {
  const rootRoute = createRootRoute({
    component: () => (
      <RouteKeepAliveProvider>
        <RouteKeepAliveOutlet />
      </RouteKeepAliveProvider>
    ),
  })
  const tasksRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks',
    component: () => <div>tasks page</div>,
  })
  const configRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/config',
    component: () => <div>config page</div>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([tasksRoute, configRoute]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })

  return render(<RouterProvider router={router} />)
}

describe('RouteKeepAliveOutlet', () => {
  it('uses pathname and search string as the active cache key', async () => {
    renderCachedOutlet('/crawler/tasks?page=2&status=running')

    const keepAlive = await screen.findByTestId('keep-alive')
    expect(keepAlive).toHaveAttribute(
      'data-active-cache-key',
      '/crawler/tasks?page=2&status=running',
    )
    expect(keepAlive).toHaveAttribute('data-exclude', '/login|/init')
    expect(await screen.findByText('tasks page')).toBeInTheDocument()
  })

  it('keeps login and init in the explicit exclude list', () => {
    expect(ROUTE_CACHE_EXCLUDE_PATHS).toEqual(['/login', '/init'])
    expect(isRouteCacheExcluded('/login')).toBe(true)
    expect(isRouteCacheExcluded('/init')).toBe(true)
    expect(isRouteCacheExcluded('/crawler/tasks')).toBe(false)
  })

  it('keeps keyed outlet content mounted for route cache keys', async () => {
    const user = userEvent.setup()
    function CachedInputPage() {
      const [value, setValue] = useState('')
      return (
        <input
          aria-label="cached input"
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
      )
    }

    const rootRoute = createRootRoute({
      component: () => (
        <RouteKeepAliveProvider>
          <nav>
            <RouterLink to="/crawler/tasks">tasks</RouterLink>
            <RouterLink to="/crawler/config">config</RouterLink>
          </nav>
          <RouteKeepAliveOutlet />
        </RouteKeepAliveProvider>
      ),
    })
    const taskRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: '/crawler/tasks',
      component: CachedInputPage,
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

    render(<RouterProvider router={router} />)

    await user.type(await screen.findByLabelText('cached input'), 'stored')
    await user.click(screen.getByText('config'))
    expect(await screen.findByText('config page')).toBeInTheDocument()
    await user.click(screen.getByText('tasks'))

    expect(await screen.findByLabelText('cached input')).toHaveValue('stored')
  })
})
