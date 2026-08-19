import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PropsWithChildren } from 'react'
import ConfigPage from '../src/pages/crawler/config/ConfigPage'
import { fetchConfig, testCookiesConfig, updateConfig } from '@/api/crawler/crawlerConfig'
import {
  fetchAgentStatus,
  fetchAgentEvents,
  rotateAgentToken,
} from '@/api/crawler/crawlerAgent'
import type { AgentStatus } from '@/api/crawler/crawlerAgent/types'

const realtimeMock = vi.hoisted(() => ({
  handlers: {} as Record<string, (event: unknown) => void>,
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  subscribeRealtime: vi.fn((eventName: string, handler: (event: unknown) => void) => {
    realtimeMock.handlers[eventName] = handler
    return vi.fn()
  }),
}))

vi.mock('@/api/crawler/crawlerConfig', () => ({
  fetchConfig: vi.fn(),
  updateConfig: vi.fn(),
  testCookiesConfig: vi.fn(),
}))

vi.mock('@/api/crawler/crawlerAgent', () => ({
  fetchAgentStatus: vi.fn(),
  fetchAgentEvents: vi.fn(),
  clearOperationalAgentEvents: vi.fn(),
  rotateAgentToken: vi.fn(),
}))

const offlineStatus: AgentStatus = {
  status: 'offline',
  agent_id: null,
  name: null,
  protocol_version: null,
  connected_at: null,
  last_seen_at: null,
  last_cookie_sync_at: null,
  version: null,
  current_work_item: null,
  pending_count: 0,
  active_count: 0,
}

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <AntApp>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </AntApp>
  )
}

function renderPage() {
  return render(<ConfigPage />, { wrapper })
}

describe('ConfigPage Agent mode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    realtimeMock.handlers = {}
    vi.mocked(fetchConfig).mockResolvedValue({
      MAX_LIST_PAGES: 50,
      LIST_MAX_WORKERS: 2,
      DETAIL_MAX_WORKERS: 4,
      LIST_PAGE_DELAY_MIN: 1,
      LIST_PAGE_DELAY_MAX: 3,
      DETAIL_PAGE_DELAY_MIN: 2,
      DETAIL_PAGE_DELAY_MAX: 5,
      SECURITY_WAIT_SECONDS: 60,
      REQUEST_TIMEOUT: 30,
      INCREMENTAL_EXIST_THRESHOLD: 10,
      JAVDB_FETCH_MODE: 'static',
    })
    vi.mocked(updateConfig).mockResolvedValue({})
    vi.mocked(testCookiesConfig).mockResolvedValue({
      ok: true,
      status_code: 200,
      reason: 'ok',
      message: 'JavDB Cookie 测试通过',
      url: 'https://javdb.com',
      logged_in_detected: true,
      fetch_mode: 'static',
    })
    vi.mocked(fetchAgentStatus).mockResolvedValue(offlineStatus)
    vi.mocked(fetchAgentEvents).mockResolvedValue({
      rows: [],
      next_cursor: null,
      has_more: false,
    })
    vi.mocked(rotateAgentToken).mockResolvedValue({
      token: 'agt_test',
      status: offlineStatus,
    })
  })

  it('renders crawler config fields', async () => {
    renderPage()

    expect(await screen.findByText('爬取参数')).toBeInTheDocument()
    expect(screen.getByText('最大翻页数')).toBeInTheDocument()
    expect(screen.getByText('列表线程数')).toBeInTheDocument()
    expect(screen.getByText('JavDB 请求模式')).toBeInTheDocument()
    expect(screen.getByText('静态请求')).toBeInTheDocument()
    expect(screen.getAllByText('Chrome Agent').length).toBeGreaterThanOrEqual(2)
  })

  it('saves config with agent fetch mode', async () => {
    renderPage()

    expect(await screen.findByText('爬取参数')).toBeInTheDocument()
    const chromeLabels = screen.getAllByText('Chrome Agent')
    await userEvent.click(chromeLabels[0])
    await userEvent.click(screen.getByText('保存配置'))

    await waitFor(() => {
      expect(updateConfig).toHaveBeenCalledWith(expect.objectContaining({
        JAVDB_FETCH_MODE: 'agent',
      }))
    })
  })

  it('shows Chrome Agent card with offline status', async () => {
    renderPage()

    const chromeLabels = await screen.findAllByText('Chrome Agent')
    expect(chromeLabels.length).toBeGreaterThanOrEqual(2)
    expect(await screen.findByText('离线')).toBeInTheDocument()
  })

  it('tests cookie from config page', async () => {
    renderPage()

    expect(await screen.findByText('爬取参数')).toBeInTheDocument()
    await userEvent.click(screen.getByText('测试 Cookie'))

    await waitFor(() => {
      expect(testCookiesConfig).toHaveBeenCalledWith()
    })
  })

  it('generates and displays a one-time Chrome Agent token', async () => {
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('离线')
    await user.click(screen.getByRole('button', { name: '生成 Agent Token' }))
    expect(await screen.findByText('重新生成 Agent Token？')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /确\s*定/ }))

    await waitFor(() => {
      expect(rotateAgentToken).toHaveBeenCalledTimes(1)
    })
    expect(await screen.findByText('Agent Token 仅显示一次')).toBeInTheDocument()
    expect(screen.getByText('agt_test')).toBeInTheDocument()
  })
})
