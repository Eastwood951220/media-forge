# Modern Console Layout UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the current ruoyi-style layout into a modern product console experience with better visual hierarchy, theme-aware chrome, and a dashboard that matches the upgraded shell.

**Architecture:** Keep the current authenticated layout route and ruoyi-style structure: `SideMenu + LayoutHeader + TagsView + Content`. Improve the visual system through focused Less modules and a dashboard module, remove the old mobile-first global token import, and verify the shell with component tests that assert theme-aware classes and visible console landmarks.

**Tech Stack:** React 19, TypeScript 6, TanStack Router 1.x, Ant Design 6, @ant-design/icons, Less modules, Vitest + React Testing Library

---

## Tooling Note

`ui-ux-pro-max` is not available as an installed or installable Codex plugin in this environment. This plan treats it as the requested design standard: modern product-console polish, restrained SaaS/admin aesthetics, better hierarchy, and theme-aware layout states.

## Current Code Findings

- `frontend/src/layout/index.tsx` already uses the desired ruoyi-style structural shell.
- `frontend/src/layout/Header`, `Sidebar`, and `TagsView` exist but are visually basic.
- `frontend/src/pages/dashboard/DashboardPage.tsx` is still placeholder-like and visually disconnected from the shell.
- `frontend/src/styles/app.css` still imports `mobile-first.css`, whose mobile overrides conflict with the previous requirement to remove mobile-specific layout adaptation.
- `frontend/src/routes/index.tsx` already wires `/` through `AppLayout`; no route changes are needed.

## File Structure

- Modify `frontend/src/layout/index.module.less`
  - Add modern console background treatment, inner layout separation, and dark theme surface colors.
- Modify `frontend/src/layout/Header/index.tsx`
  - Add a compact console title block while keeping collapse, theme toggle, user, and logout controls.
- Modify `frontend/src/layout/Header/Header.module.less`
  - Add glass-like surface, subtle border/shadow, improved controls, and dark theme parity.
- Modify `frontend/src/layout/Sidebar/Sidebar.module.less`
  - Upgrade sidebar logo, selected menu, hover states, scrollbars, and dark mode surfaces.
- Modify `frontend/src/layout/TagsView/TagsView.module.less`
  - Convert the tag row into a lighter product-console path strip.
- Modify `frontend/src/pages/dashboard/DashboardPage.tsx`
  - Replace the placeholder typography with a concise operations console dashboard.
- Create `frontend/src/pages/dashboard/DashboardPage.module.less`
  - Add dashboard cards, metrics, activity list, and dark-aware surfaces.
- Modify `frontend/src/styles/app.css`
  - Remove `mobile-first.css` import and add stable desktop console base tokens.
- Delete `frontend/src/styles/mobile-first.css`
  - Remove old mobile-specific global layout overrides.
- Create `frontend/tests/layout.ui.test.tsx`
  - Verify modern layout landmarks and dark header behavior.
- Create `frontend/tests/dashboard.ui.test.tsx`
  - Verify dashboard console content.

## Constraints

- Do not reintroduce `Settings`, a theme-color settings panel, mobile drawer, breakpoint layout logic, or marketing-style hero sections.
- Keep the ruoyi-style layout structure and existing route integration.
- Keep cards at 8px border radius or less.
- Avoid one-note purple/blue gradients and decorative orbs.
- Keep the first authenticated screen useful as the actual dashboard, not a landing page.

---

### Task 1: Add UI Regression Tests For Layout And Dashboard

**Files:**
- Create: `frontend/tests/layout.ui.test.tsx`
- Create: `frontend/tests/dashboard.ui.test.tsx`

- [ ] **Step 1: Write the modern layout test**

Create `frontend/tests/layout.ui.test.tsx`:

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
    component: () => <div>console outlet</div>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
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
  })

  it('renders console shell landmarks and dashboard navigation', async () => {
    renderLayout()

    expect(await screen.findByText('Media Forge')).toBeInTheDocument()
    expect(screen.getByText('Operations Console')).toBeInTheDocument()
    expect(screen.getByRole('menu')).toBeInTheDocument()
    expect(screen.getAllByText('仪表盘').length).toBeGreaterThanOrEqual(2)
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
```

- [ ] **Step 2: Write the dashboard UI test**

Create `frontend/tests/dashboard.ui.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import DashboardPage from '../src/pages/dashboard/DashboardPage'

describe('DashboardPage modern console content', () => {
  it('renders operational dashboard sections', () => {
    render(<DashboardPage />)

    expect(screen.getByRole('heading', { name: 'Operations Console' })).toBeInTheDocument()
    expect(screen.getByText('Media pipeline health')).toBeInTheDocument()
    expect(screen.getByText('Active jobs')).toBeInTheDocument()
    expect(screen.getByText('Queued assets')).toBeInTheDocument()
    expect(screen.getByText('Storage used')).toBeInTheDocument()
    expect(screen.getByText('Recent activity')).toBeInTheDocument()
    expect(screen.getByText('Processing lanes')).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run the tests and verify they fail before implementation**

Run:

```bash
cd frontend && npm test -- layout.ui.test.tsx dashboard.ui.test.tsx
```

Expected: FAIL because `Operations Console` is not yet present in the header/dashboard and `DashboardPage.module.less` does not exist.

- [ ] **Step 4: Commit the failing tests**

```bash
git add frontend/tests/layout.ui.test.tsx frontend/tests/dashboard.ui.test.tsx
git commit -m "test(frontend): cover modern console layout ui"
```

---

### Task 2: Upgrade Layout Shell Surfaces

**Files:**
- Modify: `frontend/src/layout/index.module.less`
- Modify: `frontend/src/styles/app.css`
- Delete: `frontend/src/styles/mobile-first.css`

- [ ] **Step 1: Replace layout shell styles**

Replace `frontend/src/layout/index.module.less` with:

```less
.layout {
  height: 100vh;
  max-height: 100vh;
  min-height: 0;
  overflow: hidden;
  background:
    linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(241, 245, 249, 0.98)),
    #f6f8fb;
}

.main {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: transparent;
}

.content {
  flex: 1 1 0;
  min-height: 0;
  padding: 18px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  scrollbar-gutter: stable;
}

.content::-webkit-scrollbar {
  width: 10px;
}

.content::-webkit-scrollbar-thumb {
  border: 3px solid transparent;
  border-radius: 999px;
  background: rgba(100, 116, 139, 0.32);
  background-clip: padding-box;
}

.pageContainer {
  min-width: 0;
  flex: 1;
}

.dark {
  background:
    linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(2, 6, 23, 0.98)),
    #020617;
}

.dark .content::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.28);
  background-clip: padding-box;
}
```

- [ ] **Step 2: Replace global app styles**

Replace `frontend/src/styles/app.css` with:

```css
@import "tailwindcss";
@import "tw-animate-css";

:root {
  --app-primary-color: #006aff;
  --app-text-color: #0f172a;
  --app-muted-color: #64748b;
  --app-bg-color: #f6f8fb;
  --app-surface-color: #ffffff;
}

:root[data-theme="dark"] {
  --app-text-color: #e5e7eb;
  --app-muted-color: #94a3b8;
  --app-bg-color: #020617;
  --app-surface-color: #111827;
}

* {
  box-sizing: border-box;
}

html,
body,
#root {
  width: 100%;
  min-width: 0;
  min-height: 100vh;
  margin: 0;
  padding: 0;
}

body {
  overflow: hidden;
  background: var(--app-bg-color);
  color: var(--app-text-color);
  font-family:
    Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
    sans-serif;
}

button,
input,
textarea,
select {
  font: inherit;
}
```

- [ ] **Step 3: Delete old mobile-first global tokens**

Run:

```bash
rm frontend/src/styles/mobile-first.css
```

- [ ] **Step 4: Verify the mobile-first import is gone**

Run:

```bash
rg -n "mobile-first|mobile-drawer-overlay|safe-area-bottom|--z-settings-btn" frontend/src
```

Expected: no output.

- [ ] **Step 5: Run build to catch global style references**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. If it fails because another file imports `mobile-first.css`, remove that import and rerun.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/layout/index.module.less frontend/src/styles/app.css
git rm frontend/src/styles/mobile-first.css
git commit -m "style(frontend): modernize console layout shell"
```

---

### Task 3: Polish Header, Sidebar, And TagsView

**Files:**
- Modify: `frontend/src/layout/Header/index.tsx`
- Modify: `frontend/src/layout/Header/Header.module.less`
- Modify: `frontend/src/layout/Sidebar/Sidebar.module.less`
- Modify: `frontend/src/layout/TagsView/TagsView.module.less`

- [ ] **Step 1: Replace header component**

Replace `frontend/src/layout/Header/index.tsx` with:

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
    void navigate({ to: '/login', search: { redirect: undefined }, replace: true })
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
        <div className={styles.titleBlock}>
          <span className={styles.title}>Operations Console</span>
          <span className={styles.subtitle}>Media pipeline health</span>
        </div>
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

- [ ] **Step 2: Replace header styles**

Replace `frontend/src/layout/Header/Header.module.less` with:

```less
.header {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 22px;
  background: rgba(255, 255, 255, 0.92);
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  box-shadow: 0 1px 0 rgba(15, 23, 42, 0.03);
  backdrop-filter: blur(14px);
}

.left {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.collapseBtn {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 1px solid rgba(203, 213, 225, 0.8);
  border-radius: 8px;
  background: #ffffff;
  color: #334155;
  font-size: 18px;
  cursor: pointer;
  transition:
    background 160ms ease,
    border-color 160ms ease,
    color 160ms ease,
    box-shadow 160ms ease;
}

.collapseBtn:hover {
  border-color: rgba(0, 106, 255, 0.45);
  color: var(--app-primary-color, #006aff);
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
}

.titleBlock {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.title {
  color: #0f172a;
  font-size: 15px;
  font-weight: 700;
  line-height: 20px;
}

.subtitle {
  color: #64748b;
  font-size: 12px;
  line-height: 16px;
}

.right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user {
  height: 36px;
  display: inline-flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  padding: 0 10px 0 4px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 8px;
  background: rgba(248, 250, 252, 0.9);
  color: #334155;
}

.avatar {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 7px;
  background: #e0ecff;
  color: #0f4fb8;
  font-size: 13px;
  font-weight: 700;
  line-height: 28px;
}

.userName {
  max-width: 128px;
  overflow: hidden;
  color: #1e293b;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dark {
  background: rgba(15, 23, 42, 0.92);
  border-bottom-color: rgba(51, 65, 85, 0.9);
  color: #cbd5e1;

  .collapseBtn {
    border-color: rgba(51, 65, 85, 0.95);
    background: rgba(30, 41, 59, 0.8);
    color: #cbd5e1;
  }

  .collapseBtn:hover {
    border-color: rgba(96, 165, 250, 0.55);
    color: #bfdbfe;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.22);
  }

  .title {
    color: #f8fafc;
  }

  .subtitle {
    color: #94a3b8;
  }

  .user {
    border-color: rgba(51, 65, 85, 0.95);
    background: rgba(30, 41, 59, 0.78);
    color: #e5e7eb;
  }

  .avatar {
    background: #134e4a;
    color: #ccfbf1;
  }

  .userName {
    color: #e5e7eb;
  }
}
```

- [ ] **Step 3: Replace sidebar styles**

Replace `frontend/src/layout/Sidebar/Sidebar.module.less` with:

```less
.sider {
  min-width: 0;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.96);
  border-right: 1px solid rgba(226, 232, 240, 0.9);

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
    background: transparent;
  }

  :global(.ant-menu-inline),
  :global(.ant-menu-vertical) {
    border-inline-end: 0;
  }

  :global(.ant-menu-item),
  :global(.ant-menu-submenu-title) {
    width: calc(100% - 16px);
    height: 40px;
    margin: 4px 8px;
    border-radius: 8px;
  }

  :global(.ant-menu-item-selected) {
    background: rgba(0, 106, 255, 0.12);
    color: var(--app-primary-color, #006aff);
    font-weight: 600;
  }
}

.collapsed {
  :global(.ant-menu-item),
  :global(.ant-menu-submenu-title) {
    width: calc(100% - 16px);
    margin-inline: 8px;
  }
}

.logo {
  height: 64px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  flex: 0 0 auto;
  border-bottom: 1px solid rgba(226, 232, 240, 0.72);
}

.logoMark {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 8px;
  background: #0f172a;
  color: #ffffff;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.18);
}

.logoText {
  overflow: hidden;
  color: #0f172a;
  font-size: 15px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menuWrapper {
  flex: 1 1 auto;
  width: 100%;
  min-width: 0;
  padding: 10px 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.menuWrapper::-webkit-scrollbar {
  width: 8px;
}

.menuWrapper::-webkit-scrollbar-thumb {
  border: 2px solid transparent;
  border-radius: 999px;
  background: rgba(100, 116, 139, 0.28);
  background-clip: padding-box;
}

.menu {
  width: 100%;
  min-width: 0;
}

.dark {
  &.sider {
    background: rgba(15, 23, 42, 0.96);
    border-right-color: rgba(51, 65, 85, 0.9);
  }

  .logo {
    border-bottom-color: rgba(51, 65, 85, 0.9);
  }

  .logoMark {
    background: #eff6ff;
    color: #0f172a;
    box-shadow: 0 8px 18px rgba(0, 0, 0, 0.28);
  }

  .logoText {
    color: #e5e7eb;
  }

  :global(.ant-menu-item-selected) {
    background: rgba(59, 130, 246, 0.2);
    color: #bfdbfe;
  }
}
```

- [ ] **Step 4: Replace TagsView styles**

Replace `frontend/src/layout/TagsView/TagsView.module.less` with:

```less
.tagsView {
  height: 38px;
  display: flex;
  align-items: center;
  background: rgba(255, 255, 255, 0.78);
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  overflow: hidden;
}

.scrollContent {
  height: 100%;
  padding: 0 10px;
  overflow-x: auto;
  overflow-y: hidden;
}

.scrollContent::-webkit-scrollbar {
  display: none;
}

.tagsInner {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 100%;
  white-space: nowrap;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 26px;
  padding: 0 11px;
  border: 1px solid rgba(203, 213, 225, 0.88);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.86);
  color: #475569;
  font-size: 12px;
  line-height: 24px;
  white-space: nowrap;
  user-select: none;
}

.active {
  border-color: rgba(0, 106, 255, 0.28);
  background: rgba(0, 106, 255, 0.1);
  color: #0759cf;
}

.affix {
  cursor: default;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--app-primary-color, #006aff);
  flex: 0 0 auto;
}

.tagTitle {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dark {
  background: rgba(15, 23, 42, 0.72);
  border-color: rgba(51, 65, 85, 0.9);

  .tag {
    border-color: rgba(71, 85, 105, 0.88);
    background: rgba(30, 41, 59, 0.76);
    color: #cbd5e1;
  }

  .active {
    border-color: rgba(96, 165, 250, 0.35);
    background: rgba(59, 130, 246, 0.16);
    color: #bfdbfe;
  }

  .dot {
    background: #60a5fa;
  }
}
```

- [ ] **Step 5: Run layout UI test**

Run:

```bash
cd frontend && npm test -- layout.ui.test.tsx
```

Expected: PASS with 2 tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/layout/Header/index.tsx frontend/src/layout/Header/Header.module.less frontend/src/layout/Sidebar/Sidebar.module.less frontend/src/layout/TagsView/TagsView.module.less
git commit -m "style(frontend): polish console navigation chrome"
```

---

### Task 4: Upgrade Dashboard First Screen

**Files:**
- Modify: `frontend/src/pages/dashboard/DashboardPage.tsx`
- Create: `frontend/src/pages/dashboard/DashboardPage.module.less`

- [ ] **Step 1: Replace dashboard page**

Replace `frontend/src/pages/dashboard/DashboardPage.tsx` with:

```typescript
import {
  ApiOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  FieldTimeOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import styles from './DashboardPage.module.less'

const metrics = [
  {
    label: 'Active jobs',
    value: '18',
    detail: '6 rendering, 12 encoding',
    icon: <ThunderboltOutlined />,
  },
  {
    label: 'Queued assets',
    value: '142',
    detail: 'Across 4 processing lanes',
    icon: <FieldTimeOutlined />,
  },
  {
    label: 'Storage used',
    value: '67%',
    detail: '18.4 TB available',
    icon: <DatabaseOutlined />,
  },
]

const lanes = [
  { name: 'Ingest', status: 'Healthy', load: '24 jobs' },
  { name: 'Transcode', status: 'Busy', load: '58 jobs' },
  { name: 'Review', status: 'Healthy', load: '12 jobs' },
]

const activity = [
  'Trailer batch completed',
  'Proxy generation started',
  'Archive sync verified',
]

function DashboardPage() {
  return (
    <div className={styles.dashboard}>
      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>Media pipeline health</p>
          <h1 className={styles.title}>Operations Console</h1>
          <p className={styles.summary}>
            Monitor processing load, asset movement, and service readiness from one workspace.
          </p>
        </div>
        <div className={styles.heroStatus}>
          <span className={styles.statusIcon}>
            <CheckCircleOutlined />
          </span>
          <div>
            <span className={styles.statusLabel}>System status</span>
            <strong>Healthy</strong>
          </div>
        </div>
      </section>

      <section className={styles.metricsGrid}>
        {metrics.map((metric) => (
          <article key={metric.label} className={styles.metricCard}>
            <span className={styles.metricIcon}>{metric.icon}</span>
            <div>
              <span className={styles.metricLabel}>{metric.label}</span>
              <strong className={styles.metricValue}>{metric.value}</strong>
              <span className={styles.metricDetail}>{metric.detail}</span>
            </div>
          </article>
        ))}
      </section>

      <section className={styles.workGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <span className={styles.panelKicker}>Workload</span>
              <h2>Processing lanes</h2>
            </div>
            <CloudServerOutlined className={styles.panelIcon} />
          </div>
          <div className={styles.laneList}>
            {lanes.map((lane) => (
              <div key={lane.name} className={styles.laneRow}>
                <span>{lane.name}</span>
                <strong>{lane.status}</strong>
                <em>{lane.load}</em>
              </div>
            ))}
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <span className={styles.panelKicker}>Timeline</span>
              <h2>Recent activity</h2>
            </div>
            <ApiOutlined className={styles.panelIcon} />
          </div>
          <div className={styles.activityList}>
            {activity.map((item) => (
              <div key={item} className={styles.activityRow}>
                <span className={styles.activityDot} />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </article>
      </section>
    </div>
  )
}

export default DashboardPage
```

- [ ] **Step 2: Create dashboard styles**

Create `frontend/src/pages/dashboard/DashboardPage.module.less`:

```less
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
}

.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 22px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06);
}

.eyebrow,
.panelKicker,
.metricLabel,
.metricDetail,
.statusLabel {
  color: #64748b;
  font-size: 12px;
}

.eyebrow {
  margin: 0 0 6px;
  font-weight: 700;
  text-transform: uppercase;
}

.title {
  margin: 0;
  color: #0f172a;
  font-size: 28px;
  font-weight: 800;
  line-height: 36px;
}

.summary {
  max-width: 560px;
  margin: 8px 0 0;
  color: #475569;
  font-size: 14px;
  line-height: 22px;
}

.heroStatus {
  min-width: 176px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid rgba(187, 247, 208, 0.9);
  border-radius: 8px;
  background: rgba(240, 253, 244, 0.9);
  color: #166534;
}

.heroStatus strong {
  display: block;
  color: #14532d;
  font-size: 14px;
}

.statusIcon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 8px;
  background: #dcfce7;
  color: #15803d;
  font-size: 18px;
}

.metricsGrid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.metricCard,
.panel {
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
}

.metricCard {
  display: flex;
  gap: 12px;
  padding: 16px;
}

.metricIcon,
.panelIcon {
  color: var(--app-primary-color, #006aff);
}

.metricIcon {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 8px;
  background: rgba(0, 106, 255, 0.1);
  font-size: 18px;
}

.metricValue {
  display: block;
  margin-top: 4px;
  color: #0f172a;
  font-size: 24px;
  line-height: 30px;
}

.metricDetail {
  display: block;
  margin-top: 2px;
}

.workGrid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.7fr);
  gap: 14px;
}

.panel {
  min-width: 0;
  padding: 16px;
}

.panelHeader {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.panelHeader h2 {
  margin: 2px 0 0;
  color: #0f172a;
  font-size: 16px;
  line-height: 22px;
}

.panelIcon {
  font-size: 20px;
}

.laneList,
.activityList {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.laneRow {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f8fafc;
  color: #334155;
  font-size: 13px;
}

.laneRow strong {
  color: #0f172a;
}

.laneRow em {
  color: #64748b;
  font-style: normal;
}

.activityRow {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 38px;
  color: #334155;
  font-size: 13px;
}

.activityDot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--app-primary-color, #006aff);
}

:global(:root[data-theme="dark"]) {
  .hero,
  .metricCard,
  .panel {
    border-color: rgba(51, 65, 85, 0.9);
    background: rgba(15, 23, 42, 0.88);
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.22);
  }

  .title,
  .metricValue,
  .panelHeader h2,
  .laneRow strong {
    color: #f8fafc;
  }

  .summary,
  .activityRow,
  .laneRow {
    color: #cbd5e1;
  }

  .eyebrow,
  .panelKicker,
  .metricLabel,
  .metricDetail,
  .statusLabel,
  .laneRow em {
    color: #94a3b8;
  }

  .heroStatus {
    border-color: rgba(20, 83, 45, 0.9);
    background: rgba(20, 83, 45, 0.28);
    color: #bbf7d0;
  }

  .heroStatus strong {
    color: #dcfce7;
  }

  .statusIcon {
    background: rgba(22, 101, 52, 0.52);
    color: #bbf7d0;
  }

  .laneRow {
    background: rgba(30, 41, 59, 0.78);
  }
}
```

- [ ] **Step 3: Run dashboard UI test**

Run:

```bash
cd frontend && npm test -- dashboard.ui.test.tsx
```

Expected: PASS with 1 test.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/dashboard/DashboardPage.tsx frontend/src/pages/dashboard/DashboardPage.module.less
git commit -m "style(frontend): upgrade dashboard console view"
```

---

### Task 5: Full Verification

**Files:**
- Modify only if verification reveals a concrete issue in files changed by Tasks 1-4.

- [ ] **Step 1: Run focused UI tests**

Run:

```bash
cd frontend && npm test -- layout.ui.test.tsx dashboard.ui.test.tsx App.test.tsx
```

Expected: PASS for all focused tests.

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

- [ ] **Step 5: Manual visual verification**

Start the dev server:

```bash
cd frontend && npm run dev -- --host 127.0.0.1
```

Expected: Vite prints a URL such as `http://127.0.0.1:5173/`.

Manual checks:
- Authenticated `/` shows a modern product console: refined sidebar, translucent header, path tag strip, and dashboard cards.
- Header, sidebar, tags, and dashboard surfaces all change coherently in dark mode.
- Sidebar collapse still works and does not shift content unpredictably.
- No Settings trigger or mobile drawer appears.
- The UI remains restrained and admin-focused, with no marketing hero, decorative orbs, or oversized visual treatment.

- [ ] **Step 6: Commit verification fixes if any were needed**

If Steps 1-5 required code changes, commit only those changed files:

```bash
git add frontend/src frontend/tests
git commit -m "fix(frontend): polish modern console ui"
```

If no code changed, skip this commit.

---

## Self-Review

- Spec coverage:
  - Uses `ui-ux-pro-max` as a high-quality UI/UX standard because no exact plugin is available.
  - Optimizes the current layout page without changing routing/auth behavior.
  - Keeps the ruoyi-style structure while making the result a modern product console.
  - Does not restore Settings or mobile-specific layout adaptation.
- Placeholder scan:
  - Every file modification includes complete code, exact paths, and exact verification commands.
- Type consistency:
  - `LayoutHeader` still accepts `darkMode`, `collapsed`, and `onCollapse`.
  - Dashboard styles match class names used by `DashboardPage.tsx`.
  - Tests assert visible text introduced by the plan.
