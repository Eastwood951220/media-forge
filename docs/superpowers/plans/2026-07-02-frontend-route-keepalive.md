# Frontend Route KeepAlive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add page state preservation for authenticated frontend routes, exclude `/init` and `/login`, and delete the matching cached page whenever a TagsView tab is closed.

**Architecture:** Keep the existing TanStack Router route tree and add a small keep-alive bridge inside the authenticated `AppLayout`. Cache identity is `TagView.fullPath` (`pathname + search`) so TagsView and page cache eviction use the same key. `keepalive-for-react-router` is installed because it was requested, but the active implementation uses `keepalive-for-react` directly because the documented router adapter replaces React Router outlets, while this app uses `@tanstack/react-router`.

**Tech Stack:** React 19, TypeScript 6, TanStack Router 1.x, Zustand 5, Ant Design 6, Vitest, React Testing Library, `keepalive-for-react`, `keepalive-for-react-router`.

---

## Context Notes

- Context7 documentation for `/finedaybreak/keepalive-for-react` shows `KeepAliveRouteOutlet` from `keepalive-for-react-router` is a replacement for React Router `<Outlet>`, not TanStack Router `<Outlet>`.
- The current app uses `@tanstack/react-router` in `frontend/src/routes/index.tsx` and `frontend/src/layout/index.tsx`.
- To preserve the current router and keep this scoped to the refactor, use `KeepAlive` and `useKeepAliveRef` from `keepalive-for-react` around the TanStack `<Outlet />`.
- `/login` and `/init` are already outside the protected `layout` route, so they are structurally excluded. The implementation also keeps an explicit exclude list for clarity and tests.

## File Structure

- Modify: `frontend/package.json`
  - Add `keepalive-for-react` and `keepalive-for-react-router` dependencies through npm.
- Modify: `frontend/package-lock.json`
  - Let npm update the lockfile.
- Create: `frontend/src/layout/routeCache.tsx`
  - Own the keep-alive provider, active cache key calculation, cache exclusion list, imperative cache control context, and TanStack outlet wrapper.
- Modify: `frontend/src/layout/index.tsx`
  - Replace the raw TanStack `<Outlet />` with `RouteKeepAliveOutlet` inside `RouteKeepAliveProvider`.
- Modify: `frontend/src/layout/TagsView/index.tsx`
  - Wire close, close-current, close-other, close-left, close-right, close-all, middle-click close, and refresh to route cache control.
- Create: `frontend/tests/route-keepalive.ui.test.tsx`
  - Verify active cache key, explicit exclusions, and pure exclude helper behavior.
- Modify: `frontend/tests/tags-view.ui.test.tsx`
  - Verify tab close operations destroy the corresponding route cache keys.

---

### Task 1: Install KeepAlive Dependencies

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [ ] **Step 1: Install both requested packages**

Run:

```bash
cd frontend
npm install keepalive-for-react keepalive-for-react-router
```

Expected: npm exits with code `0`, and both `frontend/package.json` and `frontend/package-lock.json` change.

- [ ] **Step 2: Verify package manifest entries**

Run:

```bash
cd frontend
node -e "const p=require('./package.json'); console.log(p.dependencies['keepalive-for-react']); console.log(p.dependencies['keepalive-for-react-router']);"
```

Expected: two semver strings print, one for `keepalive-for-react` and one for `keepalive-for-react-router`.

- [ ] **Step 3: Commit dependency changes**

Run:

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "feat(frontend): add keepalive route cache packages"
```

Expected: git creates one commit containing only dependency manifest and lockfile changes.

---

### Task 2: Add TanStack Router KeepAlive Bridge

**Files:**
- Create: `frontend/src/layout/routeCache.tsx`
- Modify: `frontend/src/layout/index.tsx`
- Test: `frontend/tests/route-keepalive.ui.test.tsx`

- [ ] **Step 1: Write the failing route keep-alive tests**

Create `frontend/tests/route-keepalive.ui.test.tsx` with this complete content:

```tsx
import type { PropsWithChildren } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
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
})
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```bash
cd frontend
npm test -- tests/route-keepalive.ui.test.tsx
```

Expected: FAIL because `../src/layout/routeCache` does not exist.

- [ ] **Step 3: Create the route cache bridge**

Create `frontend/src/layout/routeCache.tsx` with this complete content:

```tsx
import { createContext, useContext, useMemo, type PropsWithChildren } from 'react'
import { Outlet, useRouterState } from '@tanstack/react-router'
import { KeepAlive, useKeepAliveRef } from 'keepalive-for-react'
import { getFullPath } from '@/routes/tags'

export const ROUTE_CACHE_EXCLUDE_PATHS = ['/login', '/init']

export type RouteCacheControl = {
  destroy: (cacheKey: string) => Promise<void>
  destroyMany: (cacheKeys: string[]) => Promise<void>
  destroyOther: (cacheKey: string) => Promise<void>
  destroyAll: () => Promise<void>
  refresh: (cacheKey?: string) => void
}

const noopRouteCacheControl: RouteCacheControl = {
  destroy: async () => undefined,
  destroyMany: async () => undefined,
  destroyOther: async () => undefined,
  destroyAll: async () => undefined,
  refresh: () => undefined,
}

const RouteCacheControlContext = createContext<RouteCacheControl>(noopRouteCacheControl)

const RouteCacheRefContext = createContext<ReturnType<typeof useKeepAliveRef> | null>(null)

export function isRouteCacheExcluded(pathname: string) {
  return ROUTE_CACHE_EXCLUDE_PATHS.includes(pathname)
}

export function useRouteCacheControl() {
  return useContext(RouteCacheControlContext)
}

export function RouteKeepAliveProvider({ children }: PropsWithChildren) {
  const aliveRef = useKeepAliveRef()

  const cacheControl = useMemo<RouteCacheControl>(
    () => ({
      destroy: async (cacheKey) => {
        await aliveRef.current?.destroy(cacheKey)
      },
      destroyMany: async (cacheKeys) => {
        if (cacheKeys.length > 0) {
          await aliveRef.current?.destroy(cacheKeys)
        }
      },
      destroyOther: async (cacheKey) => {
        await aliveRef.current?.destroyOther(cacheKey)
      },
      destroyAll: async () => {
        await aliveRef.current?.destroyAll()
      },
      refresh: (cacheKey) => {
        aliveRef.current?.refresh(cacheKey)
      },
    }),
    [aliveRef],
  )

  return (
    <RouteCacheRefContext.Provider value={aliveRef}>
      <RouteCacheControlContext.Provider value={cacheControl}>
        {children}
      </RouteCacheControlContext.Provider>
    </RouteCacheRefContext.Provider>
  )
}

export function RouteKeepAliveOutlet() {
  const aliveRef = useContext(RouteCacheRefContext)
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const searchStr = useRouterState({ select: (state) => state.location.searchStr ?? '' })
  const activeCacheKey = getFullPath(pathname, searchStr)

  if (isRouteCacheExcluded(pathname) || !aliveRef) {
    return <Outlet />
  }

  return (
    <KeepAlive
      activeCacheKey={activeCacheKey}
      aliveRef={aliveRef}
      exclude={ROUTE_CACHE_EXCLUDE_PATHS}
      max={18}
    >
      <Outlet />
    </KeepAlive>
  )
}
```

- [ ] **Step 4: Replace the layout outlet with the keep-alive outlet**

Modify `frontend/src/layout/index.tsx` to this complete content:

```tsx
import { useState } from 'react'
import { Layout } from 'antd'
import { useThemeStore } from '@/stores/useThemeStore'
import { LayoutHeader } from './Header'
import { RouteKeepAliveOutlet, RouteKeepAliveProvider } from './routeCache'
import { SideMenu } from './Sidebar'
import { TagsView } from './TagsView'
import styles from './index.module.less'

const { Content } = Layout

export default function AppLayout() {
  const darkMode = useThemeStore((state) => state.darkMode)
  const [collapsed, setCollapsed] = useState(false)

  return (
    <RouteKeepAliveProvider>
      <Layout className={darkMode ? `${styles.layout} ${styles.dark}` : styles.layout}>
        <SideMenu collapsed={collapsed} />

        <Layout className={styles.main}>
          <LayoutHeader
            darkMode={darkMode}
            collapsed={collapsed}
            onCollapse={setCollapsed}
          />
          <TagsView darkMode={darkMode} />

          <Content className={styles.content}>
            <div className={styles.pageContainer}>
              <RouteKeepAliveOutlet />
            </div>
          </Content>
        </Layout>
      </Layout>
    </RouteKeepAliveProvider>
  )
}
```

- [ ] **Step 5: Run route keep-alive tests**

Run:

```bash
cd frontend
npm test -- tests/route-keepalive.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit route cache bridge**

Run:

```bash
git add frontend/src/layout/routeCache.tsx frontend/src/layout/index.tsx frontend/tests/route-keepalive.ui.test.tsx
git commit -m "feat(frontend): cache tanstack route pages"
```

Expected: git creates one commit with the route cache bridge, layout wiring, and tests.

---

### Task 3: Evict Cached Pages When TagsView Closes Tabs

**Files:**
- Modify: `frontend/src/layout/TagsView/index.tsx`
- Test: `frontend/tests/tags-view.ui.test.tsx`

- [ ] **Step 1: Write failing TagsView cache eviction tests**

Modify `frontend/tests/tags-view.ui.test.tsx` to this complete content:

```tsx
import { describe, expect, it, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { TagsView } from '../src/layout/TagsView'
import type { RouteCacheControl } from '../src/layout/routeCache'
import { useTagsViewStore } from '../src/stores/useTagsViewStore'

function createCacheControl(): RouteCacheControl {
  return {
    destroy: vi.fn().mockResolvedValue(undefined),
    destroyMany: vi.fn().mockResolvedValue(undefined),
    destroyOther: vi.fn().mockResolvedValue(undefined),
    destroyAll: vi.fn().mockResolvedValue(undefined),
    refresh: vi.fn(),
  }
}

function renderTagsView(initialPath: string, cacheControl = createCacheControl()) {
  const rootRoute = createRootRoute({
    component: () => <TagsView cacheControl={cacheControl} />,
  })
  const dashboardRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => null,
  })
  const taskRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks',
    component: () => null,
  })
  const newTaskRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks/new',
    component: () => null,
  })
  const configRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/config',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([dashboardRoute, taskRoute, newTaskRoute, configRoute]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })

  return {
    cacheControl,
    ...render(<RouterProvider router={router} />),
  }
}

describe('TagsView', () => {
  beforeEach(() => {
    useTagsViewStore.getState().resetViews()
  })

  it('adds current crawler task page to tags view', async () => {
    renderTagsView('/crawler/tasks')

    expect(await screen.findByText('仪表盘')).toBeInTheDocument()
    expect(await screen.findByText('任务列表')).toBeInTheDocument()
  })

  it('shows right-click context menu actions', async () => {
    renderTagsView('/crawler/tasks')

    await userEvent.pointer({
      keys: '[MouseRight]',
      target: await screen.findByText('任务列表'),
    })

    expect(await screen.findByText('刷新页面')).toBeInTheDocument()
    expect(screen.getByText('关闭当前')).toBeInTheDocument()
    expect(screen.getByText('关闭其他')).toBeInTheDocument()
    expect(screen.getByText('关闭左侧')).toBeInTheDocument()
    expect(screen.getByText('关闭右侧')).toBeInTheDocument()
    expect(screen.getByText('全部关闭')).toBeInTheDocument()
  })

  it('destroys the matching route cache when a tag close icon is clicked', async () => {
    const cacheControl = createCacheControl()
    renderTagsView('/crawler/tasks', cacheControl)

    await userEvent.click(await screen.findByLabelText('关闭 任务列表'))

    expect(cacheControl.destroy).toHaveBeenCalledWith('/crawler/tasks')
  })

  it('destroys removed route caches when closing other tags', async () => {
    const cacheControl = createCacheControl()
    useTagsViewStore.setState({
      visitedViews: [
        { path: '/', fullPath: '/', title: '仪表盘', closable: false },
        { path: '/crawler/tasks', fullPath: '/crawler/tasks', title: '任务列表', closable: true },
        {
          path: '/crawler/tasks/new',
          fullPath: '/crawler/tasks/new?draft=1',
          title: '新建任务',
          closable: true,
        },
        {
          path: '/crawler/config',
          fullPath: '/crawler/config',
          title: '爬虫配置',
          closable: true,
        },
      ],
    })
    renderTagsView('/crawler/tasks', cacheControl)

    await userEvent.pointer({
      keys: '[MouseRight]',
      target: await screen.findByText('任务列表'),
    })
    await userEvent.click(await screen.findByText('关闭其他'))

    expect(cacheControl.destroyMany).toHaveBeenCalledWith([
      '/crawler/tasks/new?draft=1',
      '/crawler/config',
    ])
  })

  it('refreshes the selected route cache from the context menu', async () => {
    const cacheControl = createCacheControl()
    renderTagsView('/crawler/tasks', cacheControl)

    await userEvent.pointer({
      keys: '[MouseRight]',
      target: await screen.findByText('任务列表'),
    })
    await userEvent.click(await screen.findByText('刷新页面'))

    expect(cacheControl.refresh).toHaveBeenCalledWith('/crawler/tasks')
  })
})
```

- [ ] **Step 2: Run TagsView tests to verify they fail**

Run:

```bash
cd frontend
npm test -- tests/tags-view.ui.test.tsx
```

Expected: FAIL because `TagsView` does not accept `cacheControl` and does not call cache eviction methods.

- [ ] **Step 3: Wire TagsView close operations to route cache control**

Modify `frontend/src/layout/TagsView/index.tsx` to this complete content:

```tsx
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import {
  CloseCircleOutlined,
  CloseOutlined,
  ReloadOutlined,
  RollbackOutlined,
} from '@ant-design/icons'
import { getFullPath, getRouteTagMeta } from '@/routes/tags'
import type { RouteCacheControl } from '@/layout/routeCache'
import { useRouteCacheControl } from '@/layout/routeCache'
import { useTagsViewStore } from '@/stores/useTagsViewStore'
import type { TagView } from '@/stores/useTagsViewStore'
import styles from './TagsView.module.less'

/** TagsView 白名单 - 这些路径不会显示在标签页中 */
const TAGS_VIEW_WHITELIST = ['/login', '/init']

type TagsViewProps = {
  darkMode?: boolean
  cacheControl?: RouteCacheControl
}

type ContextMenuState = {
  visible: boolean
  left: number
  top: number
  selectedTag?: TagView
}

function getRemovedCacheKeys(beforeViews: TagView[], nextViews: TagView[]) {
  const nextKeys = new Set(nextViews.map((view) => view.fullPath))
  return beforeViews
    .filter((view) => view.closable !== false && !nextKeys.has(view.fullPath))
    .map((view) => view.fullPath)
}

export function TagsView({ darkMode, cacheControl: cacheControlProp }: TagsViewProps) {
  const navigate = useNavigate()
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const searchStr = useRouterState({ select: (state) => state.location.searchStr ?? '' })
  const visitedViews = useTagsViewStore((state) => state.visitedViews)
  const addVisitedView = useTagsViewStore((state) => state.addVisitedView)
  const removeSelectedView = useTagsViewStore((state) => state.removeSelectedView)
  const removeOtherViews = useTagsViewStore((state) => state.removeOtherViews)
  const removeLeftViews = useTagsViewStore((state) => state.removeLeftViews)
  const removeRightViews = useTagsViewStore((state) => state.removeRightViews)
  const removeAllViews = useTagsViewStore((state) => state.removeAllViews)
  const routeCacheControl = useRouteCacheControl()
  const cacheControl = cacheControlProp ?? routeCacheControl
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    visible: false,
    left: 0,
    top: 0,
  })

  const fullPath = getFullPath(pathname, searchStr)
  const currentMeta = useMemo(() => getRouteTagMeta(pathname), [pathname])
  const isActive = useCallback((view: TagView) => view.fullPath === fullPath, [fullPath])

  useEffect(() => {
    if (TAGS_VIEW_WHITELIST.includes(pathname)) {
      return
    }

    addVisitedView({
      path: pathname,
      fullPath,
      title: currentMeta.title,
      closable: pathname !== '/' && !currentMeta.affix,
      query: searchStr ? Object.fromEntries(new URLSearchParams(searchStr)) : undefined,
    })
  }, [addVisitedView, currentMeta, fullPath, pathname, searchStr])

  const closeContextMenu = useCallback(() => {
    setContextMenu((prev) => (prev.visible ? { ...prev, visible: false } : prev))
  }, [])

  useEffect(() => {
    document.addEventListener('click', closeContextMenu)
    return () => document.removeEventListener('click', closeContextMenu)
  }, [closeContextMenu])

  const navigateAfterClose = useCallback(
    (views: TagView[]) => {
      if (views.some((view) => view.fullPath === fullPath)) return
      const last = views.at(-1)
      void navigate({ to: last?.fullPath ?? '/' })
    },
    [fullPath, navigate],
  )

  const destroyRemovedCaches = useCallback(
    (beforeViews: TagView[], nextViews: TagView[]) => {
      const removedCacheKeys = getRemovedCacheKeys(beforeViews, nextViews)
      void cacheControl.destroyMany(removedCacheKeys)
    },
    [cacheControl],
  )

  const handleClose = useCallback(
    (tag: TagView, event?: React.MouseEvent) => {
      event?.stopPropagation()
      if (tag.closable === false) return
      const nextViews = removeSelectedView(tag)
      void cacheControl.destroy(tag.fullPath)
      navigateAfterClose(nextViews)
    },
    [cacheControl, navigateAfterClose, removeSelectedView],
  )

  const handleMouseDown = useCallback(
    (tag: TagView, event: React.MouseEvent) => {
      if (event.button === 1 && tag.closable !== false) {
        event.preventDefault()
        const nextViews = removeSelectedView(tag)
        void cacheControl.destroy(tag.fullPath)
        navigateAfterClose(nextViews)
      }
    },
    [cacheControl, navigateAfterClose, removeSelectedView],
  )

  const handleContextMenu = useCallback((tag: TagView, event: React.MouseEvent) => {
    event.preventDefault()
    const menuWidth = 140
    const menuHeight = 260
    const left = event.clientX + menuWidth > window.innerWidth
      ? window.innerWidth - menuWidth - 8
      : event.clientX
    const top = event.clientY + menuHeight > window.innerHeight
      ? window.innerHeight - menuHeight - 8
      : event.clientY

    setContextMenu({
      visible: true,
      left: Math.max(0, left),
      top: Math.max(0, top),
      selectedTag: tag,
    })
  }, [])

  const handleRefresh = useCallback(() => {
    closeContextMenu()
    cacheControl.refresh(contextMenu.selectedTag?.fullPath ?? fullPath)
    void navigate({ to: fullPath, replace: true })
  }, [cacheControl, closeContextMenu, contextMenu.selectedTag, fullPath, navigate])

  const handleCloseCurrent = useCallback(() => {
    closeContextMenu()
    const tag = contextMenu.selectedTag
    if (!tag || tag.closable === false) return
    const nextViews = removeSelectedView(tag)
    void cacheControl.destroy(tag.fullPath)
    navigateAfterClose(nextViews)
  }, [
    cacheControl,
    closeContextMenu,
    contextMenu.selectedTag,
    navigateAfterClose,
    removeSelectedView,
  ])

  const handleCloseOthers = useCallback(() => {
    closeContextMenu()
    const tag = contextMenu.selectedTag
    if (!tag) return
    const beforeViews = visitedViews
    const nextViews = removeOtherViews(tag)
    destroyRemovedCaches(beforeViews, nextViews)
    navigateAfterClose(nextViews)
  }, [
    closeContextMenu,
    contextMenu.selectedTag,
    destroyRemovedCaches,
    navigateAfterClose,
    removeOtherViews,
    visitedViews,
  ])

  const handleCloseLeft = useCallback(() => {
    closeContextMenu()
    const tag = contextMenu.selectedTag
    if (!tag) return
    const beforeViews = visitedViews
    const nextViews = removeLeftViews(tag)
    destroyRemovedCaches(beforeViews, nextViews)
    navigateAfterClose(nextViews)
  }, [
    closeContextMenu,
    contextMenu.selectedTag,
    destroyRemovedCaches,
    navigateAfterClose,
    removeLeftViews,
    visitedViews,
  ])

  const handleCloseRight = useCallback(() => {
    closeContextMenu()
    const tag = contextMenu.selectedTag
    if (!tag) return
    const beforeViews = visitedViews
    const nextViews = removeRightViews(tag)
    destroyRemovedCaches(beforeViews, nextViews)
    navigateAfterClose(nextViews)
  }, [
    closeContextMenu,
    contextMenu.selectedTag,
    destroyRemovedCaches,
    navigateAfterClose,
    removeRightViews,
    visitedViews,
  ])

  const handleCloseAll = useCallback(() => {
    closeContextMenu()
    const beforeViews = visitedViews
    const nextViews = removeAllViews()
    destroyRemovedCaches(beforeViews, nextViews)
    navigateAfterClose(nextViews)
  }, [
    closeContextMenu,
    destroyRemovedCaches,
    navigateAfterClose,
    removeAllViews,
    visitedViews,
  ])

  const selectedTag = contextMenu.selectedTag
  const selectedIndex = selectedTag
    ? visitedViews.findIndex((view) => view.fullPath === selectedTag.fullPath)
    : -1
  const isFirst = selectedIndex <= 0
  const isLast = selectedIndex === visitedViews.length - 1
  const isOnly = visitedViews.filter((view) => view.closable !== false).length <= 1
  const isSelectedAffix = selectedTag?.closable === false

  return (
    <>
      <div className={darkMode ? `${styles.tagsView} ${styles.dark}` : styles.tagsView}>
        <div className={styles.scrollContent}>
          <div className={styles.tagsInner}>
            {visitedViews.map((view) => (
              <span
                key={view.fullPath}
                data-path={view.path}
                data-full-path={view.fullPath}
                className={`${styles.tag} ${isActive(view) ? styles.active : ''} ${view.closable === false ? styles.affix : ''}`}
                onClick={() => void navigate({ to: view.fullPath })}
                onMouseDown={(event) => handleMouseDown(view, event)}
                onContextMenu={(event) => handleContextMenu(view, event)}
              >
                {isActive(view) ? <span className={styles.dot} /> : null}
                <span className={styles.tagTitle}>{view.title}</span>
                {view.closable !== false && (
                  <CloseOutlined
                    aria-label={`关闭 ${view.title}`}
                    className={styles.closeIcon}
                    onClick={(event) => handleClose(view, event)}
                  />
                )}
              </span>
            ))}
          </div>
        </div>
      </div>

      {contextMenu.visible && selectedTag && (
        <div
          className={styles.contextMenu}
          style={{ position: 'fixed', left: contextMenu.left, top: contextMenu.top }}
        >
          <button type="button" className={styles.menuItem} onClick={handleRefresh}>
            <ReloadOutlined /> 刷新页面
          </button>
          <div className={styles.menuDivider} />
          <button
            type="button"
            className={`${styles.menuItem} ${isSelectedAffix ? styles.disabled : ''}`}
            disabled={isSelectedAffix}
            onClick={handleCloseCurrent}
          >
            <CloseOutlined /> 关闭当前
          </button>
          <button
            type="button"
            className={`${styles.menuItem} ${isOnly ? styles.disabled : ''}`}
            disabled={isOnly}
            onClick={handleCloseOthers}
          >
            <CloseCircleOutlined /> 关闭其他
          </button>
          <button
            type="button"
            className={`${styles.menuItem} ${isFirst ? styles.disabled : ''}`}
            disabled={isFirst}
            onClick={handleCloseLeft}
          >
            <RollbackOutlined /> 关闭左侧
          </button>
          <button
            type="button"
            className={`${styles.menuItem} ${isLast ? styles.disabled : ''}`}
            disabled={isLast}
            onClick={handleCloseRight}
          >
            <RollbackOutlined className={styles.flipX} /> 关闭右侧
          </button>
          <div className={styles.menuDivider} />
          <button
            type="button"
            className={`${styles.menuItem} ${isOnly ? styles.disabled : ''}`}
            disabled={isOnly}
            onClick={handleCloseAll}
          >
            <CloseCircleOutlined /> 全部关闭
          </button>
        </div>
      )}
    </>
  )
}
```

- [ ] **Step 4: Run TagsView tests**

Run:

```bash
cd frontend
npm test -- tests/tags-view.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit TagsView cache eviction**

Run:

```bash
git add frontend/src/layout/TagsView/index.tsx frontend/tests/tags-view.ui.test.tsx
git commit -m "feat(frontend): evict route caches from tags view"
```

Expected: git creates one commit with TagsView cache-control wiring and tests.

---

### Task 4: Verify Existing App and Layout Tests Still Pass

**Files:**
- Test: `frontend/tests/App.test.tsx`
- Test: `frontend/tests/layout.ui.test.tsx`
- Test: `frontend/tests/tags-view-store.test.ts`

- [ ] **Step 1: Run existing routing and layout tests**

Run:

```bash
cd frontend
npm test -- tests/App.test.tsx tests/layout.ui.test.tsx tests/tags-view-store.test.ts
```

Expected: PASS. The authenticated layout still renders dashboard, crawler pages, header, side menu, and TagsView.

- [ ] **Step 2: Fix only regressions caused by keep-alive wiring**

If the command in Step 1 fails because `KeepAlive` needs DOM behavior that jsdom does not provide, add this mock at the top of the failing test file before imports from `../src/routes` or `../src/layout`:

```tsx
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
```

Run the same test command again:

```bash
cd frontend
npm test -- tests/App.test.tsx tests/layout.ui.test.tsx tests/tags-view-store.test.ts
```

Expected: PASS.

- [ ] **Step 3: Commit test compatibility changes if any were needed**

If Step 2 changed tests, run:

```bash
git add frontend/tests/App.test.tsx frontend/tests/layout.ui.test.tsx frontend/tests/tags-view-store.test.ts
git commit -m "test(frontend): keep layout tests compatible with route cache"
```

Expected: git creates a commit only when test files changed. If no files changed, skip this commit.

---

### Task 5: Final Frontend Verification

**Files:**
- Verify: `frontend/src/layout/routeCache.tsx`
- Verify: `frontend/src/layout/index.tsx`
- Verify: `frontend/src/layout/TagsView/index.tsx`
- Verify: `frontend/tests/route-keepalive.ui.test.tsx`
- Verify: `frontend/tests/tags-view.ui.test.tsx`

- [ ] **Step 1: Run the focused route cache test suite**

Run:

```bash
cd frontend
npm test -- tests/route-keepalive.ui.test.tsx tests/tags-view.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run all frontend tests**

Run:

```bash
cd frontend
npm test -- --run
```

Expected: PASS for all Vitest suites.

- [ ] **Step 3: Run lint**

Run:

```bash
cd frontend
npm run lint
```

Expected: PASS with no ESLint errors.

- [ ] **Step 4: Run production build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS. TypeScript compiles and Vite builds production assets.

- [ ] **Step 5: Inspect git diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: no uncommitted changes if all earlier commit steps were followed.

---

## Self-Review

- Spec coverage: The plan installs the requested packages, adds route page storage for authenticated pages, keeps `/init` and `/login` excluded, and destroys matching cache entries when TagsView tabs close.
- Adapter constraint: The plan records that `keepalive-for-react-router` is React Router-specific in the current documentation and avoids replacing TanStack Router with React Router as part of this scoped refactor.
- Placeholder scan: No placeholder steps are left. Every code-changing step includes the exact file content or command to run.
- Type consistency: Cache keys are consistently `fullPath` strings. `RouteCacheControl` methods match the method names used by `TagsView` tests and implementation.
