import { describe, expect, it, vi } from 'vitest'
import { createMovieColumns } from '../src/pages/content/movies/components/MovieTable'

describe('MovieTable columns', () => {
  it('keeps rating and release date sorting controlled by the query form only', () => {
    const columns = createMovieColumns({ onViewDetail: vi.fn() })
    const ratingColumn = columns.find((column) => column.key === 'rating')
    const releaseDateColumn = columns.find((column) => column.key === 'release_date')

    expect(ratingColumn).toMatchObject({ key: 'rating' })
    expect(releaseDateColumn).toMatchObject({ key: 'release_date' })
    expect(ratingColumn).not.toHaveProperty('sorter')
    expect(ratingColumn).not.toHaveProperty('defaultSortOrder')
    expect(releaseDateColumn).not.toHaveProperty('sorter')
    expect(releaseDateColumn).not.toHaveProperty('defaultSortOrder')
  })
})
