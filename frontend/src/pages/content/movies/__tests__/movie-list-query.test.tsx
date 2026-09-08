import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
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
  beforeEach(() => {
    vi.clearAllMocks()
  })
  it('loads movie list through a query keyed by filters and pagination', async () => {
    vi.mocked(fetchMovies).mockResolvedValue({ items: [], total: 0 } as never)

    const { result } = renderHook(() => useMovieList({ search: 'abc' } as never), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual({ items: [], total: 0 })
    expect(fetchMovies).toHaveBeenCalledWith(expect.objectContaining({ search: 'abc', page: 1 }))
  })

  it('loads movies when filters transition from not ready to empty filters', async () => {
    vi.mocked(fetchMovies).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, total_pages: 1 } as never)

    const { result, rerender } = renderHook(
      ({ filters }) => useMovieList(filters as never),
      { wrapper, initialProps: { filters: undefined as Record<string, never> | undefined } },
    )

    await act(async () => {})
    expect(fetchMovies).not.toHaveBeenCalled()

    rerender({ filters: {} })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fetchMovies).toHaveBeenCalledWith(expect.objectContaining({ page: 1, limit: 20 }))
  })

  it('searches with the current ready filters after starting not ready', async () => {
    vi.mocked(fetchMovies).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, total_pages: 1 } as never)

    const { result, rerender } = renderHook(
      ({ filters }) => useMovieList(filters as never),
      { wrapper, initialProps: { filters: undefined as { search?: string } | undefined } },
    )

    rerender({ filters: { search: 'ready' } })
    await waitFor(() => expect(fetchMovies).toHaveBeenCalledWith(expect.objectContaining({ search: 'ready' })))

    vi.mocked(fetchMovies).mockClear()
    act(() => result.current.search())

    await waitFor(() => expect(fetchMovies).toHaveBeenCalledWith(expect.objectContaining({ search: 'ready', page: 1 })))
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
    act(() => result.current.setSelectedRowKeys(['movie-1']))

    rerender({ filters: { search: 'xyz' } })

    await waitFor(() => expect(result.current.page).toBe(1))
    expect(result.current.selectedRowKeys).toEqual([])
    // The reload after the filter change must target the first page with the new filters.
    expect(fetchMovies).toHaveBeenCalledWith(expect.objectContaining({ search: 'xyz', page: 1 }))
  })

  it('does not reset or refetch when a new object of equal filter content arrives', async () => {
    vi.mocked(fetchMovies).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, total_pages: 1 } as never)

    const { result, rerender } = renderHook(
      ({ filters }) => useMovieList(filters as never),
      { wrapper, initialProps: { filters: { search: 'abc' } } },
    )

    await waitFor(() => expect(result.current.loading).toBe(false))
    act(() => result.current.handlePageChange(3, 20))
    await waitFor(() => expect(result.current.page).toBe(3))

    const callsBeforeEqualContentRerender = vi.mocked(fetchMovies).mock.calls.length
    rerender({ filters: { search: 'abc' } })

    await act(async () => {})
    expect(result.current.page).toBe(3)
    expect(vi.mocked(fetchMovies).mock.calls.length).toBe(callsBeforeEqualContentRerender)
  })

  it('discards responses from superseded requests that resolve out of order', async () => {
    const filters = { search: 'abc' }
    const resolvers: Array<(value: never) => void> = []
    vi.mocked(fetchMovies).mockImplementation((() => new Promise<never>((resolve) => {
      resolvers.push(resolve)
    })) as never)

    const { result } = renderHook(() => useMovieList(filters as never), { wrapper })
    await waitFor(() => expect(resolvers).toHaveLength(1))
    act(() => resolvers[0]({ items: [], total: 0, page: 1, page_size: 20, total_pages: 1 } as never))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.handlePageChange(2, 20))
    await waitFor(() => expect(resolvers).toHaveLength(2))
    act(() => result.current.handlePageChange(3, 20))
    await waitFor(() => expect(resolvers).toHaveLength(3))

    const page3Result = { items: [{ _id: 'm-3' }], total: 1, page: 3, page_size: 20, total_pages: 1 }
    const page2Result = { items: [{ _id: 'm-2' }], total: 1, page: 2, page_size: 20, total_pages: 1 }

    // Newest (page 3) resolves first and is applied...
    await act(async () => { resolvers[2](page3Result as never) })
    expect(result.current.data).toEqual(page3Result)
    // ...then the superseded page-2 response lands late and must be discarded.
    await act(async () => { resolvers[1](page2Result as never) })
    expect(result.current.data).toEqual(page3Result)
  })

  it('refreshes storage fields for the current page without resetting pagination or sort', async () => {
    const initialPage = {
      items: [
        {
          _id: 'movie-1',
          storage_status: 'not_stored',
          storage_locations: [],
          storage_summary: { storage_status: 'not_stored' },
          code: 'AAA-001',
        },
      ],
      total: 40,
      page: 1,
      limit: 20,
      total_pages: 2,
    }
    const pageThree = {
      ...initialPage,
      items: [
        {
          ...initialPage.items[0],
          _id: 'movie-1',
          storage_status: 'not_stored',
          storage_locations: [],
          storage_summary: { storage_status: 'not_stored' },
        },
      ],
      page: 3,
    }
    const refreshedPageThree = {
      ...pageThree,
      items: [
        {
          ...pageThree.items[0],
          code: 'SHOULD-NOT-REPLACE',
          storage_status: 'stored',
          storage_locations: ['Movies/AAA-001'],
          storage_summary: { storage_status: 'stored', synced_at: '2026-09-08T00:00:00Z' },
        },
      ],
    }

    vi.mocked(fetchMovies)
      .mockResolvedValueOnce(initialPage as never)
      .mockResolvedValueOnce(pageThree as never)
      .mockResolvedValueOnce(refreshedPageThree as never)

    const { result } = renderHook(
      () => useMovieList({ search: 'abc' } as never, { sortBy: 'rating', sortOrder: -1 }),
      { wrapper },
    )

    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.handlePageChange(3, 50))

    await waitFor(() => expect(fetchMovies).toHaveBeenCalledWith(expect.objectContaining({
      search: 'abc',
      page: 3,
      limit: 50,
      sort_by: 'rating',
      sort_order: -1,
    })))

    await act(async () => {
      await result.current.refreshStorageFields()
    })

    expect(result.current.page).toBe(3)
    expect(result.current.pageSize).toBe(50)
    expect(result.current.sortBy).toBe('rating')
    expect(result.current.sortOrder).toBe(-1)
    expect(result.current.data.items[0]).toEqual(expect.objectContaining({
      code: 'AAA-001',
      storage_status: 'stored',
      storage_locations: ['Movies/AAA-001'],
      storage_summary: { storage_status: 'stored', synced_at: '2026-09-08T00:00:00Z' },
    }))
    expect(result.current.loading).toBe(false)
  })
})
