import { App as AntApp } from 'antd'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScrapingConfigPage from '../ScrapingConfigPage'
import {
  getScrapingConfig,
  runScrapingStrm,
  updateScrapingConfig,
} from '@/api/scraping/scrapingConfig'

vi.mock('@/api/scraping/scrapingConfig', () => ({
  getScrapingConfig: vi.fn(),
  updateScrapingConfig: vi.fn(),
  runScrapingStrm: vi.fn(),
}))

const savedConfig = {
  base_url: 'https://example.com',
  api_key: '************1234',
  api_key_configured: true,
  directory_id: 4,
  trigger_delay_seconds: 30,
  scrape_root: '/mnt/media',
  media_root: '/media',
  metadata_sources: ['javdb', 'javbus'],
}

function renderPage() {
  return render(
    <AntApp>
      <ScrapingConfigPage />
    </AntApp>,
  )
}

describe('ScrapingConfigPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getScrapingConfig).mockResolvedValue(savedConfig)
    vi.mocked(updateScrapingConfig).mockResolvedValue(savedConfig)
    vi.mocked(runScrapingStrm).mockResolvedValue({
      success: true,
      status_code: 200,
      message: 'HTTP 200',
    })
  })

  it('loads the saved config', async () => {
    renderPage()

    expect(await screen.findByDisplayValue('https://example.com')).toBeInTheDocument()
    expect(screen.getByText('已配置: ************1234')).toBeInTheDocument()
  })

  it('does not send an untouched api key when saving', async () => {
    renderPage()
    const baseUrl = await screen.findByLabelText('服务地址')
    fireEvent.change(baseUrl, { target: { value: 'https://new.example.com' } })

    fireEvent.click(screen.getByRole('button', { name: '保存配置' }))

    await waitFor(() => expect(updateScrapingConfig).toHaveBeenCalled())
    const payload = vi.mocked(updateScrapingConfig).mock.calls[0][0]
    expect(payload.base_url).toBe('https://new.example.com')
    expect(payload).not.toHaveProperty('api_key')
  })

  it('saves before running the manual trigger', async () => {
    renderPage()
    await screen.findByDisplayValue('https://example.com')

    fireEvent.click(screen.getByRole('button', { name: '立即生成' }))

    await waitFor(() => expect(runScrapingStrm).toHaveBeenCalled())
    expect(vi.mocked(updateScrapingConfig).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(runScrapingStrm).mock.invocationCallOrder[0],
    )
  })
})
