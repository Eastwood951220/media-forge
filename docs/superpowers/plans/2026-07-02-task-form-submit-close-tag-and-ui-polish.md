# Task Form Submit Close Tag And UI Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After successful crawler task create/edit, close the current task form TagsView tab, destroy its keepalive cache, and improve the new/edit task form into a denser, more polished operational UI.

**Architecture:** Add a small route-level hook that knows the current TanStack Router location, removes the matching TagsView entry, and destroys the matching `keepalive-for-react` cache key. Wire `TaskFormPage` to call that hook only after successful `createCrawlTask` or `updateCrawlTask`, then navigate back to the task list with `replace`. Polish the form page in-place using Ant Design controls, restrained layout, stable dimensions, and focused tests; `ui-ux-pro-max` is not available as a callable tool in this session, so its intent is captured as concrete UI constraints in this plan.

**Tech Stack:** React 19, TypeScript, TanStack Router, Zustand, keepalive-for-react, Ant Design 6, Less modules, Vitest, React Testing Library.

---

## Debugging Notes

- Current submit behavior in `frontend/src/pages/crawler/tasks/TaskFormPage.tsx` ends with `void navigate({ to: '/crawler/tasks' })`.
- Current TagsView close behavior already destroys route cache in `frontend/src/layout/TagsView/index.tsx` by calling `cacheControl.destroy(tag.fullPath)`.
- Current route cache key is `getFullPath(pathname, searchStr)` in `frontend/src/layout/routeCache.tsx`, so the task form cache keys are `/crawler/tasks/new` and `/crawler/tasks/{id}/edit`.
- There is no reusable non-UI API for "close current tag and destroy current cache" yet, so form submit cannot reuse the same logic without reaching into the store/cache directly.
- `ui-ux-pro-max` was requested by name but no callable skill/tool with that name is available through `tool_search`. The UI work should therefore follow the local frontend guidance: operational, dense, clear controls, no marketing hero, no decorative gradients/orbs, stable dimensions, and URL cards only for repeated URL entries.

## File Structure

- Modify: `frontend/src/layout/routeCache.tsx`
  - Export a testable `RouteCacheControlProvider` so route-cache consumers can be tested without a real keepalive instance.
- Create: `frontend/src/layout/useCloseCurrentRouteView.ts`
  - Encapsulate current-route tag removal and current-route cache destruction.
- Create: `frontend/tests/close-current-route-view.test.tsx`
  - Verify the hook removes `/crawler/tasks/new` and destroys the matching cache key.
- Modify: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
  - Call the close-current-route hook after successful create/edit.
  - Add task-form summary data and a more ergonomic form layout.
- Modify: `frontend/src/pages/crawler/tasks/TaskPages.module.less`
  - Replace the plain panel layout with a denser form shell, repeated URL cards, summary rail, and sticky action bar.
- Modify: `frontend/tests/task-form-restore.ui.test.tsx`
  - Verify successful create/edit closes the form tag and destroys cache.
- Create: `frontend/tests/task-form-ux.ui.test.tsx`
  - Verify key UI structure for the optimized task form page.

---

### Task 1: Add Testable Current Route Close Hook

**Files:**
- Modify: `frontend/src/layout/routeCache.tsx`
- Create: `frontend/src/layout/useCloseCurrentRouteView.ts`
- Create: `frontend/tests/close-current-route-view.test.tsx`

- [ ] **Step 1: Export a route cache control provider**

Modify `frontend/src/layout/routeCache.tsx` by adding this component after `useRouteCacheControl()`:

```tsx
export function RouteCacheControlProvider({
  children,
  value,
}: PropsWithChildren<{ value: RouteCacheControl }>) {
  return (
    <RouteCacheControlContext.Provider value={value}>
      {children}
    </RouteCacheControlContext.Provider>
  )
}
```

- [ ] **Step 2: Create the current-route close hook**

Create `frontend/src/layout/useCloseCurrentRouteView.ts`:

```tsx
import { useCallback, useMemo } from 'react'
import { useRouterState } from '@tanstack/react-router'
import { getFullPath, getRouteTagMeta } from '@/routes/tags'
import { useTagsViewStore } from '@/stores/useTagsViewStore'
import { useRouteCacheControl } from './routeCache'

export function useCloseCurrentRouteView() {
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const searchStr = useRouterState({ select: (state) => state.location.searchStr ?? '' })
  const fullPath = useMemo(() => getFullPath(pathname, searchStr), [pathname, searchStr])
  const routeMeta = useMemo(() => getRouteTagMeta(pathname), [pathname])
  const removeSelectedView = useTagsViewStore((state) => state.removeSelectedView)
  const cacheControl = useRouteCacheControl()

  return useCallback(async () => {
    removeSelectedView({
      path: pathname,
      fullPath,
      title: routeMeta.title,
      closable: pathname !== '/' && !routeMeta.affix,
      query: searchStr ? Object.fromEntries(new URLSearchParams(searchStr)) : undefined,
    })
    await cacheControl.destroy(fullPath)
  }, [cacheControl, fullPath, pathname, removeSelectedView, routeMeta, searchStr])
}
```

- [ ] **Step 3: Write the hook test**

Create `frontend/tests/close-current-route-view.test.tsx`:

```tsx
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RouteCacheControl } from '../src/layout/routeCache'
import { RouteCacheControlProvider } from '../src/layout/routeCache'
import { useCloseCurrentRouteView } from '../src/layout/useCloseCurrentRouteView'
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

function CloseButton() {
  const closeCurrentRouteView = useCloseCurrentRouteView()
  return (
    <button type="button" onClick={() => void closeCurrentRouteView()}>
      close-current
    </button>
  )
}

function renderHookRoute(cacheControl = createCacheControl()) {
  const rootRoute = createRootRoute({
    component: () => (
      <RouteCacheControlProvider value={cacheControl}>
        <CloseButton />
      </RouteCacheControlProvider>
    ),
  })
  const newTaskRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks/new',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([newTaskRoute]),
    history: createMemoryHistory({ initialEntries: ['/crawler/tasks/new'] }),
  })

  return {
    cacheControl,
    ...render(<RouterProvider router={router} />),
  }
}

describe('useCloseCurrentRouteView', () => {
  beforeEach(() => {
    useTagsViewStore.getState().resetViews()
    useTagsViewStore.getState().addVisitedView({
      path: '/crawler/tasks/new',
      fullPath: '/crawler/tasks/new',
      title: '新建任务',
      closable: true,
    })
  })

  it('removes current tag and destroys the current route cache', async () => {
    const { cacheControl } = renderHookRoute()

    await userEvent.click(await screen.findByRole('button', { name: 'close-current' }))

    expect(useTagsViewStore.getState().visitedViews.map((view) => view.fullPath)).toEqual(['/'])
    expect(cacheControl.destroy).toHaveBeenCalledWith('/crawler/tasks/new')
  })
})
```

- [ ] **Step 4: Run the hook test**

Run:

```bash
cd frontend && npm test -- close-current-route-view.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/layout/routeCache.tsx frontend/src/layout/useCloseCurrentRouteView.ts frontend/tests/close-current-route-view.test.tsx
git commit -m "feat: close current route tag with cache"
```

---

### Task 2: Close Task Form Tag And Cache After Successful Submit

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
- Modify: `frontend/tests/task-form-restore.ui.test.tsx`

- [ ] **Step 1: Update the task form test harness to accept route/cache state**

In `frontend/tests/task-form-restore.ui.test.tsx`, update imports:

```tsx
import type { RouteCacheControl } from '../src/layout/routeCache'
import { RouteCacheControlProvider } from '../src/layout/routeCache'
import { useTagsViewStore } from '../src/stores/useTagsViewStore'
```

Add this helper above `renderForm()`:

```tsx
function createCacheControl(): RouteCacheControl {
  return {
    destroy: vi.fn().mockResolvedValue(undefined),
    destroyMany: vi.fn().mockResolvedValue(undefined),
    destroyOther: vi.fn().mockResolvedValue(undefined),
    destroyAll: vi.fn().mockResolvedValue(undefined),
    refresh: vi.fn(),
  }
}
```

Replace `renderForm()` with:

```tsx
function renderForm({
  initialPath = '/crawler/tasks/new',
  cacheControl = createCacheControl(),
}: {
  initialPath?: string
  cacheControl?: RouteCacheControl
} = {}) {
  const rootRoute = createRootRoute({
    component: () => (
      <RouteCacheControlProvider value={cacheControl}>
        <AntApp>
          <TaskFormPage />
        </AntApp>
      </RouteCacheControlProvider>
    ),
  })
  const newTaskRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks/new',
    component: () => null,
  })
  const editTaskRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks/$id/edit',
    component: () => null,
  })
  const taskListRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([newTaskRoute, editTaskRoute, taskListRoute]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })
  return {
    cacheControl,
    router,
    ...render(<RouterProvider router={router} />),
  }
}
```

- [ ] **Step 2: Write create-submit tag/cache test**

Append this test inside `describe('TaskFormPage restored crawler task form', ...)`:

```tsx
  it('closes the new-task tag and destroys cache after successful create', async () => {
    useTagsViewStore.getState().resetViews()
    useTagsViewStore.getState().addVisitedView({
      path: '/crawler/tasks/new',
      fullPath: '/crawler/tasks/new',
      title: '新建任务',
      closable: true,
    })
    const { cacheControl } = renderForm()

    await userEvent.type(await screen.findByLabelText('任务名称'), '巨乳')
    await userEvent.type(screen.getByLabelText('URL'), 'https://javdb.com/actors/QV49G')

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '获取名称' })).not.toBeDisabled()
    })
    await userEvent.click(document.querySelector('button[type="submit"]')!)

    await waitFor(() => {
      expect(createCrawlTask).toHaveBeenCalled()
      expect(cacheControl.destroy).toHaveBeenCalledWith('/crawler/tasks/new')
      expect(useTagsViewStore.getState().visitedViews.some((view) => view.fullPath === '/crawler/tasks/new')).toBe(false)
    })
  })
```

- [ ] **Step 3: Write edit-submit tag/cache test**

Append this test in the same describe block:

```tsx
  it('closes the edit-task tag and destroys cache after successful update', async () => {
    useTagsViewStore.getState().resetViews()
    useTagsViewStore.getState().addVisitedView({
      path: '/crawler/tasks/abc/edit',
      fullPath: '/crawler/tasks/abc/edit',
      title: '编辑任务',
      closable: true,
    })
    vi.mocked(getCrawlTask).mockResolvedValue({
      id: 'abc',
      name: '巨乳',
      urls: [
        {
          url: 'https://javdb.com/actors/QV49G',
          url_type: 'actors',
          has_magnet: true,
          has_chinese_sub: false,
          sort_type: 0,
          url_name: '演员 QV49G',
        },
      ],
      is_skip: false,
      status: 'pending',
      task_id: null,
      error_message: null,
      total_found: 0,
      total_qualified: 0,
      owner_id: 'owner-id',
      created_at: '2026-07-02T00:00:00',
      updated_at: null,
    })
    const { cacheControl } = renderForm({ initialPath: '/crawler/tasks/abc/edit' })

    await screen.findByDisplayValue('巨乳')
    await userEvent.click(document.querySelector('button[type="submit"]')!)

    await waitFor(() => {
      expect(updateCrawlTask).toHaveBeenCalled()
      expect(cacheControl.destroy).toHaveBeenCalledWith('/crawler/tasks/abc/edit')
      expect(useTagsViewStore.getState().visitedViews.some((view) => view.fullPath === '/crawler/tasks/abc/edit')).toBe(false)
    })
  })
```

- [ ] **Step 4: Run tests to verify they fail before wiring submit**

Run:

```bash
cd frontend && npm test -- task-form-restore.ui.test.tsx
```

Expected before implementation: the new tests fail because `cacheControl.destroy()` is not called and the form tag remains in `useTagsViewStore`.

- [ ] **Step 5: Wire submit success to close current route view**

Modify imports in `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`:

```tsx
import { SaveOutlined, RollbackOutlined, MinusCircleOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { useCloseCurrentRouteView } from '@/layout/useCloseCurrentRouteView'
```

Inside `TaskFormPage`, after `const navigate = useNavigate()` add:

```tsx
  const closeCurrentRouteView = useCloseCurrentRouteView()
```

Replace the success navigation block in `handleSubmit()`:

```tsx
      if (isEdit && taskId) {
        await updateCrawlTask(taskId, payload)
        message.success('任务已更新')
      } else {
        await createCrawlTask(payload)
        message.success('任务已创建')
      }
      void navigate({ to: '/crawler/tasks' })
```

with:

```tsx
      if (isEdit && taskId) {
        await updateCrawlTask(taskId, payload)
        message.success('任务已更新')
      } else {
        await createCrawlTask(payload)
        message.success('任务已创建')
      }
      await closeCurrentRouteView()
      void navigate({ to: '/crawler/tasks', replace: true })
```

Update action buttons later in the file:

```tsx
            <Button type="primary" htmlType="submit" loading={submitting} icon={<SaveOutlined />}>
              {isEdit ? '更新' : '创建'}
            </Button>
            <Button icon={<RollbackOutlined />} onClick={() => navigate({ to: '/crawler/tasks' })}>
              取消
            </Button>
```

- [ ] **Step 6: Run submit close tests**

Run:

```bash
cd frontend && npm test -- task-form-restore.ui.test.tsx close-current-route-view.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/crawler/tasks/TaskFormPage.tsx frontend/tests/task-form-restore.ui.test.tsx
git commit -m "fix: close task form tag after submit"
```

---

### Task 3: Add UI Regression Tests For Optimized Task Form

**Files:**
- Create: `frontend/tests/task-form-ux.ui.test.tsx`

- [ ] **Step 1: Write UI structure test**

Create `frontend/tests/task-form-ux.ui.test.tsx`:

```tsx
import { App as AntApp } from 'antd'
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskFormPage from '../src/pages/crawler/tasks/TaskFormPage'
import { createCrawlTask, extractTaskName, getCrawlTask, updateCrawlTask } from '../src/api/crawlTask'
import type { RouteCacheControl } from '../src/layout/routeCache'
import { RouteCacheControlProvider } from '../src/layout/routeCache'

vi.mock('../src/api/crawlTask', () => ({
  createCrawlTask: vi.fn(),
  extractTaskName: vi.fn(),
  getCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

function cacheControl(): RouteCacheControl {
  return {
    destroy: vi.fn().mockResolvedValue(undefined),
    destroyMany: vi.fn().mockResolvedValue(undefined),
    destroyOther: vi.fn().mockResolvedValue(undefined),
    destroyAll: vi.fn().mockResolvedValue(undefined),
    refresh: vi.fn(),
  }
}

function renderForm() {
  const rootRoute = createRootRoute({
    component: () => (
      <RouteCacheControlProvider value={cacheControl()}>
        <AntApp>
          <TaskFormPage />
        </AntApp>
      </RouteCacheControlProvider>
    ),
  })
  const formRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks/new',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([formRoute]),
    history: createMemoryHistory({ initialEntries: ['/crawler/tasks/new'] }),
  })
  return render(<RouterProvider router={router} />)
}

describe('TaskFormPage optimized UI', () => {
  beforeEach(() => {
    vi.mocked(createCrawlTask).mockResolvedValue({} as never)
    vi.mocked(updateCrawlTask).mockResolvedValue({} as never)
    vi.mocked(getCrawlTask).mockResolvedValue({} as never)
    vi.mocked(extractTaskName).mockResolvedValue({ name: '演员 A' })
  })

  it('renders a dense task form shell with summary and sticky actions', async () => {
    renderForm()

    expect(await screen.findByRole('heading', { name: '新建任务' })).toBeInTheDocument()
    expect(screen.getByText('来源配置')).toBeInTheDocument()
    expect(screen.getByText('提交状态')).toBeInTheDocument()
    expect(screen.getByText('URL 数')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /创建/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /取消/ })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify current UI gap**

Run:

```bash
cd frontend && npm test -- task-form-ux.ui.test.tsx
```

Expected before implementation: FAIL because the page does not render `来源配置`, `提交状态`, or `URL 数`.

- [ ] **Step 3: Commit failing UI test**

```bash
git add frontend/tests/task-form-ux.ui.test.tsx
git commit -m "test: cover optimized task form layout"
```

---

### Task 4: Polish Task Form Page UI

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
- Modify: `frontend/src/pages/crawler/tasks/TaskPages.module.less`

- [ ] **Step 1: Add summary state and icon imports**

Modify the icon import in `TaskFormPage.tsx`:

```tsx
import {
  CheckCircleOutlined,
  DatabaseOutlined,
  LinkOutlined,
  MinusCircleOutlined,
  PlusOutlined,
  RollbackOutlined,
  SaveOutlined,
  SearchOutlined,
} from '@ant-design/icons'
```

Inside `TaskFormPage`, after `const title = useMemo(...)`, add:

```tsx
  const watchedUrls = Form.useWatch('urls', form) ?? []
  const configuredUrlCount = watchedUrls.filter((entry) => entry?.url).length
  const detectedTypeCount = watchedUrls.filter((entry) => entry?.url_type).length
  const submitLabel = isEdit ? '更新' : '创建'
```

- [ ] **Step 2: Replace the header and form shell JSX**

In `TaskFormPage.tsx`, replace the current return body from `<div className={styles.page}>` through the closing `</section>` with this structure:

```tsx
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{title}</h1>
          <div className={styles.headerMeta}>
            <span>{isEdit ? '编辑模式' : '新建模式'}</span>
            <span>JavDB</span>
          </div>
        </div>
      </div>

      <div className={styles.formShell}>
        <main className={styles.mainColumn}>
          <section className={styles.formBand} aria-label="基础信息">
            <div className={styles.sectionTitle}>
              <DatabaseOutlined />
              <span>基础信息</span>
            </div>
            <Form<CrawlTaskCreateParams>
              form={form}
              layout="vertical"
              disabled={loading}
              onFinish={(values) => void handleSubmit(values)}
              initialValues={{
                urls: [{ has_magnet: true, has_chinese_sub: false, sort_type: 0 }],
                is_skip: false,
              }}
            >
              <Row gutter={16}>
                <Col xs={24} md={18}>
                  <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称' }]}>
                    <Input placeholder="例如：某演员名称" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={6}>
                  <Form.Item name="is_skip" label="启用状态" valuePropName="checked">
                    <Switch checkedChildren="禁用" unCheckedChildren="启用" />
                  </Form.Item>
                </Col>
              </Row>

              <div className={styles.sectionTitle}>
                <LinkOutlined />
                <span>来源配置</span>
              </div>

              <Form.List name="urls">
                {(fields, { add, remove }) => (
                  <div className={styles.urlGrid}>
                    {fields.map((field) => (
                      <div key={field.key} className={styles.urlGridItem}>
                        <UrlEntryCard
                          index={field.name}
                          remove={fields.length > 1 ? () => remove(field.name) : undefined}
                          onNameExtracted={(index, name) => {
                            setUrlEntryValue(index, { url_name: name })
                            if (!form.getFieldValue('name')) form.setFieldsValue({ name })
                          }}
                          onUrlTypeDetected={(index, urlType) => setUrlEntryValue(index, { url_type: urlType })}
                        />
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() => add({ has_magnet: true, has_chinese_sub: false, sort_type: 0 })}
                      className={styles.addUrlTile}
                    >
                      <PlusOutlined />
                      <span>添加 URL</span>
                    </button>
                  </div>
                )}
              </Form.List>

              <div className={styles.actions}>
                <Button type="primary" htmlType="submit" loading={submitting} icon={<SaveOutlined />}>
                  {submitLabel}
                </Button>
                <Button icon={<RollbackOutlined />} onClick={() => navigate({ to: '/crawler/tasks' })}>
                  取消
                </Button>
              </div>
            </Form>
          </section>
        </main>

        <aside className={styles.summaryRail} aria-label="提交状态">
          <div className={styles.summaryTitle}>
            <CheckCircleOutlined />
            <span>提交状态</span>
          </div>
          <div className={styles.summaryMetric}>
            <span>URL 数</span>
            <strong>{configuredUrlCount}</strong>
          </div>
          <div className={styles.summaryMetric}>
            <span>已识别</span>
            <strong>{detectedTypeCount}</strong>
          </div>
          <div className={styles.summaryStatus}>
            {submitting ? '提交中' : loading ? '加载中' : '就绪'}
          </div>
        </aside>
      </div>
    </div>
```

- [ ] **Step 3: Replace task page styles**

Replace the contents of `frontend/src/pages/crawler/tasks/TaskPages.module.less` with:

```less
.page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
}

.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.title {
  margin: 0;
  color: #111827;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.25;
}

.headerMeta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  color: #475569;
  font-size: 13px;
}

.headerMeta span {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border: 1px solid rgba(148, 163, 184, 0.32);
  border-radius: 6px;
  background: #f8fafc;
}

.formShell {
  display: grid;
  align-items: start;
  grid-template-columns: minmax(0, 1fr) 260px;
  gap: 20px;
}

.mainColumn {
  min-width: 0;
}

.formBand {
  min-width: 0;
}

.sectionTitle {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 14px;
  color: #0f172a;
  font-size: 15px;
  font-weight: 650;
}

.urlGrid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
}

.urlGridItem {
  min-width: 0;
}

.urlCard {
  height: 100%;
  border-radius: 8px;
}

.urlCard :global(.ant-card-head) {
  min-height: 42px;
  border-bottom-color: rgba(148, 163, 184, 0.22);
}

.urlCard :global(.ant-card-body) {
  display: flex;
  flex-direction: column;
  min-height: 360px;
  padding: 14px;
}

.addUrlTile {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 8px;
  min-height: 180px;
  border: 1px dashed rgba(71, 85, 105, 0.42);
  border-radius: 8px;
  background: #f8fafc;
  color: #334155;
  cursor: pointer;
  font: inherit;
  transition: border-color 0.16s ease, background 0.16s ease;
}

.addUrlTile:hover {
  border-color: #1677ff;
  background: #f0f7ff;
}

.summaryRail {
  position: sticky;
  top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  padding-left: 18px;
  border-left: 1px solid rgba(148, 163, 184, 0.32);
}

.summaryTitle {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #0f172a;
  font-weight: 650;
}

.summaryMetric {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 34px;
  color: #475569;
  font-size: 13px;
}

.summaryMetric strong {
  color: #0f172a;
  font-size: 18px;
}

.summaryStatus {
  min-height: 32px;
  padding: 7px 10px;
  border-radius: 6px;
  background: #ecfdf5;
  color: #047857;
  font-size: 13px;
  font-weight: 600;
}

.actions {
  position: sticky;
  bottom: 0;
  z-index: 2;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 22px;
  padding: 12px 0 0;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0), #fff 28%);
}

@media (max-width: 1024px) {
  .formShell {
    grid-template-columns: 1fr;
  }

  .summaryRail {
    position: static;
    padding-left: 0;
    border-left: 0;
    border-top: 1px solid rgba(148, 163, 184, 0.32);
    padding-top: 14px;
  }
}

@media (max-width: 640px) {
  .header {
    align-items: stretch;
    flex-direction: column;
  }

  .urlGrid {
    grid-template-columns: 1fr;
  }

  .actions {
    align-items: stretch;
    flex-direction: column;
  }
}
```

- [ ] **Step 4: Run UI tests**

Run:

```bash
cd frontend && npm test -- task-form-ux.ui.test.tsx task-form-restore.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/crawler/tasks/TaskFormPage.tsx frontend/src/pages/crawler/tasks/TaskPages.module.less
git commit -m "style: polish crawler task form"
```

---

### Task 5: Verify Integration

**Files:**
- No additional files.

- [ ] **Step 1: Run focused frontend tests**

Run:

```bash
cd frontend && npm test -- \
  close-current-route-view.test.tsx \
  task-form-restore.ui.test.tsx \
  task-form-ux.ui.test.tsx \
  tags-view.ui.test.tsx \
  route-keepalive.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS with no TypeScript errors.

- [ ] **Step 3: Start the frontend for visual verification**

Run:

```bash
cd frontend && npm run dev
```

Expected: Vite starts and prints a local URL such as `http://localhost:5173/`.

- [ ] **Step 4: Manually verify submit cleanup**

Open the app and perform both flows:

1. Navigate to `/crawler/tasks/new`, create a task successfully.
2. Confirm the `新建任务` tag is gone and returning to `/crawler/tasks/new` shows a fresh form.
3. Navigate to `/crawler/tasks/{id}/edit`, update successfully.
4. Confirm the `编辑任务` tag is gone and returning to the same edit URL reloads fresh detail data.

Expected: task-list tag remains available, current form tag closes, and stale form state does not reappear.

- [ ] **Step 5: Manually verify responsive UI**

Check the task form at desktop and mobile widths:

- Desktop: two-column URL grid when width allows, summary rail on the right, sticky action bar at bottom.
- Mobile: single-column URL list, summary rail below form, action buttons stacked without text overflow.

Expected: no overlapping text, no layout jump when URL type/name appears, and action buttons remain reachable.

---

## Self-Review

- Spec coverage:
  - Successful create and edit close current TagsView tab through `useCloseCurrentRouteView()`.
  - Matching keepalive cache is destroyed with the same full-path key used by `RouteKeepAliveOutlet`.
  - New/edit task page UI is optimized with a denser operational layout, summary rail, stable URL cards, and sticky actions.
  - `ui-ux-pro-max` is unavailable as a callable capability, so the plan applies its requested intent through explicit UI constraints and tests.
- Placeholder scan:
  - No `TBD`, vague validation steps, or "similar to" tasks remain.
  - Every code-changing step includes concrete code.
- Type consistency:
  - Hook name is consistently `useCloseCurrentRouteView`.
  - Provider name is consistently `RouteCacheControlProvider`.
  - Cache key remains `getFullPath(pathname, searchStr)` and matches existing TagsView/keepalive behavior.
