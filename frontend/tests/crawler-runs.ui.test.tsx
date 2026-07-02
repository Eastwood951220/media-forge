import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RunListPage from '../src/pages/crawler/runs/RunListPage'
import { getCrawlerRuns, restartCrawlerRun } from '../src/api/crawlerRun'

vi.mock('../src/api/crawlerRun', () => ({
  getCrawlerRuns: vi.fn(),
  getCrawlerRun: vi.fn(),
  getCrawlerRunTasks: vi.fn(),
  stopCrawlerRun: vi.fn(),
  restartCrawlerRun: vi.fn(),
  getCrawlerQueueStatus: vi.fn(),
}))

describe('RunListPage', () => {
  beforeEach(() => {
    vi.mocked(getCrawlerRuns).mockResolvedValue({
      rows: [{
        id: 'run-1',
        task_id: 'task-1',
        task_name: '任务A',
        status: 'stopped',
        crawl_mode: 'incremental',
        queued_at: '2026-07-02T00:00:00',
        started_at: null,
        finished_at: null,
        result: null,
        error: null,
        resumed_from: null,
        created_at: '2026-07-02T00:00:00',
        updated_at: null,
        logs: [],
      }],
      total: 1,
    })
    vi.mocked(restartCrawlerRun).mockResolvedValue({ id: 'run-2' } as never)
  })

  it('renders runs and shows restart button for stopped runs', async () => {
    render(<RunListPage />)

    expect(await screen.findByText('任务A')).toBeInTheDocument()
    expect(screen.getByText('已停止')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重启' })).toBeInTheDocument()
  })

  it('restarts a stopped run', async () => {
    render(<RunListPage />)

    await userEvent.click(await screen.findByRole('button', { name: '重启' }))

    await waitFor(() => {
      expect(restartCrawlerRun).toHaveBeenCalledWith('run-1')
    })
  })
})
