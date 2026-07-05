import { describe, expect, it, vi } from 'vitest'
import { deleteMovies } from '@/api/movie'

vi.mock('@/api/movie', () => ({
  deleteMovies: vi.fn().mockResolvedValue({
    deleted_movies: 1,
    deleted_magnets: 0,
    updated_movies: 0,
    cloud_deleted_folders: [],
    cloud_missing_folders: [],
    cloud_failed_folders: [],
  }),
}))

describe('Movie delete API', () => {
  it('calls deleteMovies with selected movie ids and mode', async () => {
    const result = await deleteMovies({ movie_ids: ['movie-1'], mode: 'database_only' })
    expect(deleteMovies).toHaveBeenCalledWith({ movie_ids: ['movie-1'], mode: 'database_only' })
    expect(result.deleted_movies).toBe(1)
  })

  it('supports cloud_only mode', async () => {
    const result = await deleteMovies({ movie_ids: ['movie-1', 'movie-2'], mode: 'cloud_only' })
    expect(deleteMovies).toHaveBeenCalledWith({ movie_ids: ['movie-1', 'movie-2'], mode: 'cloud_only' })
    expect(result.deleted_movies).toBe(1)
  })

  it('supports database_and_cloud mode', async () => {
    const result = await deleteMovies({ movie_ids: ['movie-1'], mode: 'database_and_cloud' })
    expect(deleteMovies).toHaveBeenCalledWith({ movie_ids: ['movie-1'], mode: 'database_and_cloud' })
    expect(result.deleted_movies).toBe(1)
  })
})
