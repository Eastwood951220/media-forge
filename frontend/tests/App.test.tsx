import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { createMemoryHistory } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { routeTree } from '../src/routeTree.gen'
import { queryClient } from '../src/lib/query-client'

function renderApp() {
  const history = createMemoryHistory({ initialEntries: ['/'] })
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

describe('App smoke test', () => {
  it('renders the Media Forge heading', async () => {
    renderApp()

    await waitFor(() => {
      expect(screen.getByText(/media forge/i)).toBeInTheDocument()
    })
  })
})
