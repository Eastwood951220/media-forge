import { createRootRoute, createRoute, createRouter, Outlet } from '@tanstack/react-router'
import { ConfigProvider, App as AntApp } from 'antd'
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
  validateSearch: (search: Record<string, unknown>) => ({
    redirect: typeof search.redirect === 'string' ? search.redirect : undefined,
  }),
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
