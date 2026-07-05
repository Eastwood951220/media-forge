import { createRootRoute, createRoute, createRouter, Outlet, redirect } from '@tanstack/react-router'
import { ConfigProvider, App as AntApp, theme } from 'antd'
import { useThemeStore } from '@/stores/useThemeStore'
import { redirectIfAuthenticated, requireAuth, requireInit } from './-guards'
import LoginPage from '@/pages/login/LoginPage'
import DashboardPage from '@/pages/dashboard/DashboardPage'
import InitPage from '@/pages/init/InitPage'
import ConfigPage from '@/pages/crawler/config/ConfigPage'
import TaskListPage from '@/pages/crawler/tasks/TaskListPage'
import TaskFormPage from '@/pages/crawler/tasks/TaskFormPage'
import RunListPage from '@/pages/crawler/runs/RunListPage'
import RunDetailPage from '@/pages/crawler/runs/RunDetailPage'
import MovieListPage from '@/pages/content/movies/MovieListPage'
import StorageConfigPage from '@/pages/storage/config/StorageConfigPage'
import StorageTaskListPage from '@/pages/storage/tasks/StorageTaskListPage'
import StorageTaskDetailPage from '@/pages/storage/tasks/StorageTaskDetailPage'
import StorageSubTaskDetailPage from '@/pages/storage/tasks/StorageSubTaskDetailPage'
import AppLayout from '@/layout'

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

const crawlerIndexRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler',
  beforeLoad: () => {
    throw redirect({ to: '/crawler/tasks' })
  },
})

const crawlerTasksRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/tasks',
  component: TaskListPage,
})

const crawlerConfigRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/config',
  component: ConfigPage,
})

const crawlerTaskNewRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/tasks/new',
  component: TaskFormPage,
})

const crawlerTaskEditRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/tasks/$id/edit',
  component: TaskFormPage,
})

const crawlerRunsRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/runs',
  component: RunListPage,
})

const crawlerRunDetailRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/runs/$id',
  component: RunDetailPage,
})

const storageConfigRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/storage/config',
  component: StorageConfigPage,
})

const storageTasksRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/storage/tasks',
  component: StorageTaskListPage,
})

const storageTaskDetailRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/storage/tasks/$id',
  component: StorageTaskDetailPage,
})

const storageSubTaskDetailRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/storage/tasks/subtasks/$id',
  component: StorageSubTaskDetailPage,
})

const contentMoviesRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/content/movies',
  component: MovieListPage,
})

const routeTree = rootRoute.addChildren([
  initRoute,
  loginRoute,
  layoutRoute.addChildren([
    indexRoute,
    crawlerIndexRoute,
    crawlerTasksRoute,
    crawlerConfigRoute,
    crawlerTaskNewRoute,
    crawlerTaskEditRoute,
    crawlerRunsRoute,
    crawlerRunDetailRoute,
    storageConfigRoute,
    storageTasksRoute,
    storageTaskDetailRoute,
    storageSubTaskDetailRoute,
    contentMoviesRoute,
  ]),
])

export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
})
