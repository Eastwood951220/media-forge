import { useState, useEffect } from 'react'
import './styles/app.css'
import './styles/view-transition.css'
import { RouterProvider } from '@tanstack/react-router'
import { router } from './routes'
import { queryClient } from './lib/query-client'
import { QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/useAuthStore'
import { useThemeStore } from '@/stores/useThemeStore'
import { checkInitStatus } from './routes/-guards'
import { Spin } from 'antd'

function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const darkMode = useThemeStore((s) => s.darkMode)
  const primaryColor = useThemeStore((s) => s.primaryColor)
  const [ready, setReady] = useState(false)

  // Sync root theme attributes for Ant Design tokens, app CSS, and theme-toggle CSS.
  useEffect(() => {
    const root = document.documentElement
    root.dataset.theme = darkMode ? 'dark' : 'light'
    root.classList.toggle('dark', darkMode)
    root.style.setProperty('--app-primary-color', primaryColor)
  }, [darkMode, primaryColor])

  useEffect(() => {
    if (isAuthenticated) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- App readiness intentionally flips once auth state settles.
      setReady(true)
    } else {
      checkInitStatus().then(() => {
        setReady(true)
      })
    }
  }, [isAuthenticated])

  if (!ready) {
    return (
      <div className="app-loading">
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
