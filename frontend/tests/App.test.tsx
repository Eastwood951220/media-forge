import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { createMemoryHistory } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { routeTree } from '../src/routeTree.gen'
import { queryClient } from '../src/lib/query-client'
import { useAuthStore } from '../src/stores/useAuthStore'

function renderApp(initialPath = '/') {
  const history = createMemoryHistory({ initialEntries: [initialPath] })
  const router = createRouter({
    routeTree,
    context: { queryClient },
    history,
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

describe('App auth routing', () => {
  beforeEach(() => {
    // Reset auth state before each test
    useAuthStore.setState({
      token: '',
      isAuthenticated: false,
      userInfo: null,
      roles: [],
      permissions: [],
      hasUserInfo: false,
    })
  })

  it('redirects unauthenticated user to login page', async () => {
    renderApp('/')

    await waitFor(() => {
      expect(screen.getByText(/media forge/i)).toBeInTheDocument()
      expect(screen.getByText(/媒体处理平台/i)).toBeInTheDocument()
    })
  })

  it('shows dashboard for authenticated user', async () => {
    useAuthStore.setState({ token: 'test-token', isAuthenticated: true })

    renderApp('/')

    await waitFor(() => {
      const matches = screen.getAllByText(/media forge/i)
      expect(matches.length).toBeGreaterThanOrEqual(2)
      expect(screen.getByText(/welcome to media forge dashboard/i)).toBeInTheDocument()
    })
  })
})
