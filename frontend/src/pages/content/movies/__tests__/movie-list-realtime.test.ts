import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useMovieListRealtime } from '../hooks/useMovieListRealtime'

const { handlers } = vi.hoisted(() => ({
  handlers: {} as Record<string, Array<(event: unknown) => void>>,
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  subscribeRealtime: (name: string, handler: (event: unknown) => void) => {
    handlers[name] = [...(handlers[name] ?? []), handler]
    return () => {
      handlers[name] = (handlers[name] ?? []).filter((item) => item !== handler)
    }
  },
}))

function emitStorageUpdate(movieId: string, storageStatus: string) {
  for (const handler of handlers['movie.storage.updated'] ?? []) {
    handler({ payload: { movie_id: movieId, storage_summary: { storage_status: storageStatus } } })
  }
}

function emitScrapingUpdate(
  movieId: string,
  scrapingStatus: 'scraped' | 'not_scraped' | null,
  scrapingCheckedAt: string | null,
) {
  for (const handler of handlers['movie.scraping.updated'] ?? []) {
    handler({
      payload: {
        movie_id: movieId,
        scraping_status: scrapingStatus,
        scraping_checked_at: scrapingCheckedAt,
      },
    })
  }
}

describe('useMovieListRealtime', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    for (const key of Object.keys(handlers)) delete handlers[key]
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('coalesces a burst of storage events into a single batched update', () => {
    const applyStorageUpdates = vi.fn()
    renderHook(() => useMovieListRealtime(applyStorageUpdates))

    act(() => {
      emitStorageUpdate('movie-1', 'storing')
      emitStorageUpdate('movie-2', 'stored')
      emitStorageUpdate('movie-1', 'stored')
    })

    // Nothing is committed until the coalescing window closes.
    expect(applyStorageUpdates).not.toHaveBeenCalled()

    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(applyStorageUpdates).toHaveBeenCalledTimes(1)
    expect(applyStorageUpdates.mock.calls[0][0]).toEqual([
      { movie_id: 'movie-1', storage_summary: { storage_status: 'storing' } },
      { movie_id: 'movie-2', storage_summary: { storage_status: 'stored' } },
      { movie_id: 'movie-1', storage_summary: { storage_status: 'stored' } },
    ])
  })

  it('starts a fresh window for a later burst', () => {
    const applyStorageUpdates = vi.fn()
    renderHook(() => useMovieListRealtime(applyStorageUpdates))

    act(() => {
      emitStorageUpdate('movie-1', 'storing')
      vi.advanceTimersByTime(100)
    })
    act(() => {
      emitStorageUpdate('movie-2', 'stored')
      vi.advanceTimersByTime(100)
    })

    expect(applyStorageUpdates).toHaveBeenCalledTimes(2)
    expect(applyStorageUpdates.mock.calls[0][0]).toHaveLength(1)
    expect(applyStorageUpdates.mock.calls[1][0]).toEqual([
      { movie_id: 'movie-2', storage_summary: { storage_status: 'stored' } },
    ])
  })

  it('applies movie.scraping.updated events immediately', () => {
    const applyStorageUpdates = vi.fn()
    const applyScrapingUpdates = vi.fn()
    renderHook(() => useMovieListRealtime(applyStorageUpdates, applyScrapingUpdates))

    act(() => {
      emitScrapingUpdate('movie-1', 'scraped', '2026-01-02T03:04:05.000Z')
    })

    expect(applyScrapingUpdates).toHaveBeenCalledWith([
      {
        movie_id: 'movie-1',
        scraping_status: 'scraped',
        scraping_checked_at: '2026-01-02T03:04:05.000Z',
      },
    ])
  })

  it('drops a pending batch when the page unmounts', () => {
    const applyStorageUpdates = vi.fn()
    const { unmount } = renderHook(() => useMovieListRealtime(applyStorageUpdates))

    act(() => {
      emitStorageUpdate('movie-1', 'stored')
    })
    unmount()
    act(() => {
      vi.advanceTimersByTime(1000)
    })

    expect(applyStorageUpdates).not.toHaveBeenCalled()
  })
})
