import { redirect } from '@tanstack/react-router'
import { useAuthStore } from '@/stores/useAuthStore'

export function requireAuth() {
  const { isAuthenticated } = useAuthStore.getState()

  if (!isAuthenticated) {
    const currentPath = window.location.pathname + window.location.search

    throw redirect({
      to: '/login',
      search: { redirect: currentPath !== '/login' ? currentPath : undefined },
    })
  }
}

export function redirectIfAuthenticated() {
  const { isAuthenticated } = useAuthStore.getState()

  if (isAuthenticated) {
    throw redirect({ to: '/' })
  }
}

// --- Init check ---

let _initChecked = false
let _initResult: { initialized: boolean } | null = null

export async function checkInitStatus(): Promise<boolean> {
  if (_initChecked && _initResult !== null) {
    return _initResult.initialized
  }
  // Dynamic import to avoid circular dependency with api module
  const { getInitConfig } = await import('@/api/init')
  try {
    const res = await getInitConfig()
    _initResult = res as unknown as { initialized: boolean }
    _initChecked = true
    return _initResult.initialized
  } catch {
    _initChecked = true
    _initResult = { initialized: false }
    return false
  }
}

export async function requireInit(): Promise<void> {
  const isInit = await checkInitStatus()
  if (!isInit) {
    throw redirect({ to: '/init' as never })
  }
}
