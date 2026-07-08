import { App as AntApp } from 'antd'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ConfigPage from '../src/pages/crawler/config/ConfigPage'
import {
  fetchConfig,
  fetchCookiesConfig,
  updateConfig,
  updateCookiesConfig,
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
})
