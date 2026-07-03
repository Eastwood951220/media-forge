# Layout Header Current Page Title Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the layout header hardcoded title/subtitle block with the current page name only.

**Architecture:** The header will read the active TanStack Router pathname and reuse `getRouteTagMeta(pathname).title`, which is already the central source for page titles used by tagsView. The `titleBlock` keeps the same structural role in the header but renders a single title line and no subtitle DOM. Header styles are simplified to a single-line title layout.

**Tech Stack:** React 19, TypeScript 6, TanStack Router 1.x, Ant Design 6, Less CSS modules, Vitest 3, React Testing Library.

---

## File Structure

- Modify `frontend/src/layout/Header/index.tsx`: derive the current page title from router state and remove the subtitle element.
- Modify `frontend/src/layout/Header/Header.module.less`: remove subtitle styling and make `titleBlock` a single-line title container.
- Modify `frontend/tests/layout.ui.test.tsx`: assert the header shows the current page name and no longer renders the old subtitle.

---

### Task 1: Header Page Title Behavior

**Files:**
- Modify: `frontend/src/layout/Header/index.tsx`
- Modify: `frontend/src/layout/Header/Header.module.less`
- Modify: `frontend/tests/layout.ui.test.tsx`

- [ ] **Step 1: Write the failing layout header tests**

Modify the import from React Testing Library in `frontend/tests/layout.ui.test.tsx`:

```ts
import { act, render, screen, within } from '@testing-library/react'
```

Modify `renderLayout()` so the test router contains both task list and crawler config routes:

```tsx
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
  const crawlerConfigRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/config',
    component: () => <div>console outlet</div>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute, crawlerTasksRoute, crawlerConfigRoute]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })

  return render(<RouterProvider router={router} />)
}
```

Replace the existing assertion for `Operations Console` in `renders console shell landmarks, crawler navigation, and tags view` with header-scoped assertions:

```tsx
    const header = await screen.findByRole('banner')
    expect(within(header).getByText('任务列表')).toBeInTheDocument()
    expect(within(header).queryByText('Operations Console')).not.toBeInTheDocument()
    expect(within(header).queryByText('Media pipeline health')).not.toBeInTheDocument()
```

Add this test to the `modern console layout` describe block:

```tsx
  it('updates the header title from the active route name', async () => {
    renderLayout('/crawler/config')

    const header = await screen.findByRole('banner')
    expect(within(header).getByText('爬虫配置')).toBeInTheDocument()
    expect(within(header).queryByText('Operations Console')).not.toBeInTheDocument()
    expect(within(header).queryByText('Media pipeline health')).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run the layout test and verify it fails**

Run:

```bash
cd frontend
npm test -- layout.ui.test.tsx
```

Expected: FAIL because the header still renders `Operations Console` and `Media pipeline health`.

- [ ] **Step 3: Implement current page title in the header**

Modify `frontend/src/layout/Header/index.tsx`.

Change the TanStack Router import:

```ts
import { useNavigate, useRouterState } from '@tanstack/react-router'
```

Add the route title helper import:

```ts
import { getRouteTagMeta } from '@/routes/tags'
```

Inside `LayoutHeader`, after `const navigate = useNavigate()`, add:

```ts
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const pageTitle = getRouteTagMeta(pathname).title
```

Replace the `titleBlock` JSX:

```tsx
        <div className={styles.titleBlock}>
          <span className={styles.title}>{pageTitle}</span>
        </div>
```

The complete top part of the component should now look like:

```tsx
export function LayoutHeader({ darkMode, collapsed, onCollapse }: LayoutHeaderProps) {
  const navigate = useNavigate()
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const pageTitle = getRouteTagMeta(pathname).title
  const userInfo = useAuthStore((state) => state.userInfo)
  const logout = useAuthStore((state) => state.logout)
  const displayName = userInfo?.displayName || userInfo?.username || 'Admin'
```

- [ ] **Step 4: Simplify header titleBlock styles**

Modify `frontend/src/layout/Header/Header.module.less`.

Replace `.titleBlock`:

```less
.titleBlock {
  display: flex;
  align-items: center;
  min-width: 0;
}
```

Replace `.title`:

```less
.title {
  max-width: min(42vw, 360px);
  overflow: hidden;
  color: #0f172a;
  font-size: 16px;
  font-weight: 700;
  line-height: 22px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

Delete the entire `.subtitle` block:

```less
.subtitle {
  color: #64748b;
  font-size: 12px;
  line-height: 16px;
}
```

Delete the nested dark subtitle block:

```less
  .subtitle {
    color: #94a3b8;
  }
```

- [ ] **Step 5: Run the layout test and verify it passes**

Run:

```bash
cd frontend
npm test -- layout.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/layout/Header/index.tsx frontend/src/layout/Header/Header.module.less frontend/tests/layout.ui.test.tsx
git commit -m "fix: show current page title in layout header"
```

---

### Task 2: Full Frontend Verification

**Files:**
- No source changes.

- [ ] **Step 1: Run focused layout test**

Run:

```bash
cd frontend
npm test -- layout.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 3: Manual UI verification**

Run:

```bash
cd frontend
npm run dev
```

Open these routes:

```text
/crawler/tasks
/crawler/config
/crawler/runs
/content/movies
```

Expected:

- Header title shows `任务列表` on `/crawler/tasks`.
- Header title shows `爬虫配置` on `/crawler/config`.
- Header title shows `运行记录` on `/crawler/runs`.
- Header title shows `影片列表` on `/content/movies`.
- Header no longer displays `Operations Console`.
- Header no longer displays `Media pipeline health`.
- Long page titles stay on one line and truncate with ellipsis instead of pushing the user controls.

---

## Self-Review

- Spec coverage:
  - `layout header中的titleBlock，改为当前页面名称` is covered by Task 1 using `getRouteTagMeta(pathname).title`.
  - `去除subtitle部分` is covered by Task 1 JSX removal, style cleanup, and tests asserting the old subtitle is absent.
- Red-flag scan:
  - The plan includes exact file paths, commands, expected results, and source/test snippets.
- Type consistency:
  - `getRouteTagMeta(pathname).title` already returns `string`, so `pageTitle` can render directly inside the existing `styles.title` span.
  - The route title source is shared with tagsView, so current page naming remains consistent across header and tabs.
