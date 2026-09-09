import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from 'antd'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ActressListPage from '../ActressListPage'
import ActressDetailPage from '../ActressDetailPage'
import { fetchActress, fetchActresses } from '@/api/content/actresses'

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({ id: 'actress-1' }),
}))

vi.mock('@/api/content/actresses', () => ({
  fetchActress: vi.fn(),
  fetchActresses: vi.fn(),
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
  })

  it('renders actress cards and requests the default 24 item page size', async () => {
    vi.mocked(fetchActresses).mockResolvedValue({ items: [profile], total: 1, page: 1, limit: 24, total_pages: 1 })

    renderWithClient(<ActressListPage />)

    await waitFor(() => {
      expect(fetchActresses).toHaveBeenCalledWith(expect.objectContaining({ page: 1, limit: 24 }))
    })
    expect(await screen.findByText('宮上唯依花')).toBeInTheDocument()
    expect(screen.getByText('みやうえゆいか')).toBeInTheDocument()
  })

  it('renders standalone detail with recent movies sorted by backend response', async () => {
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
  })
})
