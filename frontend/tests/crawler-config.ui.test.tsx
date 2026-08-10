import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ConfigPage from '../src/pages/crawler/config/ConfigPage'
import { fetchConfig, testCookiesConfig, updateConfig, fetchAgentStatus, rotateAgentToken } from '@/api/crawler/crawlerConfig'

vi.mock('@/api/crawler/crawlerConfig', () => ({
  fetchConfig: vi.fn(),
  updateConfig: vi.fn(),
  testCookiesConfig: vi.fn(),
  fetchAgentStatus: vi.fn(),
  rotateAgentToken: vi.fn(),
}))

function renderPage() {
  return render(
    <AntApp>
      <ConfigPage />
    </AntApp>,
  )
}

describe('ConfigPage Agent mode', () => {
  beforeEach(() => {
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
    vi.mocked(fetchAgentStatus).mockResolvedValue({
      status: 'offline',
      last_cookie_sync_at: null,
      last_seen_at: null,
    })
    vi.mocked(rotateAgentToken).mockResolvedValue({
      token: 'agt_test',
      status: { status: 'offline' },
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

  it('shows Chrome Agent card', async () => {
    renderPage()

    const chromeLabels = await screen.findAllByText('Chrome Agent')
    expect(chromeLabels.length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('offline')).toBeInTheDocument()
  })

  it('tests cookie from config page', async () => {
    renderPage()

    expect(await screen.findByText('爬取参数')).toBeInTheDocument()
    await userEvent.click(screen.getByText('测试 Cookie'))

    await waitFor(() => {
      expect(testCookiesConfig).toHaveBeenCalledWith()
    })
  })
})
