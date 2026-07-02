# Auth 401 And TagsView Context Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix stale-token `{"detail":"Invalid or expired token"}` failures and make TagsView track crawler task pages with a RuoYi-style right-click menu.

**Architecture:** Handle bare HTTP 401 responses from FastAPI at the request error boundary, immediately clearing the invalid token/cookie and redirecting to login with the current URL as `redirect`. Replace the hardcoded dashboard-only TagsView with a persisted route-aware visited-view store adapted from `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/layout/TagsView`, using Media Forge's manual route map for titles and affix behavior.

**Tech Stack:** React 19, TypeScript 6, Zustand 5, TanStack Router, Axios, Ant Design 6, Vitest, React Testing Library.

---

## Root Cause Notes

- Backend raises `HTTPException(status_code=401, detail="Invalid or expired token")` in `backend/app/core/dependencies.py` when JWT decode fails.
- Frontend request success transform handles business-code `401`, but `handleResponseError()` only shows a generic network message for bare HTTP 401 responses.
- `useAuthStore.isLoggedIn()` trusts persisted state/cookie presence. If the backend secret changes or a token expires, the app still enters protected pages and the API returns `Invalid or expired token`.
- `frontend/src/layout/TagsView/index.tsx` currently renders only an affix dashboard tag and never adds `/crawler/tasks` or `/crawler/tasks/new`.
- RuoYi reference implements a store-backed `visitedViews` list, route-derived titles, close actions, middle-click close, and a fixed-position right-click context menu.

## File Structure

- Modify `frontend/src/request/transform.ts` to handle HTTP 401 errors by clearing auth and redirecting.
- Modify `frontend/src/stores/useAuthStore.ts` so persisted token state cannot disagree with cookie state.
- Create `frontend/src/stores/useTagsViewStore.ts` for persisted visited tags and close operations.
- Create `frontend/src/routes/tags.ts` for route title/affix/active-menu metadata used by TagsView.
- Modify `frontend/src/layout/TagsView/index.tsx` to add current routes as tags and implement context menu actions.
- Modify `frontend/src/layout/TagsView/TagsView.module.less` for close icons and right-click menu styling from the RuoYi reference.
- Modify `frontend/src/layout/Sidebar/index.tsx` only if route labels need to align with `frontend/src/routes/tags.ts`.
- Add `frontend/tests/auth-invalid-token.test.ts` for HTTP 401 cleanup.
- Add `frontend/tests/tags-view.ui.test.tsx` for crawler task tags and context menu actions.
- Update `frontend/tests/layout.ui.test.tsx` if existing hardcoded dashboard tag assertions need to include crawler task tags.

---

### Task 1: Fix HTTP 401 Invalid Token Handling

**Files:**
- Modify: `frontend/src/request/transform.ts`
- Modify: `frontend/src/stores/useAuthStore.ts`
- Test: `frontend/tests/auth-invalid-token.test.ts`

- [ ] **Step 1: Write the failing HTTP 401 cleanup test**

Create `frontend/tests/auth-invalid-token.test.ts`:

```ts
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { AxiosError } from 'axios'
import { handleResponseError, isRelogin } from '../src/request/transform'
import { useAuthStore } from '../src/stores/useAuthStore'
import { getToken, setToken } from '../src/utils/auth'

vi.mock('antd', () => ({
  message: { error: vi.fn() },
  notification: { error: vi.fn() },
  Modal: {
    confirm: vi.fn(),
  },
}))

function http401Error(): AxiosError {
  return {
    name: 'AxiosError',
    message: 'Request failed with status code 401',
    isAxiosError: true,
    toJSON: () => ({}),
    config: {
      url: '/api/crawler/tasks',
      method: 'get',
      headers: {},
    },
    response: {
      status: 401,
      statusText: 'Unauthorized',
      headers: {},
      config: {
        url: '/api/crawler/tasks',
        method: 'get',
        headers: {},
      },
      data: { detail: 'Invalid or expired token' },
    },
  } as AxiosError
}

describe('HTTP 401 invalid token handling', () => {
  beforeEach(() => {
    isRelogin.show = false
    setToken('expired-token')
    useAuthStore.setState({
      token: 'expired-token',
      isAuthenticated: true,
      userInfo: null,
    })
  })

  it('clears stale auth state when FastAPI returns bare HTTP 401', async () => {
    await expect(handleResponseError(http401Error())).rejects.toThrow('Invalid or expired token')

    expect(getToken()).toBeNull()
    expect(useAuthStore.getState().token).toBe('')
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd frontend && npm test -- auth-invalid-token.test.ts
```

Expected: FAIL because `handleResponseError()` currently leaves the stale cookie and auth store untouched for HTTP 401.

- [ ] **Step 3: Make persisted auth state require a valid cookie token**

Modify `frontend/src/stores/useAuthStore.ts`:

```ts
import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'
import { getToken, removeToken, setToken } from '@/utils/auth.ts'

type UserInfo = {
  userId?: number | string
  username: string
  displayName: string
  avatar?: string
}

type AuthState = {
  token: string
  userInfo: UserInfo | null
  isAuthenticated: boolean
  setLoginState: (token: string, userInfo?: UserInfo | null) => void
  logout: () => void
  syncFromCookie: () => void
}

function cookieToken(): string {
  return getToken() ?? ''
}

export const useAuthStore = create<AuthState>()(
  devtools(
    persist(
      (set) => ({
        token: cookieToken(),
        userInfo: null,
        isAuthenticated: Boolean(cookieToken()),

        setLoginState: (token, userInfo) => {
          setToken(token)
          set({
            token,
            userInfo: userInfo ?? null,
            isAuthenticated: true,
          })
        },

        logout: () => {
          removeToken()
          set({
            token: '',
            userInfo: null,
            isAuthenticated: false,
          })
        },

        syncFromCookie: () => {
          const token = cookieToken()
          set({
            token,
            isAuthenticated: Boolean(token),
          })
        },
      }),
      {
        name: 'media-forge-auth',
        partialize: (state) => ({
          token: state.token,
          isAuthenticated: state.isAuthenticated,
        }),
        onRehydrateStorage: () => (state) => {
          state?.syncFromCookie()
        },
      },
    ),
  ),
)

/** Check if user is logged in — token from cookie must exist AND state must agree. */
export function isLoggedIn(): boolean {
  const cookie = getToken()
  const { token, isAuthenticated } = useAuthStore.getState()
  return Boolean(cookie) && Boolean(token) && isAuthenticated
}
```

- [ ] **Step 4: Handle bare HTTP 401 in request error transform**

Modify `frontend/src/request/transform.ts`:

```ts
import { message, Modal, notification } from 'antd'
import type { AxiosError, AxiosResponse } from 'axios'
import { HttpStatus } from '@/enums/RespEnum'
import { useAuthStore } from '@/stores/useAuthStore.ts'
import errorCode from '@/request/errorCode'
import { BusinessError } from './error'
import type { ApiResponse, RequestConfig } from './types'
import { isCancelledError } from './cancel'

export const isRelogin = { show: false }

export function getBusinessMessage(data: ApiResponse): string {
  const code = data.code ?? HttpStatus.SUCCESS
  return errorCode[code as string | number] || data.msg || errorCode.default
}

function loginRedirectUrl(): string {
  const current = `${window.location.pathname}${window.location.search}`
  const params = new URLSearchParams()
  if (current && current !== '/login') {
    params.set('redirect', current)
  }
  const query = params.toString()
  return query ? `/login?${query}` : '/login'
}

function expireSession(msg: string): Promise<never> {
  useAuthStore.getState().logout()

  if (!isRelogin.show) {
    isRelogin.show = true
    Modal.confirm({
      title: '系统提示',
      content: '登录状态已过期，请重新登录。',
      okText: '重新登录',
      cancelText: '取消',
      onOk: () => {
        isRelogin.show = false
        window.location.href = loginRedirectUrl()
      },
      onCancel: () => {
        isRelogin.show = false
      },
    })
  }

  return Promise.reject(new Error(msg))
}

function getHttpErrorDetail(error: AxiosError): string {
  const data = error.response?.data
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
  }
  return '无效的会话，或者会话已过期，请重新登录。'
}

export function normalizeNetworkError(error: AxiosError): string {
  const msg = error.message

  if (msg === 'Network Error') {
    return '后端接口连接异常'
  }

  if (msg.includes('timeout')) {
    return '系统接口请求超时'
  }

  if (msg.includes('Request failed with status code')) {
    return `系统接口${msg.substring(msg.length - 3)}异常`
  }

  if (error.response?.status) {
    return `系统接口${error.response.status}异常`
  }

  return msg || errorCode.default
}

export const transformResponse = (response: AxiosResponse<ApiResponse>): unknown => {
  const config = response.config as RequestConfig

  if (config.isReturnNativeResponse === true) {
    return response
  }

  if (
    response.request.responseType === 'blob' ||
    response.request.responseType === 'arraybuffer'
  ) {
    return response.data
  }

  if (config.isTransformResponse === true) {
    return response.data
  }

  const code = response.data.code ?? HttpStatus.SUCCESS
  const msg = getBusinessMessage(response.data)

  if (code === HttpStatus.SUCCESS || code === String(HttpStatus.SUCCESS)) {
    return response.data
  }

  if (code === HttpStatus.UNAUTHORIZED || code === String(HttpStatus.UNAUTHORIZED)) {
    return expireSession('无效的会话，或者会话已过期，请重新登录。')
  }

  if (config.showError === false) {
    return Promise.reject(new BusinessError(msg, code, response.data))
  }

  if (code === HttpStatus.SERVER_ERROR || code === String(HttpStatus.SERVER_ERROR)) {
    void message.error(msg)
    return Promise.reject(new BusinessError(msg, code, response.data))
  }

  if (code === HttpStatus.WARN || code === String(HttpStatus.WARN)) {
    void message.warning(msg)
    return Promise.reject(new BusinessError(msg, code, response.data))
  }

  notification.error({ message: msg })
  return Promise.reject(new BusinessError(msg, code, response.data))
}

export function handleResponseError(error: AxiosError): Promise<never> {
  if (isCancelledError(error)) {
    return Promise.reject(error)
  }

  if (error.response?.status === HttpStatus.UNAUTHORIZED) {
    return expireSession(getHttpErrorDetail(error))
  }

  const requestConfig = error.config as RequestConfig | undefined
  const msg = normalizeNetworkError(error)

  if (requestConfig?.showError !== false) {
    void message.error(msg, 5)
  }

  return Promise.reject(error)
}
```

- [ ] **Step 5: Run auth 401 test**

Run:

```bash
cd frontend && npm test -- auth-invalid-token.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

Run:

```bash
git add frontend/src/request/transform.ts frontend/src/stores/useAuthStore.ts frontend/tests/auth-invalid-token.test.ts
git commit -m "fix: clear stale auth on http 401"
```

Expected: Commit succeeds.

---

### Task 2: Add TagsView Store And Route Metadata

**Files:**
- Create: `frontend/src/stores/useTagsViewStore.ts`
- Create: `frontend/src/routes/tags.ts`
- Test: `frontend/tests/tags-view-store.test.ts`

- [ ] **Step 1: Write TagsView store tests**

Create `frontend/tests/tags-view-store.test.ts`:

```ts
import { beforeEach, describe, expect, it } from 'vitest'
import { useTagsViewStore } from '../src/stores/useTagsViewStore'

describe('useTagsViewStore', () => {
  beforeEach(() => {
    useTagsViewStore.getState().resetViews()
  })

  it('keeps dashboard affix and adds crawler task routes', () => {
    useTagsViewStore.getState().addVisitedView({
      path: '/crawler/tasks',
      fullPath: '/crawler/tasks',
      title: '任务列表',
      closable: true,
    })

    expect(useTagsViewStore.getState().visitedViews.map((view) => view.title)).toEqual([
      '仪表盘',
      '任务列表',
    ])
  })

  it('removes right-side closable views while preserving affix dashboard', () => {
    const store = useTagsViewStore.getState()
    store.addVisitedView({
      path: '/crawler/tasks',
      fullPath: '/crawler/tasks',
      title: '任务列表',
      closable: true,
    })
    store.addVisitedView({
      path: '/crawler/tasks/new',
      fullPath: '/crawler/tasks/new',
      title: '新建任务',
      closable: true,
    })

    const nextViews = store.removeRightViews({
      path: '/crawler/tasks',
      fullPath: '/crawler/tasks',
      title: '任务列表',
      closable: true,
    })

    expect(nextViews.map((view) => view.fullPath)).toEqual(['/', '/crawler/tasks'])
  })
})
```

- [ ] **Step 2: Run store tests to verify they fail**

Run:

```bash
cd frontend && npm test -- tags-view-store.test.ts
```

Expected: FAIL because `frontend/src/stores/useTagsViewStore.ts` does not exist.

- [ ] **Step 3: Add TagsView store**

Create `frontend/src/stores/useTagsViewStore.ts`:

```ts
import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

export type TagView = {
  path: string
  fullPath: string
  title: string
  query?: Record<string, unknown>
  closable?: boolean
}

const DASHBOARD_TAG: TagView = {
  path: '/',
  fullPath: '/',
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

function normalizeViews(views: TagView[]): TagView[] {
  const withDashboard = views.some((view) => view.fullPath === DASHBOARD_TAG.fullPath)
    ? views
    : [DASHBOARD_TAG, ...views]
  return withDashboard.length > 0 ? withDashboard : [DASHBOARD_TAG]
}

export const useTagsViewStore = create<TagsViewState>()(
  devtools(
    persist(
      (set, get) => ({
        visitedViews: [DASHBOARD_TAG],

        addVisitedView: (view) => {
          const { visitedViews } = get()
          if (visitedViews.some((item) => item.fullPath === view.fullPath)) {
            get().updateVisitedView(view)
            return
          }

          set({ visitedViews: normalizeViews([...visitedViews, view]) })
        },

        updateVisitedView: (view) => {
          const { visitedViews } = get()
          set({
            visitedViews: normalizeViews(
              visitedViews.map((item) =>
                item.fullPath === view.fullPath ? { ...item, ...view } : item,
              ),
            ),
          })
        },

        removeSelectedView: (view) => {
          const nextViews = normalizeViews(
            get().visitedViews.filter(
              (item) => item.fullPath !== view.fullPath || item.closable === false,
            ),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        removeOtherViews: (view) => {
          const nextViews = normalizeViews(
            get().visitedViews.filter(
              (item) => item.fullPath === view.fullPath || item.closable === false,
            ),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        removeLeftViews: (view) => {
          const { visitedViews } = get()
          const targetIndex = visitedViews.findIndex((item) => item.fullPath === view.fullPath)
          if (targetIndex <= 0) return visitedViews

          const nextViews = normalizeViews(
            visitedViews.filter((item, index) => index >= targetIndex || item.closable === false),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        removeRightViews: (view) => {
          const { visitedViews } = get()
          const targetIndex = visitedViews.findIndex((item) => item.fullPath === view.fullPath)
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
        partialize: (state) => ({ visitedViews: state.visitedViews }),
      },
    ),
  ),
)
```

- [ ] **Step 4: Add route metadata helper**

Create `frontend/src/routes/tags.ts`:

```ts
export type RouteTagMeta = {
  title: string
  affix?: boolean
  activeMenu?: string
}

const ROUTE_TAGS: Array<{ pattern: RegExp; meta: RouteTagMeta }> = [
  { pattern: /^\/$/, meta: { title: '仪表盘', affix: true } },
  { pattern: /^\/crawler\/tasks$/, meta: { title: '任务列表' } },
  {
    pattern: /^\/crawler\/tasks\/new$/,
    meta: { title: '新建任务', activeMenu: '/crawler/tasks' },
  },
  {
    pattern: /^\/crawler\/tasks\/[^/]+\/edit$/,
    meta: { title: '编辑任务', activeMenu: '/crawler/tasks' },
  },
]

export function getRouteTagMeta(pathname: string): RouteTagMeta {
  return ROUTE_TAGS.find((item) => item.pattern.test(pathname))?.meta ?? {
    title: pathname,
  }
}

export function getFullPath(pathname: string, searchStr: string): string {
  return `${pathname}${searchStr || ''}`
}
```

- [ ] **Step 5: Run store tests**

Run:

```bash
cd frontend && npm test -- tags-view-store.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add frontend/src/stores/useTagsViewStore.ts frontend/src/routes/tags.ts frontend/tests/tags-view-store.test.ts
git commit -m "feat: add tags view store"
```

Expected: Commit succeeds.

---

### Task 3: Implement Route-Aware TagsView With Context Menu

**Files:**
- Modify: `frontend/src/layout/TagsView/index.tsx`
- Modify: `frontend/src/layout/TagsView/TagsView.module.less`
- Test: `frontend/tests/tags-view.ui.test.tsx`

- [ ] **Step 1: Write TagsView UI tests**

Create `frontend/tests/tags-view.ui.test.tsx`:

```tsx
import { describe, expect, it, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { TagsView } from '../src/layout/TagsView'
import { useTagsViewStore } from '../src/stores/useTagsViewStore'

function renderTagsView(initialPath: string) {
  const rootRoute = createRootRoute({
    component: () => <TagsView />,
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
  const router = createRouter({
    routeTree: rootRoute.addChildren([dashboardRoute, taskRoute, newTaskRoute]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })

  return render(<RouterProvider router={router} />)
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
})
```

- [ ] **Step 2: Run TagsView UI tests to verify they fail**

Run:

```bash
cd frontend && npm test -- tags-view.ui.test.tsx
```

Expected: FAIL because current TagsView does not render route tags or context menu actions.

- [ ] **Step 3: Implement TagsView logic**

Modify `frontend/src/layout/TagsView/index.tsx`:

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
import { useTagsViewStore } from '@/stores/useTagsViewStore'
import type { TagView } from '@/stores/useTagsViewStore'
import styles from './TagsView.module.less'

type TagsViewProps = {
  darkMode?: boolean
}

type ContextMenuState = {
  visible: boolean
  left: number
  top: number
  selectedTag?: TagView
}

export function TagsView({ darkMode }: TagsViewProps) {
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
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    visible: false,
    left: 0,
    top: 0,
  })

  const fullPath = getFullPath(pathname, searchStr)
  const currentMeta = useMemo(() => getRouteTagMeta(pathname), [pathname])
  const isActive = useCallback((view: TagView) => view.fullPath === fullPath, [fullPath])

  useEffect(() => {
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

  const handleClose = useCallback(
    (tag: TagView, event?: React.MouseEvent) => {
      event?.stopPropagation()
      if (tag.closable === false) return
      const nextViews = removeSelectedView(tag)
      navigateAfterClose(nextViews)
    },
    [navigateAfterClose, removeSelectedView],
  )

  const handleMouseDown = useCallback(
    (tag: TagView, event: React.MouseEvent) => {
      if (event.button === 1 && tag.closable !== false) {
        event.preventDefault()
        const nextViews = removeSelectedView(tag)
        navigateAfterClose(nextViews)
      }
    },
    [navigateAfterClose, removeSelectedView],
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
    void navigate({ to: fullPath, replace: true })
  }, [closeContextMenu, fullPath, navigate])

  const handleCloseCurrent = useCallback(() => {
    closeContextMenu()
    const tag = contextMenu.selectedTag
    if (!tag || tag.closable === false) return
    navigateAfterClose(removeSelectedView(tag))
  }, [closeContextMenu, contextMenu.selectedTag, navigateAfterClose, removeSelectedView])

  const handleCloseOthers = useCallback(() => {
    closeContextMenu()
    const tag = contextMenu.selectedTag
    if (!tag) return
    navigateAfterClose(removeOtherViews(tag))
  }, [closeContextMenu, contextMenu.selectedTag, navigateAfterClose, removeOtherViews])

  const handleCloseLeft = useCallback(() => {
    closeContextMenu()
    const tag = contextMenu.selectedTag
    if (!tag) return
    navigateAfterClose(removeLeftViews(tag))
  }, [closeContextMenu, contextMenu.selectedTag, navigateAfterClose, removeLeftViews])

  const handleCloseRight = useCallback(() => {
    closeContextMenu()
    const tag = contextMenu.selectedTag
    if (!tag) return
    navigateAfterClose(removeRightViews(tag))
  }, [closeContextMenu, contextMenu.selectedTag, navigateAfterClose, removeRightViews])

  const handleCloseAll = useCallback(() => {
    closeContextMenu()
    navigateAfterClose(removeAllViews())
  }, [closeContextMenu, navigateAfterClose, removeAllViews])

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

- [ ] **Step 4: Add TagsView menu styles**

Modify `frontend/src/layout/TagsView/TagsView.module.less`:

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
  cursor: pointer;
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

.closeIcon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  font-size: 10px;
  color: #94a3b8;
  margin-left: 2px;
}

.closeIcon:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.contextMenu {
  z-index: 3000;
  min-width: 132px;
  padding: 4px 0;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #ffffff;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.14);
}

.menuItem {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border: 0;
  background: transparent;
  color: #374151;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  text-align: left;
}

.menuItem:hover {
  background: #f3f4f6;
  color: var(--app-primary-color, #006aff);
}

.disabled,
.disabled:hover {
  color: #cbd5e1;
  cursor: not-allowed;
  background: transparent;
}

.menuDivider {
  height: 1px;
  margin: 4px 0;
  background: #e5e7eb;
}

.flipX {
  transform: scaleX(-1);
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

  .contextMenu {
    border-color: #334155;
    background: #1f2937;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  }

  .menuItem {
    color: #d1d5db;
  }

  .menuItem:hover {
    background: #334155;
    color: #60a5fa;
  }

  .disabled,
  .disabled:hover {
    color: #64748b;
    background: transparent;
  }
}
```

- [ ] **Step 5: Run TagsView UI tests**

Run:

```bash
cd frontend && npm test -- tags-view.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add frontend/src/layout/TagsView/index.tsx frontend/src/layout/TagsView/TagsView.module.less frontend/tests/tags-view.ui.test.tsx
git commit -m "feat: add tags view context menu"
```

Expected: Commit succeeds.

---

### Task 4: Integrate TagsView With Crawler Task Pages And Verify

**Files:**
- Modify: `frontend/tests/layout.ui.test.tsx`
- Modify: `frontend/tests/App.test.tsx`
- Verify: `frontend/src/routes/index.tsx`
- Verify: `frontend/src/layout/Sidebar/index.tsx`

- [ ] **Step 1: Update layout test for crawler tag behavior**

Modify the first test in `frontend/tests/layout.ui.test.tsx`:

```tsx
  it('renders console shell landmarks, crawler navigation, and tags view', async () => {
    renderLayout()

    expect(await screen.findByText('Media Forge')).toBeInTheDocument()
    expect(screen.getByText('Operations Console')).toBeInTheDocument()
    expect(screen.getByRole('menu')).toBeInTheDocument()
    expect(screen.getAllByText('仪表盘').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('爬虫')).toBeInTheDocument()
    expect(screen.getByText('任务列表')).toBeInTheDocument()
    expect(screen.getByText('console outlet')).toBeInTheDocument()
    expect(screen.queryByLabelText('Open settings')).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Update app route test for crawler task page tag**

Add this test in `frontend/tests/App.test.tsx`:

```tsx
  it('shows crawler task page with a task list tag for authenticated user', async () => {
    useAuthStore.setState({ token: 'test-token', isAuthenticated: true })

    renderApp('/crawler/tasks')

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '爬取任务' })).toBeInTheDocument()
      expect(screen.getByText('任务列表')).toBeInTheDocument()
    })
  })
```

- [ ] **Step 3: Run route/layout regression tests**

Run:

```bash
cd frontend && npm test -- layout.ui.test.tsx App.test.tsx tags-view.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Verify all frontend tests**

Run:

```bash
cd frontend && npm test
```

Expected: PASS.

- [ ] **Step 5: Run lint and build**

Run:

```bash
cd frontend && npm run lint && npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

Run:

```bash
git add frontend/tests/layout.ui.test.tsx frontend/tests/App.test.tsx
git commit -m "test: cover crawler tags view integration"
```

Expected: Commit succeeds.

---

## Self-Review

**Spec coverage:** The plan fixes `Invalid or expired token` by clearing stale auth on bare HTTP 401 responses, prevents persisted auth from outliving the cookie token, adds TagsView entries for crawler task pages, and adds a RuoYi-style right-click context menu with refresh/close-current/close-others/close-left/close-right/close-all.

**Placeholder scan:** No placeholder markers or incomplete steps remain. The term `placeholder` appears only as a real JSX prop in existing UI code examples.

**Type consistency:** `TagView`, route metadata, `visitedViews`, `fullPath`, and context menu operations use the same names across store, TagsView, and tests.
