import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RunDetailPage from '../RunDetailPage'
import {
  getCrawlerRun,
  getCrawlerRunLogs,
  getCrawlerRunTaskSummary,
  getCrawlerRunTasks,
  retryCrawlerRunTasks,
} from '@/api/crawlerRun'

vi.mock('@tanstack/react-router', () => ({
  useParams: vi.fn().mockReturnValue({ id: 'run-1' }),
}))

vi.mock('@/api/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunLogs: vi.fn().mockResolvedValue([]),
  getCrawlerRunTaskSummary: vi.fn(),
  getCrawlerRunTasks: vi.fn(),
  restartCrawlerRun: vi.fn(),
  stopCrawlerRun: vi.fn(),
  retryCrawlerRunTasks: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  subscribeRealtime: vi.fn().mockReturnValue(() => {}),
}))

import type { CrawlRun, CrawlRunDetailTask } from '@/api/crawlerRun/types'

const endedRun: CrawlRun = {
  id: 'run-1',
  task_id: 'task-1',
  task_name: '任务',
  status: 'completed',
  crawl_mode: 'incremental',
  queued_at: null,
  started_at: null,
  finished_at: null,
  result: null,
  error: null,
  resumed_from: null,
  created_at: '2026-07-08T00:00:00Z',
  updated_at: null,
  logs: [],
}

const failedTask: CrawlRunDetailTask = {
  id: 'detail-1',
  run_id: 'run-1',
  task_name: '任务',
  code: 'FAIL-001',
  source_url: 'https://example.test/fail',
  source_name: 'FAIL 001',
  source_url_name: '演员A',
  task_url: 'https://javdb.com/actors/a',
  task_final_url: 'https://javdb.com/actors/a?page=1',
  task_url_type: 'actors',
  status: 'crawl_failed',
  error: 'timeout',
  item_data: null,
  created_at: '2026-07-08T00:00:00Z',
  crawled_at: null,
  saved_at: null,
}

const savedTask: CrawlRunDetailTask = {
  ...failedTask,
  id: 'detail-2',
  code: 'SAVED-001',
  source_name: 'SAVED 001',
  status: 'saved',
  error: null,
}

describe('RunDetail retry controls', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getCrawlerRun).mockResolvedValue(endedRun)
    vi.mocked(getCrawlerRunLogs).mockResolvedValue([])
    vi.mocked(getCrawlerRunTasks).mockResolvedValue({
      rows: [failedTask, savedTask],
      total: 2,
    })
    vi.mocked(getCrawlerRunTaskSummary).mockResolvedValue({ total: 2, pending_crawl: 0, crawling: 0, saved: 1, skipped: 0, crawl_failed: 1, save_failed: 0, completed: 1, waiting: 0, failed: 1 })
    vi.mocked(retryCrawlerRunTasks).mockResolvedValue({ ...endedRun, status: 'queued' })
  })

  it('retries one failed row with one detail id', async () => {
    render(<RunDetailPage />)

    expect(await screen.findByText('FAIL-001')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重新爬取' }))
    const okButton = await screen.findByRole('button', { name: '确 定' })
    fireEvent.click(okButton)

    await waitFor(() => {
      expect(retryCrawlerRunTasks).toHaveBeenCalledWith('run-1', {
        detail_ids: ['detail-1'],
        retry_all: false,
      })
    })
  })

  it('retries all failed rows with retry_all payload', async () => {
    render(<RunDetailPage />)

    expect(await screen.findByText('FAIL-001')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重新爬取全部失败 (1)' }))
    const okButton = await screen.findByRole('button', { name: '确 定' })
    fireEvent.click(okButton)

    await waitFor(() => {
      expect(retryCrawlerRunTasks).toHaveBeenCalledWith('run-1', {
        retry_all: true,
      })
    })
  })

  it('hides retry controls while run is running', async () => {
    vi.mocked(getCrawlerRun).mockResolvedValueOnce({ ...endedRun, status: 'running' })

    render(<RunDetailPage />)

    expect(await screen.findByText('FAIL-001')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重新爬取' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重新爬取全部失败' })).not.toBeInTheDocument()
  })

  it('fetches first task page with page and size', async () => {
    render(<RunDetailPage />)

    await screen.findByText('FAIL-001')

    expect(getCrawlerRunTasks).toHaveBeenCalledWith('run-1', {
      page: 1,
      size: 50,
      status: undefined,
      keyword: undefined,
    })
  })

  it('fetches tasks with server-side pagination params', async () => {
    render(<RunDetailPage />)

    await screen.findByText('FAIL-001')

    expect(getCrawlerRunTasks).toHaveBeenCalledWith('run-1', {
      page: 1,
      size: 50,
      status: undefined,
      keyword: undefined,
    })
  })

  it('renders temporary task display code and source name fallbacks', async () => {
    vi.mocked(getCrawlerRunTasks).mockResolvedValueOnce({
      rows: [{
        ...savedTask,
        id: 'detail-temp',
        code: null,
        source_name: '临时详情页',
        display_code: 'AVSA-257',
        display_source_name: '真实电影名',
        item_data: { code: 'AVSA-257', source_name: '真实电影名' },
      } as any],
      total: 1,
    })

    render(<RunDetailPage />)

    expect(await screen.findByText('AVSA-257')).toBeInTheDocument()
    expect(screen.getByText('真实电影名')).toBeInTheDocument()
  })
})
