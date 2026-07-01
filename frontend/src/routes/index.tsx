import { createFileRoute } from '@tanstack/react-router'
import { requireAuth } from './-guards'
import DashboardPage from '@/pages/dashboard/DashboardPage'

export const Route = createFileRoute('/')({
  beforeLoad: requireAuth,
  component: DashboardPage,
})
