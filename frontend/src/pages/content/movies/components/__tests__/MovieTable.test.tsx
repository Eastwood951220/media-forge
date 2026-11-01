import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Movie } from '@/api/movie/types'
import { createMovieColumns } from '../MovieTable'

const movie: Movie = {
  _id: 'movie-1',
  id: 'movie-1',
  code: 'AAA-001',
  source_url: 'https://javdb.com/v/aaa',
  source_name: '测试电影',
  cover: 'https://example.test/movie-cover.jpg',
  release_date: '2026-01-01',
  duration: 120,
  director: '导演A',
  maker: '片商A',
  series: '系列A',
  rating: 4.5,
  actors: ['演员A'],
  tags: ['标签A'],
  source_task_names: ['任务A'],
  marked: false,
  storage_status: 'stored',
  storage_summary: { storage_status: 'stored' },
  raw_detail: {},
  created_at: '2026-07-02T00:00:00',
  updated_at: null,
}

describe('MovieTable columns', () => {
  it('renders synced Jellyfin watch state', () => {
    const columns = createMovieColumns({ onViewDetail: vi.fn() })
    const column = columns.find((item) => item.key === 'jellyfin_watch_status')
    expect(column).toBeDefined()
    render(<>{column?.render?.('played', { ...movie, jellyfin_watch_status: 'played' }, 0)}</>)
    expect(screen.getByText('已观看')).toBeInTheDocument()
  })

  it('shows last played time and play count in the movie list', () => {
    const columns = createMovieColumns({ onViewDetail: vi.fn() })
    const lastPlayed = columns.find((item) => item.key === 'jellyfin_last_played_at')
    const playCount = columns.find((item) => item.key === 'jellyfin_play_count')

    expect(lastPlayed).toBeDefined()
    expect(playCount).toBeDefined()
    render(<><span>{String(lastPlayed?.render?.('2026-10-31T02:03:04+00:00', movie, 0))}</span><span>{String(playCount?.render?.(3, movie, 0))}</span></>)
    expect(screen.getByText(/2026/)).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('renders a compact movie cover image in the list', () => {
    const columns = createMovieColumns({ onViewDetail: vi.fn() })
    const coverColumn = columns.find((column) => column.key === 'cover')

    expect(coverColumn?.render).toBeDefined()

    render(<>{coverColumn?.render?.(movie.cover, movie, 0)}</>)

    expect(screen.getByAltText('AAA-001')).toHaveAttribute('src', movie.cover)
  })
})
