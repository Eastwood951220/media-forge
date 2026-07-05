import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MovieListPage from '../src/pages/content/movies/MovieListPage'
import {
  fetchFilters,
  fetchMovie,
  fetchMovieFilterConfig,
  fetchMovies,
  updateMovieFilterConfig,
} from '../src/api/movie'
import { getTaskDict } from '../src/api/crawlTask'

vi.mock('../src/api/movie', () => ({
  fetchMovies: vi.fn(),
  fetchMovie: vi.fn(),
  fetchFilters: vi.fn(),
  fetchMovieFilterConfig: vi.fn(),
  updateMovieFilterConfig: vi.fn(),
}))

vi.mock('../src/api/crawlTask', () => ({
  getTaskDict: vi.fn(),
}))

function renderPage() {
  return render(
    <AntApp>
      <MovieListPage />
    </AntApp>,
  )
}

const movie = {
  _id: 'movie-1',
  id: 'movie-1',
  code: 'AAA-001',
  source_url: 'https://javdb.com/v/aaa',
  source_name: '测试电影',
  cover: '',
  release_date: '2026-01-01',
  duration: 120,
  director: '导演A',
  maker: '片商A',
  series: '系列A',
  rating: 4.5,
  actors: ['演员A'],
  tags: ['标签A'],
  source_task_name: '任务A',
  source_task_names: ['任务A'],
  marked: false,
  storage_status: 'stored' as const,
  storage_summary: { last_status: 'stored' as const, storage_status: 'stored' as const },
  raw_detail: {},
  created_at: '2026-07-02T00:00:00',
  updated_at: null,
  magnets: [{
    _id: 'm-1',
    id: 'm-1',
    magnet: 'magnet:?x',
    magnet_url: 'magnet:?x',
    name: '磁力A',
    title: '磁力A',
    size_text: '1.2GB',
    has_chinese_sub: true,
    date: '',
    selected: true,
    dedupe_key: 'abc',
  }],
  selected_magnet_dedupe_key: 'abc',
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, resolve, reject }
}

describe('MovieListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(fetchMovies).mockResolvedValue({
      items: [movie],
      total: 1,
      page: 1,
      limit: 20,
      total_pages: 1,
    })
    vi.mocked(fetchMovie).mockResolvedValue(movie)
    vi.mocked(getTaskDict).mockResolvedValue([{ id: 'task-1', name: '任务A' }])
    vi.mocked(fetchFilters).mockImplementation(async (type) => {
      if (type === 'actor') return ['演员A']
      if (type === 'tag') return ['标签A']
      if (type === 'director') return ['导演A']
      if (type === 'maker') return ['片商A']
      if (type === 'series') return ['系列A']
      return []
    })
    vi.mocked(fetchMovieFilterConfig).mockResolvedValue({ _key: 'default', filters: {} })
    vi.mocked(updateMovieFilterConfig).mockResolvedValue({ success: true })
  })

  it('hides configured filters and does not call option or list APIs before filter config completes', () => {
    const configRequest = deferred<Awaited<ReturnType<typeof fetchMovieFilterConfig>>>()
    vi.mocked(fetchMovieFilterConfig).mockReturnValue(configRequest.promise)

    renderPage()

    expect(screen.queryByText('筛选演员')).not.toBeInTheDocument()
    expect(screen.queryByText('筛选标签')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /配置/ })).not.toBeInTheDocument()
    expect(getTaskDict).not.toHaveBeenCalled()
    expect(fetchFilters).not.toHaveBeenCalled()
    expect(fetchMovies).not.toHaveBeenCalled()
  })

  it('loads configured filters and movie list after filter config completes', async () => {
    const configRequest = deferred<Awaited<ReturnType<typeof fetchMovieFilterConfig>>>()
    vi.mocked(fetchMovieFilterConfig).mockReturnValue(configRequest.promise)

    renderPage()

    expect(fetchMovies).not.toHaveBeenCalled()
    expect(fetchFilters).not.toHaveBeenCalled()

    configRequest.resolve({
      _key: 'default',
      filters: {
        actors: { visible: true, order: 0 },
        tags: { visible: false, order: 1 },
        sortBy: { visible: true, order: 2, defaultValue: 'rating:-1' },
      },
    })

    await waitFor(() => {
      expect(screen.queryByText('筛选演员')).toBeInTheDocument()
    })

    expect(screen.queryByText('筛选标签')).not.toBeInTheDocument()

    await waitFor(() => {
      expect(getTaskDict).toHaveBeenCalledTimes(1)
      expect(fetchFilters).toHaveBeenCalled()
      expect(fetchMovies).toHaveBeenCalledTimes(1)
    })

    expect(fetchMovies).toHaveBeenLastCalledWith(expect.objectContaining({
      page: 1,
      limit: 20,
      sort_by: 'rating',
      sort_order: -1,
    }))
  })

  it('renders filters with settings button and opens read-only detail', async () => {
    renderPage()

    expect(await screen.findByText('AAA-001')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('搜索番号、标题...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /配置/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '隐藏搜索' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '刷新列表' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /详情/ }))

    expect(await screen.findByText('影片详情')).toBeInTheDocument()
    expect(screen.getByText('最佳磁力')).toBeInTheDocument()
    expect(screen.getByText('磁力A')).toBeInTheDocument()
    expect(screen.queryByText('删除')).not.toBeInTheDocument()
    expect(screen.queryByText('推送存储')).not.toBeInTheDocument()
    expect(screen.queryByText('标记')).not.toBeInTheDocument()
  })

  it('persists filter drawer settings', async () => {
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: /配置/ }))
    expect(await screen.findByText('筛选条件配置')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '保存配置' }))

    await waitFor(() => {
      expect(updateMovieFilterConfig).toHaveBeenCalled()
    })
  })

  it('sends original filter params when searching after config and options are ready', async () => {
    renderPage()

    await waitFor(() => {
      expect(fetchMovies).toHaveBeenCalledTimes(1)
    })

    await userEvent.type(await screen.findByPlaceholderText('搜索番号、标题...'), 'AAA')
    const searchButtons = screen.getAllByRole('button', { name: /搜\s*索/ })
    await userEvent.click(searchButtons[0])

    await waitFor(() => {
      expect(fetchMovies).toHaveBeenLastCalledWith(expect.objectContaining({
        search: 'AAA',
        page: 1,
        limit: 20,
        sort_by: 'created_at',
        sort_order: -1,
      }))
    })
  })

  it('keeps the requested page when table pagination changes', async () => {
    vi.mocked(fetchMovies).mockResolvedValue({
      items: [movie],
      total: 45,
      page: 1,
      limit: 20,
      total_pages: 3,
    })

    renderPage()

    await waitFor(() => {
      expect(fetchMovies).toHaveBeenCalledTimes(1)
    })

    await userEvent.click(await screen.findByTitle('2'))

    await waitFor(() => {
      expect(fetchMovies).toHaveBeenLastCalledWith(expect.objectContaining({
        page: 2,
        limit: 20,
      }))
    })
  })

  it('does not flash config-hidden filters after config loads', async () => {
    vi.mocked(fetchMovieFilterConfig).mockResolvedValue({
      _key: 'default',
      filters: {
        actors: { visible: true, order: 0 },
        tags: { visible: false, order: 1 },
        tagsNot: { visible: false, order: 2 },
      },
    })

    renderPage()

    expect(await screen.findByText('筛选演员')).toBeInTheDocument()
    expect(screen.queryByText('筛选标签')).not.toBeInTheDocument()
    expect(screen.queryByText('排除标签')).not.toBeInTheDocument()
  })
})
