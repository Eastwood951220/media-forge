import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, renderHook, screen, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchFilters, updateMovieFilterConfig } from '@/api/movie'
import { getTaskDict } from '@/api/crawler/crawlTask'
import FilterConfigDrawer from '../components/FilterConfigDrawer'
import { useMovieFilters } from '../hooks/useMovieFilters'

vi.mock('@/api/movie', () => ({
  fetchFilters: vi.fn(),
  updateMovieFilterConfig: vi.fn(),
}))

vi.mock('@/api/crawler/crawlTask', () => ({
  getTaskDict: vi.fn(),
}))

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={client}>
      <App>{children}</App>
    </QueryClientProvider>
  )
}

describe('movie filter configuration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getTaskDict).mockResolvedValue([])
    vi.mocked(fetchFilters).mockResolvedValue([])
    vi.mocked(updateMovieFilterConfig).mockResolvedValue({ filters: {} } as never)
  })

  it('applies configured default values to initial movie query params', async () => {
    const { result } = renderHook(
      () => useMovieFilters({
        filterConfig: {
          storageStatus: { visible: true, order: 10, defaultValue: 'stored' },
          ratingMin: { visible: true, order: 11, defaultValue: 4 },
          actors: { visible: true, order: 0, defaultValue: 'Alice,Bob' },
        },
      }),
      { wrapper },
    )

    await waitFor(() => expect(result.current.optionsLoaded).toBe(true))
    await waitFor(() => expect(result.current.requestParams).toEqual(expect.objectContaining({
      storage_status: 'stored',
      rating_min: 4,
      actors: 'Alice,Bob',
    })))
  })

  it('shows configured movie storage status defaults with matching option labels', async () => {
    render(
      <FilterConfigDrawer
        open
        onClose={vi.fn()}
        onSave={vi.fn()}
        config={{ storageStatus: { visible: true, order: 10, defaultValue: 'stored' } }}
      />,
      { wrapper },
    )

    expect(await screen.findByText('已存储')).toBeInTheDocument()
    expect(screen.queryByText('缺失')).not.toBeInTheDocument()
  })
})
