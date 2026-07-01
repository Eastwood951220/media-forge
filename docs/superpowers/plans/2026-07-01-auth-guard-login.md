# Auth Guard + Login Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add TanStack Router route guards (auth required / redirect-if-authenticated) and a login page with Ant Design form, adapted from ruoyi-react but using static routes instead of dynamic routes.

**Architecture:** TanStack Router file-based routes with `beforeLoad` guards. `requireAuth` checks `useAuthStore.getState().isAuthenticated` and redirects to `/login`. `redirectIfAuthenticated` sends logged-in users away from `/login`. Login page posts credentials to `/auth/login` and calls `setLoginState` on success. `App.tsx` gains a simple auth bootstrap effect.

**Tech Stack:** TanStack Router 1.x, Ant Design 6, Less, Zustand 5

## Reference Source

Adapted from: `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/`

## Global Constraints

- Static routes only — no `getRouters()` API, no `usePermissionStore`, no dynamic route loading
- Login page: username + password + remember me (no tenant, no captcha)
- Route guard: `requireAuth` beforeLoad on protected routes, `redirectIfAuthenticated` on login route
- `useAuthStore` already exists with `token`, `isAuthenticated`, `setLoginState`, `logout`
- `js-cookie` and `axios` already in dependencies
- All new pages go under `src/pages/`
- The smoke test (`tests/App.test.tsx`) must still pass

---

### Task 1: Create route guards

**Files:**
- Create: `frontend/src/routes/guards.ts`

**Interfaces:**
- Consumes: `useAuthStore` from `@/store/useAuthStore`
- Produces: `requireAuth` — beforeLoad that redirects to `/login` if not authenticated; `redirectIfAuthenticated` — beforeLoad that redirects to `/` if already authenticated
- Consumed by: route files (Tasks 5-6)

- [ ] **Step 1: Write the file**

```typescript
import { redirect } from '@tanstack/react-router'
import { useAuthStore } from '@/store/useAuthStore'

export function requireAuth() {
  const { isAuthenticated } = useAuthStore.getState()

  if (!isAuthenticated) {
    const currentPath = window.location.pathname + window.location.search

    throw redirect({
      to: '/login',
      search: currentPath !== '/login' ? { redirect: currentPath } : undefined,
    })
  }
}

export function redirectIfAuthenticated() {
  const { isAuthenticated } = useAuthStore.getState()

  if (isAuthenticated) {
    throw redirect({ to: '/' })
  }
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/routes/guards.ts
git commit -m "feat: add route guards (requireAuth + redirectIfAuthenticated)"
```

---

### Task 2: Create login API

**Files:**
- Create: `frontend/src/api/login/index.ts`
- Create: `frontend/src/api/login/types.ts`

**Interfaces:**
- Consumes: `request` from `@/request` (the unified request function)
- Produces: `login(params): Promise<LoginResult>` and `LoginParams` / `LoginResult` types
- Consumed by: LoginPage (Task 4)

- [ ] **Step 1: Write src/api/login/types.ts**

```typescript
export interface LoginParams {
  username: string
  password: string
}

export interface LoginResult {
  access_token: string
  token_type?: string
  expires_in?: number
}
```

- [ ] **Step 2: Write src/api/login/index.ts**

```typescript
import { request } from '@/request'
import type { LoginParams, LoginResult } from './types'

export function login(data: LoginParams): Promise<LoginResult> {
  return request<LoginResult>({
    url: '/auth/login',
    method: 'post',
    data,
    isToken: false,
    isRepeatSubmit: false,
  })
}

export function logout(): Promise<void> {
  return request({
    url: '/auth/logout',
    method: 'post',
  })
}
```

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/api/login/index.ts src/api/login/types.ts
git commit -m "feat: add login API (login/logout)"
```

---

### Task 3: Create dashboard placeholder page

**Files:**
- Create: `frontend/src/pages/dashboard/DashboardPage.tsx`

**Interfaces:**
- Produces: `DashboardPage` — a simple welcome component
- Consumed by: index route (Task 5)

- [ ] **Step 1: Write the file**

```typescript
import { Typography } from 'antd'

const { Title, Paragraph } = Typography

function DashboardPage() {
  return (
    <div className="p-8">
      <Title level={1}>Media Forge 🎬</Title>
      <Paragraph>Welcome to Media Forge dashboard.</Paragraph>
    </div>
  )
}

export default DashboardPage
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/pages/dashboard/DashboardPage.tsx
git commit -m "feat: add dashboard placeholder page"
```

---

### Task 4: Create login page

**Files:**
- Create: `frontend/src/pages/login/LoginPage.tsx`
- Create: `frontend/src/pages/login/LoginPage.module.less`

**Interfaces:**
- Consumes: `login` from `@/api/login` (Task 2), `useAuthStore` from `@/store/useAuthStore`
- Produces: `LoginPage` component
- Consumed by: login route (Task 5)

- [ ] **Step 1: Write src/pages/login/LoginPage.module.less**

```less
.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 430px;
  padding: 40px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 12px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15);
  backdrop-filter: blur(10px);
}

.login-title {
  text-align: center;
  margin-bottom: 32px;

  h2 {
    font-size: 28px;
    color: #333;
    margin: 0 0 8px;
  }

  p {
    color: #999;
    margin: 0;
    font-size: 14px;
  }
}

.login-form {
  .remember-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  .login-btn {
    width: 100%;
    height: 44px;
    font-size: 16px;
  }
}
```

- [ ] **Step 2: Write src/pages/login/LoginPage.tsx**

```typescript
import { useState } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { Form, Input, Button, Checkbox, message } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { login } from '@/api/login'
import { useAuthStore } from '@/store/useAuthStore'
import styles from './LoginPage.module.less'

interface LoginFormValues {
  username: string
  password: string
  rememberMe: boolean
}

function LoginPage() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const search = useSearch({ from: '/login' }) as { redirect?: string }
  const setLoginState = useAuthStore((s) => s.setLoginState)

  const handleFinish = async (values: LoginFormValues) => {
    setLoading(true)
    try {
      const res = await login({
        username: values.username,
        password: values.password,
      })
      const token = (res as unknown as { data?: { access_token?: string } }).data?.access_token
        ?? (res as unknown as { access_token?: string }).access_token

      if (!token) {
        void message.error('登录失败：未获取到 token')
        return
      }

      setLoginState(token)
      void message.success('登录成功')

      await navigate({ to: search.redirect || '/' })
    } catch {
      void message.error('登录失败，请检查用户名和密码')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles['login-page']}>
      <div className={styles['login-card']}>
        <div className={styles['login-title']}>
          <h2>Media Forge</h2>
          <p>媒体处理平台</p>
        </div>

        <Form<LoginFormValues>
          className={styles['login-form']}
          initialValues={{
            username: 'admin',
            password: 'admin123',
            rememberMe: false,
          }}
          onFinish={(values) => {
            void handleFinish(values)
          }}
          size="large"
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入您的账号' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="账号" />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入您的密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>

          <div className={styles['remember-row']}>
            <Form.Item name="rememberMe" valuePropName="checked" noStyle>
              <Checkbox>记住密码</Checkbox>
            </Form.Item>
          </div>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              className={styles['login-btn']}
            >
              登录
            </Button>
          </Form.Item>
        </Form>
      </div>
    </div>
  )
}

export default LoginPage
```

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/pages/login/LoginPage.tsx src/pages/login/LoginPage.module.less
git commit -m "feat: add login page with Ant Design form"
```

---

### Task 5: Create static route files

**Files:**
- Create: `frontend/src/routes/login.tsx`
- Create: `frontend/src/routes/index.tsx`

**Interfaces:**
- Consumes: `requireAuth` / `redirectIfAuthenticated` from `./guards` (Task 1), `LoginPage` (Task 4), `DashboardPage` (Task 3)
- Produces: File-based routes for `/login` and `/` (index)
- Consumed by: auto-generated `routeTree.gen.ts`

- [ ] **Step 1: Write src/routes/login.tsx**

```typescript
import { createFileRoute } from '@tanstack/react-router'
import { redirectIfAuthenticated } from './guards'
import LoginPage from '@/pages/login/LoginPage'

export const Route = createFileRoute('/login')({
  beforeLoad: redirectIfAuthenticated,
  component: LoginPage,
  validateSearch: (search: Record<string, unknown>) => ({
    redirect: typeof search.redirect === 'string' ? search.redirect : undefined,
  }),
})
```

- [ ] **Step 2: Write src/routes/index.tsx**

```typescript
import { createFileRoute } from '@tanstack/react-router'
import { requireAuth } from './guards'
import DashboardPage from '@/pages/dashboard/DashboardPage'

export const Route = createFileRoute('/')({
  beforeLoad: requireAuth,
  component: DashboardPage,
})
```

- [ ] **Step 3: Regenerate the route tree**

The TanStack Router Vite plugin auto-generates the route tree on dev/build. Run a quick build to trigger it:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npm run build 2>&1 | tail -5
```

Expected: Build succeeds. `src/routeTree.gen.ts` now includes `/login` and `/` routes.

- [ ] **Step 4: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/routes/login.tsx src/routes/index.tsx src/routeTree.gen.ts
git commit -m "feat: add static routes (login + index) with guards"
```

---

### Task 6: Update `__root.tsx` — remove dashboard content from root layout

**Files:**
- Modify: `frontend/src/routes/__root.tsx`

**Context:** The root route currently has the "Media Forge 🎬" title and padding — that's now the dashboard's responsibility. The root layout should be a clean wrapper that provides the Ant Design `ConfigProvider`.

- [ ] **Step 1: Rewrite __root.tsx**

```typescript
import { createRootRoute, Outlet } from '@tanstack/react-router'
import { ConfigProvider, App as AntApp } from 'antd'

export const Route = createRootRoute({
  component: () => (
    <ConfigProvider>
      <AntApp>
        <Outlet />
      </AntApp>
    </ConfigProvider>
  ),
})
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/routes/__root.tsx
git commit -m "refactor: simplify root route to ConfigProvider wrapper"
```

---

### Task 7: Update `App.tsx` — add auth bootstrap

**Files:**
- Modify: `frontend/src/App.tsx`

**Context:** The App component should check if the user is authenticated on mount. Currently it just renders the router. Adapted from ruoyi's `Root` component — but simplified: no dynamic route loading, no theme sync.

- [ ] **Step 1: Rewrite App.tsx**

```typescript
import { useState, useEffect } from 'react'
import './styles/app.css'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { routeTree } from './routeTree.gen'
import { queryClient } from './lib/query-client'
import { QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/store/useAuthStore'
import { Spin } from 'antd'

const router = createRouter({
  routeTree,
  context: {
    queryClient,
  },
  defaultPreload: 'intent',
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (isAuthenticated) {
      // In the future, loadUserInfo() will be called here.
      // For now, just mark as ready.
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

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/App.tsx
git commit -m "feat: add auth bootstrap to App component"
```

---

### Task 8: Update smoke test for new route structure

**Files:**
- Modify: `frontend/tests/App.test.tsx`

**Context:** The smoke test currently renders the full App and asserts "Media Forge" text. Now "Media Forge" lives on the dashboard page (which requires auth). The test needs to account for this. The simplest fix: set auth state before rendering.

- [ ] **Step 1: Rewrite tests/App.test.tsx**

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { createMemoryHistory } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { routeTree } from '../src/routeTree.gen'
import { queryClient } from '../src/lib/query-client'
import { useAuthStore } from '../src/store/useAuthStore'

function renderApp() {
  const history = createMemoryHistory({ initialEntries: ['/'] })
  const router = createRouter({
    routeTree,
    context: { queryClient },
    history,
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

describe('App smoke test', () => {
  beforeEach(() => {
    // Reset auth state before each test
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
    renderApp()

    await waitFor(() => {
      // Unauthenticated user should see login form
      expect(screen.getByText(/media forge/i)).toBeInTheDocument()
      expect(screen.getByText(/媒体处理平台/i)).toBeInTheDocument()
    })
  })

  it('shows dashboard for authenticated user', async () => {
    useAuthStore.setState({ token: 'test-token', isAuthenticated: true })

    renderApp()

    await waitFor(() => {
      expect(screen.getByText(/media forge/i)).toBeInTheDocument()
      expect(screen.getByText(/welcome to media forge dashboard/i)).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 2: Run tests — TDD: they should fail or pass**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && ./node_modules/.bin/vitest run
```

Expected: Tests pass (2 tests — one for unauthenticated, one for authenticated).

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f tests/App.test.tsx
git commit -m "test: update smoke test for auth guard and login page"
```

---

### Task 9: Final verification

**Files:** (none — verification only)

- [ ] **Step 1: Run full verification**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
./node_modules/.bin/tsc -b && echo "✅ TSC"
./node_modules/.bin/eslint . && echo "✅ LINT"
npm run build && echo "✅ BUILD"
./node_modules/.bin/vitest run && echo "✅ TEST"
```

Expected: All four pass.

- [ ] **Step 2: Commit any fixes if needed**
