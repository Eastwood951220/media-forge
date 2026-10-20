import {
  createRootRoute,
  createRoute,
  createRouter,
  lazyRouteComponent,
  Outlet,
  redirect,
} from '@tanstack/react-router'
import { ConfigProvider, App as AntApp, theme } from 'antd'
import { useThemeStore } from '@/stores/useThemeStore'
import { redirectIfAuthenticated, requireAuth, requireInit } from './-guards'
import { RoutePending } from './-routePending'
import AppLayout from '@/layout'

// Route pages load on demand, so opening one page no longer downloads and
// parses the crawler, storage, movie, chart, and editor code of every other
// page. The authenticated shell stays eager because every route needs it.
const LoginPage = lazyRouteComponent(() => import('@/pages/login/LoginPage'))
const InitPage = lazyRouteComponent(() => import('@/pages/init/InitPage'))
const DashboardPage = lazyRouteComponent(() => import('@/pages/dashboard/DashboardPage'))
const ConfigPage = lazyRouteComponent(() => import('@/pages/crawler/config/ConfigPage'))
const TaskListPage = lazyRouteComponent(() => import('@/pages/crawler/tasks/TaskListPage'))
const TaskFormPage = lazyRouteComponent(() => import('@/pages/crawler/tasks/TaskFormPage'))
const RunListPage = lazyRouteComponent(() => import('@/pages/crawler/runs/RunListPage'))
const RunDetailPage = lazyRouteComponent(() => import('@/pages/crawler/runs/RunDetailPage'))
const ScheduleListPage = lazyRouteComponent(() => import('@/pages/crawler/schedules/ScheduleListPage'))
const ActressListPage = lazyRouteComponent(() => import('@/pages/content/actresses/ActressListPage'))
const ActressDetailPage = lazyRouteComponent(() => import('@/pages/content/actresses/ActressDetailPage'))
const MovieListPage = lazyRouteComponent(() => import('@/pages/content/movies/MovieListPage'))
const BackupPage = lazyRouteComponent(() => import('@/pages/backup/BackupPage'))
const StorageConfigPage = lazyRouteComponent(() => import('@/pages/storage/config/StorageConfigPage'))
const StorageTaskListPage = lazyRouteComponent(() => import('@/pages/storage/tasks/StorageTaskListPage'))
const StorageTaskDetailPage = lazyRouteComponent(() => import('@/pages/storage/tasks/StorageTaskDetailPage'))
const StorageSubTaskDetailPage = lazyRouteComponent(() => import('@/pages/storage/tasks/StorageSubTaskDetailPage'))
const ScrapingConfigPage = lazyRouteComponent(() => import('@/pages/scraping/config/ScrapingConfigPage'))
const ScrapingTaskListPage = lazyRouteComponent(() => import('@/pages/scraping/tasks/TaskListPage'))
const ScrapingTaskDetailPage = lazyRouteComponent(() => import('@/pages/scraping/tasks/TaskDetailPage'))

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

const crawlerSchedulesRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/schedules',
  component: ScheduleListPage,
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

const scrapingTasksRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/scraping/tasks',
  component: ScrapingTaskListPage,
})

const scrapingTaskDetailRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/scraping/tasks/$id',
  component: ScrapingTaskDetailPage,
})

const scrapingConfigRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/scraping/config',
  component: ScrapingConfigPage,
})

const contentMoviesRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/content/movies',
  component: MovieListPage,
  validateSearch: (search: Record<string, unknown>): { task_id?: string; search?: string } => {
    const parsed: { task_id?: string; search?: string } = {}
    if (typeof search.task_id === 'string') parsed.task_id = search.task_id
    if (typeof search.search === 'string') parsed.search = search.search
    return parsed
  },
})

const contentActressesRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/content/actresses',
  component: ActressListPage,
})

const contentActressDetailRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/content/actresses/$id',
  component: ActressDetailPage,
})

const backupRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/backup',
  component: BackupPage,
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
    crawlerSchedulesRoute,
    storageConfigRoute,
    storageTasksRoute,
    storageTaskDetailRoute,
    storageSubTaskDetailRoute,
    scrapingTasksRoute,
    scrapingTaskDetailRoute,
    scrapingConfigRoute,
    contentMoviesRoute,
    contentActressesRoute,
    contentActressDetailRoute,
    backupRoute,
  ]),
])

export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
  defaultPendingComponent: RoutePending,
})
