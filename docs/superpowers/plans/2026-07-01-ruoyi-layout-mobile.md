# Ruoyi-Style Layout Mobile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a ruoyi-react-style authenticated application layout to the Media Forge frontend, including sidebar navigation, header controls, visited page tags, and a phone-friendly drawer navigation mode.

**Architecture:** Keep the current manual TanStack Router setup and wrap only authenticated app routes in a new `AppLayout`. Port the reference layout shape from `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/layout`, but avoid importing its dynamic permission system by using a small local static menu model that can later be replaced by backend menu data. Mobile uses Ant Design `Drawer` for navigation while desktop keeps an Ant Design `Sider` with collapsible width.

**Tech Stack:** React 19, TypeScript 6, TanStack Router 1.x, Ant Design 6 `Layout/Menu/Drawer`, Zustand 5, Less modules, Vitest + React Testing Library

---

## Reference Source

- `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/layout/AppLayout.tsx`
- `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/layout/AppLayout.module.less`
- `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/layout/Sidebar/index.tsx`
- `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/layout/Sidebar/Sidebar.module.less`
- `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/layout/Header/index.tsx`
- `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/layout/Header/Header.module.less`
- `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/layout/TagsView/index.tsx`
- `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/layout/TagsView/TagsView.module.less`
- `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/store/useTagsViewStore.ts`

## File Structure

- Create `frontend/src/layout/types.ts`
  - Owns `LayoutMenuItem` and `TagView` types used by layout-only code.
- Create `frontend/src/layout/menu.ts`
  - Owns static menu metadata, menu lookup helpers, and Ant Design menu item conversion.
- Create `frontend/src/stores/useTagsViewStore.ts`
  - Owns persisted visited route tags and tag close/reset actions.
- Create `frontend/src/layout/Sidebar/index.tsx` and `frontend/src/layout/Sidebar/Sidebar.module.less`
  - Owns desktop sider and mobile drawer menu rendering.
- Create `frontend/src/layout/Header/index.tsx` and `frontend/src/layout/Header/Header.module.less`
  - Owns collapse/drawer trigger, theme toggle, user identity, and logout command.
- Create `frontend/src/layout/TagsView/index.tsx` and `frontend/src/layout/TagsView/TagsView.module.less`
  - Owns route tag rendering and tag close behavior.
- Create `frontend/src/layout/AppLayout.tsx` and `frontend/src/layout/AppLayout.module.less`
  - Owns authenticated shell composition and route outlet.
- Modify `frontend/src/routes/index.tsx`
  - Adds a layout route around authenticated pages and keeps `/login` and `/init` outside the shell.
- Modify `frontend/src/styles/app.css`
  - Adds root sizing and dark/light background variables used by the layout.
- Add tests in `frontend/tests/layout.menu.test.ts`, `frontend/tests/tagsViewStore.test.ts`, and update `frontend/tests/App.test.tsx`.

## Constraints

- Do not copy `usePermissionStore`, backend dynamic route transforms, or SVG icon infrastructure from `ruoyi-react`.
- Use Ant Design icons already installed in this project.
- Keep the current login and init routes full-screen and outside the layout.
- The protected `/` route must still run `requireInit()` and `requireAuth()`.
- Mobile breakpoint is `768px`: desktop uses `Sider`; mobile hides `Sider` and opens `Drawer`.
- The plan intentionally creates only the current dashboard menu entry; future modules can append to `APP_MENU_ITEMS`.

---

### Task 1: Add Layout Menu Types And Helpers

**Files:**
- Create: `frontend/src/layout/types.ts`
- Create: `frontend/src/layout/menu.ts`
- Test: `frontend/tests/layout.menu.test.ts`

- [ ] **Step 1: Write the failing menu helper test**

Create `frontend/tests/layout.menu.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'
import {
  APP_MENU_ITEMS,
  findMenuItemByPath,
  getDefaultOpenKeys,
  getSelectedMenuKey,
} from '../src/layout/menu'

describe('layout menu helpers', () => {
  it('contains the dashboard as an affix home menu item', () => {
    expect(APP_MENU_ITEMS).toEqual([
      {
        key: '/',
        path: '/',
        title: '仪表盘',
        icon: 'dashboard',
        affix: true,
      },
    ])
  })

  it('selects the exact menu item for known paths', () => {
    expect(getSelectedMenuKey('/')).toBe('/')
    expect(findMenuItemByPath('/')).toMatchObject({
      key: '/',
      title: '仪表盘',
      affix: true,
    })
  })

  it('falls back to dashboard when a path is not represented in the menu', () => {
    expect(getSelectedMenuKey('/missing')).toBe('/')
    expect(findMenuItemByPath('/missing')).toBeUndefined()
  })

  it('computes parent open keys from nested menu items', () => {
    expect(
      getDefaultOpenKeys('/media/tasks', [
        {
          key: '/media',
          path: '/media',
          title: '媒体处理',
          children: [
            {
              key: '/media/tasks',
              path: '/media/tasks',
              title: '任务列表',
            },
          ],
        },
      ]),
    ).toEqual(['/media'])
  })
})
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd frontend && npm test -- layout.menu.test.ts
```

Expected: FAIL because `../src/layout/menu` does not exist.

- [ ] **Step 3: Create the layout types**

Create `frontend/src/layout/types.ts`:

```typescript
export type LayoutMenuIcon = 'dashboard'

export type LayoutMenuItem = {
  key: string
  path: string
  title: string
  icon?: LayoutMenuIcon
  affix?: boolean
  hidden?: boolean
  children?: LayoutMenuItem[]
}

export type TagView = {
  path: string
  fullPath: string
  title: string
  closable?: boolean
}
```

- [ ] **Step 4: Create the static menu helper module**

Create `frontend/src/layout/menu.ts`:

```typescript
import { DashboardOutlined } from '@ant-design/icons'
import type { MenuProps } from 'antd'
import type { LayoutMenuIcon, LayoutMenuItem } from './types'

type AntdMenuItem = Required<MenuProps>['items'][number]

export const APP_MENU_ITEMS: LayoutMenuItem[] = [
  {
    key: '/',
    path: '/',
    title: '仪表盘',
    icon: 'dashboard',
    affix: true,
  },
]

const iconMap: Record<LayoutMenuIcon, React.ReactNode> = {
  dashboard: <DashboardOutlined />,
}

function flattenMenuItems(items: LayoutMenuItem[]): LayoutMenuItem[] {
  return items.flatMap((item) => [
    item,
    ...(item.children ? flattenMenuItems(item.children) : []),
  ])
}

export function findMenuItemByPath(
  pathname: string,
  items: LayoutMenuItem[] = APP_MENU_ITEMS,
): LayoutMenuItem | undefined {
  return flattenMenuItems(items).find((item) => item.path === pathname)
}

export function getSelectedMenuKey(
  pathname: string,
  items: LayoutMenuItem[] = APP_MENU_ITEMS,
): string {
  const exact = findMenuItemByPath(pathname, items)
  if (exact) return exact.key

  const visibleItems = flattenMenuItems(items).filter((item) => !item.hidden)
  const prefixMatch = visibleItems
    .filter((item) => item.path !== '/' && pathname.startsWith(`${item.path}/`))
    .sort((a, b) => b.path.length - a.path.length)[0]

  return prefixMatch?.key ?? '/'
}

export function getDefaultOpenKeys(
  selectedKey: string,
  items: LayoutMenuItem[] = APP_MENU_ITEMS,
): string[] {
  const keys: string[] = []

  function walk(nodes: LayoutMenuItem[], parents: string[]): boolean {
    for (const node of nodes) {
      if (node.key === selectedKey) {
        keys.push(...parents)
        return true
      }

      if (node.children?.length && walk(node.children, [...parents, node.key])) {
        return true
      }
    }

    return false
  }

  walk(items, [])
  return keys
}

export function toAntdMenuItems(items: LayoutMenuItem[]): AntdMenuItem[] {
  return items
    .filter((item) => !item.hidden)
    .map((item) => ({
      key: item.key,
      label: item.title,
      icon: item.icon ? iconMap[item.icon] : undefined,
      children: item.children ? toAntdMenuItems(item.children) : undefined,
    }))
}
```

- [ ] **Step 5: Run the menu helper test and verify it passes**

Run:

```bash
cd frontend && npm test -- layout.menu.test.ts
```

Expected: PASS with 4 tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/layout/types.ts frontend/src/layout/menu.ts frontend/tests/layout.menu.test.ts
git commit -m "feat(frontend): add layout menu helpers"
```

---

### Task 2: Add Tags View Store

**Files:**
- Create: `frontend/src/stores/useTagsViewStore.ts`
- Test: `frontend/tests/tagsViewStore.test.ts`

- [ ] **Step 1: Write the failing tags store test**

Create `frontend/tests/tagsViewStore.test.ts`:

```typescript
import { beforeEach, describe, expect, it } from 'vitest'
import { useTagsViewStore } from '../src/stores/useTagsViewStore'

describe('useTagsViewStore', () => {
  beforeEach(() => {
    useTagsViewStore.getState().resetViews()
  })

  it('starts with the dashboard tag pinned', () => {
    expect(useTagsViewStore.getState().visitedViews).toEqual([
      {
        path: '/',
        fullPath: '/',
        title: '仪表盘',
        closable: false,
      },
    ])
  })

  it('adds one tag per full path and updates duplicate paths without query strings', () => {
    const store = useTagsViewStore.getState()

    store.addVisitedView({
      path: '/reports',
      fullPath: '/reports',
      title: '报表',
      closable: true,
    })
    store.addVisitedView({
      path: '/reports',
      fullPath: '/reports',
      title: '报表更新',
      closable: true,
    })

    expect(useTagsViewStore.getState().visitedViews).toEqual([
      {
        path: '/',
        fullPath: '/',
        title: '仪表盘',
        closable: false,
      },
      {
        path: '/reports',
        fullPath: '/reports',
        title: '报表更新',
        closable: true,
      },
    ])
  })

  it('keeps pinned tags when removing all views', () => {
    const store = useTagsViewStore.getState()

    store.addVisitedView({
      path: '/reports',
      fullPath: '/reports?page=1',
      title: '报表',
      closable: true,
    })

    expect(store.removeAllViews()).toEqual([
      {
        path: '/',
        fullPath: '/',
        title: '仪表盘',
        closable: false,
      },
    ])
  })
})
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd frontend && npm test -- tagsViewStore.test.ts
```

Expected: FAIL because `../src/stores/useTagsViewStore` does not exist.

- [ ] **Step 3: Create the tags view store**

Create `frontend/src/stores/useTagsViewStore.ts`:

```typescript
import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'
import type { TagView } from '@/layout/types'

const HOME_TAG: TagView = {
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
  removeAllViews: () => TagView[]
  resetViews: () => void
}

function normalizeViews(views: TagView[]): TagView[] {
  return views.length > 0 ? views : [HOME_TAG]
}

export const useTagsViewStore = create<TagsViewState>()(
  devtools(
    persist(
      (set, get) => ({
        visitedViews: [HOME_TAG],

        addVisitedView: (view) => {
          const { visitedViews } = get()

          if (visitedViews.some((item) => item.fullPath === view.fullPath)) {
            get().updateVisitedView(view)
            return
          }

          const samePathIndex = visitedViews.findIndex((item) => item.path === view.path)
          if (samePathIndex !== -1 && view.fullPath === view.path) {
            set({
              visitedViews: visitedViews.map((item, index) =>
                index === samePathIndex ? { ...item, ...view } : item,
              ),
            })
            return
          }

          set({ visitedViews: [...visitedViews, view] })
        },

        updateVisitedView: (view) => {
          const { visitedViews } = get()
          set({
            visitedViews: visitedViews.map((item) =>
              item.fullPath === view.fullPath ? { ...item, ...view } : item,
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

        removeAllViews: () => {
          const nextViews = normalizeViews(
            get().visitedViews.filter((item) => item.closable === false),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        resetViews: () => {
          set({ visitedViews: [HOME_TAG] })
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

- [ ] **Step 4: Run the tags store test and verify it passes**

Run:

```bash
cd frontend && npm test -- tagsViewStore.test.ts
```

Expected: PASS with 3 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/useTagsViewStore.ts frontend/tests/tagsViewStore.test.ts
git commit -m "feat(frontend): add visited route tag store"
```

---

### Task 3: Add Sidebar And Header Components With Mobile Drawer Support

**Files:**
- Create: `frontend/src/layout/Sidebar/index.tsx`
- Create: `frontend/src/layout/Sidebar/Sidebar.module.less`
- Create: `frontend/src/layout/Header/index.tsx`
- Create: `frontend/src/layout/Header/Header.module.less`

- [ ] **Step 1: Create the sidebar component**

Create `frontend/src/layout/Sidebar/index.tsx`:

```typescript
import { useMemo } from 'react'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import { Drawer, Layout, Menu } from 'antd'
import type { MenuProps } from 'antd'
import { APP_MENU_ITEMS, getDefaultOpenKeys, getSelectedMenuKey, toAntdMenuItems } from '@/layout/menu'
import { useThemeStore } from '@/stores/useThemeStore'
import styles from './Sidebar.module.less'

const { Sider } = Layout

type SideMenuProps = {
  collapsed: boolean
  mobileOpen: boolean
  onMobileClose: () => void
}

export function SideMenu({ collapsed, mobileOpen, onMobileClose }: SideMenuProps) {
  const navigate = useNavigate()
  const darkMode = useThemeStore((state) => state.darkMode)
  const pathname = useRouterState({ select: (state) => state.location.pathname })

  const selectedKey = getSelectedMenuKey(pathname)
  const defaultOpenKeys = useMemo(() => getDefaultOpenKeys(selectedKey), [selectedKey])
  const items = useMemo(() => toAntdMenuItems(APP_MENU_ITEMS), [])

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    const nextPath = String(key)
    onMobileClose()
    if (nextPath !== pathname) {
      void navigate({ to: nextPath })
    }
  }

  const menu = (
    <Menu
      className={styles.menu}
      mode="inline"
      theme={darkMode ? 'dark' : 'light'}
      inlineCollapsed={collapsed}
      selectedKeys={[selectedKey]}
      defaultOpenKeys={defaultOpenKeys}
      items={items}
      onClick={handleMenuClick}
    />
  )

  return (
    <>
      <Sider
        collapsed={collapsed}
        width={232}
        collapsedWidth={72}
        trigger={null}
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
        <div className={styles.menuWrapper}>{menu}</div>
      </Sider>

      <Drawer
        className={darkMode ? styles.mobileDrawerDark : undefined}
        open={mobileOpen}
        placement="left"
        width={280}
        title={
          <div className={styles.drawerTitle}>
            <span className={styles.logoMark}>MF</span>
            <span className={styles.logoText}>Media Forge</span>
          </div>
        }
        styles={{ body: { padding: 0 } }}
        onClose={onMobileClose}
      >
        <div className={styles.mobileMenu}>{menu}</div>
      </Drawer>
    </>
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
  border-right: 1px solid #e5e7eb;

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

  :global(.ant-menu-item),
  :global(.ant-menu-submenu-title) {
    width: calc(100% - 8px);
    margin-inline: 4px;
  }
}

.collapsed {
  :global(.ant-menu-title-content) {
    opacity: 0;
  }
}

.logo,
.drawerTitle {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.logo {
  height: 64px;
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
  background: var(--app-primary-color, #006aff);
  color: #ffffff;
  font-size: 13px;
  font-weight: 700;
}

.logoText {
  min-width: 0;
  overflow: hidden;
  color: #0f172a;
  font-size: 15px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menuWrapper {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.menu,
.mobileMenu {
  min-width: 0;
}

.mobileMenu {
  padding: 8px 0;
}

.dark {
  &.sider {
    background: #111827;
    border-right-color: #1f2937;
  }

  .logoText {
    color: #e5e7eb;
  }
}

.mobileDrawerDark {
  :global(.ant-drawer-content),
  :global(.ant-drawer-header) {
    background: #111827;
    color: #e5e7eb;
  }

  :global(.ant-drawer-header) {
    border-bottom-color: #1f2937;
  }

  :global(.ant-drawer-close) {
    color: #e5e7eb;
  }

  .logoText {
    color: #e5e7eb;
  }
}

@media (max-width: 768px) {
  .sider {
    display: none;
  }
}
```

- [ ] **Step 3: Create the header component**

Create `frontend/src/layout/Header/index.tsx`:

```typescript
import { useNavigate } from '@tanstack/react-router'
import {
  LogoutOutlined,
  MenuFoldOutlined,
  MenuOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons'
import { Button, Layout, Space } from 'antd'
import { ThemeModeToggle } from '@/components/ThemeModeToggle'
import { useAuthStore } from '@/stores/useAuthStore'
import styles from './Header.module.less'

const { Header } = Layout

type LayoutHeaderProps = {
  darkMode: boolean
  collapsed: boolean
  isMobile: boolean
  onCollapse: (collapsed: boolean) => void
  onMobileMenuOpen: () => void
}

export function LayoutHeader({
  darkMode,
  collapsed,
  isMobile,
  onCollapse,
  onMobileMenuOpen,
}: LayoutHeaderProps) {
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
        <Button
          aria-label={isMobile ? '打开导航菜单' : collapsed ? '展开侧边栏' : '收起侧边栏'}
          className={styles.trigger}
          type="text"
          icon={isMobile ? <MenuOutlined /> : collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          onClick={() => {
            if (isMobile) {
              onMobileMenuOpen()
            } else {
              onCollapse(!collapsed)
            }
          }}
        />
      </div>

      <Space size={12} className={styles.right}>
        <ThemeModeToggle size="middle" variant="header" />
        <div className={styles.user}>
          <span className={styles.avatar}>{displayName.slice(0, 1).toUpperCase()}</span>
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

- [ ] **Step 4: Create the header styles**

Create `frontend/src/layout/Header/Header.module.less`:

```less
.header {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex: 0 0 64px;
  padding: 0 24px;
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
}

.left,
.right {
  display: flex;
  align-items: center;
  min-width: 0;
}

.trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #334155;
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
  border-bottom-color: #1f2937;
  color: #cbd5e1;

  .trigger,
  .user {
    color: #e5e7eb;
  }

  .avatar {
    background: #134e4a;
    color: #ccfbf1;
  }
}

@media (max-width: 768px) {
  .header {
    padding: 0 12px;
  }

  .right {
    gap: 8px;
  }

  .userName {
    display: none;
  }
}
```

- [ ] **Step 5: Run TypeScript to verify imports compile**

Run:

```bash
cd frontend && npm run build
```

Expected: FAIL because `AppLayout` and routing integration are not created yet, or PASS if TypeScript has not imported these files. If it fails for `Cannot find module '@/layout/AppLayout'`, continue to Task 4. If it fails for syntax/type errors in Task 3 files, fix those exact errors before continuing.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/layout/Sidebar/index.tsx frontend/src/layout/Sidebar/Sidebar.module.less frontend/src/layout/Header/index.tsx frontend/src/layout/Header/Header.module.less
git commit -m "feat(frontend): add responsive layout navigation chrome"
```

---

### Task 4: Add TagsView And AppLayout Shell

**Files:**
- Create: `frontend/src/layout/TagsView/index.tsx`
- Create: `frontend/src/layout/TagsView/TagsView.module.less`
- Create: `frontend/src/layout/AppLayout.tsx`
- Create: `frontend/src/layout/AppLayout.module.less`

- [ ] **Step 1: Create the tags view component**

Create `frontend/src/layout/TagsView/index.tsx`:

```typescript
import { useEffect, useMemo } from 'react'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import { CloseOutlined } from '@ant-design/icons'
import { findMenuItemByPath } from '@/layout/menu'
import { useTagsViewStore } from '@/stores/useTagsViewStore'
import type { TagView } from '@/layout/types'
import styles from './TagsView.module.less'

type TagsViewProps = {
  darkMode: boolean
}

function getFullPath(pathname: string, searchStr?: string): string {
  if (!searchStr || searchStr === '?') return pathname
  return `${pathname}${searchStr.startsWith('?') ? searchStr : `?${searchStr}`}`
}

export function TagsView({ darkMode }: TagsViewProps) {
  const navigate = useNavigate()
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const searchStr = useRouterState({ select: (state) => state.location.searchStr ?? '' })
  const fullPath = useMemo(() => getFullPath(pathname, searchStr), [pathname, searchStr])

  const visitedViews = useTagsViewStore((state) => state.visitedViews)
  const addVisitedView = useTagsViewStore((state) => state.addVisitedView)
  const removeSelectedView = useTagsViewStore((state) => state.removeSelectedView)
  const removeOtherViews = useTagsViewStore((state) => state.removeOtherViews)
  const removeAllViews = useTagsViewStore((state) => state.removeAllViews)

  useEffect(() => {
    const menuItem = findMenuItemByPath(pathname)
    const view: TagView = {
      path: pathname,
      fullPath,
      title: menuItem?.title ?? '页面',
      closable: pathname !== '/' && !menuItem?.affix,
    }
    addVisitedView(view)
  }, [addVisitedView, fullPath, pathname])

  const navigateAfterClose = (views: TagView[]) => {
    if (views.some((view) => view.fullPath === fullPath)) return
    void navigate({ to: views.at(-1)?.fullPath ?? '/' })
  }

  const handleClose = (view: TagView, event: React.MouseEvent) => {
    event.stopPropagation()
    if (view.closable === false) return
    navigateAfterClose(removeSelectedView(view))
  }

  const handleCloseOthers = () => {
    const activeView = visitedViews.find((view) => view.fullPath === fullPath)
    if (!activeView) return
    navigateAfterClose(removeOtherViews(activeView))
  }

  const handleCloseAll = () => {
    navigateAfterClose(removeAllViews())
  }

  return (
    <div className={darkMode ? `${styles.tagsView} ${styles.dark}` : styles.tagsView}>
      <div className={styles.scrollContent}>
        <div className={styles.tagsInner}>
          {visitedViews.map((view) => {
            const active = view.fullPath === fullPath
            return (
              <button
                key={view.fullPath}
                type="button"
                className={[
                  styles.tag,
                  active ? styles.active : '',
                  view.closable === false ? styles.affix : '',
                ].filter(Boolean).join(' ')}
                onClick={() => void navigate({ to: view.fullPath })}
              >
                {active ? <span className={styles.dot} /> : null}
                <span className={styles.tagTitle}>{view.title}</span>
                {view.closable !== false ? (
                  <CloseOutlined
                    aria-label={`关闭${view.title}`}
                    className={styles.closeIcon}
                    onClick={(event) => handleClose(view, event)}
                  />
                ) : null}
              </button>
            )
          })}
        </div>
      </div>

      <div className={styles.actions}>
        <button type="button" className={styles.actionButton} onClick={handleCloseOthers}>
          关闭其他
        </button>
        <button type="button" className={styles.actionButton} onClick={handleCloseAll}>
          全部关闭
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create the tags view styles**

Create `frontend/src/layout/TagsView/TagsView.module.less`:

```less
.tagsView {
  height: 36px;
  display: flex;
  align-items: center;
  flex: 0 0 36px;
  min-width: 0;
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
  overflow: hidden;
}

.scrollContent {
  flex: 1 1 auto;
  min-width: 0;
  height: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;

  &::-webkit-scrollbar {
    display: none;
  }
}

.tagsInner {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 100%;
  padding: 0 8px;
  white-space: nowrap;
}

.tag {
  height: 26px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 160px;
  padding: 0 10px;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: #ffffff;
  color: #4b5563;
  font-size: 12px;
  line-height: 24px;
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
}

.tag:hover {
  border-color: var(--app-primary-color, #006aff);
  color: var(--app-primary-color, #006aff);
}

.active {
  border-color: var(--app-primary-color, #006aff);
  background: var(--app-primary-color, #006aff);
  color: #ffffff;

  &:hover {
    color: #ffffff;
  }
}

.affix {
  cursor: default;
}

.dot {
  width: 6px;
  height: 6px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #ffffff;
}

.tagTitle {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.closeIcon {
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  border-radius: 50%;
  color: inherit;
  font-size: 10px;
}

.closeIcon:hover {
  background: rgba(255, 255, 255, 0.2);
}

.actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
  padding: 0 8px;
  border-left: 1px solid #e5e7eb;
}

.actionButton {
  height: 24px;
  padding: 0 8px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #64748b;
  font-size: 12px;
  cursor: pointer;
}

.actionButton:hover {
  background: #f1f5f9;
  color: var(--app-primary-color, #006aff);
}

.dark {
  background: #111827;
  border-color: #1f2937;

  .tag {
    border-color: #374151;
    background: #1f2937;
    color: #cbd5e1;
  }

  .active {
    border-color: var(--app-primary-color, #006aff);
    background: var(--app-primary-color, #006aff);
    color: #ffffff;
  }

  .actions {
    border-left-color: #1f2937;
  }

  .actionButton {
    color: #cbd5e1;
  }

  .actionButton:hover {
    background: #1f2937;
    color: #ffffff;
  }
}

@media (max-width: 768px) {
  .tagsView {
    height: 34px;
    flex-basis: 34px;
  }

  .tag {
    max-width: 128px;
  }

  .actions {
    display: none;
  }
}
```

- [ ] **Step 3: Create the AppLayout component**

Create `frontend/src/layout/AppLayout.tsx`:

```typescript
import { useEffect, useState } from 'react'
import { Outlet } from '@tanstack/react-router'
import { Layout } from 'antd'
import { useThemeStore } from '@/stores/useThemeStore'
import { LayoutHeader } from './Header'
import { SideMenu } from './Sidebar'
import { TagsView } from './TagsView'
import styles from './AppLayout.module.less'

const { Content } = Layout
const MOBILE_QUERY = '(max-width: 768px)'

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => window.matchMedia(MOBILE_QUERY).matches)

  useEffect(() => {
    const media = window.matchMedia(MOBILE_QUERY)
    const handleChange = () => setIsMobile(media.matches)

    handleChange()
    media.addEventListener('change', handleChange)
    return () => media.removeEventListener('change', handleChange)
  }, [])

  return isMobile
}

export function AppLayout() {
  const darkMode = useThemeStore((state) => state.darkMode)
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const isMobile = useIsMobile()

  useEffect(() => {
    if (!isMobile) {
      setMobileOpen(false)
    }
  }, [isMobile])

  return (
    <Layout className={darkMode ? `${styles.layout} ${styles.dark}` : styles.layout}>
      <SideMenu
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />

      <Layout className={styles.main}>
        <LayoutHeader
          darkMode={darkMode}
          collapsed={collapsed}
          isMobile={isMobile}
          onCollapse={setCollapsed}
          onMobileMenuOpen={() => setMobileOpen(true)}
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

- [ ] **Step 4: Create the AppLayout styles**

Create `frontend/src/layout/AppLayout.module.less`:

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
  background: #f5f7fb;
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

  .main {
    background: #0f172a;
  }
}

@media (max-width: 768px) {
  .content {
    padding: 12px;
  }
}
```

- [ ] **Step 5: Run TypeScript and fix only local compile errors**

Run:

```bash
cd frontend && npm run build
```

Expected: FAIL because routing is not wrapped with `AppLayout` yet only if `AppLayout` is imported elsewhere incorrectly; otherwise PASS. If TypeScript reports missing imports from Task 4 files, correct those imports before continuing.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/layout/TagsView/index.tsx frontend/src/layout/TagsView/TagsView.module.less frontend/src/layout/AppLayout.tsx frontend/src/layout/AppLayout.module.less
git commit -m "feat(frontend): add authenticated app layout shell"
```

---

### Task 5: Wrap Authenticated Routes In AppLayout

**Files:**
- Modify: `frontend/src/routes/index.tsx`
- Modify: `frontend/src/styles/app.css`
- Test: `frontend/tests/App.test.tsx`

- [ ] **Step 1: Update the app routing test for layout chrome**

Replace `frontend/tests/App.test.tsx` with:

```typescript
// @ts-nocheck — test file, router types are complex; functionality is what matters
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { createRouter, RouterProvider, createMemoryHistory } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { router as baseRouter } from '../src/routes'
import { queryClient } from '../src/lib/query-client'
import { useAuthStore } from '../src/stores/useAuthStore'
import { useTagsViewStore } from '../src/stores/useTagsViewStore'

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
    useTagsViewStore.getState().resetViews()
  })

  it('redirects unauthenticated user to login page without layout chrome', async () => {
    renderApp('/')

    await waitFor(() => {
      expect(screen.getByText(/欢迎回来/i)).toBeInTheDocument()
      expect(screen.getByText(/请登录您的账户以继续/i)).toBeInTheDocument()
    })

    expect(screen.queryByRole('button', { name: /收起侧边栏|打开导航菜单/i })).not.toBeInTheDocument()
  })

  it('shows ruoyi-style layout chrome for authenticated users', async () => {
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
      expect(screen.getByRole('button', { name: /收起侧边栏|打开导航菜单/i })).toBeInTheDocument()
      expect(screen.getByText('Media Forge')).toBeInTheDocument()
      expect(screen.getAllByText('仪表盘').length).toBeGreaterThanOrEqual(2)
      expect(screen.getByText(/welcome to media forge dashboard/i)).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 2: Run the test and verify it fails before route integration**

Run:

```bash
cd frontend && npm test -- App.test.tsx
```

Expected: FAIL because authenticated `/` still renders `DashboardPage` directly and does not include the layout trigger/sidebar/tags chrome.

- [ ] **Step 3: Modify routes to add an authenticated layout route**

Replace `frontend/src/routes/index.tsx` with:

```typescript
import { createRootRoute, createRoute, createRouter, Outlet } from '@tanstack/react-router'
import { ConfigProvider, App as AntApp, theme } from 'antd'
import { useThemeStore } from '@/stores/useThemeStore'
import { redirectIfAuthenticated, requireAuth, requireInit } from './-guards'
import { AppLayout } from '@/layout/AppLayout'
import LoginPage from '@/pages/login/LoginPage'
import DashboardPage from '@/pages/dashboard/DashboardPage'
import InitPage from '@/pages/init/InitPage'

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

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'app',
  beforeLoad: async () => {
    await requireInit()
    requireAuth()
  },
  component: AppLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/',
  component: DashboardPage,
})

const routeTree = rootRoute.addChildren([initRoute, loginRoute, appRoute.addChildren([indexRoute])])

export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
})
```

- [ ] **Step 4: Add global sizing and background variables**

Replace `frontend/src/styles/app.css` with:

```css
@import "tailwindcss";
@import "tw-animate-css";

:root {
  --app-primary-color: #006aff;
  --app-bg-color: #f5f7fb;
  --app-text-color: #0f172a;
}

:root[data-theme="dark"] {
  --app-bg-color: #0f172a;
  --app-text-color: #e5e7eb;
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
}

button,
input,
textarea,
select {
  font: inherit;
}
```

- [ ] **Step 5: Run the updated app test**

Run:

```bash
cd frontend && npm test -- App.test.tsx
```

Expected: PASS with the unauthenticated test confirming no layout chrome and the authenticated test confirming layout chrome.

- [ ] **Step 6: Run the focused frontend tests**

Run:

```bash
cd frontend && npm test -- layout.menu.test.ts tagsViewStore.test.ts App.test.tsx
```

Expected: PASS for all focused layout tests.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/index.tsx frontend/src/styles/app.css frontend/tests/App.test.tsx
git commit -m "feat(frontend): wrap authenticated routes with layout"
```

---

### Task 6: Verify Mobile Interaction And Production Build

**Files:**
- Modify only if verification finds a concrete issue in files created by Tasks 1-5.

- [ ] **Step 1: Run the complete frontend test suite**

Run:

```bash
cd frontend && npm test -- --run
```

Expected: PASS for all Vitest tests.

- [ ] **Step 2: Run lint**

Run:

```bash
cd frontend && npm run lint
```

Expected: PASS with no ESLint errors.

- [ ] **Step 3: Run production build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS and Vite emits `dist/`.

- [ ] **Step 4: Start the dev server for manual responsive verification**

Run:

```bash
cd frontend && npm run dev -- --host 127.0.0.1
```

Expected: Vite prints a local URL such as `http://127.0.0.1:5173/`.

- [ ] **Step 5: Verify desktop layout manually**

Open the local URL in a browser at `1280x800`.

Expected:
- Authenticated `/` shows a left sidebar with `MF` and `Media Forge`.
- Header shows a collapse button, theme toggle, user avatar/name, and logout button.
- Tags row shows `仪表盘`.
- Content scrolls inside the layout, not the body.
- Collapse button changes sidebar width without overlapping the header or content.

- [ ] **Step 6: Verify phone layout manually**

Open the same URL in responsive mode at `390x844`.

Expected:
- Desktop sidebar is hidden.
- Header left button label is `打开导航菜单`.
- Tapping it opens a left drawer with `MF`, `Media Forge`, and `仪表盘`.
- Tapping `仪表盘` closes the drawer.
- User name is hidden, avatar remains visible.
- Tags row stays horizontally scrollable and does not overlap the content.

- [ ] **Step 7: Commit verification-only fixes if needed**

If Steps 1-6 required a code fix, commit only the changed files:

```bash
git add frontend/src/layout frontend/src/routes/index.tsx frontend/src/styles/app.css frontend/tests
git commit -m "fix(frontend): polish layout responsive behavior"
```

If no code changed, do not create an empty commit.

---

## Self-Review

- Spec coverage:
  - Adds layout to this frontend: Tasks 3-5.
  - Follows `/Users/eastwood/Code/WebstormProjects/ruoyi-react` layout pattern: Reference Source plus Tasks 2-4 mirror `AppLayout`, `Sidebar`, `Header`, and `TagsView`.
  - Mobile adaptation: Task 3 uses `Drawer`, Task 4 CSS constrains tags, Task 6 verifies `390x844`.
  - Keeps login/init outside layout: Task 5 tests and route tree.
- Placeholder scan:
  - No placeholder markers or omitted code blocks.
  - Every file creation/modification step includes complete content.
- Type consistency:
  - `LayoutMenuItem` and `TagView` are defined in Task 1 and used consistently in Tasks 2-5.
  - `SideMenu`, `LayoutHeader`, `TagsView`, and `AppLayout` prop names match their call sites.
  - Store methods in tests match methods implemented in `useTagsViewStore`.
