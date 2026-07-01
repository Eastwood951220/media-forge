import { createFileRoute } from '@tanstack/react-router'
import { redirectIfAuthenticated } from './-guards'
import LoginPage from '@/pages/login/LoginPage'

export const Route = createFileRoute('/login')({
  beforeLoad: redirectIfAuthenticated,
  component: LoginPage,
  validateSearch: (search: Record<string, unknown>) => ({
    redirect: typeof search.redirect === 'string' ? search.redirect : undefined,
  }),
})
