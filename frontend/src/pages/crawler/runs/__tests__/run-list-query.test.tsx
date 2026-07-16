import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { getCrawlerRunCount, getCrawlerRuns } from '@/api/crawlerRun'
import RunListPage from '../RunListPage'

vi.mock('@/api/crawlerRun', () => ({
  deleteCrawlerRun: vi.fn(),
  getCrawlerRunCount: vi.fn(),
  getCrawlerRuns: vi.fn(),
  restartCrawlerRun: vi.fn(),
  stopCrawlerRun: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  subscribeRealtime: vi.fn().mockReturnValue(() => {}),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: vi.fn().mockReturnValue(vi.fn()),
}))

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('RunListPage', () => {
  it('loads runs with page and size before count is required', async () => {
    vi.mocked(getCrawlerRuns).mockResolvedValue({ rows: [], page: 1, size: 20, has_more: false })
    vi.mocked(getCrawlerRunCount).mockResolvedValue({ total: 0 })

    render(<RunListPage />, { wrapper })

    await waitFor(() => expect(getCrawlerRuns).toHaveBeenCalledWith({ page: 1, size: 20 }))
    expect(getCrawlerRunCount).toHaveBeenCalledWith({})
  })
})
