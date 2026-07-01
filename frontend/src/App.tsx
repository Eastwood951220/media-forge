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

  // Sync data-theme to <html> for Tailwind dark mode + CSS custom properties
  useEffect(() => {
    document.documentElement.dataset.theme = darkMode ? 'dark' : 'light'
    document.documentElement.style.setProperty('--app-primary-color', primaryColor)
  }, [darkMode, primaryColor])

  useEffect(() => {
    if (isAuthenticated) {
      setReady(true)
    } else {
      checkInitStatus().then(() => {
        setReady(true)
      })
    }
  }, [isAuthenticated])

  if (!ready) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
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
