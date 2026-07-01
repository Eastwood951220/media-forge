# ThemeModeToggle + Manual Routes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add dark/light theme mode toggle with View Transition API animation, and switch from auto-generated file-based routes to manual code-based route definitions (ruoyi-react pattern).

**Architecture:** Theme uses a persisted Zustand store (`useThemeStore`) + `useThemeViewTransition` hook for animated switching. Routes are defined manually via `createRoute()`/`createRouter()` in `src/routes/index.tsx`, eliminating the auto-generated `routeTree.gen.ts` and the TanStack Router Vite plugin.

**Tech Stack:** Zustand 5, Ant Design 6 `theme.algorithm`, View Transition API, TanStack Router 1.x (code-based routes)

## Reference Source

Adapted from: `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/`

## Global Constraints

- `routeTree.gen.ts` deleted; TanStack Router Vite plugin removed from `vite.config.ts`
- Routes defined manually in `src/routes/index.tsx` using `createRoute()`/`createRouter()`
- Theme toggle uses Ant Design `Switch` with `MoonOutlined`/`BulbOutlined` icons
- View Transition API animation: circular clip-path reveal from toggle position
- `data-theme` attribute synced to `document.documentElement`
- `ConfigProvider` receives `theme.algorithm` (darkAlgorithm / defaultAlgorithm)
- All existing functionality preserved: tsc, lint, build, test

---

### Task 1: Create `useThemeStore` (Zustand)

**Files:**
- Create: `frontend/src/stores/useThemeStore.ts`

**Interfaces:**
- Produces: `useThemeStore` — persisted Zustand store with `mode`, `darkMode`, `primaryColor`, `toggleMode()`, `setPrimaryColor()`
- Consumed by: ThemeModeToggle (Task 3), ConfigProvider (Task 5), App.tsx (Task 6)

- [ ] **Step 1: Write the file**

```typescript
import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

type ThemeMode = 'light' | 'dark'

type ThemeState = {
  mode: ThemeMode
  darkMode: boolean
  primaryColor: string
  setMode: (mode: ThemeMode) => void
  setDarkMode: (darkMode: boolean) => void
  toggleMode: () => void
  setPrimaryColor: (color: string) => void
}

export const useThemeStore = create<ThemeState>()(
  devtools(
    persist(
      (set) => ({
        mode: 'light',
        darkMode: false,
        primaryColor: '#0f3076',

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

        setPrimaryColor: (primaryColor) => set({ primaryColor }),
      }),
      {
        name: 'media-forge-theme',
      },
    ),
  ),
)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/stores/useThemeStore.ts
git commit -m "feat: add theme store (Zustand with persist)"
```

---

### Task 2: Create `useThemeViewTransition` hook

**Files:**
- Create: `frontend/src/hooks/useThemeViewTransition/index.ts`
- Create: `frontend/src/hooks/useThemeViewTransition/types.ts`

**Interfaces:**
- Produces: `useThemeViewTransition({ toggleTheme })` → `{ runTransition, transitioning, triggerRef }`
- Consumed by: ThemeModeToggle (Task 3)

- [ ] **Step 1: Write types.ts**

```typescript
export type ViewTransitionLike = {
  ready: Promise<void>
}

export type StartViewTransition = (callback: () => void | Promise<void>) => ViewTransitionLike

export type UseThemeViewTransitionOptions = {
  duration?: number
  easing?: string
  toggleTheme: () => void
}
```

- [ ] **Step 2: Write index.ts**

```typescript
import { useCallback, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { useThemeStore } from '@/stores/useThemeStore'
import type { StartViewTransition, UseThemeViewTransitionOptions } from './types'

const DEFAULT_DURATION = 900
const DEFAULT_EASING = 'cubic-bezier(0.22, 1, 0.36, 1)'
const TRANSITION_CLASS = 'theme-transition-active'

function shouldSkipTransition(): boolean {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return true
  }
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

function getStartViewTransition(): StartViewTransition | null {
  if (typeof document === 'undefined') {
    return null
  }
  const doc = document as Document & { startViewTransition?: StartViewTransition }
  const fn = doc.startViewTransition
  return typeof fn === 'function' ? fn.bind(doc) : null
}

export function useThemeViewTransition({
  duration = DEFAULT_DURATION,
  easing = DEFAULT_EASING,
  toggleTheme,
}: UseThemeViewTransitionOptions) {
  const transitionLockRef = useRef(false)
  const triggerRef = useRef<HTMLDivElement | null>(null)
  const [transitioning, setTransitioning] = useState(false)

  const runTransition = useCallback(async () => {
    if (transitionLockRef.current) {
      return
    }

    const triggerEl = triggerRef.current
    const startViewTransition = getStartViewTransition()

    if (!triggerEl || !startViewTransition || shouldSkipTransition()) {
      toggleTheme()
      return
    }

    transitionLockRef.current = true
    setTransitioning(true)

    const root = document.documentElement

    try {
      const transition = startViewTransition(() => {
        const nextDark = !useThemeStore.getState().darkMode
        root.dataset.theme = nextDark ? 'dark' : 'light'
        root.classList.add(TRANSITION_CLASS)
        flushSync(() => {
          toggleTheme()
        })
      })

      await transition.ready

      const { top, left, width, height } = triggerEl.getBoundingClientRect()
      const x = left + width / 2
      const y = top + height / 2
      const right = window.innerWidth - x
      const bottom = window.innerHeight - y
      const maxRadius = Math.hypot(Math.max(x, right), Math.max(y, bottom))

      const oldAnim = root.animate(
        { opacity: [1, 1] },
        { duration, pseudoElement: '::view-transition-old(root)' },
      )

      const newAnim = root.animate(
        {
          clipPath: [
            `circle(0px at ${x}px ${y}px)`,
            `circle(${maxRadius}px at ${x}px ${y}px)`,
          ],
        },
        { duration, easing, pseudoElement: '::view-transition-new(root)' },
      )

      await newAnim.finished
      oldAnim.commitStyles()
    } catch (error) {
      console.warn('[theme transition] failed:', error)
    } finally {
      root.classList.remove(TRANSITION_CLASS)
      transitionLockRef.current = false
      setTransitioning(false)
    }
  }, [duration, easing, toggleTheme])

  return { runTransition, transitioning, triggerRef }
}

export type { UseThemeViewTransitionOptions, ViewTransitionLike, StartViewTransition } from './types'
```

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/hooks/useThemeViewTransition/index.ts src/hooks/useThemeViewTransition/types.ts
git commit -m "feat: add useThemeViewTransition hook (View Transition API)"
```

---

### Task 3: Create `ThemeModeToggle` component

**Files:**
- Create: `frontend/src/components/ThemeModeToggle/index.tsx`
- Create: `frontend/src/components/ThemeModeToggle/index.module.less`

**Interfaces:**
- Consumes: `useThemeStore` (Task 1), `useThemeViewTransition` (Task 2)
- Produces: `<ThemeModeToggle variant="header" | "login" size="small" | "middle" />`
- Consumed by: LoginPage (Task 7), future Header component

- [ ] **Step 1: Write index.module.less**

```less
.toggleWrap {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.header {
  flex: 0 0 auto;
}

.login {
  // inherits from parent layout
}

.label {
  font-size: 14px;
  line-height: 1;
  white-space: nowrap;
}
```

- [ ] **Step 2: Write index.tsx**

```typescript
import { BulbOutlined, MoonOutlined } from '@ant-design/icons'
import { Switch } from 'antd'
import { useThemeViewTransition } from '@/hooks/useThemeViewTransition'
import { useThemeStore } from '@/stores/useThemeStore'
import styles from './index.module.less'

export type ThemeModeToggleProps = {
  className?: string
  variant?: 'header' | 'login'
  size?: 'small' | 'middle'
}

export function ThemeModeToggle({
  className,
  variant = 'header',
  size = 'middle',
}: ThemeModeToggleProps) {
  const darkMode = useThemeStore((state) => state.darkMode)
  const toggleMode = useThemeStore((state) => state.toggleMode)
  const { runTransition, transitioning, triggerRef } = useThemeViewTransition({
    toggleTheme: toggleMode,
  })

  return (
    <div
      ref={triggerRef}
      className={`${styles.toggleWrap} ${styles[variant]} ${className ?? ''}`}
    >
      {variant === 'login' ? (
        <span className={styles.label}>
          {darkMode ? '深色模式' : '浅色模式'}
        </span>
      ) : null}
      <Switch
        aria-label="切换明暗模式"
        checked={darkMode}
        checkedChildren={<MoonOutlined />}
        disabled={transitioning}
        loading={transitioning}
        size={size}
        unCheckedChildren={<BulbOutlined />}
        onChange={runTransition}
      />
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/components/ThemeModeToggle/index.tsx src/components/ThemeModeToggle/index.module.less
git commit -m "feat: add ThemeModeToggle component"
```

---

### Task 4: Convert to manual route definitions

**Files:**
- Rewrite: `frontend/src/routes/index.tsx` (manual route tree)
- Delete: `frontend/src/routes/login.tsx` (file-based — replaced)
- Delete: `frontend/src/routeTree.gen.ts` (auto-generated — replaced)
- Modify: `frontend/vite.config.ts` (remove TanStackRouterVite plugin)
- Modify: `frontend/src/routes/-guards.ts` (adapt to location-based guards if needed)

**Context:** The current setup uses TanStack Router file-based routes. We're switching to manual code-based routes following ruoyi-react's pattern.

- [ ] **Step 1: Rewrite src/routes/index.tsx**

```typescript
import { createRootRoute, createRoute, createRouter } from '@tanstack/react-router'
import { redirectIfAuthenticated, requireAuth } from './-guards'
import LoginPage from '@/pages/login/LoginPage'
import DashboardPage from '@/pages/dashboard/DashboardPage'

// Root route (layout wrapper)
const rootRoute = createRootRoute({
  component: () => {
    // Reuse __root.tsx component
    const { Route } = require('./__root')
    return <Route.options.component />
  },
})

// Login route — public, redirects authenticated users away
const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  beforeLoad: redirectIfAuthenticated,
  component: LoginPage,
})

// Index route — protected, requires authentication
const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: requireAuth,
  component: DashboardPage,
})

// Build route tree
const routeTree = rootRoute.addChildren([loginRoute, indexRoute])

// Create router
export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
```

**Important:** The above has a problem — `require('./__root')` is a dynamic require. Instead, import the component. Let's simplify by importing `__root.tsx` Route's component directly, or just define the root route inline. Update:

```typescript
import { createRootRoute, createRoute, createRouter } from '@tanstack/react-router'
import { ConfigProvider, App as AntApp } from 'antd'
import { Outlet } from '@tanstack/react-router'
import { redirectIfAuthenticated, requireAuth } from './-guards'
import LoginPage from '@/pages/login/LoginPage'
import DashboardPage from '@/pages/dashboard/DashboardPage'

// Root route — ConfigProvider layout wrapper
const rootRoute = createRootRoute({
  component: () => (
    <ConfigProvider>
      <AntApp>
        <Outlet />
      </AntApp>
    </ConfigProvider>
  ),
})

// Login route — public, redirects authenticated users away
const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  beforeLoad: redirectIfAuthenticated,
  component: LoginPage,
})

// Index route — protected, requires authentication
const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: requireAuth,
  component: DashboardPage,
})

// Build route tree
const routeTree = rootRoute.addChildren([loginRoute, indexRoute])

// Create router
export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
```

This replaces `__root.tsx` — the root route is now defined inline in `index.tsx`. `__root.tsx` can be deleted (it's no longer needed as a separate file).

- [ ] **Step 2: Delete old route files**

```bash
rm /Users/eastwood/Code/PycharmProjects/media-forge/frontend/src/routes/login.tsx
rm /Users/eastwood/Code/PycharmProjects/media-forge/frontend/src/routes/__root.tsx
rm /Users/eastwood/Code/PycharmProjects/media-forge/frontend/src/routeTree.gen.ts
```

- [ ] **Step 3: Remove TanStackRouterVite plugin from vite.config.ts**

Read `vite.config.ts`. Remove the import and plugin line:
- Remove `import { TanStackRouterVite } from '@tanstack/router-plugin/vite'`
- Remove `TanStackRouterVite(),` from the plugins array

- [ ] **Step 4: Update guards — remove file-route specific paths**

Read `src/routes/-guards.ts`. The current implementation should work as-is since it uses `useAuthStore.getState()` and doesn't depend on the route format. Verify it doesn't import from `createFileRoute`.

If no changes needed, leave as-is.

- [ ] **Step 5: Verify tsc + build**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b 2>&1 | head -20
```

Expected: Zero errors.

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npm run build 2>&1 | tail -5
```

Expected: Build succeeds.

- [ ] **Step 6: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/routes/index.tsx
git rm --cached src/routes/login.tsx src/routes/__root.tsx src/routeTree.gen.ts 2>/dev/null
git add -f vite.config.ts
git rm --cached src/routes/login.tsx src/routes/__root.tsx src/routeTree.gen.ts 2>/dev/null
git add -f src/routes/login.tsx src/routes/__root.tsx src/routeTree.gen.ts 2>/dev/null
git commit -m "refactor: convert to manual route definitions, remove routeTree.gen.ts"
```

---

### Task 5: Wire theme into ConfigProvider

**Files:**
- Modify: `frontend/src/routes/index.tsx` (update root route component)

**Context:** The root route's ConfigProvider needs to receive Ant Design's theme algorithm. This is currently a static ConfigProvider — we need to make it read from `useThemeStore`.

**NOTE:** `createRootRoute({ component })` expects a React component. The `useThemeStore` hook can be used inside it since it's a React component.

- [ ] **Step 1: Update the root route in src/routes/index.tsx**

Replace the current rootRoute definition with:

```typescript
import { theme } from 'antd'

// Root route — ConfigProvider with theme
const rootRoute = createRootRoute({
  component: function RootLayout() {
    const darkMode = useThemeStore((state) => state.darkMode)
    const primaryColor = useThemeStore((state) => state.primaryColor)

    return (
      <ConfigProvider
        theme={{
          algorithm: darkMode ? theme.darkAlgorithm : theme.defaultAlgorithm,
          token: {
            colorPrimary: primaryColor,
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
```

Add the import at the top:
```typescript
import { useThemeStore } from '@/stores/useThemeStore'
```

- [ ] **Step 2: Verify tsc**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b 2>&1 | head -10
```

Expected: Zero errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/routes/index.tsx
git commit -m "feat: wire Ant Design theme algorithm into ConfigProvider"
```

---

### Task 6: Update `App.tsx` — sync theme to DOM + import manual router

**Files:**
- Modify: `frontend/src/App.tsx`

**Context:** `App.tsx` currently imports `routeTree` from `./routeTree.gen`. It needs to import `router` from `./routes/index`. Also needs a `useEffect` to sync `data-theme` on `document.documentElement`.

- [ ] **Step 1: Rewrite App.tsx**

```typescript
import { useState, useEffect } from 'react'
import './styles/app.css'
import { RouterProvider } from '@tanstack/react-router'
import { router } from './routes'
import { queryClient } from './lib/query-client'
import { QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/useAuthStore'
import { useThemeStore } from '@/stores/useThemeStore'
import { Spin } from 'antd'

function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const darkMode = useThemeStore((s) => s.darkMode)
  const primaryColor = useThemeStore((s) => s.primaryColor)
  const [ready, setReady] = useState(false)

  // Sync data-theme to <html> for Tailwind dark mode + CSS custom properties
  useEffect(() => {
    document.documentElement.dataset.theme = darkMode ? 'dark' : 'light'
    document.documentElement.style.setProperty('--app-primary-color', primaryColor)
  }, [darkMode, primaryColor])

  useEffect(() => {
    if (isAuthenticated) {
      setReady(true)
    } else {
      setReady(true)
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

- [ ] **Step 2: Verify**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b && npm run build 2>&1 | tail -3
```

Expected: Zero errors, build succeeds.

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/App.tsx
git commit -m "feat: sync theme to DOM, import manual router"
```

---

### Task 7: Add ThemeModeToggle to login page

**Files:**
- Modify: `frontend/src/pages/login/LoginPage.tsx`
- Modify: `frontend/src/pages/login/LoginPage.module.less`

- [ ] **Step 1: Add toggle class to LoginPage.module.less**

Append to the file:

```less
.theme-toggle {
  position: fixed;
  top: 24px;
  right: 24px;
  z-index: 10;
}
```

- [ ] **Step 2: Add ThemeModeToggle to LoginPage**

Read the current file. Add import:
```typescript
import { ThemeModeToggle } from '@/components/ThemeModeToggle'
```

Add inside the login-page div, before the login-card:
```tsx
<div className={styles['theme-toggle']}>
  <ThemeModeToggle variant="login" size="middle" />
</div>
```

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/pages/login/LoginPage.tsx src/pages/login/LoginPage.module.less
git commit -m "feat: add theme toggle to login page"
```

---

### Task 8: Update smoke test for manual routes

**Files:**
- Modify: `frontend/tests/App.test.tsx`

**Context:** The test currently imports `routeTree` from `../src/routeTree.gen`. It must now import `router` from `../src/routes`.

- [ ] **Step 1: Rewrite tests/App.test.tsx**

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { RouterProvider } from '@tanstack/react-router'
import { createMemoryHistory } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { router } from '../src/routes'
import { queryClient } from '../src/lib/query-client'
import { useAuthStore } from '../src/stores/useAuthStore'

function renderApp(initialPath = '/') {
  const history = createMemoryHistory({ initialEntries: [initialPath] })
  // Create a fresh router instance with memory history for each test
  const testRouter = {
    ...router,
    history,
  }

  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={testRouter as typeof router} />
    </QueryClientProvider>,
  )
}

describe('App auth routing', () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: '',
      isAuthenticated: false,
      userInfo: null,
      roles: [],
      permissions: [],
      hasUserInfo: false,
    })
  })

  it('redirects unauthenticated user to login page', async () => {
    renderApp('/')

    await waitFor(() => {
      const elements = screen.getAllByText(/media forge/i)
      expect(elements.length).toBeGreaterThan(0)
      expect(screen.getByText(/媒体处理平台/i)).toBeInTheDocument()
    })
  })

  it('shows dashboard for authenticated user', async () => {
    useAuthStore.setState({ token: 'test-token', isAuthenticated: true })

    renderApp('/')

    await waitFor(() => {
      const elements = screen.getAllByText(/media forge/i)
      expect(elements.length).toBeGreaterThan(0)
      expect(screen.getByText(/welcome to media forge dashboard/i)).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 2: Run tests**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && ./node_modules/.bin/vitest run
```

Expected: 2 tests pass.

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f tests/App.test.tsx
git commit -m "test: update smoke test for manual router"
```

---

### Task 9: Final verification

**Files:** (none — verification only)

- [ ] **Step 1: Full verification**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && ./node_modules/.bin/tsc -b && echo "✅ TSC" && ./node_modules/.bin/eslint . && echo "✅ LINT" && npm run build && echo "✅ BUILD" && ./node_modules/.bin/vitest run && echo "✅ TEST"
```

Expected: All four pass.

- [ ] **Step 2: Commit any fixes**
