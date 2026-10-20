import { useState, type PropsWithChildren, type ReactNode } from 'react'
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
} from '../src/layout/routeCacheControl'
import {
  RouteKeepAliveOutlet,
  RouteKeepAliveProvider,
} from '../src/layout/routeCache'

// Mirrors the parts of keepalive-for-react the outlet depends on: keep one
// React subtree per cache key, portal it into its own container, attach only the
// active container to the document (inactive pages keep their state but are not
// queryable), and destroy an excluded key once it deactivates. While a page is
// active it renders against the live router; once it deactivates it keeps a
// frozen snapshot of the match it had, so it does not follow later navigations.
// A regression that unmounts KeepAlive discards every cached subtree.
vi.mock('keepalive-for-react', async () => {
  const React = await import('react')
  const ReactDOM = await import('react-dom')
  const {
    RouterContextProvider,
    useRouter,
    useRouterState,
  } = await import('@tanstack/react-router')

  type AnyRouter = ReturnType<typeof useRouter>
  type MatchSnapshot = Map<string, unknown>

  function frozenStore<T>(value: T) {
    return {
      get: () => value,
      subscribe: () => ({ unsubscribe: () => undefined }),
    }
  }

  function createFrozenRouter(
    router: AnyRouter,
    routeIds: string[],
    matches: MatchSnapshot,
  ): AnyRouter {
    return Object.assign(Object.create(router) as AnyRouter, {
      stores: {
        ...router.stores,
        ids: frozenStore(routeIds),
        getMatchStore: (routeId: string) =>
          frozenStore(
            matches.get(routeId) ??
              router.stores.getMatchStore(routeId).get(),
          ),
      } as unknown as AnyRouter['stores'],
    })
  }

  type CacheEntry = {
    container: HTMLDivElement
    node: ReactNode
    matches: MatchSnapshot
    routeIds: string[]
    frozenRouter?: AnyRouter
  }

  return {
    KeepAlive: ({
      activeCacheKey,
      exclude,
      children,
    }: PropsWithChildren<{ activeCacheKey: string; exclude: string[] }>) => {
      const router = useRouter()
      const matches = useRouterState({ select: (state) => state.matches })
      const routeIds = matches.map((match) => match.routeId)
      const hostRef = React.useRef<HTMLDivElement>(null)
      const cacheRef = React.useRef(new Map<string, CacheEntry>())
      const previousKeyRef = React.useRef(activeCacheKey)

      if (previousKeyRef.current !== activeCacheKey) {
        if (exclude.includes(previousKeyRef.current)) {
          const previous = cacheRef.current.get(previousKeyRef.current)
          previous?.container.remove()
          cacheRef.current.delete(previousKeyRef.current)
        }
        previousKeyRef.current = activeCacheKey
      }

      let activeEntry = cacheRef.current.get(activeCacheKey)
      if (!activeEntry) {
        const container = document.createElement('div')
        container.setAttribute('data-cache-key', activeCacheKey)
        activeEntry = {
          container,
          node: children,
          matches: new Map(),
          routeIds,
        }
        cacheRef.current.set(activeCacheKey, activeEntry)
      }

      for (const [cacheKey, entry] of cacheRef.current) {
        if (cacheKey === activeCacheKey) {
          entry.node = children
          entry.routeIds = routeIds
          entry.matches = new Map(
            routeIds.map((id) => [
              id,
              router.stores.getMatchStore(id).get(),
            ]),
          )
        } else if (!entry.frozenRouter) {
          entry.frozenRouter = createFrozenRouter(router, entry.routeIds, entry.matches)
        }
      }

      React.useLayoutEffect(() => {
        const host = hostRef.current
        if (!host) return
        for (const [cacheKey, entry] of cacheRef.current) {
          if (cacheKey === activeCacheKey) {
            host.appendChild(entry.container)
          } else {
            entry.container.remove()
          }
        }
      })

      return (
        <div
          ref={hostRef}
          data-testid="keep-alive"
          data-active-cache-key={activeCacheKey}
          data-exclude={exclude.join('|')}
        >
          {Array.from(cacheRef.current, ([cacheKey, entry]) =>
            ReactDOM.createPortal(
              <RouterContextProvider router={entry.frozenRouter ?? router}>
                {entry.node}
              </RouterContextProvider>,
              entry.container,
              cacheKey,
            ),
          )}
        </div>
      )
    },
    useKeepAliveRef: () => ({
      current: {
        destroy: vi.fn(),
        destroyAll: vi.fn(),
        destroyOther: vi.fn(),
        refresh: vi.fn(),
        getCacheNodes: vi.fn(() => []),
      },
    }),
  }
})

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
    expect(keepAlive).toHaveAttribute(
      'data-exclude',
      '/login|/init|/crawler/runs|/storage/tasks|/scraping/tasks',
    )
    expect(await screen.findByText('tasks page')).toBeInTheDocument()
  })

  it('keeps login, init, and task list pages in the explicit exclude list', () => {
    expect(ROUTE_CACHE_EXCLUDE_PATHS).toEqual([
      '/login',
      '/init',
      '/crawler/runs',
      '/storage/tasks',
      '/scraping/tasks',
    ])
    expect(isRouteCacheExcluded('/login')).toBe(true)
    expect(isRouteCacheExcluded('/init')).toBe(true)
    expect(isRouteCacheExcluded('/crawler/runs')).toBe(true)
    expect(isRouteCacheExcluded('/storage/tasks')).toBe(true)
    expect(isRouteCacheExcluded('/scraping/tasks')).toBe(true)
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

  it('keeps other cached pages when visiting an excluded list page', async () => {
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
            <RouterLink to="/storage/tasks">storage tasks</RouterLink>
          </nav>
          <RouteKeepAliveOutlet />
        </RouteKeepAliveProvider>
      ),
    })
    const tasksRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: '/crawler/tasks',
      component: CachedInputPage,
    })
    const storageRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: '/storage/tasks',
      component: () => <div>storage tasks page</div>,
    })
    const router = createRouter({
      routeTree: rootRoute.addChildren([tasksRoute, storageRoute]),
      history: createMemoryHistory({ initialEntries: ['/crawler/tasks'] }),
    })

    render(<RouterProvider router={router} />)

    await user.type(await screen.findByLabelText('cached input'), 'stored')
    await user.click(screen.getByText('storage tasks'))
    expect(await screen.findByText('storage tasks page')).toBeInTheDocument()
    await user.click(screen.getByText('tasks'))

    expect(await screen.findByLabelText('cached input')).toHaveValue('stored')
  })
})
