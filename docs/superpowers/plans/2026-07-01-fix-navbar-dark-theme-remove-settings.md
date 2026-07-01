# Navbar Dark Theme And Settings Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the current layout header so it follows light/dark theme changes, while removing the complex settings drawer and configurable theme color chain.

**Architecture:** Keep the existing authenticated layout structure in `frontend/src/layout/index.tsx`: `Sidebar`, `Navbar`, `TabsView`, and `AppMain`. Make `Navbar` consume `useThemeStore.darkMode` directly and apply a dark CSS module class, then remove the unused `Settings` component and the `primaryColor` state/sync flow so theme switching only means light/dark mode.

**Tech Stack:** React 19, TypeScript 6, TanStack Router 1.x, Ant Design 6, Zustand 5, Less modules, Vitest + React Testing Library

---

## Current Code Findings

- `frontend/src/layout/components/Navbar/index.tsx` renders a fixed class list and never reads `useThemeStore.darkMode`.
- `frontend/src/layout/components/Navbar/index.module.less` sets `.navbar` to a light background via `var(--color-bg-container, #fff)` and has no dark variant.
- `frontend/src/layout/index.tsx` still imports and renders `Settings`.
- `frontend/src/layout/components/Settings/index.tsx` owns a settings drawer, `ColorPicker`, layout toggles, and theme color controls.
- `frontend/src/stores/useThemeStore.ts`, `frontend/src/App.tsx`, and `frontend/src/routes/index.tsx` still carry configurable `primaryColor` state.
- The requested fix does not need a settings component and does not need theme color configuration.

## File Structure

- Modify `frontend/src/layout/components/Navbar/index.tsx`
  - Add `darkMode` subscription and append `styles.navbarDark` when dark mode is active.
- Modify `frontend/src/layout/components/Navbar/index.module.less`
  - Add dark header, hamburger, and breadcrumb color rules using the current layout class structure.
- Modify `frontend/src/layout/index.tsx`
  - Remove `Settings` import/render and keep the original `Sidebar + Navbar + TabsView + AppMain` layout.
- Delete `frontend/src/layout/components/Settings/index.tsx`
  - Remove the complex drawer/settings UI.
- Delete `frontend/src/layout/components/Settings/index.module.less`
  - Remove dead styles for the settings UI.
- Modify `frontend/src/stores/useThemeStore.ts`
  - Remove `primaryColor` and `setPrimaryColor`; persist only `mode` and `darkMode`.
- Modify `frontend/src/stores/useSettingsStore.ts`
  - Keep only layout state currently consumed by layout components: `showTagsView`, `showSidebarLogo`, and `fixedHeader`.
- Modify `frontend/src/App.tsx`
  - Sync only `data-theme` to `<html>`.
- Modify `frontend/src/routes/index.tsx`
  - Stop reading configurable `primaryColor`; keep Ant Design algorithm and fixed `borderRadius`.
- Add tests:
  - `frontend/tests/Navbar.theme.test.tsx`
  - `frontend/tests/AppLayout.settings.test.tsx`
  - `frontend/tests/themeStore.test.ts`

## Constraints

- Do not introduce a new settings panel, theme color picker, or theme preset feature.
- Do not redesign the layout tree; preserve the current layout order.
- Do not remove the existing header `ThemeModeToggle`; it remains the only theme control in the header.
- Preserve mobile layout behavior from the current `Sidebar`, `Navbar`, and `useBreakpoint` code.
- Keep login and init routes unchanged.

---

### Task 1: Make Navbar Follow Dark Mode

**Files:**
- Modify: `frontend/src/layout/components/Navbar/index.tsx`
- Modify: `frontend/src/layout/components/Navbar/index.module.less`
- Test: `frontend/tests/Navbar.theme.test.tsx`

- [ ] **Step 1: Write the failing navbar theme test**

Create `frontend/tests/Navbar.theme.test.tsx`:

```typescript
import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Navbar from '../src/layout/components/Navbar'
import styles from '../src/layout/components/Navbar/index.module.less'
import { useSettingsStore } from '../src/stores/useSettingsStore'
import { useThemeStore } from '../src/stores/useThemeStore'

vi.mock('../src/layout/components/Navbar/Hamburger', () => ({
  default: () => <button type="button">hamburger</button>,
}))

vi.mock('../src/layout/components/Navbar/Breadcrumb', () => ({
  default: () => <nav aria-label="breadcrumb">首页</nav>,
}))

vi.mock('../src/components/ThemeModeToggle', () => ({
  ThemeModeToggle: () => <button type="button">theme toggle</button>,
}))

describe('Navbar theme styling', () => {
  beforeEach(() => {
    useSettingsStore.setState({ fixedHeader: false })
    useThemeStore.setState({ mode: 'light', darkMode: false })
  })

  it('does not apply the dark navbar class in light mode', () => {
    render(<Navbar />)

    const header = screen.getByRole('banner')
    expect(header).toHaveClass(styles.navbar)
    expect(header).not.toHaveClass(styles.navbarDark)
  })

  it('applies the dark navbar class in dark mode', () => {
    act(() => {
      useThemeStore.setState({ mode: 'dark', darkMode: true })
    })

    render(<Navbar />)

    const header = screen.getByRole('banner')
    expect(header).toHaveClass(styles.navbar)
    expect(header).toHaveClass(styles.navbarDark)
  })
})
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd frontend && npm test -- Navbar.theme.test.tsx
```

Expected: FAIL because `styles.navbarDark` is not applied by `Navbar`.

- [ ] **Step 3: Update Navbar to read dark mode**

Replace `frontend/src/layout/components/Navbar/index.tsx` with:

```typescript
import { useSettingsStore } from '@/stores/useSettingsStore'
import { useThemeStore } from '@/stores/useThemeStore'
import { ThemeModeToggle } from '@/components/ThemeModeToggle'
import Hamburger from './Hamburger'
import BreadcrumbNav from './Breadcrumb'
import styles from './index.module.less'

/**
 * Top navigation bar: hamburger (always), breadcrumb (desktop),
 * and a right-side slot for the theme toggle.
 *
 * When `fixedHeader` is enabled the bar is position: fixed.
 */
export default function Navbar() {
  const fixedHeader = useSettingsStore((s) => s.fixedHeader)
  const darkMode = useThemeStore((s) => s.darkMode)

  const className = [
    styles.navbar,
    fixedHeader && styles.navbarFixed,
    darkMode && styles.navbarDark,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <header className={className}>
      <div className={styles.leftSection}>
        <Hamburger />
        <BreadcrumbNav />
      </div>

      <div className={styles.rightSection}>
        <ThemeModeToggle variant="header" />
      </div>
    </header>
  )
}
```

- [ ] **Step 4: Add dark navbar styles**

Replace `frontend/src/layout/components/Navbar/index.module.less` with:

```less
/* Navbar */

.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--navbar-height, 50px);
  padding: 0 12px;
  background: var(--ant-color-bg-container, #ffffff);
  border-bottom: 1px solid var(--ant-color-border-secondary, #f0f0f0);
  color: var(--ant-color-text, #1f2937);
  box-sizing: border-box;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease;
}

.navbarDark {
  background: #141414;
  border-bottom-color: #303030;
  color: rgba(255, 255, 255, 0.88);

  .hamburger {
    color: rgba(255, 255, 255, 0.88);

    &:hover {
      background: rgba(255, 255, 255, 0.08);
    }

    svg {
      color: rgba(255, 255, 255, 0.88);
    }
  }

  .breadcrumb {
    color: rgba(255, 255, 255, 0.88);

    :global(.ant-breadcrumb-link),
    :global(.ant-breadcrumb-separator) {
      color: rgba(255, 255, 255, 0.65);
    }
  }
}

.navbarFixed {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: var(--z-navbar, 100);
}

.leftSection {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.rightSection {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.hamburger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 50px;
  height: 50px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--ant-color-text, #333333);
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    color 0.2s ease;
  flex-shrink: 0;

  &:hover {
    background: var(--ant-color-bg-text-hover, rgba(0, 0, 0, 0.06));
  }

  svg {
    width: 20px;
    height: 20px;
    color: currentColor;
    transition: transform 0.3s ease;
  }
}

.hamburgerCollapsed svg {
  transform: rotate(90deg);
}

.breadcrumb {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--ant-color-text, #1f2937);
}

@media (max-width: 767px) {
  .hamburger {
    width: 46px;
    height: 46px;
  }

  .breadcrumb {
    display: none;
  }
}
```

- [ ] **Step 5: Run the navbar theme test and verify it passes**

Run:

```bash
cd frontend && npm test -- Navbar.theme.test.tsx
```

Expected: PASS with 2 tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/layout/components/Navbar/index.tsx frontend/src/layout/components/Navbar/index.module.less frontend/tests/Navbar.theme.test.tsx
git commit -m "fix(frontend): sync navbar colors with dark theme"
```

---

### Task 2: Remove Settings Drawer From The Existing Layout

**Files:**
- Modify: `frontend/src/layout/index.tsx`
- Delete: `frontend/src/layout/components/Settings/index.tsx`
- Delete: `frontend/src/layout/components/Settings/index.module.less`
- Modify: `frontend/src/stores/useSettingsStore.ts`
- Test: `frontend/tests/AppLayout.settings.test.tsx`

- [ ] **Step 1: Write the failing layout settings test**

Create `frontend/tests/AppLayout.settings.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AppLayout from '../src/layout'
import { useSettingsStore } from '../src/stores/useSettingsStore'

vi.mock('../src/layout/components/Sidebar', () => ({
  default: () => <aside>sidebar</aside>,
}))

vi.mock('../src/layout/components/Navbar', () => ({
  default: () => <header>navbar</header>,
}))

vi.mock('../src/layout/components/TabsView', () => ({
  default: () => <nav>tabs view</nav>,
}))

vi.mock('../src/layout/components/AppMain', () => ({
  default: () => <main>app main</main>,
}))

vi.mock('../src/hooks/useBreakpoint', () => ({
  useBreakpoint: () => ({
    breakpoint: 'desktop',
    isMobile: false,
    isTablet: false,
    isDesktop: true,
    screenWidth: 1280,
  }),
}))

describe('AppLayout settings panel', () => {
  beforeEach(() => {
    useSettingsStore.setState({
      showTagsView: true,
      showSidebarLogo: true,
      fixedHeader: true,
    })
  })

  it('keeps the original layout sections without rendering the settings trigger', () => {
    render(<AppLayout />)

    expect(screen.getByText('sidebar')).toBeInTheDocument()
    expect(screen.getByText('navbar')).toBeInTheDocument()
    expect(screen.getByText('tabs view')).toBeInTheDocument()
    expect(screen.getByText('app main')).toBeInTheDocument()
    expect(screen.queryByLabelText('Open settings')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd frontend && npm test -- AppLayout.settings.test.tsx
```

Expected: FAIL because the current `AppLayout` renders the `Settings` component, whose desktop trigger has `aria-label="Open settings"`.

- [ ] **Step 3: Remove Settings from AppLayout**

Replace `frontend/src/layout/index.tsx` with:

```typescript
import { useEffect } from 'react'
import { Layout } from 'antd'
import { useBreakpoint } from '@/hooks/useBreakpoint'
import { useAppStore } from '@/stores/useAppStore'
import { useSettingsStore } from '@/stores/useSettingsStore'
import Sidebar from './components/Sidebar'
import Navbar from './components/Navbar'
import TabsView from './components/TabsView'
import AppMain from './components/AppMain'
import styles from './index.module.less'

/**
 * Root layout for authenticated pages.
 *
 * Composes Sidebar + Navbar + TabsView + AppMain,
 * with responsive behaviour driven by useBreakpoint.
 */
export default function AppLayout() {
  const { isMobile } = useBreakpoint()
  const setDevice = useAppStore((s) => s.setDevice)
  const setSidebarCollapsed = useAppStore((s) => s.setSidebarCollapsed)
  const fixedHeader = useSettingsStore((s) => s.fixedHeader)

  useEffect(() => {
    setDevice(isMobile ? 'mobile' : 'desktop')
    if (isMobile) {
      setSidebarCollapsed(true)
    }
  }, [isMobile, setDevice, setSidebarCollapsed])

  return (
    <Layout className={styles.layout}>
      <Sidebar />
      <Layout>
        {fixedHeader && <div style={{ height: 'var(--navbar-height)' }} />}
        <Navbar />
        <TabsView />
        <AppMain />
      </Layout>
    </Layout>
  )
}
```

- [ ] **Step 4: Simplify settings store to layout state only**

Replace `frontend/src/stores/useSettingsStore.ts` with:

```typescript
import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

type SettingsState = {
  showTagsView: boolean
  showSidebarLogo: boolean
  fixedHeader: boolean
}

type PersistedSettingsState = Partial<SettingsState>

export const useSettingsStore = create<SettingsState>()(
  devtools(
    persist(
      () => ({
        showTagsView: true,
        showSidebarLogo: true,
        fixedHeader: true,
      }),
      {
        name: 'media-forge-settings',
        partialize: (state) => ({
          showTagsView: state.showTagsView,
          showSidebarLogo: state.showSidebarLogo,
          fixedHeader: state.fixedHeader,
        }),
        merge: (persisted, current) => {
          const saved = persisted as PersistedSettingsState

          return {
            ...current,
            showTagsView:
              typeof saved.showTagsView === 'boolean'
                ? saved.showTagsView
                : current.showTagsView,
            showSidebarLogo:
              typeof saved.showSidebarLogo === 'boolean'
                ? saved.showSidebarLogo
                : current.showSidebarLogo,
            fixedHeader:
              typeof saved.fixedHeader === 'boolean'
                ? saved.fixedHeader
                : current.fixedHeader,
          }
        },
      },
    ),
  ),
)
```

- [ ] **Step 5: Delete the settings component files**

Delete:

```bash
rm frontend/src/layout/components/Settings/index.tsx
rm frontend/src/layout/components/Settings/index.module.less
```

- [ ] **Step 6: Run the layout settings test and verify it passes**

Run:

```bash
cd frontend && npm test -- AppLayout.settings.test.tsx
```

Expected: PASS with 1 test.

- [ ] **Step 7: Verify there are no Settings references left**

Run:

```bash
rg -n "components/Settings|<Settings|showSettingsDrawer|Open settings|ColorPicker|Theme Color" frontend/src frontend/tests
```

Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/layout/index.tsx frontend/src/stores/useSettingsStore.ts frontend/tests/AppLayout.settings.test.tsx
git rm frontend/src/layout/components/Settings/index.tsx frontend/src/layout/components/Settings/index.module.less
git commit -m "refactor(frontend): remove layout settings drawer"
```

---

### Task 3: Remove Configurable Theme Color State

**Files:**
- Modify: `frontend/src/stores/useThemeStore.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/routes/index.tsx`
- Test: `frontend/tests/themeStore.test.ts`

- [ ] **Step 1: Write the failing theme store test**

Create `frontend/tests/themeStore.test.ts`:

```typescript
import { beforeEach, describe, expect, it } from 'vitest'
import { useThemeStore } from '../src/stores/useThemeStore'

describe('useThemeStore', () => {
  beforeEach(() => {
    useThemeStore.setState({ mode: 'light', darkMode: false })
  })

  it('keeps only light and dark mode state, without configurable primary color state', () => {
    const state = useThemeStore.getState() as unknown as Record<string, unknown>

    expect(state.mode).toBe('light')
    expect(state.darkMode).toBe(false)
    expect('primaryColor' in state).toBe(false)
    expect('setPrimaryColor' in state).toBe(false)
  })

  it('toggles between light and dark mode', () => {
    useThemeStore.getState().toggleMode()

    expect(useThemeStore.getState().mode).toBe('dark')
    expect(useThemeStore.getState().darkMode).toBe(true)

    useThemeStore.getState().toggleMode()

    expect(useThemeStore.getState().mode).toBe('light')
    expect(useThemeStore.getState().darkMode).toBe(false)
  })
})
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd frontend && npm test -- themeStore.test.ts
```

Expected: FAIL because the current `useThemeStore` exposes `primaryColor` and `setPrimaryColor`.

- [ ] **Step 3: Simplify the theme store**

Replace `frontend/src/stores/useThemeStore.ts` with:

```typescript
import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

type ThemeMode = 'light' | 'dark'

type ThemeState = {
  mode: ThemeMode
  darkMode: boolean
  setMode: (mode: ThemeMode) => void
  setDarkMode: (darkMode: boolean) => void
  toggleMode: () => void
}

type PersistedThemeState = Partial<Pick<ThemeState, 'mode' | 'darkMode'>>

function isThemeMode(value: unknown): value is ThemeMode {
  return value === 'light' || value === 'dark'
}

export const useThemeStore = create<ThemeState>()(
  devtools(
    persist(
      (set) => ({
        mode: 'light',
        darkMode: false,

        setMode: (mode) =>
          set({
            mode,
            darkMode: mode === 'dark',
          }),

        setDarkMode: (darkMode) =>
          set({
            darkMode,
            mode: darkMode ? 'dark' : 'light',
          }),

        toggleMode: () =>
          set((state) => {
            const nextMode = state.darkMode ? 'light' : 'dark'
            return {
              mode: nextMode,
              darkMode: nextMode === 'dark',
            }
          }),
      }),
      {
        name: 'media-forge-theme',
        partialize: (state) => ({
          mode: state.mode,
          darkMode: state.darkMode,
        }),
        merge: (persisted, current) => {
          const saved = persisted as PersistedThemeState
          const mode = isThemeMode(saved.mode) ? saved.mode : current.mode
          const darkMode =
            typeof saved.darkMode === 'boolean' ? saved.darkMode : mode === 'dark'

          return {
            ...current,
            mode,
            darkMode,
          }
        },
      },
    ),
  ),
)
```

- [ ] **Step 4: Simplify App theme syncing**

Replace `frontend/src/App.tsx` with:

```typescript
import { useState, useEffect } from 'react'
import './styles/app.css'
import './styles/view-transition.css'
import { RouterProvider } from '@tanstack/react-router'
import { router } from './routes'
import { queryClient } from './lib/query-client'
import { QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/useAuthStore'
import { useThemeStore } from '@/stores/useThemeStore'
import { checkInitStatus } from './routes/-guards'
import { Spin } from 'antd'

function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const darkMode = useThemeStore((s) => s.darkMode)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    document.documentElement.dataset.theme = darkMode ? 'dark' : 'light'
  }, [darkMode])

  useEffect(() => {
    if (isAuthenticated) {
      setReady(true)
    } else {
      checkInitStatus().then(() => {
        setReady(true)
      })
    }
  }, [isAuthenticated])

  if (!ready) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    )
  }

  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

export default App
```

- [ ] **Step 5: Simplify route-level Ant Design theme config**

Replace `frontend/src/routes/index.tsx` with:

```typescript
import { createRootRoute, createRoute, createRouter, Outlet } from '@tanstack/react-router'
import { ConfigProvider, App as AntApp, theme } from 'antd'
import { useThemeStore } from '@/stores/useThemeStore'
import { redirectIfAuthenticated, requireAuth, requireInit } from './-guards'
import LoginPage from '@/pages/login/LoginPage'
import DashboardPage from '@/pages/dashboard/DashboardPage'
import InitPage from '@/pages/init/InitPage'
import AppLayout from '@/layout'

const rootRoute = createRootRoute({
  component: function RootLayout() {
    const darkMode = useThemeStore((state) => state.darkMode)

    return (
      <ConfigProvider
        theme={{
          algorithm: darkMode ? theme.darkAlgorithm : theme.defaultAlgorithm,
          token: {
            borderRadius: 8,
          },
        }}
      >
        <AntApp>
          <Outlet />
        </AntApp>
      </ConfigProvider>
    )
  },
})

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  beforeLoad: redirectIfAuthenticated,
  component: LoginPage,
  validateSearch: (search: Record<string, unknown>) => ({
    redirect: typeof search.redirect === 'string' ? search.redirect : undefined,
  }),
})

const initRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/init',
  component: InitPage,
})

const layoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'layout',
  beforeLoad: async () => {
    await requireInit()
    requireAuth()
  },
  component: AppLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/',
  component: DashboardPage,
})

const routeTree = rootRoute.addChildren([
  initRoute,
  loginRoute,
  layoutRoute.addChildren([indexRoute]),
])

export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
})
```

- [ ] **Step 6: Run the theme store test and verify it passes**

Run:

```bash
cd frontend && npm test -- themeStore.test.ts
```

Expected: PASS with 2 tests.

- [ ] **Step 7: Verify configurable theme color references are gone**

Run:

```bash
rg -n "primaryColor|setPrimaryColor|ColorPicker|--app-primary-color|colorPrimary|Theme Color|COLOR_PRESETS" frontend/src frontend/tests
```

Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/stores/useThemeStore.ts frontend/src/App.tsx frontend/src/routes/index.tsx frontend/tests/themeStore.test.ts
git commit -m "refactor(frontend): remove configurable theme color state"
```

---

### Task 4: Run Focused And Full Verification

**Files:**
- Modify only if verification reveals a concrete issue in files changed by Tasks 1-3.

- [ ] **Step 1: Run focused tests**

Run:

```bash
cd frontend && npm test -- Navbar.theme.test.tsx AppLayout.settings.test.tsx themeStore.test.ts App.test.tsx
```

Expected: PASS for all focused tests.

- [ ] **Step 2: Run the full test suite once**

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

- [ ] **Step 5: Manually verify the header in light and dark mode**

Run the dev server:

```bash
cd frontend && npm run dev -- --host 127.0.0.1
```

Expected: Vite prints a local URL such as `http://127.0.0.1:5173/`.

Manual checks:
- In light mode, the top header is light and the hamburger/breadcrumb are dark enough to read.
- After toggling dark mode from the header switch, the top header changes to dark with readable hamburger/breadcrumb colors.
- The settings floating button is absent.
- No settings drawer can be opened.
- The original layout order remains: sidebar, navbar, tabs view, app main.
- On a phone viewport, the hamburger and header remain readable in both themes.

- [ ] **Step 6: Commit verification fixes if any were needed**

If Steps 1-5 required code changes, commit only those changed files:

```bash
git add frontend/src frontend/tests
git commit -m "fix(frontend): polish header theme verification issues"
```

If there were no code changes, skip this commit.

---

## Self-Review

- Spec coverage:
  - Fixes header staying light during theme changes: Task 1.
  - Uses current code and original layout structure: Tasks 1-2 modify `Navbar` and `AppLayout` in place.
  - Avoids a complex settings component: Task 2 deletes `Settings`.
  - Removes theme color settings: Task 3 removes `primaryColor`, `setPrimaryColor`, `ColorPicker`, and route token color config.
  - Keeps mobile behavior: Task 4 includes mobile manual verification and does not rewrite `Sidebar` or breakpoint behavior.
- Placeholder scan:
  - The plan includes concrete files, commands, and complete code blocks for each code change.
- Type consistency:
  - `useThemeStore` exposes only `mode`, `darkMode`, `setMode`, `setDarkMode`, and `toggleMode`.
  - `useSettingsStore` exposes only `showTagsView`, `showSidebarLogo`, and `fixedHeader`, matching remaining consumers.
  - `Navbar` references `styles.navbarDark`, which is defined in the same task.
