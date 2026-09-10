import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ActressListPage from '../ActressListPage'
import ActressDetailPage from '../ActressDetailPage'
import { createTaskUrlRun } from '@/api/crawler/crawlTask'
import { fetchActress, fetchActresses, getActressTags, updateActressTags } from '@/api/content/actresses'
import { useImageBlurStore } from '@/stores/useImageBlurStore'

const navigateMock = vi.hoisted(() => vi.fn())

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
  useParams: () => ({ id: 'actress-1' }),
}))

vi.mock('@/api/content/actresses', () => ({
  fetchActress: vi.fn(),
  fetchActresses: vi.fn(),
  getActressTags: vi.fn(),
  updateActressTags: vi.fn(),
}))

vi.mock('@/api/crawler/crawlTask', () => ({
  createTaskUrlRun: vi.fn(),
}))

const profile = {
  id: 'actress-1',
  _id: 'actress-1',
  display_name: '宮上唯依花',
  reading: 'みやうえゆいか',
  aliases: ['Miyaue Yuika'],
  canonical_names: ['宮上唯依花', 'Miyaue Yuika'],
  source_url: 'https://db.avjoho.com/宮上唯依花/',
  source_site: 'avjoho',
  source_task_ids: ['task-1'],
  source_task_url_ids: ['url-1'],
  external_links: [],
  tags: ['单体', '清楚'],
  image_url: 'https://example.test/cover.jpg',
  debut_date: '2026-09-03',
  birth_date: '1977-12-01',
  height_cm: 163,
  bust_cm: 90,
  waist_cm: 62,
  hip_cm: 93,
  cup: 'E',
  birthplace: '京都府',
  blood_type: 'A型',
  hobbies: 'ヨガ',
  biography: '2026年にデビュー。',
  exclusive_maker: 'DAHLIA',
  sns_links: [],
  representative_works: [],
  similar_actresses: [],
  raw_profile: {},
  last_fetched_at: '2026-09-09T10:00:00',
  created_at: '2026-09-09T10:00:00',
  updated_at: null,
}

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <App>{ui}</App>
    </QueryClientProvider>,
  )
}

describe('Actress pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useImageBlurStore.setState({ enabled: true })
    vi.mocked(updateActressTags).mockResolvedValue(profile)
    vi.mocked(createTaskUrlRun).mockResolvedValue({ accepted: true, run_id: 'run-1' } as never)
    vi.mocked(getActressTags).mockResolvedValue([
      { id: 'tag-1', name: '清楚' },
      { id: 'tag-2', name: '企划' },
    ])
  })

  it('renders actress cards and requests the default 24 item page size', async () => {
    vi.mocked(fetchActresses).mockResolvedValue({ items: [profile], total: 1, page: 1, limit: 24, total_pages: 1 })

    renderWithClient(<ActressListPage />)

    await waitFor(() => {
      expect(fetchActresses).toHaveBeenCalledWith(expect.objectContaining({ page: 1, limit: 24 }))
    })
    expect(await screen.findByText('宮上唯依花')).toBeInTheDocument()
    expect(screen.getByText('みやうえゆいか')).toBeInTheDocument()
    expect(screen.getByText('单体')).toBeInTheDocument()
    expect(screen.getByText('清楚')).toBeInTheDocument()
    expect(screen.getByLabelText('标签')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '预览 宮上唯依花' })).not.toBeInTheDocument()
    expect(screen.getByAltText('宮上唯依花').className).toMatch(/blurred/)
  })

  it('opens actress detail directly when clicking a list card image without preview', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchActresses).mockResolvedValue({ items: [profile], total: 1, page: 1, limit: 24, total_pages: 1 })

    renderWithClient(<ActressListPage />)

    await user.click(await screen.findByAltText('宮上唯依花'))

    expect(navigateMock).toHaveBeenCalledWith({ to: '/content/actresses/$id', params: { id: 'actress-1' } })
  })

  it('keeps advanced filters collapsed and sends dropdown range filters when expanded', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchActresses).mockResolvedValue({ items: [], total: 0, page: 1, limit: 24, total_pages: 1 })

    renderWithClient(<ActressListPage />)

    expect(screen.queryByLabelText('罩杯')).not.toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: '更多筛选' }))
    await user.click(screen.getByLabelText('罩杯'))
    await user.click(await screen.findByText('E杯'))
    await user.click(screen.getByLabelText('身高'))
    await user.click(await screen.findByText('162-165cm'))
    await user.click(screen.getByLabelText('年龄'))
    await user.click(await screen.findByText('30代'))
    await user.click(screen.getByLabelText('胸围'))
    await user.click(await screen.findByText('B90-94cm'))
    await user.click(screen.getByLabelText('腰围'))
    await user.click(await screen.findByText('W56-59cm'))
    await user.click(screen.getByLabelText('臀围'))
    await user.click(await screen.findByText('H85-88cm'))

    await waitFor(() => {
      expect(fetchActresses).toHaveBeenLastCalledWith(expect.objectContaining({
        page: 1,
        limit: 24,
        cup: 'E',
        height_range: '162_165',
        age_range: '30s',
        bust_range: '90_94',
        waist_range: '56_59',
        hip_range: '85_88',
      }))
    })
  })

  it('renders standalone detail with recent movies sorted by backend response', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchActress).mockResolvedValue({
      ...profile,
      recent_movies: [
        { id: 'movie-1', code: 'NEW-001', title: 'New Movie', cover: 'https://example.test/new.jpg', release_date: '2026-09-01' },
        { id: 'movie-2', code: 'OLD-001', title: 'Old Movie', cover: 'https://example.test/old.jpg', release_date: '2026-01-01' },
      ],
    })

    renderWithClient(<ActressDetailPage />)

    expect(await screen.findByText('最近影片')).toBeInTheDocument()
    expect(screen.getByText('NEW-001')).toBeInTheDocument()
    expect(screen.getByText('New Movie')).toBeInTheDocument()
    expect(screen.getByText('OLD-001')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /NEW-001/ }))
    expect(navigateMock).toHaveBeenCalledWith({ to: '/content/movies', search: { search: 'NEW-001' } })
  })

  it('does not open movie list when closing a recent movie image preview', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchActress).mockResolvedValue({
      ...profile,
      recent_movies: [
        { id: 'movie-1', code: 'NEW-001', title: 'New Movie', cover: 'https://example.test/new.jpg', release_date: '2026-09-01' },
      ],
    })

    renderWithClient(<ActressDetailPage />)

    await user.click(await screen.findByRole('button', { name: '预览 New Movie' }))
    expect(await screen.findByRole('dialog', { name: 'New Movie' })).toHaveClass('ant-image-preview')

    await user.click(await screen.findByRole('button', { name: /close/i }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'New Movie' })).not.toBeInTheDocument()
    })
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('renders profile metadata in a structured detail layout', async () => {
    const today = new Date()
    const birthDate = `${today.getFullYear() - 48}-01-01`
    vi.mocked(fetchActress).mockResolvedValue({
      ...profile,
      birth_date: birthDate,
      aliases: ['Miyaue Yuika', '宮上ゆいか'],
      recent_movies: [],
    })

    renderWithClient(<ActressDetailPage />)

    expect(await screen.findByRole('heading', { name: '宮上唯依花' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '预览 宮上唯依花' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '查看 avjoho 资料' })).toHaveAttribute('href', profile.source_url)
    expect(screen.getByText('别名')).toBeInTheDocument()
    expect(screen.getByText('Miyaue Yuika')).toBeInTheDocument()
    expect(screen.getByText('宮上ゆいか')).toBeInTheDocument()
    expect(screen.getByText('基础资料')).toBeInTheDocument()
    expect(screen.getByText('年龄')).toBeInTheDocument()
    expect(screen.getByText('48岁')).toBeInTheDocument()
    expect(screen.getByText('身高')).toBeInTheDocument()
    expect(screen.getByText('163cm')).toBeInTheDocument()
    expect(screen.getByText('三围')).toBeInTheDocument()
    expect(screen.getByText('B90 / W62 / H93')).toBeInTheDocument()
  })

  it('renders avjoho and external site links in the detail header', async () => {
    vi.mocked(fetchActress).mockResolvedValue({
      ...profile,
      external_links: [
        {
          id: 'url-1',
          task_id: 'task-1',
          source: 'javdb',
          label: 'JavDB',
          url: 'https://javdb.com/actors/yuika',
          url_type: 'actors',
          url_name: '宮上唯依花',
        },
        {
          id: 'url-2',
          task_id: 'task-1',
          source: 'javbus',
          label: 'JavBus',
          url: 'https://www.javbus.com/star/abc',
          url_type: 'actors',
          url_name: '宮上唯依花',
        },
      ],
      recent_movies: [],
    })

    renderWithClient(<ActressDetailPage />)

    expect(await screen.findByRole('link', { name: '查看 avjoho 资料' })).toHaveAttribute('href', profile.source_url)
    expect(screen.getByRole('link', { name: '查看 JavDB 关联' })).toHaveAttribute('href', 'https://javdb.com/actors/yuika')
    expect(screen.getByRole('link', { name: '查看 JavBus 关联' })).toHaveAttribute('href', 'https://www.javbus.com/star/abc')
  })

  it('updates tags from the detail page', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchActress).mockResolvedValue({ ...profile, recent_movies: [] })

    renderWithClient(<ActressDetailPage />)

    await user.click(await screen.findByRole('button', { name: '编辑标签' }))
    await user.click(screen.getByRole('button', { name: /保\s*存/ }))

    expect(updateActressTags).toHaveBeenCalledWith('actress-1', { tags: ['单体', '清楚'] })
  })

  it('offers existing actress tags in the detail tag editor', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchActress).mockResolvedValue({ ...profile, recent_movies: [] })

    renderWithClient(<ActressDetailPage />)

    await user.click(await screen.findByRole('button', { name: '编辑标签' }))
    await user.click(screen.getByRole('combobox', { name: '编辑标签' }))
    expect(await screen.findByRole('option', { name: '企划' })).toBeInTheDocument()
  })

  it('submits a movie crawl for the selected actress link', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchActress).mockResolvedValue({
      ...profile,
      external_links: [
        {
          id: 'url-1',
          task_id: 'task-1',
          source: 'javdb',
          label: 'JavDB',
          url: 'https://javdb.com/actors/yuika',
          url_type: 'actors',
          url_name: '宮上唯依花',
        },
      ],
      recent_movies: [],
    })

    renderWithClient(<ActressDetailPage />)

    await user.click(await screen.findByRole('button', { name: /爬取影片/ }))
    await user.click(screen.getByRole('button', { name: /开始爬取/ }))

    expect(createTaskUrlRun).toHaveBeenCalledWith('task-1', {
      url_ids: ['url-1'],
      crawl_mode: 'incremental',
    })
  })
})
