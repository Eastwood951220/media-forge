# Match Ruoyi Layout Desktop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current mixed layout with a ruoyi-react-style desktop layout so the top header follows light/dark theme changes and no mobile-specific layout adaptation remains.

**Architecture:** Keep the route integration unchanged: `frontend/src/routes/index.tsx` imports the authenticated layout from `@/layout`. Rebuild `frontend/src/layout` to match `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/layout`: `SideMenu` beside a main `Layout`, then `LayoutHeader`, `TagsView`, and scrollable `Content`. Use a small static menu/tag model for the current dashboard route because this project does not yet have ruoyi-react's permission route store.

**Tech Stack:** React 19, TypeScript 6, TanStack Router 1.x, Ant Design 6 `Layout/Menu/Button/Space`, Zustand 5, Less modules, Vitest + React Testing Library

---

## Current Code Findings

- `frontend/src/layout/index.tsx` still uses `useBreakpoint`, `useAppStore`, `useSettingsStore`, `Sidebar`, `Navbar`, `TabsView`, and `AppMain`.
- `frontend/src/layout/components/Navbar/index.tsx` does not read `useThemeStore.darkMode`, so the top header stays light.
- `frontend/src/layout/components/Sidebar/index.tsx` switches between `DesktopSidebar` and `MobileDrawer`, which the new requirement explicitly removes.
- `frontend/src/layout/components/TabsView/index.tsx`, `frontend/src/layout/components/AppMain/index.tsx`, and `frontend/src/layout/components/AppMain/PullToRefresh.tsx` contain mobile-specific behavior and padding logic.
- `frontend/src/layout/components/Settings/index.tsx` and `index.module.less` are already deleted in the current worktree; the new plan keeps them deleted.
- `ruoyi-react` layout uses direct files: `AppLayout.tsx`, `Header/`, `Sidebar/`, `TagsView/`, and an `AppLayout.module.less` with full-height overflow control.

## File Structure

- Modify `frontend/src/layout/index.tsx`
  - Make it the ruoyi-style `AppLayout` default export using `SideMenu`, `LayoutHeader`, `TagsView`, and `Content`.
- Replace `frontend/src/layout/index.module.less`
  - Use ruoyi-style full-height layout styles and dark background class.
- Create `frontend/src/layout/Header/index.tsx`
  - Ruoyi-style header with collapse toggle, `ThemeModeToggle`, user avatar/name, and logout.
- Create `frontend/src/layout/Header/Header.module.less`
  - Ruoyi-style header styles including the dark class that fixes the top header color.
- Create `frontend/src/layout/Sidebar/index.tsx`
  - Ruoyi-style `Sider` and `Menu`, no mobile drawer branch.
- Create `frontend/src/layout/Sidebar/Sidebar.module.less`
  - Ruoyi-style sider, logo, menu, collapsed, and dark styles.
- Create `frontend/src/layout/TagsView/index.tsx`
  - Ruoyi-style tags row for the dashboard route, no swipe or mobile hiding.
- Create `frontend/src/layout/TagsView/TagsView.module.less`
  - Ruoyi-style tag row with dark styles.
- Delete old layout files:
  - `frontend/src/layout/components/Navbar/Breadcrumb.tsx`
  - `frontend/src/layout/components/Navbar/Hamburger.tsx`
  - `frontend/src/layout/components/Navbar/index.tsx`
  - `frontend/src/layout/components/Navbar/index.module.less`
  - `frontend/src/layout/components/Sidebar/DesktopSidebar.tsx`
  - `frontend/src/layout/components/Sidebar/MobileDrawer.tsx`
  - `frontend/src/layout/components/Sidebar/SidebarLogo.tsx`
  - `frontend/src/layout/components/Sidebar/index.tsx`
  - `frontend/src/layout/components/Sidebar/index.module.less`
  - `frontend/src/layout/components/TabsView/index.tsx`
  - `frontend/src/layout/components/TabsView/index.module.less`
  - `frontend/src/layout/components/TabsView/useSwipeTabs.ts`
  - `frontend/src/layout/components/AppMain/PullToRefresh.tsx`
  - `frontend/src/layout/components/AppMain/index.tsx`
  - `frontend/src/layout/components/AppMain/index.module.less`
  - `frontend/src/layout/components/Settings/index.tsx`
  - `frontend/src/layout/components/Settings/index.module.less`
- Delete unused mobile/settings state:
  - `frontend/src/hooks/useBreakpoint.ts`
  - `frontend/src/stores/useAppStore.ts`
  - `frontend/src/stores/useSettingsStore.ts`
- Add tests:
  - `frontend/tests/layout.ruoyi.test.tsx`
  - Update `frontend/tests/App.test.tsx`

## Constraints

- Do not reintroduce a settings component or settings drawer.
- Do not keep mobile-specific layout switching, mobile drawer, swipe tabs, pull-to-refresh, or breakpoint-driven layout behavior.
- Keep `/login` and `/init` outside authenticated layout.
- Keep `ThemeModeToggle` in the top header.
- Keep the current `@/layout` import in `frontend/src/routes/index.tsx`.
- The top header must have a dark background when `useThemeStore.darkMode === true`.

---

### Task 1: Add Tests For Ruoyi-Style Layout And Dark Header

**Files:**
- Create: `frontend/tests/layout.ruoyi.test.tsx`
- Modify: `frontend/tests/App.test.tsx`

- [ ] **Step 1: Write the failing ruoyi layout test**

Create `frontend/tests/layout.ruoyi.test.tsx`:

```typescript
import { act, render, screen } from '@testing-library/react'
import { createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { createMemoryHistory } from '@tanstack/react-router'
import { beforeEach, describe, expect, it } from 'vitest'
import AppLayout from '../src/layout'
import headerStyles from '../src/layout/Header/Header.module.less'
import { useAuthStore } from '../src/stores/useAuthStore'
import { useThemeStore } from '../src/stores/useThemeStore'

function renderLayout() {
  const rootRoute = createRootRoute({ component: AppLayout })
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => <div>dashboard outlet</div>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })

  return render(<RouterProvider router={router} />)
}

describe('ruoyi-style AppLayout', () => {
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
  })

  it('renders ruoyi-style layout regions without mobile drawer or settings controls', async () => {
    renderLayout()

    expect(await screen.findByText('Media Forge')).toBeInTheDocument()
    expect(screen.getByRole('menu')).toBeInTheDocument()
    expect(screen.getByText('仪表盘')).toBeInTheDocument()
    expect(screen.getByText('dashboard outlet')).toBeInTheDocument()
    expect(screen.queryByLabelText('Open settings')).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('applies the header dark class when dark mode is active', async () => {
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
```

- [ ] **Step 2: Update the app routing test to assert ruoyi layout chrome**

Replace `frontend/tests/App.test.tsx` with:

```typescript
// @ts-nocheck — test file, router types are complex; functionality is what matters
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { createMemoryHistory } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { router as baseRouter } from '../src/routes'
import { queryClient } from '../src/lib/query-client'
import { useAuthStore } from '../src/stores/useAuthStore'
import { useThemeStore } from '../src/stores/useThemeStore'

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
    useAuthStore.setState({
      token: '',
      isAuthenticated: false,
      userInfo: null,
    })
    useThemeStore.setState({
      mode: 'light',
      darkMode: false,
      primaryColor: '#006AFF',
    })
  })

  it('redirects unauthenticated user to login page', async () => {
    renderApp('/')

    await waitFor(() => {
      expect(screen.getByText(/欢迎回来/i)).toBeInTheDocument()
      expect(screen.getByText(/请登录您的账户以继续/i)).toBeInTheDocument()
    })

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('shows dashboard inside ruoyi-style layout for authenticated user', async () => {
    useAuthStore.setState({
      token: 'test-token',
      isAuthenticated: true,
      userInfo: {
        username: 'admin',
        displayName: 'Admin',
      },
    })

    renderApp('/')

    await waitFor(() => {
      expect(screen.getByRole('banner')).toBeInTheDocument()
      expect(screen.getByRole('menu')).toBeInTheDocument()
      expect(screen.getAllByText('Media Forge').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('仪表盘').length).toBeGreaterThanOrEqual(2)
      expect(screen.getByText(/welcome to media forge dashboard/i)).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 3: Run the tests and verify they fail against the current layout**

Run:

```bash
cd frontend && npm test -- layout.ruoyi.test.tsx App.test.tsx
```

Expected: FAIL because `frontend/src/layout/Header/Header.module.less` does not exist and the current layout still uses `Navbar`, mobile branches, and old tabs.

- [ ] **Step 4: Commit the failing tests**

```bash
git add frontend/tests/layout.ruoyi.test.tsx frontend/tests/App.test.tsx
git commit -m "test(frontend): cover ruoyi style layout shell"
```

---

### Task 2: Replace AppLayout With Ruoyi-Style Composition

**Files:**
- Modify: `frontend/src/layout/index.tsx`
- Modify: `frontend/src/layout/index.module.less`

- [ ] **Step 1: Replace the layout component**

Replace `frontend/src/layout/index.tsx` with:

```typescript
import { useState } from 'react'
import { Outlet } from '@tanstack/react-router'
import { Layout } from 'antd'
import { useThemeStore } from '@/stores/useThemeStore'
import { LayoutHeader } from './Header'
import { SideMenu } from './Sidebar'
import { TagsView } from './TagsView'
import styles from './index.module.less'

const { Content } = Layout

export default function AppLayout() {
  const darkMode = useThemeStore((state) => state.darkMode)
  const [collapsed, setCollapsed] = useState(false)

  return (
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
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}
```

- [ ] **Step 2: Replace layout styles**

Replace `frontend/src/layout/index.module.less` with:

```less
.layout {
  height: 100vh;
  max-height: 100vh;
  min-height: 0;
  overflow: hidden;
  background: #f5f7fb;
}

.main {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.content {
  flex: 1 1 0;
  min-height: 0;
  padding: 16px;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.pageContainer {
  min-width: 0;
  flex: 1;
}

.dark {
  background: #0f172a;
}
```

- [ ] **Step 3: Run TypeScript and verify expected missing component errors**

Run:

```bash
cd frontend && npm run build
```

Expected: FAIL with missing module errors for `./Header`, `./Sidebar`, and `./TagsView`. If it fails for any unrelated file, stop and inspect that failure before continuing.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/layout/index.tsx frontend/src/layout/index.module.less
git commit -m "refactor(frontend): switch layout shell to ruoyi structure"
```

---

### Task 3: Add Ruoyi-Style Header

**Files:**
- Create: `frontend/src/layout/Header/index.tsx`
- Create: `frontend/src/layout/Header/Header.module.less`

- [ ] **Step 1: Create the header component**

Create `frontend/src/layout/Header/index.tsx`:

```typescript
import { useNavigate } from '@tanstack/react-router'
import { LogoutOutlined, MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons'
import { Button, Layout, Space } from 'antd'
import { ThemeModeToggle } from '@/components/ThemeModeToggle'
import { useAuthStore } from '@/stores/useAuthStore'
import styles from './Header.module.less'

const { Header } = Layout

type LayoutHeaderProps = {
  darkMode?: boolean
  collapsed?: boolean
  onCollapse?: (collapsed: boolean) => void
}

export function LayoutHeader({ darkMode, collapsed, onCollapse }: LayoutHeaderProps) {
  const navigate = useNavigate()
  const userInfo = useAuthStore((state) => state.userInfo)
  const logout = useAuthStore((state) => state.logout)
  const displayName = userInfo?.displayName || userInfo?.username || 'Admin'

  const handleLogout = () => {
    logout()
    void navigate({ to: '/login', replace: true })
  }

  return (
    <Header className={darkMode ? `${styles.header} ${styles.dark}` : styles.header}>
      <div className={styles.left}>
        <button
          type="button"
          className={styles.collapseBtn}
          aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
          onClick={() => onCollapse?.(!collapsed)}
        >
          {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </button>
      </div>

      <Space size={12} className={styles.right}>
        <ThemeModeToggle size="middle" variant="header" />
        <div className={styles.user}>
          <span className={styles.avatar}>
            {displayName.slice(0, 1).toUpperCase()}
          </span>
          <span className={styles.userName}>{displayName}</span>
        </div>
        <Button
          aria-label="退出登录"
          title="退出登录"
          shape="circle"
          icon={<LogoutOutlined />}
          onClick={handleLogout}
        />
      </Space>
    </Header>
  )
}
```

- [ ] **Step 2: Create the header styles**

Create `frontend/src/layout/Header/Header.module.less`:

```less
.header {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #ffffff;
}

.left {
  display: flex;
  align-items: center;
}

.collapseBtn {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #334155;
  font-size: 18px;
  cursor: pointer;
}

.collapseBtn:hover {
  background: rgba(15, 23, 42, 0.06);
}

.right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: #334155;
}

.avatar {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #dbeafe;
  color: #1d4ed8;
  font-size: 14px;
  font-weight: 700;
  line-height: 32px;
}

.userName {
  max-width: 128px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dark {
  background: #111827;
  color: #cbd5e1;

  .collapseBtn {
    color: #cbd5e1;
  }

  .collapseBtn:hover {
    background: rgba(255, 255, 255, 0.08);
  }

  .user {
    color: #e5e7eb;
  }

  .avatar {
    background: #134e4a;
    color: #ccfbf1;
  }
}
```

- [ ] **Step 3: Run the ruoyi layout test and verify Header import is resolved**

Run:

```bash
cd frontend && npm test -- layout.ruoyi.test.tsx
```

Expected: FAIL because `./Sidebar` and `./TagsView` are still missing, but there is no missing `./Header` error.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/layout/Header/index.tsx frontend/src/layout/Header/Header.module.less
git commit -m "feat(frontend): add ruoyi style layout header"
```

---

### Task 4: Add Ruoyi-Style Sidebar Without Mobile Drawer

**Files:**
- Create: `frontend/src/layout/Sidebar/index.tsx`
- Create: `frontend/src/layout/Sidebar/Sidebar.module.less`

- [ ] **Step 1: Create the sidebar component**

Create `frontend/src/layout/Sidebar/index.tsx`:

```typescript
import { useMemo } from 'react'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import { DashboardOutlined } from '@ant-design/icons'
import { Layout, Menu } from 'antd'
import type { MenuProps } from 'antd'
import { useThemeStore } from '@/stores/useThemeStore'
import styles from './Sidebar.module.less'

const { Sider } = Layout

const menuItems: MenuProps['items'] = [
  {
    key: '/',
    icon: <DashboardOutlined />,
    label: '仪表盘',
  },
]

type SideMenuProps = {
  collapsed: boolean
}

export function SideMenu({ collapsed }: SideMenuProps) {
  const navigate = useNavigate()
  const darkMode = useThemeStore((state) => state.darkMode)
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const selectedKeys = useMemo(() => [pathname === '/' ? '/' : pathname], [pathname])

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    const nextPath = String(key)
    if (nextPath !== pathname) {
      void navigate({ to: nextPath })
    }
  }

  return (
    <Sider
      collapsed={collapsed}
      width={232}
      collapsedWidth={80}
      collapsible={false}
      className={[
        styles.sider,
        darkMode ? styles.dark : '',
        collapsed ? styles.collapsed : '',
      ].filter(Boolean).join(' ')}
    >
      <div className={styles.logo}>
        <span className={styles.logoMark}>MF</span>
        {!collapsed && <span className={styles.logoText}>Media Forge</span>}
      </div>

      <div className={styles.menuWrapper}>
        <Menu
          className={styles.menu}
          mode="inline"
          theme={darkMode ? 'dark' : 'light'}
          inlineCollapsed={collapsed}
          selectedKeys={selectedKeys}
          items={menuItems}
          onClick={handleMenuClick}
        />
      </div>
    </Sider>
  )
}
```

- [ ] **Step 2: Create the sidebar styles**

Create `frontend/src/layout/Sidebar/Sidebar.module.less`:

```less
.sider {
  min-width: 0;
  overflow: hidden;
  background: #ffffff;

  :global(.ant-layout-sider-children) {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-width: 0;
    overflow: hidden;
  }

  :global(.ant-menu) {
    width: 100%;
    min-width: 0;
    border-inline-end: 0;
  }

  :global(.ant-menu-inline),
  :global(.ant-menu-vertical) {
    border-inline-end: 0;
  }

  :global(.ant-menu-item),
  :global(.ant-menu-submenu-title) {
    width: calc(100% - 8px);
    margin-inline: 4px;
  }
}

.collapsed {
  :global(.ant-menu-item),
  :global(.ant-menu-submenu-title) {
    width: calc(100% - 8px);
    margin-inline: 4px;
  }
}

.logo {
  height: 64px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  flex: 0 0 auto;
}

.logoMark {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 8px;
  background: var(--app-primary-color, #1677ff);
  color: #ffffff;
  font-size: 14px;
  font-weight: 700;
}

.logoText {
  overflow: hidden;
  color: #0f172a;
  font-size: 15px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menuWrapper {
  flex: 1 1 auto;
  width: 100%;
  min-width: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.menu {
  width: 100%;
  min-width: 0;
}

.dark {
  &.sider {
    background: #111827;
  }

  .logoText {
    color: #e5e7eb;
  }
}
```

- [ ] **Step 3: Run the ruoyi layout test and verify Sidebar import is resolved**

Run:

```bash
cd frontend && npm test -- layout.ruoyi.test.tsx
```

Expected: FAIL because `./TagsView` is still missing, but there is no missing `./Sidebar` error.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/layout/Sidebar/index.tsx frontend/src/layout/Sidebar/Sidebar.module.less
git commit -m "feat(frontend): add ruoyi style desktop sidebar"
```

---

### Task 5: Add Ruoyi-Style TagsView Without Mobile Hiding

**Files:**
- Create: `frontend/src/layout/TagsView/index.tsx`
- Create: `frontend/src/layout/TagsView/TagsView.module.less`

- [ ] **Step 1: Create the TagsView component**

Create `frontend/src/layout/TagsView/index.tsx`:

```typescript
import { useRouterState } from '@tanstack/react-router'
import styles from './TagsView.module.less'

type TagsViewProps = {
  darkMode?: boolean
}

export function TagsView({ darkMode }: TagsViewProps) {
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const isDashboard = pathname === '/'

  return (
    <div className={darkMode ? `${styles.tagsView} ${styles.dark}` : styles.tagsView}>
      <div className={styles.scrollContent}>
        <div className={styles.tagsInner}>
          <span className={`${styles.tag} ${isDashboard ? styles.active : ''} ${styles.affix}`}>
            {isDashboard ? <span className={styles.dot} /> : null}
            <span className={styles.tagTitle}>仪表盘</span>
          </span>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create the TagsView styles**

Create `frontend/src/layout/TagsView/TagsView.module.less`:

```less
.tagsView {
  height: 34px;
  display: flex;
  align-items: center;
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
  overflow: hidden;
}

.scrollContent {
  height: 100%;
  padding: 0 8px;
  overflow-x: auto;
  overflow-y: hidden;
}

.tagsInner {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 100%;
  white-space: nowrap;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 10px;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: #ffffff;
  color: #4b5563;
  font-size: 12px;
  line-height: 24px;
  white-space: nowrap;
  user-select: none;
}

.active {
  border-color: var(--app-primary-color, #1677ff);
  background: var(--app-primary-color, #1677ff);
  color: #ffffff;
}

.affix {
  cursor: default;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #ffffff;
  flex: 0 0 auto;
}

.tagTitle {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dark {
  background: #111827;
  border-color: #1f2937;

  .tag {
    border-color: #374151;
    background: #1f2937;
    color: #9ca3af;
  }

  .active {
    border-color: var(--app-primary-color, #1677ff);
    background: var(--app-primary-color, #1677ff);
    color: #ffffff;
  }
}
```

- [ ] **Step 3: Run ruoyi layout tests and verify they pass**

Run:

```bash
cd frontend && npm test -- layout.ruoyi.test.tsx App.test.tsx
```

Expected: PASS for ruoyi layout and app routing tests.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/layout/TagsView/index.tsx frontend/src/layout/TagsView/TagsView.module.less
git commit -m "feat(frontend): add ruoyi style tags view"
```

---

### Task 6: Delete Old Mobile/Settings Layout Code

**Files:**
- Delete old layout component files listed in File Structure.
- Delete `frontend/src/hooks/useBreakpoint.ts`
- Delete `frontend/src/stores/useAppStore.ts`
- Delete `frontend/src/stores/useSettingsStore.ts`

- [ ] **Step 1: Delete old layout files**

Run:

```bash
rm -f frontend/src/layout/components/Navbar/Breadcrumb.tsx
rm -f frontend/src/layout/components/Navbar/Hamburger.tsx
rm -f frontend/src/layout/components/Navbar/index.tsx
rm -f frontend/src/layout/components/Navbar/index.module.less
rm -f frontend/src/layout/components/Sidebar/DesktopSidebar.tsx
rm -f frontend/src/layout/components/Sidebar/MobileDrawer.tsx
rm -f frontend/src/layout/components/Sidebar/SidebarLogo.tsx
rm -f frontend/src/layout/components/Sidebar/index.tsx
rm -f frontend/src/layout/components/Sidebar/index.module.less
rm -f frontend/src/layout/components/TabsView/index.tsx
rm -f frontend/src/layout/components/TabsView/index.module.less
rm -f frontend/src/layout/components/TabsView/useSwipeTabs.ts
rm -f frontend/src/layout/components/AppMain/PullToRefresh.tsx
rm -f frontend/src/layout/components/AppMain/index.tsx
rm -f frontend/src/layout/components/AppMain/index.module.less
rm -f frontend/src/layout/components/Settings/index.tsx
rm -f frontend/src/layout/components/Settings/index.module.less
rm -f frontend/src/hooks/useBreakpoint.ts
rm -f frontend/src/stores/useAppStore.ts
rm -f frontend/src/stores/useSettingsStore.ts
```

- [ ] **Step 2: Verify no old mobile/settings imports remain**

Run:

```bash
rg -n "useBreakpoint|useMobile|useAppStore|useSettingsStore|MobileDrawer|DesktopSidebar|PullToRefresh|useSwipeTabs|components/Navbar|components/Sidebar|components/TabsView|components/AppMain|components/Settings|Open settings" frontend/src frontend/tests
```

Expected: no output.

- [ ] **Step 3: Verify no Settings files remain**

Run:

```bash
find frontend/src/layout -path '*Settings*' -print
```

Expected: no output.

- [ ] **Step 4: Run TypeScript build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. If TypeScript reports imports from deleted files, replace those imports with the new `frontend/src/layout/Header`, `Sidebar`, or `TagsView` modules before continuing.

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src/layout frontend/src/hooks frontend/src/stores
git commit -m "refactor(frontend): remove old mobile settings layout code"
```

---

### Task 7: Full Verification

**Files:**
- Modify only if verification reveals a concrete issue in files changed by Tasks 1-6.

- [ ] **Step 1: Run focused tests**

Run:

```bash
cd frontend && npm test -- layout.ruoyi.test.tsx App.test.tsx
```

Expected: PASS for both test files.

- [ ] **Step 2: Run the full test suite**

Run:

```bash
cd frontend && npm test -- --run
```

Expected: PASS for all Vitest tests.

- [ ] **Step 3: Run lint**

Run:

```bash
cd frontend && npm run lint
```

Expected: PASS with no ESLint errors.

- [ ] **Step 4: Run production build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS and Vite emits `dist/`.

- [ ] **Step 5: Manually verify layout and header theme**

Start the dev server:

```bash
cd frontend && npm run dev -- --host 127.0.0.1
```

Expected: Vite prints a URL such as `http://127.0.0.1:5173/`.

Manual checks:
- Authenticated `/` shows the ruoyi-style structure: left sider, top header, tags row, scrollable content.
- The top header is light in light mode.
- Toggling dark mode changes the top header to `#111827`-style dark background with readable icons/user text.
- The left sider and tags row also follow dark mode.
- Collapse/expand in the header changes the sider width.
- No settings trigger, settings drawer, mobile drawer, breakpoint behavior, swipe tabs, or pull-to-refresh UI is present.
- On narrow viewport, the same desktop layout remains instead of switching to a mobile drawer.

- [ ] **Step 6: Commit verification fixes if any were needed**

If Steps 1-5 required code changes, commit only those changed files:

```bash
git add frontend/src frontend/tests
git commit -m "fix(frontend): polish ruoyi layout parity"
```

If no code changed, skip this commit.

---

## Self-Review

- Spec coverage:
  - Header follows theme: Tasks 1 and 3 assert/apply `Header.module.less` dark class.
  - Settings component remains removed: Task 6 deletes old `Settings` files and verifies no references.
  - Mobile adaptation removed: Tasks 2-6 remove breakpoint-driven layout, mobile drawer, swipe tabs, and pull-to-refresh.
  - Layout matches ruoyi-react structure: Tasks 2-5 implement `SideMenu + LayoutHeader + TagsView + Content`.
- Placeholder scan:
  - Every file creation/modification step includes concrete code or exact shell commands.
- Type consistency:
  - `AppLayout` passes `darkMode`, `collapsed`, and `onCollapse` to `LayoutHeader`.
  - `SideMenu` accepts only `collapsed`.
  - `TagsView` accepts only `darkMode`.
