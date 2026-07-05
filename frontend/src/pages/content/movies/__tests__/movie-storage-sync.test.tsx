import { describe, expect, it, vi } from 'vitest'
import { syncMovieStorageStatus } from '@/api/movie'

vi.mock('@/api/movie', () => ({
  syncMovieStorageStatus: vi.fn().mockResolvedValue({ total: 1, stored_count: 1, not_stored_count: 0, results: [] }),
}))

describe('Movie storage sync API', () => {
  it('calls syncMovieStorageStatus with selected movie ids', async () => {
    const result = await syncMovieStorageStatus({ movie_ids: ['movie-1'] })
    expect(syncMovieStorageStatus).toHaveBeenCalledWith({ movie_ids: ['movie-1'] })
    expect(result.total).toBe(1)
    expect(result.stored_count).toBe(1)
  })

  it('calls syncMovieStorageStatus with filters when no selection', async () => {
    const result = await syncMovieStorageStatus({ filters: { search: 'test' } })
    expect(syncMovieStorageStatus).toHaveBeenCalledWith({ filters: { search: 'test' } })
    expect(result.total).toBe(1)
  })
})
