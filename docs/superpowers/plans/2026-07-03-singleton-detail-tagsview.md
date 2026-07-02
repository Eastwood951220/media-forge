# Singleton Detail TagsView Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make dynamic detail pages such as crawler task edit and crawler run detail reuse one last-opened tagsView tab and one KeepAlive page cache.

**Architecture:** Route tag metadata will define a stable singleton cache key for dynamic detail routes while preserving the latest real URL for navigation. The tagsView store will deduplicate by this cache key and update the existing tab to the latest opened detail page. The route cache outlet will use the same key, so detail pages share one cached component instance instead of creating one cache per ID.

**Tech Stack:** React 19, TypeScript 6, TanStack Router 1.x, Zustand 5, keepalive-for-react 5, Vitest 3, React Testing Library.

---

## File Structure

- Modify `frontend/src/routes/tags.ts`: add `singletonKey` metadata and `getRouteViewKey()` helper for dynamic detail routes.
- Modify `frontend/src/stores/useTagsViewStore.ts`: add `cacheKey` to `TagView` and compare/deduplicate tags by `cacheKey`.
- Modify `frontend/src/layout/TagsView/index.tsx`: store the latest real `fullPath` but compare active tags and destroy/refresh caches by `cacheKey`.
- Modify `frontend/src/layout/routeCache.tsx`: use `getRouteViewKey()` for `KeepAlive.activeCacheKey` and `<Outlet key>`.
- Modify `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`: close the current dynamic edit tag/cache by route view key and reset form state when editing a different task in the shared cached page.
- Modify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`: reset run detail state when switching to a different run in the shared cached page.
- Create `frontend/tests/routes-tags.test.ts`: unit coverage for singleton route keys.
- Modify `frontend/tests/tags-view-store.test.ts`: store-level dedupe coverage.
- Modify `frontend/tests/tags-view.ui.test.tsx`: UI-level tagsView coverage for dynamic edit/run detail pages.
- Modify `frontend/tests/route-keepalive.ui.test.tsx`: KeepAlive cache-key coverage for dynamic detail routes.

---

### Task 1: Route Tag Singleton Keys

**Files:**
- Modify: `frontend/src/routes/tags.ts`
- Create: `frontend/tests/routes-tags.test.ts`

- [ ] **Step 1: Write the failing route key tests**

Create `frontend/tests/routes-tags.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { getFullPath, getRouteTagMeta, getRouteViewKey } from '../src/routes/tags'

describe('route tag helpers', () => {
  it('keeps ordinary routes keyed by pathname and search string', () => {
    expect(getFullPath('/crawler/tasks', '?page=2')).toBe('/crawler/tasks?page=2')
    expect(getRouteViewKey('/crawler/tasks', '?page=2')).toBe('/crawler/tasks?page=2')
  })

  it('uses one singleton key for crawler task edit pages', () => {
    expect(getRouteTagMeta('/crawler/tasks/task-a/edit')).toMatchObject({
      title: '编辑任务',
      activeMenu: '/crawler/tasks',
      singletonKey: '/crawler/tasks/:id/edit',
    })
    expect(getRouteViewKey('/crawler/tasks/task-a/edit', '')).toBe('/crawler/tasks/:id/edit')
    expect(getRouteViewKey('/crawler/tasks/task-b/edit', '?tab=url')).toBe('/crawler/tasks/:id/edit')
  })

  it('uses one singleton key for crawler run detail pages', () => {
    expect(getRouteTagMeta('/crawler/runs/run-a')).toMatchObject({
      title: '运行详情',
      activeMenu: '/crawler/runs',
      singletonKey: '/crawler/runs/:id',
    })
    expect(getRouteViewKey('/crawler/runs/run-a', '')).toBe('/crawler/runs/:id')
    expect(getRouteViewKey('/crawler/runs/run-b', '?status=failed')).toBe('/crawler/runs/:id')
  })
})
```

- [ ] **Step 2: Run the route key test and verify it fails**

Run:

```bash
cd frontend
npm test -- routes-tags.test.ts
```

Expected: FAIL because `getRouteViewKey` is not exported.

- [ ] **Step 3: Implement singleton route keys**

Replace `frontend/src/routes/tags.ts` with:

```ts
export type RouteTagMeta = {
  title: string
  affix?: boolean
  activeMenu?: string
  singletonKey?: string
}

const ROUTE_TAGS: Array<{ pattern: RegExp; meta: RouteTagMeta }> = [
  { pattern: /^\/$/, meta: { title: '仪表盘', affix: true } },
  { pattern: /^\/crawler\/tasks$/, meta: { title: '任务列表' } },
  { pattern: /^\/crawler\/config$/, meta: { title: '爬虫配置' } },
  {
    pattern: /^\/crawler\/tasks\/new$/,
    meta: { title: '新建任务', activeMenu: '/crawler/tasks' },
  },
  {
    pattern: /^\/crawler\/tasks\/[^/]+\/edit$/,
    meta: {
      title: '编辑任务',
      activeMenu: '/crawler/tasks',
      singletonKey: '/crawler/tasks/:id/edit',
    },
  },
  { pattern: /^\/crawler\/runs$/, meta: { title: '运行记录', activeMenu: '/crawler/runs' } },
  {
    pattern: /^\/crawler\/runs\/[^/]+$/,
    meta: {
      title: '运行详情',
      activeMenu: '/crawler/runs',
      singletonKey: '/crawler/runs/:id',
    },
  },
  { pattern: /^\/content\/movies$/, meta: { title: '影片列表' } },
]

export function getRouteTagMeta(pathname: string): RouteTagMeta {
  return ROUTE_TAGS.find((item) => item.pattern.test(pathname))?.meta ?? {
    title: pathname,
  }
}

export function getFullPath(pathname: string, searchStr: string): string {
  return `${pathname}${searchStr || ''}`
}

export function getRouteViewKey(pathname: string, searchStr: string): string {
  return getRouteTagMeta(pathname).singletonKey ?? getFullPath(pathname, searchStr)
}
```

- [ ] **Step 4: Run the route key test and verify it passes**

Run:

```bash
cd frontend
npm test -- routes-tags.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/tags.ts frontend/tests/routes-tags.test.ts
git commit -m "feat: add singleton route view keys"
```

---

### Task 2: TagsView Store Deduplication

**Files:**
- Modify: `frontend/src/stores/useTagsViewStore.ts`
- Modify: `frontend/tests/tags-view-store.test.ts`

- [ ] **Step 1: Write the failing store tests**

Append these tests to `frontend/tests/tags-view-store.test.ts`:

```ts
  it('deduplicates dynamic task edit tags by cache key and keeps the latest url', () => {
    const store = useTagsViewStore.getState()
    store.addVisitedView({
      path: '/crawler/tasks/task-a/edit',
      fullPath: '/crawler/tasks/task-a/edit',
      cacheKey: '/crawler/tasks/:id/edit',
      title: '编辑任务',
      closable: true,
    })
    store.addVisitedView({
      path: '/crawler/tasks/task-b/edit',
      fullPath: '/crawler/tasks/task-b/edit',
      cacheKey: '/crawler/tasks/:id/edit',
      title: '编辑任务',
      closable: true,
    })

    expect(useTagsViewStore.getState().visitedViews).toEqual([
      { path: '/', fullPath: '/', cacheKey: '/', title: '仪表盘', closable: false },
      {
        path: '/crawler/tasks/task-b/edit',
        fullPath: '/crawler/tasks/task-b/edit',
        cacheKey: '/crawler/tasks/:id/edit',
        title: '编辑任务',
        closable: true,
      },
    ])
  })

  it('removes and keeps tags by cache key', () => {
    const store = useTagsViewStore.getState()
    store.addVisitedView({
      path: '/crawler/tasks',
      fullPath: '/crawler/tasks',
      cacheKey: '/crawler/tasks',
      title: '任务列表',
      closable: true,
    })
    store.addVisitedView({
      path: '/crawler/runs/run-a',
      fullPath: '/crawler/runs/run-a',
      cacheKey: '/crawler/runs/:id',
      title: '运行详情',
      closable: true,
    })

    const nextViews = store.removeSelectedView({
      path: '/crawler/runs/run-b',
      fullPath: '/crawler/runs/run-b',
      cacheKey: '/crawler/runs/:id',
      title: '运行详情',
      closable: true,
    })

    expect(nextViews.map((view) => view.cacheKey)).toEqual(['/', '/crawler/tasks'])
  })
```

- [ ] **Step 2: Run the store test and verify it fails**

Run:

```bash
cd frontend
npm test -- tags-view-store.test.ts
```

Expected: FAIL because `TagView` does not have `cacheKey` and store actions compare by `fullPath`.

- [ ] **Step 3: Implement cache-key based store actions**

Replace `frontend/src/stores/useTagsViewStore.ts` with:

```ts
import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

export type TagView = {
  path: string
  fullPath: string
  cacheKey: string
  title: string
  query?: Record<string, unknown>
  closable?: boolean
}

const DASHBOARD_TAG: TagView = {
  path: '/',
  fullPath: '/',
  cacheKey: '/',
  title: '仪表盘',
  closable: false,
}

type TagsViewState = {
  visitedViews: TagView[]
  addVisitedView: (view: TagView) => void
  updateVisitedView: (view: TagView) => void
  removeSelectedView: (view: TagView) => TagView[]
  removeOtherViews: (view: TagView) => TagView[]
  removeLeftViews: (view: TagView) => TagView[]
  removeRightViews: (view: TagView) => TagView[]
  removeAllViews: () => TagView[]
  resetViews: () => void
}

function getTagKey(view: TagView): string {
  return view.cacheKey || view.fullPath
}

function hydrateView(view: TagView): TagView {
  return {
    ...view,
    cacheKey: view.cacheKey || view.fullPath,
  }
}

function normalizeViews(views: TagView[]): TagView[] {
  const normalized: TagView[] = []
  const indexes = new Map<string, number>()

  for (const rawView of views) {
    const view = hydrateView(rawView)
    const key = getTagKey(view)
    const index = indexes.get(key)
    if (index === undefined) {
      indexes.set(key, normalized.length)
      normalized.push(view)
    } else {
      normalized[index] = { ...normalized[index], ...view }
    }
  }

  const dashboardIndex = normalized.findIndex((view) => getTagKey(view) === DASHBOARD_TAG.cacheKey)
  if (dashboardIndex === -1) {
    return [DASHBOARD_TAG, ...normalized]
  }

  const dashboard = { ...DASHBOARD_TAG, ...normalized[dashboardIndex], closable: false }
  const withoutDashboard = normalized.filter((_, index) => index !== dashboardIndex)
  return [dashboard, ...withoutDashboard]
}

export const useTagsViewStore = create<TagsViewState>()(
  devtools(
    persist(
      (set, get) => ({
        visitedViews: [DASHBOARD_TAG],

        addVisitedView: (view) => {
          const normalizedView = hydrateView(view)
          const viewKey = getTagKey(normalizedView)
          const { visitedViews } = get()
          if (visitedViews.some((item) => getTagKey(item) === viewKey)) {
            get().updateVisitedView(normalizedView)
            return
          }

          set({ visitedViews: normalizeViews([...visitedViews, normalizedView]) })
        },

        updateVisitedView: (view) => {
          const normalizedView = hydrateView(view)
          const viewKey = getTagKey(normalizedView)
          const { visitedViews } = get()
          set({
            visitedViews: normalizeViews(
              visitedViews.map((item) =>
                getTagKey(item) === viewKey ? { ...item, ...normalizedView } : item,
              ),
            ),
          })
        },

        removeSelectedView: (view) => {
          const viewKey = getTagKey(hydrateView(view))
          const nextViews = normalizeViews(
            get().visitedViews.filter(
              (item) => getTagKey(item) !== viewKey || item.closable === false,
            ),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        removeOtherViews: (view) => {
          const viewKey = getTagKey(hydrateView(view))
          const nextViews = normalizeViews(
            get().visitedViews.filter(
              (item) => getTagKey(item) === viewKey || item.closable === false,
            ),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        removeLeftViews: (view) => {
          const { visitedViews } = get()
          const viewKey = getTagKey(hydrateView(view))
          const targetIndex = visitedViews.findIndex((item) => getTagKey(item) === viewKey)
          if (targetIndex <= 0) return visitedViews

          const nextViews = normalizeViews(
            visitedViews.filter((item, index) => index >= targetIndex || item.closable === false),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        removeRightViews: (view) => {
          const { visitedViews } = get()
          const viewKey = getTagKey(hydrateView(view))
          const targetIndex = visitedViews.findIndex((item) => getTagKey(item) === viewKey)
          if (targetIndex === -1) return visitedViews

          const nextViews = normalizeViews(
            visitedViews.filter((item, index) => index <= targetIndex || item.closable === false),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        removeAllViews: () => {
          const nextViews = normalizeViews(
            get().visitedViews.filter((item) => item.closable === false),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        resetViews: () => {
          set({ visitedViews: [DASHBOARD_TAG] })
        },
      }),
      {
        name: 'media-forge-tags-view',
        partialize: (state) => ({ visitedViews: normalizeViews(state.visitedViews) }),
      },
    ),
  ),
)
```

- [ ] **Step 4: Update existing store test fixtures**

In `frontend/tests/tags-view-store.test.ts`, update existing `TagView` literals so each one includes `cacheKey` matching its previous `fullPath`.

Use this exact first test body:

```ts
  it('keeps dashboard affix and adds crawler task routes', () => {
    useTagsViewStore.getState().addVisitedView({
      path: '/crawler/tasks',
      fullPath: '/crawler/tasks',
      cacheKey: '/crawler/tasks',
      title: '任务列表',
      closable: true,
    })

    expect(useTagsViewStore.getState().visitedViews.map((view) => view.title)).toEqual([
      '仪表盘',
      '任务列表',
    ])
  })
```

Use this exact second test body:

```ts
  it('removes right-side closable views while preserving affix dashboard', () => {
    const store = useTagsViewStore.getState()
    store.addVisitedView({
      path: '/crawler/tasks',
      fullPath: '/crawler/tasks',
      cacheKey: '/crawler/tasks',
      title: '任务列表',
      closable: true,
    })
    store.addVisitedView({
      path: '/crawler/tasks/new',
      fullPath: '/crawler/tasks/new',
      cacheKey: '/crawler/tasks/new',
      title: '新建任务',
      closable: true,
    })

    const nextViews = store.removeRightViews({
      path: '/crawler/tasks',
      fullPath: '/crawler/tasks',
      cacheKey: '/crawler/tasks',
      title: '任务列表',
      closable: true,
    })

    expect(nextViews.map((view) => view.fullPath)).toEqual(['/', '/crawler/tasks'])
  })
```

- [ ] **Step 5: Run the store test and verify it passes**

Run:

```bash
cd frontend
npm test -- tags-view-store.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/stores/useTagsViewStore.ts frontend/tests/tags-view-store.test.ts
git commit -m "fix: deduplicate tags by route cache key"
```

---

### Task 3: TagsView And KeepAlive Integration

**Files:**
- Modify: `frontend/src/layout/TagsView/index.tsx`
- Modify: `frontend/src/layout/routeCache.tsx`
- Modify: `frontend/tests/tags-view.ui.test.tsx`
- Modify: `frontend/tests/route-keepalive.ui.test.tsx`
- Modify: `frontend/tests/layout.ui.test.tsx`

- [ ] **Step 1: Write failing TagsView UI coverage**

Modify `renderTagsView()` in `frontend/tests/tags-view.ui.test.tsx` so the test router contains dynamic task edit and run detail routes:

```tsx
  const editTaskRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks/$id/edit',
    component: () => null,
  })
  const runDetailRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/runs/$id',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([
      dashboardRoute,
      taskRoute,
      newTaskRoute,
      configRoute,
      editTaskRoute,
      runDetailRoute,
    ]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })
```

Append these tests to the `TagsView` describe block:

```tsx
  it('keeps one task edit tag and updates it to the latest opened task', async () => {
    const { rerender } = renderTagsView('/crawler/tasks/task-a/edit')

    expect(await screen.findByText('编辑任务')).toBeInTheDocument()
    expect(useTagsViewStore.getState().visitedViews).toMatchObject([
      { fullPath: '/', cacheKey: '/' },
      {
        fullPath: '/crawler/tasks/task-a/edit',
        cacheKey: '/crawler/tasks/:id/edit',
        title: '编辑任务',
      },
    ])

    const rootRoute = createRootRoute({
      component: () => <TagsView cacheControl={createCacheControl()} />,
    })
    const editTaskRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: '/crawler/tasks/$id/edit',
      component: () => null,
    })
    const router = createRouter({
      routeTree: rootRoute.addChildren([editTaskRoute]),
      history: createMemoryHistory({ initialEntries: ['/crawler/tasks/task-b/edit'] }),
    })

    rerender(<RouterProvider router={router} />)

    expect(screen.getAllByText('编辑任务')).toHaveLength(1)
    expect(useTagsViewStore.getState().visitedViews).toMatchObject([
      { fullPath: '/', cacheKey: '/' },
      {
        fullPath: '/crawler/tasks/task-b/edit',
        cacheKey: '/crawler/tasks/:id/edit',
        title: '编辑任务',
      },
    ])
  })

  it('destroys the singleton route cache when closing a run detail tag', async () => {
    const cacheControl = createCacheControl()
    renderTagsView('/crawler/runs/run-a', cacheControl)

    await userEvent.click(await screen.findByLabelText('关闭 运行详情'))

    expect(cacheControl.destroy).toHaveBeenCalledWith('/crawler/runs/:id')
  })
```

- [ ] **Step 2: Write failing KeepAlive coverage**

Modify `renderCachedOutlet()` in `frontend/tests/route-keepalive.ui.test.tsx` so the test router contains dynamic task edit and run detail routes:

```tsx
  const taskEditRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks/$id/edit',
    component: () => <div>task edit page</div>,
  })
  const runDetailRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/runs/$id',
    component: () => <div>run detail page</div>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([tasksRoute, configRoute, taskEditRoute, runDetailRoute]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })
```

Append these tests to the `RouteKeepAliveOutlet` describe block:

```tsx
  it('uses one cache key for crawler task edit pages', async () => {
    renderCachedOutlet('/crawler/tasks/task-a/edit?draft=1')

    const keepAlive = await screen.findByTestId('keep-alive')
    expect(keepAlive).toHaveAttribute('data-active-cache-key', '/crawler/tasks/:id/edit')
    expect(await screen.findByText('task edit page')).toBeInTheDocument()
  })

  it('uses one cache key for crawler run detail pages', async () => {
    renderCachedOutlet('/crawler/runs/run-a?status=failed')

    const keepAlive = await screen.findByTestId('keep-alive')
    expect(keepAlive).toHaveAttribute('data-active-cache-key', '/crawler/runs/:id')
    expect(await screen.findByText('run detail page')).toBeInTheDocument()
  })
```

- [ ] **Step 3: Run UI cache tests and verify they fail**

Run:

```bash
cd frontend
npm test -- tags-view.ui.test.tsx route-keepalive.ui.test.tsx
```

Expected: FAIL because TagsView and KeepAlive still use `fullPath` as the unique cache key.

- [ ] **Step 4: Update TagsView to use cacheKey for identity and fullPath for navigation**

Modify `frontend/src/layout/TagsView/index.tsx`.

Change the route tag import:

```ts
import { getFullPath, getRouteTagMeta, getRouteViewKey } from '@/routes/tags'
```

Change `getRemovedCacheKeys` to:

```ts
function getRemovedCacheKeys(beforeViews: TagView[], nextViews: TagView[]) {
  const nextKeys = new Set(nextViews.map((view) => view.cacheKey))
  return beforeViews
    .filter((view) => view.closable !== false && !nextKeys.has(view.cacheKey))
    .map((view) => view.cacheKey)
}
```

Change the current route key block to:

```ts
  const fullPath = getFullPath(pathname, searchStr)
  const cacheKey = getRouteViewKey(pathname, searchStr)
  const currentMeta = useMemo(() => getRouteTagMeta(pathname), [pathname])
  const isActive = useCallback((view: TagView) => view.cacheKey === cacheKey, [cacheKey])
```

Change `addVisitedView` call to include `cacheKey`:

```ts
    addVisitedView({
      path: pathname,
      fullPath,
      cacheKey,
      title: currentMeta.title,
      closable: pathname !== '/' && !currentMeta.affix,
      query: searchStr ? Object.fromEntries(new URLSearchParams(searchStr)) : undefined,
    })
  }, [addVisitedView, cacheKey, currentMeta, fullPath, pathname, searchStr])
```

Change `navigateAfterClose` to check the active cache key:

```ts
  const navigateAfterClose = useCallback(
    (views: TagView[]) => {
      if (views.some((view) => view.cacheKey === cacheKey)) return
      const last = views.at(-1)
      void navigate({ to: last?.fullPath ?? '/' })
    },
    [cacheKey, navigate],
  )
```

Change cache destruction and refresh calls:

```ts
      void cacheControl.destroy(tag.cacheKey)
```

```ts
        void cacheControl.destroy(tag.cacheKey)
```

```ts
    cacheControl.refresh(contextMenu.selectedTag?.cacheKey ?? cacheKey)
    void navigate({ to: fullPath, replace: true })
```

```ts
    void cacheControl.destroy(tag.cacheKey)
```

Change selected tag lookup:

```ts
  const selectedIndex = selectedTag
    ? visitedViews.findIndex((view) => view.cacheKey === selectedTag.cacheKey)
    : -1
```

Keep tag rendering keyed by `view.cacheKey`, and keep click navigation using `view.fullPath`:

```tsx
            {visitedViews.map((view) => (
              <span
                key={view.cacheKey}
                data-path={view.path}
                data-full-path={view.fullPath}
                data-cache-key={view.cacheKey}
                className={`${styles.tag} ${isActive(view) ? styles.active : ''} ${view.closable === false ? styles.affix : ''}`}
                onClick={() => void navigate({ to: view.fullPath })}
                onMouseDown={(event) => handleMouseDown(view, event)}
                onContextMenu={(event) => handleContextMenu(view, event)}
              >
```

- [ ] **Step 5: Update RouteKeepAliveOutlet to use route view keys**

Modify `frontend/src/layout/routeCache.tsx`.

Change the import:

```ts
import { getRouteViewKey } from '@/routes/tags'
```

Change the active cache key:

```ts
  const activeCacheKey = getRouteViewKey(pathname, searchStr)
```

Keep the keyed outlet using the same cache key:

```tsx
      <Outlet key={activeCacheKey} />
```

- [ ] **Step 6: Update layout test fixtures**

Modify `frontend/tests/layout.ui.test.tsx` initial `visitedViews` fixture to include `cacheKey`:

```ts
    useTagsViewStore.setState({
      visitedViews: [
        { path: '/', fullPath: '/', cacheKey: '/', title: '仪表盘', closable: false },
        {
          path: '/crawler/tasks',
          fullPath: '/crawler/tasks',
          cacheKey: '/crawler/tasks',
          title: '任务列表',
          closable: true,
        },
      ],
    })
```

Modify `frontend/tests/tags-view.ui.test.tsx` seeded `visitedViews` fixture in the “destroys removed route caches” test:

```ts
    useTagsViewStore.setState({
      visitedViews: [
        { path: '/', fullPath: '/', cacheKey: '/', title: '仪表盘', closable: false },
        {
          path: '/crawler/tasks',
          fullPath: '/crawler/tasks',
          cacheKey: '/crawler/tasks',
          title: '任务列表',
          closable: true,
        },
        {
          path: '/crawler/tasks/new',
          fullPath: '/crawler/tasks/new?draft=1',
          cacheKey: '/crawler/tasks/new?draft=1',
          title: '新建任务',
          closable: true,
        },
        {
          path: '/crawler/config',
          fullPath: '/crawler/config',
          cacheKey: '/crawler/config',
          title: '爬虫配置',
          closable: true,
        },
      ],
    })
```

- [ ] **Step 7: Run UI cache tests and verify they pass**

Run:

```bash
cd frontend
npm test -- tags-view.ui.test.tsx route-keepalive.ui.test.tsx layout.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/layout/TagsView/index.tsx frontend/src/layout/routeCache.tsx frontend/tests/tags-view.ui.test.tsx frontend/tests/route-keepalive.ui.test.tsx frontend/tests/layout.ui.test.tsx
git commit -m "fix: reuse one tag and cache for detail routes"
```

---

### Task 4: Shared Cached Detail Page State Reset

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
- Modify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- Create: `frontend/tests/detail-singleton-state.ui.test.tsx`

- [ ] **Step 1: Write failing page state reset tests**

Create `frontend/tests/detail-singleton-state.ui.test.tsx`:

```tsx
import { App as AntApp } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import TaskFormPage from '../src/pages/crawler/tasks/TaskFormPage'
import RunDetailPage from '../src/pages/crawler/runs/RunDetailPage'
import { useTagsViewStore } from '../src/stores/useTagsViewStore'

const getCrawlTask = vi.fn()
const updateCrawlTask = vi.fn()
const createCrawlTask = vi.fn()
const extractTaskName = vi.fn()
const getCrawlerRun = vi.fn()
const getCrawlerRunTasks = vi.fn()

vi.mock('../src/api/crawlTask', () => ({
  getCrawlTask: (...args: unknown[]) => getCrawlTask(...args),
  updateCrawlTask: (...args: unknown[]) => updateCrawlTask(...args),
  createCrawlTask: (...args: unknown[]) => createCrawlTask(...args),
  extractTaskName: (...args: unknown[]) => extractTaskName(...args),
}))

vi.mock('../src/api/crawlerRun', () => ({
  getCrawlerRun: (...args: unknown[]) => getCrawlerRun(...args),
  getCrawlerRunTasks: (...args: unknown[]) => getCrawlerRunTasks(...args),
}))

vi.mock('../src/layout/routeCache', () => ({
  useRouteCacheControl: () => ({
    destroy: vi.fn().mockResolvedValue(undefined),
    destroyMany: vi.fn().mockResolvedValue(undefined),
    destroyOther: vi.fn().mockResolvedValue(undefined),
    destroyAll: vi.fn().mockResolvedValue(undefined),
    refresh: vi.fn(),
  }),
}))

function renderTaskEdit(initialPath: string) {
  const rootRoute = createRootRoute({
    component: () => (
      <AntApp>
        <TaskFormPage />
      </AntApp>
    ),
  })
  const editRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks/$id/edit',
    component: () => null,
  })
  const taskListRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks',
    component: () => <div>任务列表</div>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([editRoute, taskListRoute]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })

  return render(<RouterProvider router={router} />)
}

function renderRunDetail(initialPath: string) {
  const rootRoute = createRootRoute({
    component: () => <RunDetailPage />,
  })
  const detailRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/runs/$id',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([detailRoute]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })

  return render(<RouterProvider router={router} />)
}

describe('singleton cached detail pages', () => {
  beforeEach(() => {
    useTagsViewStore.getState().resetViews()
    getCrawlTask.mockReset()
    updateCrawlTask.mockReset()
    createCrawlTask.mockReset()
    extractTaskName.mockReset()
    getCrawlerRun.mockReset()
    getCrawlerRunTasks.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('reloads task form values when the shared edit page switches task id', async () => {
    getCrawlTask.mockImplementation(async (id: string) => ({
      id,
      name: id === 'task-a' ? '任务A' : '任务B',
      storage_location: id === 'task-a' ? 'A' : 'B',
      is_skip: false,
      urls: [
        {
          url: `https://javdb.com/actors/${id}`,
          url_type: 'actors',
          has_magnet: true,
          has_chinese_sub: false,
          sort_type: 0,
          url_name: id === 'task-a' ? '演员A' : '演员B',
        },
      ],
    }))

    const { rerender } = renderTaskEdit('/crawler/tasks/task-a/edit')

    expect(await screen.findByDisplayValue('任务A')).toBeInTheDocument()

    const rootRoute = createRootRoute({
      component: () => (
        <AntApp>
          <TaskFormPage />
        </AntApp>
      ),
    })
    const editRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: '/crawler/tasks/$id/edit',
      component: () => null,
    })
    const taskListRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: '/crawler/tasks',
      component: () => <div>任务列表</div>,
    })
    const router = createRouter({
      routeTree: rootRoute.addChildren([editRoute, taskListRoute]),
      history: createMemoryHistory({ initialEntries: ['/crawler/tasks/task-b/edit'] }),
    })

    rerender(<RouterProvider router={router} />)

    expect(await screen.findByDisplayValue('任务B')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByDisplayValue('任务A')).not.toBeInTheDocument()
    })
  })

  it('clears previous run detail rows while loading another run id in the shared page', async () => {
    getCrawlerRun.mockImplementation(async (id: string) => ({
      id,
      task_name: id === 'run-a' ? '任务A' : '任务B',
      status: 'completed',
      crawl_mode: 'incremental',
      created_at: '2026-07-03T00:00:00Z',
      logs: [],
    }))
    getCrawlerRunTasks.mockImplementation(async (id: string) => ({
      rows: id === 'run-a'
        ? [{ id: 'row-a', code: 'AAA-001', source_name: '来源A', status: 'saved', error: '' }]
        : [{ id: 'row-b', code: 'BBB-002', source_name: '来源B', status: 'saved', error: '' }],
      total: 1,
    }))

    const { rerender } = renderRunDetail('/crawler/runs/run-a')

    expect(await screen.findByText('运行详情 - 任务A')).toBeInTheDocument()
    expect(await screen.findByText('AAA-001')).toBeInTheDocument()

    const rootRoute = createRootRoute({
      component: () => <RunDetailPage />,
    })
    const detailRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: '/crawler/runs/$id',
      component: () => null,
    })
    const router = createRouter({
      routeTree: rootRoute.addChildren([detailRoute]),
      history: createMemoryHistory({ initialEntries: ['/crawler/runs/run-b'] }),
    })

    rerender(<RouterProvider router={router} />)

    expect(await screen.findByText('运行详情 - 任务B')).toBeInTheDocument()
    expect(await screen.findByText('BBB-002')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText('AAA-001')).not.toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 2: Run the state reset test and verify it fails**

Run:

```bash
cd frontend
npm test -- detail-singleton-state.ui.test.tsx
```

Expected: FAIL because the shared cached pages keep previous state while loading another ID.

- [ ] **Step 3: Update TaskFormPage to use route view key and reset on task ID changes**

Modify imports in `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`:

```ts
import { getFullPath, getRouteViewKey } from '@/routes/tags'
```

Change route key calculation:

```ts
  const fullPath = getFullPath(pathname, searchStr)
  const cacheKey = getRouteViewKey(pathname, searchStr)
```

Change `closeCurrentTag`:

```ts
  const closeCurrentTag = useCallback(() => {
    const currentView = useTagsViewStore.getState().visitedViews.find((v) => v.cacheKey === cacheKey)
    if (currentView) {
      removeSelectedView(currentView)
    }
    void cacheControl.destroy(cacheKey)
  }, [cacheKey, removeSelectedView, cacheControl])
```

At the start of the edit-loading effect, reset form state before fetching:

```ts
  useEffect(() => {
    if (!isEdit || !taskId) return
    form.resetFields()
    setStorageLocationManuallyEdited(false)
    setLoading(true)
    getCrawlTask(taskId)
      .then((task) => {
        form.setFieldsValue({
          name: task.name,
          storage_location: task.storage_location,
          is_skip: task.is_skip,
          urls: task.urls.map((entry) => ({
            url: entry.url,
            url_type: entry.url_type,
            has_magnet: entry.has_magnet ?? true,
            has_chinese_sub: entry.has_chinese_sub ?? false,
            sort_type: entry.sort_type ?? 0,
            url_name: entry.url_name ?? '',
          })),
        })
      })
      .catch(() => message.error('任务详情加载失败'))
      .finally(() => setLoading(false))
  }, [form, isEdit, message, taskId])
```

- [ ] **Step 4: Update RunDetailPage to reset state on run ID changes**

Modify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`.

Add this effect after state declarations:

```ts
  useEffect(() => {
    setRun(null)
    setTasks([])
    setStatusFilter(undefined)
    setKeyword('')
  }, [id])
```

Change the run fetch effect to guard stale async results:

```ts
  useEffect(() => {
    if (!id) return
    let cancelled = false
    const fetchRun = async () => {
      const data = await getCrawlerRun(id)
      if (!cancelled) {
        setRun(data)
      }
    }
    void fetchRun()
    return () => {
      cancelled = true
    }
  }, [id])
```

Change the task fetch effect to guard stale async results:

```ts
  useEffect(() => {
    if (!id) return
    let cancelled = false
    const fetchTasks = async () => {
      setLoading(true)
      try {
        const data = await getCrawlerRunTasks(id, {
          limit: 200,
          status: statusFilter,
          keyword: keyword || undefined,
        })
        if (!cancelled) {
          setTasks(data.rows)
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    void fetchTasks()
    return () => {
      cancelled = true
    }
  }, [id, statusFilter, keyword])
```

- [ ] **Step 5: Run the state reset test and verify it passes**

Run:

```bash
cd frontend
npm test -- detail-singleton-state.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/crawler/tasks/TaskFormPage.tsx frontend/src/pages/crawler/runs/RunDetailPage.tsx frontend/tests/detail-singleton-state.ui.test.tsx
git commit -m "fix: reset shared detail page state on id change"
```

---

### Task 5: Full Frontend Verification

**Files:**
- No source changes.

- [ ] **Step 1: Run focused tests**

Run:

```bash
cd frontend
npm test -- routes-tags.test.ts tags-view-store.test.ts tags-view.ui.test.tsx route-keepalive.ui.test.tsx layout.ui.test.tsx detail-singleton-state.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 3: Manual browser verification**

Run:

```bash
cd frontend
npm run dev
```

Open these paths in order:

```text
/crawler/tasks/task-a/edit
/crawler/tasks/task-b/edit
/crawler/runs/run-a
/crawler/runs/run-b
```

Expected:

- The tags bar shows one `编辑任务` tag after opening both task edit URLs.
- That single `编辑任务` tag has `data-full-path="/crawler/tasks/task-b/edit"` and `data-cache-key="/crawler/tasks/:id/edit"`.
- The tags bar shows one `运行详情` tag after opening both run detail URLs.
- That single `运行详情` tag has `data-full-path="/crawler/runs/run-b"` and `data-cache-key="/crawler/runs/:id"`.
- Closing `编辑任务` destroys cache key `/crawler/tasks/:id/edit`.
- Closing `运行详情` destroys cache key `/crawler/runs/:id`.
- Navigating back to the latest detail tag opens the last real URL, not the route-pattern cache key.

- [ ] **Step 4: Commit final verification note if tests required fixture-only updates**

If Step 1 or Step 2 required only fixture alignment without source behavior changes, commit those test fixture changes:

```bash
git add frontend/tests
git commit -m "test: align tags view singleton fixtures"
```

Skip this commit when there are no uncommitted changes after verification.

---

## Self-Review

- Spec coverage:
  - “编辑爬取任务只能有一个最后打开的 tagsView” is covered by Task 1 route singleton keys, Task 2 store dedupe, and Task 3 TagsView UI test.
  - “运行记录详情只能有一个最后打开的 tagsView” is covered by the same route/store/UI tasks for `/crawler/runs/:id`.
  - “只有一个页面贮存” is covered by Task 3 KeepAlive cache key changes and Task 4 state reset for shared cached component instances.
- Red-flag scan:
  - The plan includes exact file paths, commands, expected results, and code snippets for source edits.
- Type consistency:
  - `TagView.cacheKey` is introduced in Task 2 and used consistently in TagsView, route cache tests, and layout fixtures.
  - `getRouteViewKey(pathname, searchStr)` is defined in Task 1 and imported by both `TagsView` and `RouteKeepAliveOutlet`.
  - `fullPath` remains the real navigation target; `cacheKey` is the singleton identity for tabs and cached pages.
