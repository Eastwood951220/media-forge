import { render, screen, waitFor } from '@testing-library/react'
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { PropsWithChildren } from 'react'
import RunDetailPage from '../RunDetailPage'

// jsdom does not implement getComputedStyle(elt, pseudoElt) which Ant Table's
// scrollbar measurement invokes. Patch it to ignore the pseudo-element arg.
const originalGetComputedStyle = window.getComputedStyle.bind(window)
beforeAll(() => {
  vi.stubGlobal('getComputedStyle', (elt: Element) => originalGetComputedStyle(elt))
})
afterAll(() => {
  vi.unstubAllGlobals()
})
import {
  getCrawlerRun,
  getCrawlerRunLogs,
  getCrawlerRunTasks,
  getCrawlerRunAgentWorkItems,
  getCrawlerRunAgentEvents,
} from '@/api/crawler/crawlerRun'
import type { CrawlRunDetailTask, CrawlRun } from '@/api/crawler/crawlerRun/types'
import type { AgentEvent } from '@/api/crawler/crawlerAgent/types'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'

vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: vi.fn((opts: { count: number }) => ({
    getVirtualItems: vi.fn(() =>
      Array.from({ length: opts.count }, (_, i) => ({
        key: i,
        index: i,
        start: i * 48,
        end: (i + 1) * 48,
        size: 48,
        lane: 0,
      })),
    ),
    getTotalSize: vi.fn(() => opts.count * 48),
    measureElement: vi.fn(),
  })),
}))

vi.mock('@tanstack/react-router', () => ({
  useParams: vi.fn().mockReturnValue({ id: 'run-1' }),
}))

const realtimeMock = vi.hoisted(() => ({
  handlers: {} as Record<string, (event: unknown) => void>,
  handlerList: {} as Record<string, ((event: unknown) => void)[]>,
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  subscribeRealtime: vi.fn((eventName: string, handler: (event: unknown) => void) => {
    realtimeMock.handlerList[eventName] = realtimeMock.handlerList[eventName] ?? []
    realtimeMock.handlerList[eventName].push(handler)
    realtimeMock.handlers[eventName] = handler
    return vi.fn()
  }),
}))

// Mock the API module — must be hoisted before the suite
vi.mock('@/api/crawler/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunLogs: vi.fn(),
  getCrawlerRunTasks: vi.fn(),
  restartCrawlerRun: vi.fn(),
  stopCrawlerRun: vi.fn(),
  retryCrawlerRunTasks: vi.fn(),
  getCrawlerRunAgentWorkItems: vi.fn(),
  getCrawlerRunAgentEvents: vi.fn(),
}))

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

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('RunDetail realtime event ownership', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    realtimeMock.handlers = {}
    useCrawlerRuntimeStore.getState().reset()

    vi.mocked(getCrawlerRun).mockResolvedValue(endedRun)
    vi.mocked(getCrawlerRunLogs).mockResolvedValue([])
    vi.mocked(getCrawlerRunTasks).mockResolvedValue({
      rows: [failedTask, savedTask],
      total: 2,
      summary: {
        total: 2,
        pending_crawl: 0,
        crawling: 0,
        saved: 1,
        skipped: 0,
        crawl_failed: 1,
        save_failed: 0,
        completed: 1,
        waiting: 0,
        failed: 1,
      },
    })
    vi.mocked(getCrawlerRunAgentWorkItems).mockResolvedValue({
      rows: [],
      summary: { pending: 0, active: 0, completed: 0, failed: 0, total: 0 },
    })
    vi.mocked(getCrawlerRunAgentEvents).mockResolvedValue({
      rows: [],
      next_cursor: null,
      has_more: false,
    })
  })

  it('applies detail event updates to rendered row status and summary', async () => {
    useCrawlerRuntimeStore.getState().setConnectionStatus('connected')

    render(<RunDetailPage />, { wrapper })

    // Wait for initial data to render
    expect(await screen.findByText('FAIL-001')).toBeInTheDocument()

    // Send a realtime detail patch — CrawlerRunDetailUpdatedPayload shape
    realtimeMock.handlers['crawler.run.detail.updated']({
      id: 'event-1',
      event: 'crawler.run.detail.updated',
      scope: 'crawler.run.detail',
      resource_id: 'run-1',
      owner_id: 'user-1',
      payload: {
        run_id: 'run-1',
        tasks: [{
          id: 'detail-1',
          status: 'crawling',
          error: null,
          code: null,
          source_name: null,
          source_url_name: null,
          task_url_type: null,
          display_code: null,
          display_source_name: null,
        }],
      },
      created_at: '2026-07-08T00:01:00Z',
    })

    // The row status should update
    await waitFor(() => {
      // The status tag should show "crawling" text
      expect(screen.getByText('crawling')).toBeInTheDocument()
    })
  })

  it('appends new log entries from realtime events', async () => {
    useCrawlerRuntimeStore.getState().setConnectionStatus('connected')

    render(<RunDetailPage />, { wrapper })

    // Wait for initial data to render
    expect(await screen.findByText('FAIL-001')).toBeInTheDocument()

    // Send a log appended event — CrawlerRunLogAppendedPayload shape
    realtimeMock.handlers['crawler.run.log.appended']({
      id: 'event-2',
      event: 'crawler.run.log.appended',
      scope: 'crawler.run.log',
      resource_id: 'run-1',
      owner_id: 'user-1',
      payload: {
        run_id: 'run-1',
        log: {
          id: 'log-1',
          run_id: 'run-1',
          timestamp: '2026-07-08T00:01:00Z',
          component: 'crawler',
          event: 'task_started',
          message: '开始爬取任务',
          level: 'INFO',
        },
      },
      created_at: '2026-07-08T00:01:00Z',
    })

    // The log entry should appear
    await waitFor(() => {
      expect(screen.getByText('开始爬取任务')).toBeInTheDocument()
    })
  })

  it('deduplicates duplicate log entries', async () => {
    useCrawlerRuntimeStore.getState().setConnectionStatus('connected')

    render(<RunDetailPage />, { wrapper })

    expect(await screen.findByText('FAIL-001')).toBeInTheDocument()

    const logPayload = {
      run_id: 'run-1',
      log: {
        id: 'log-1',
        run_id: 'run-1',
        timestamp: '2026-07-08T00:01:00Z',
        component: 'crawler',
        event: 'task_started',
        message: '开始爬取任务',
        level: 'INFO',
      },
    }

    // Send the same log event twice
    realtimeMock.handlers['crawler.run.log.appended']({
      id: 'event-2',
      event: 'crawler.run.log.appended',
      scope: 'crawler.run.log',
      resource_id: 'run-1',
      owner_id: 'user-1',
      payload: logPayload,
      created_at: '2026-07-08T00:01:00Z',
    })

    realtimeMock.handlers['crawler.run.log.appended']({
      id: 'event-3',
      event: 'crawler.run.log.appended',
      scope: 'crawler.run.log',
      resource_id: 'run-1',
      owner_id: 'user-1',
      payload: logPayload,
      created_at: '2026-07-08T00:01:01Z',
    })

    // Wait for the log to appear
    await screen.findByText('开始爬取任务')

    // There should be only one instance of the log message
    const logElements = screen.getAllByText('开始爬取任务')
    expect(logElements).toHaveLength(1)
  })

  it('does not refetch REST data for normal terminal status events', async () => {
    useCrawlerRuntimeStore.getState().setConnectionStatus('connected')

    render(<RunDetailPage />, { wrapper })

    expect(await screen.findByText('FAIL-001')).toBeInTheDocument()
    vi.mocked(getCrawlerRun).mockClear()
    vi.mocked(getCrawlerRunLogs).mockClear()
    vi.mocked(getCrawlerRunTasks).mockClear()

    realtimeMock.handlers['crawler.run.status.updated']({
      id: 'event-terminal',
      event: 'crawler.run.status.updated',
      scope: 'crawler.run',
      resource_id: 'run-1',
      owner_id: 'user-1',
      payload: {
        run_id: 'run-1',
        task_id: 'task-1',
        status: 'completed',
        crawl_mode: 'incremental',
        error: null,
        started_at: null,
        finished_at: '2026-07-08T00:03:00Z',
        state_updated_at: '2026-07-08T00:03:00Z',
      },
      created_at: '2026-07-08T00:03:00Z',
    })

    await waitFor(() => {
      expect(screen.getByText('已完成')).toBeInTheDocument()
    })
    expect(getCrawlerRun).not.toHaveBeenCalled()
    expect(getCrawlerRunLogs).not.toHaveBeenCalled()
    expect(getCrawlerRunTasks).not.toHaveBeenCalled()
  })

  it('detail/log/summary are not stored in the global store', async () => {
    useCrawlerRuntimeStore.getState().setConnectionStatus('connected')

    render(<RunDetailPage />, { wrapper })

    expect(await screen.findByText('FAIL-001')).toBeInTheDocument()

    const store = useCrawlerRuntimeStore.getState()

    // The store should not have summary/detail/log collections
    expect(store).not.toHaveProperty('taskSummary')
    expect(store).not.toHaveProperty('taskRows')
    expect(store).not.toHaveProperty('logs')
    // The store should have run runtime data
    expect(store).toHaveProperty('runRuntimeById')
    expect(store).toHaveProperty('connectionStatus')
  })

  it('disables stop/restart/retry when realtime is not connected', async () => {
    // connectionStatus is 'idle' by default after reset — not connected
    render(<RunDetailPage />, { wrapper })

    expect(await screen.findByText('FAIL-001')).toBeInTheDocument()

    // retry button should be disabled (aria-disabled)
    const retryButtons = screen.getAllByRole('button', { name: '重新爬取' })
    for (const btn of retryButtons) {
      expect(btn).toBeDisabled()
    }
  })

  it('static run details, subtasks, and logs remain readable when disconnected', async () => {
    render(<RunDetailPage />, { wrapper })

    // Even without connection, the static data should render
    expect(await screen.findByText('FAIL-001')).toBeInTheDocument()
    expect(screen.getByText('SAVED-001')).toBeInTheDocument()
    // Run status tag should render
    expect(screen.getByText('已完成')).toBeInTheDocument()
  })

  it('renders Chrome Agent failure reason from run logs', async () => {
    useCrawlerRuntimeStore.getState().setConnectionStatus('connected')
    vi.mocked(getCrawlerRun).mockResolvedValue({
      id: 'run-1',
      task_id: 'task-agent',
      task_name: 'Agent Task',
      status: 'failed',
      crawl_mode: 'incremental',
      queued_at: null,
      started_at: null,
      finished_at: null,
      result: null,
      error: 'Chrome Agent 未在线，无法执行 JavDB Agent 爬取',
      resumed_from: null,
      created_at: '2026-08-14T00:00:00Z',
      updated_at: null,
      logs: [],
    })
    vi.mocked(getCrawlerRunLogs).mockResolvedValue([
      {
        timestamp: '2026-08-14T00:00:01Z',
        level: 'ERROR',
        component: null,
        event: null,
        message: 'Chrome Agent 未在线，无法执行 JavDB Agent 爬取',
        context: {},
      },
    ])

    render(<RunDetailPage />, { wrapper })

    // The Agent failure reason is surfaced from run logs (and run error)
    expect((await screen.findAllByText('Chrome Agent 未在线，无法执行 JavDB Agent 爬取')).length).toBeGreaterThan(0)
  })

  it('appends only current-run agent events to the timeline', async () => {
    vi.mocked(getCrawlerRunAgentWorkItems).mockResolvedValue({
      rows: [],
      summary: { pending: 0, active: 0, completed: 0, failed: 0, total: 0 },
    })
    const runEvent: AgentEvent = {
      id: 'agent-event-1',
      agent_id: 'agent-1',
      run_id: 'run-1',
      work_item_id: 'item-1',
      attempt: 1,
      source: 'backend',
      event_type: 'work.assigned',
      phase: 'claim',
      level: 'info',
      message: 'Agent 已领取',
      details: null,
      retention_class: 'run_audit',
      created_at: '2026-07-08T00:01:00Z',
    }
    vi.mocked(getCrawlerRunAgentEvents).mockResolvedValue({
      rows: [runEvent],
      next_cursor: null,
      has_more: false,
    })
    render(<RunDetailPage />, { wrapper })

    // The current run's event appears in the execution card.
    expect(await screen.findByText('Agent 已领取')).toBeInTheDocument()

    // A realtime event for another run is ignored.
    realtimeMock.handlers['crawler.agent.event.created']({
      id: 'rt-other',
      event: 'crawler.agent.event.created',
      scope: 'crawler.agent',
      resource_id: 'event-other',
      owner_id: 'owner-1',
      payload: {
        ...runEvent,
        id: 'event-other',
        run_id: 'run-999',
        message: '其他运行事件',
      },
      created_at: '2026-07-08T00:02:00Z',
    })
    // A realtime event for the current run is appended.
    realtimeMock.handlers['crawler.agent.event.created']({
      id: 'rt-current',
      event: 'crawler.agent.event.created',
      scope: 'crawler.agent',
      resource_id: 'event-current',
      owner_id: 'owner-1',
      payload: {
        ...runEvent,
        id: 'event-current',
        event_type: 'page.loaded',
        phase: 'page.loaded',
        message: '页面加载完成',
        created_at: '2026-07-08T00:02:00Z',
      },
      created_at: '2026-07-08T00:02:00Z',
    })

    expect(await screen.findByText('页面加载完成')).toBeInTheDocument()
    expect(screen.queryByText('其他运行事件')).not.toBeInTheDocument()
  })

  it('refetches agent work and events on system resync', async () => {
    vi.mocked(getCrawlerRunAgentWorkItems).mockClear()
    vi.mocked(getCrawlerRunAgentEvents).mockClear()

    render(<RunDetailPage />, { wrapper })
    expect(await screen.findByText('FAIL-001')).toBeInTheDocument()
    expect(getCrawlerRunAgentWorkItems).toHaveBeenCalled()
    expect(getCrawlerRunAgentEvents).toHaveBeenCalled()

    vi.mocked(getCrawlerRunAgentWorkItems).mockClear()
    vi.mocked(getCrawlerRunAgentEvents).mockClear()

    realtimeMock.handlerList['system.resync_required']?.forEach((handler) => {
      handler({
        id: 'resync-1',
        event: 'system.resync_required',
        scope: 'system',
        resource_id: null,
        owner_id: 'owner-1',
        payload: { reason: 'test' },
        created_at: '2026-07-08T00:03:00Z',
      })
    })

    await waitFor(() => {
      expect(getCrawlerRunAgentWorkItems).toHaveBeenCalled()
      expect(getCrawlerRunAgentEvents).toHaveBeenCalled()
    })
  })
})
