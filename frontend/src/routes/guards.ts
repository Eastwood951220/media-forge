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
