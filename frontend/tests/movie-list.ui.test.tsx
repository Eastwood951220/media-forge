import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MovieListPage from '../src/pages/content/movies/MovieListPage'
import { getMovie, getMovies } from '../src/api/movie'

vi.mock('../src/api/movie', () => ({
  getMovies: vi.fn(),
  getMovie: vi.fn(),
}))

describe('MovieListPage', () => {
  beforeEach(() => {
    vi.mocked(getMovies).mockResolvedValue({
      rows: [{
        id: 'movie-1',
        code: 'AAA-001',
        source_url: 'https://javdb.com/v/aaa',
        source_name: '测试电影',
        cover: '',
        release_date: '2026-01-01',
        duration: 120,
        director: '',
        maker: '',
        series: '',
        rating: 4.5,
        actors: ['演员A'],
        tags: ['标签A'],
        source_task_names: ['任务A'],
        storage_summary: {},
        raw_detail: {},
        created_at: '2026-07-02T00:00:00',
        updated_at: null,
      }],
      total: 1,
    })
    vi.mocked(getMovie).mockResolvedValue({
      id: 'movie-1',
      code: 'AAA-001',
      source_url: 'https://javdb.com/v/aaa',
      source_name: '测试电影',
      cover: '',
      release_date: '2026-01-01',
      duration: 120,
      director: '',
      maker: '',
      series: '',
      rating: 4.5,
      actors: ['演员A'],
      tags: ['标签A'],
      source_task_names: ['任务A'],
      storage_summary: {},
      raw_detail: {},
      created_at: '2026-07-02T00:00:00',
      updated_at: null,
      magnets: [{ id: 'm-1', magnet_url: 'magnet:?x', name: '磁力A', size_text: '', has_chinese_sub: false, date: '', selected: false }],
    })
  })

  it('renders movies and opens read-only detail', async () => {
    render(<MovieListPage />)

    expect(await screen.findByText('AAA-001')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '详情' }))
    expect(await screen.findByText('磁力A')).toBeInTheDocument()
    expect(screen.queryByText('删除')).not.toBeInTheDocument()
  })
})
