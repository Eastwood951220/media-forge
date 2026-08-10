import { App as AntApp } from 'antd'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ConfigPage from '../src/pages/crawler/config/ConfigPage'
import {
  fetchConfig,
  fetchCookiesConfig,
  testCookiesConfig,
  updateConfig,
  updateCookiesConfig,
  fetchJavdbSessionStatus,
  openJavdbSession,
  closeJavdbSession,
  checkJavdbSession,
  exportJavdbSession,
  resetJavdbSession,
} from '@/api/crawler/crawlerConfig'

vi.mock('@monaco-editor/react', () => ({
  default: ({
    value,
    onChange,
  }: {
    value: string
    onChange: (value: string | undefined) => void
  }) => (
    <textarea
      aria-label="Cookie JSON"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}))

vi.mock('@/api/crawler/crawlerConfig', () => ({
  fetchConfig: vi.fn(),
  updateConfig: vi.fn(),
  fetchCookiesConfig: vi.fn(),
  updateCookiesConfig: vi.fn(),
  testCookiesConfig: vi.fn(),
  fetchJavdbSessionStatus: vi.fn(),
  openJavdbSession: vi.fn(),
  closeJavdbSession: vi.fn(),
  checkJavdbSession: vi.fn(),
  exportJavdbSession: vi.fn(),
  resetJavdbSession: vi.fn(),
}))

function renderPage() {
  return render(
    <AntApp>
      <ConfigPage />
    </AntApp>,
  )
}

describe('ConfigPage', () => {
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
    vi.mocked(fetchCookiesConfig).mockResolvedValue({
      cookies: [
        {
          domain: 'javdb.com',
          expirationDate: null,
          hostOnly: true,
          httpOnly: false,
          name: 'session',
          path: '/',
          sameSite: 'lax',
          secure: false,
          session: false,
          storeId: null,
          value: 'abc123',
        },
      ],
    })
    vi.mocked(updateConfig).mockResolvedValue({})
    vi.mocked(updateCookiesConfig).mockResolvedValue({ cookies: [] })
    vi.mocked(testCookiesConfig).mockResolvedValue({
      ok: true,
      status_code: 200,
      reason: 'ok',
      message: 'JavDB Cookie 测试通过',
      url: 'https://javdb.com',
      logged_in_detected: true,
      fetch_mode: 'static',
    })
    vi.mocked(fetchJavdbSessionStatus).mockResolvedValue({
      profile_exists: false,
      storage_state_exists: false,
      verification_browser_open: false,
      last_check_at: null,
      last_check_url: null,
      last_status_code: null,
      last_reason: 'not_checked',
      last_message: '尚未检测 JavDB 浏览器会话',
      logged_in_detected: false,
      runtime_environment: 'local_gui',
    })
    vi.mocked(openJavdbSession).mockResolvedValue({
      profile_exists: true,
      storage_state_exists: false,
      verification_browser_open: true,
      last_reason: 'not_checked',
      last_message: '尚未检测 JavDB 浏览器会话',
      logged_in_detected: false,
      runtime_environment: 'local_gui',
    })
    vi.mocked(closeJavdbSession).mockResolvedValue({
      profile_exists: true,
      storage_state_exists: false,
      verification_browser_open: false,
      last_reason: 'not_checked',
      last_message: '尚未检测 JavDB 浏览器会话',
      logged_in_detected: false,
      runtime_environment: 'local_gui',
    })
    vi.mocked(checkJavdbSession).mockResolvedValue({
      ok: true,
      status_code: 200,
      reason: 'ok',
      message: 'JavDB 浏览器会话检测通过',
      url: 'https://javdb.com',
      logged_in_detected: true,
      checked_at: '2026-08-10T00:00:00+00:00',
      runtime_environment: 'local_gui',
    })
    vi.mocked(exportJavdbSession).mockResolvedValue({
      path: '/app/data/cookies/javdb_storage_state.json',
    })
    vi.mocked(resetJavdbSession).mockResolvedValue({
      profile_exists: false,
      storage_state_exists: false,
      verification_browser_open: false,
      last_reason: 'not_checked',
      last_message: '尚未检测 JavDB 浏览器会话',
      logged_in_detected: false,
      runtime_environment: 'local_gui',
    })
  })

  it('renders original crawler config fields and cookie editor', async () => {
    renderPage()

    expect(await screen.findByText('爬取参数')).toBeInTheDocument()
    expect(screen.getByText('最大翻页数')).toBeInTheDocument()
    expect(screen.getByText('列表线程数')).toBeInTheDocument()
    expect(screen.getByText('详情线程数')).toBeInTheDocument()
    expect(screen.getByText('列表页最小延迟 (秒)')).toBeInTheDocument()
    expect(screen.getByText('列表页最大延迟 (秒)')).toBeInTheDocument()
    expect(screen.getByText('详情页最小延迟 (秒)')).toBeInTheDocument()
    expect(screen.getByText('详情页最大延迟 (秒)')).toBeInTheDocument()
    expect(screen.getByText('安全验证等待 (秒)')).toBeInTheDocument()
    expect(screen.getByText('请求超时 (秒)')).toBeInTheDocument()
    expect(screen.getByText('JavDB 请求模式')).toBeInTheDocument()
    expect(screen.getByText('增量爬取阈值')).toBeInTheDocument()
    expect(screen.getByText('Cookie 配置')).toBeInTheDocument()
  })

  it('saves cookies with original wrapper shape', async () => {
    renderPage()

    // Wait for component to load
    expect(await screen.findByText('爬取参数')).toBeInTheDocument()

    const editor = screen.getByLabelText('Cookie JSON')
    const jsonValue = '[{"domain":"javdb.com","name":"session","value":"next","path":"/"}]'
    fireEvent.change(editor, { target: { value: jsonValue } })
    await userEvent.click(screen.getByText('保存 Cookie'))

    await waitFor(() => {
      expect(updateCookiesConfig).toHaveBeenCalledWith({
        cookies: [
          {
            domain: 'javdb.com',
            name: 'session',
            value: 'next',
            path: '/',
          },
        ],
      })
    })
  })

  it('tests javdb cookies from config page', async () => {
    renderPage()

    expect(await screen.findByText('爬取参数')).toBeInTheDocument()
    await userEvent.click(screen.getByText('测试 Cookie'))

    await waitFor(() => {
      expect(testCookiesConfig).toHaveBeenCalledWith()
    })
  })

  it('shows blocked cookie test result', async () => {
    vi.mocked(testCookiesConfig).mockResolvedValue({
      ok: false,
      status_code: 403,
      reason: 'http_403',
      message: 'JavDB 返回 403，后端爬虫会话被拒绝，请在浏览器完成验证后重新导出 Cookie',
      url: 'https://javdb.com',
      logged_in_detected: false,
      fetch_mode: 'static',
    })

    renderPage()

    expect(await screen.findByText('爬取参数')).toBeInTheDocument()
    await userEvent.click(screen.getByText('测试 Cookie'))

    expect(await screen.findAllByText(/JavDB 返回 403/)).toHaveLength(2)
  })

  it('renders javdb fetch mode select', async () => {
    renderPage()

    expect(await screen.findByText('爬取参数')).toBeInTheDocument()
    expect(screen.getByText('JavDB 请求模式')).toBeInTheDocument()
    expect(screen.getByText('静态请求')).toBeInTheDocument()
  })

  it('saves browser fetch mode with crawler config', async () => {
    renderPage()

    expect(await screen.findByText('爬取参数')).toBeInTheDocument()
    await userEvent.click(screen.getByText('浏览器模式'))
    await userEvent.click(screen.getByText('保存配置'))

    await waitFor(() => {
      expect(updateConfig).toHaveBeenCalledWith(expect.objectContaining({
        JAVDB_FETCH_MODE: 'browser',
      }))
    })
  })

  it('shows fetch mode in cookie test result', async () => {
    vi.mocked(testCookiesConfig).mockResolvedValue({
      ok: false,
      status_code: 403,
      reason: 'http_403',
      message: 'JavDB static 模式返回 403，请切换浏览器模式后重试',
      url: 'https://javdb.com',
      logged_in_detected: false,
      fetch_mode: 'static',
    })

    renderPage()

    expect(await screen.findByText('爬取参数')).toBeInTheDocument()
    await userEvent.click(screen.getByText('测试 Cookie'))

    expect(await screen.findByText(/模式: static/)).toBeInTheDocument()
  })

  it('renders javdb session status panel', async () => {
    renderPage()

    expect(await screen.findByText('JavDB 访问状态')).toBeInTheDocument()
    expect(screen.getByText('Profile 未创建')).toBeInTheDocument()
    expect(screen.getByText('尚未检测 JavDB 浏览器会话')).toBeInTheDocument()
  })

  it('checks javdb browser session', async () => {
    renderPage()

    expect(await screen.findByText('JavDB 访问状态')).toBeInTheDocument()
    await userEvent.click(screen.getByText('检测会话'))

    await waitFor(() => {
      expect(checkJavdbSession).toHaveBeenCalledWith()
    })
    expect(await screen.findAllByText('JavDB 浏览器会话检测通过')).toHaveLength(3)
  })

  it('opens javdb verification browser', async () => {
    renderPage()

    expect(await screen.findByText('JavDB 访问状态')).toBeInTheDocument()
    await userEvent.click(screen.getByText('打开辅助验证浏览器'))

    await waitFor(() => {
      expect(openJavdbSession).toHaveBeenCalledWith()
    })
  })

  it('shows normal chrome as the primary javdb verification path', async () => {
    renderPage()

    expect(await screen.findByText('JavDB 访问状态')).toBeInTheDocument()
    expect(screen.getAllByText(/普通 Chrome/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Playwright 辅助浏览器/).length).toBeGreaterThan(0)
  })
})
