import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fetchMovies } from '@/api/movie'
import { useMovieList } from '../hooks/useMovieList'

vi.mock('@/api/movie', () => ({
  fetchMovies: vi.fn(),
  syncMovieStorageStatus: vi.fn(),
}))

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={client}>
      <App>{children}</App>
    </QueryClientProvider>
  )
}

describe('useMovieList', () => {
  it('loads movie list through a query keyed by filters and pagination', async () => {
    vi.mocked(fetchMovies).mockResolvedValue({ items: [], total: 0 } as any)

    const { result } = renderHook(() => useMovieList({ search: 'abc' } as any), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual({ items: [], total: 0 })
    expect(fetchMovies).toHaveBeenCalledWith(expect.objectContaining({ search: 'abc', page: 1 }))
  })
})
