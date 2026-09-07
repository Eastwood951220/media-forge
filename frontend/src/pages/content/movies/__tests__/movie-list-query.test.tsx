import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
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
    vi.mocked(fetchMovies).mockResolvedValue({ items: [], total: 0 } as never)

    const { result } = renderHook(() => useMovieList({ search: 'abc' } as never), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual({ items: [], total: 0 })
    expect(fetchMovies).toHaveBeenCalledWith(expect.objectContaining({ search: 'abc', page: 1 }))
  })

  it('resets to the first page when effective filters change', async () => {
    vi.mocked(fetchMovies).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, total_pages: 1 } as never)

    const { result, rerender } = renderHook(
      ({ filters }) => useMovieList(filters as never),
      { wrapper, initialProps: { filters: { search: 'abc' } } },
    )

    await waitFor(() => expect(result.current.loading).toBe(false))
    act(() => result.current.handlePageChange(3, 20))
    await waitFor(() => expect(result.current.page).toBe(3))

    rerender({ filters: { search: 'xyz' } })

    await waitFor(() => expect(result.current.page).toBe(1))
    expect(result.current.selectedRowKeys).toEqual([])
  })
})
