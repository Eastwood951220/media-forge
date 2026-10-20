import { App as AntApp } from 'antd'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScrapingConfigPage from '../ScrapingConfigPage'
import {
  getScrapingConfig,
  runScrapingScan,
  runScrapingStrm,
  updateScrapingConfig,
} from '@/api/scraping/scrapingConfig'

vi.mock('@/api/scraping/scrapingConfig', () => ({
  getScrapingConfig: vi.fn(),
  updateScrapingConfig: vi.fn(),
  runScrapingStrm: vi.fn(),
  runScrapingScan: vi.fn(),
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
    vi.mocked(runScrapingScan).mockResolvedValue({
      folders_scanned: 0,
      folders_with_strm: 0,
      scraped_folders: 0,
      not_scraped_folders: 0,
      matched_movies: 0,
      updated_movies: 0,
      unmatched_folders: [],
      duration_ms: 0,
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

  it('loads scraping directory fields', async () => {
    renderPage()
    expect(await screen.findByDisplayValue('/mnt/media')).toBeInTheDocument()
    expect(screen.getByDisplayValue('/media')).toBeInTheDocument()
  })

  it('saves reordered metadata sources', async () => {
    renderPage()
    await screen.findByDisplayValue('/mnt/media')
    fireEvent.click(screen.getByRole('button', { name: '下移 JavDB' }))
    fireEvent.click(screen.getByRole('button', { name: '保存配置' }))
    await waitFor(() => expect(updateScrapingConfig).toHaveBeenCalled())
    const payload = vi.mocked(updateScrapingConfig).mock.calls[0][0]
    expect(payload.metadata_sources).toEqual(['javbus', 'javdb'])
  })

  it('runs a scan and shows the summary', async () => {
    vi.mocked(runScrapingScan).mockResolvedValue({
      folders_scanned: 10,
      folders_with_strm: 4,
      scraped_folders: 3,
      not_scraped_folders: 1,
      matched_movies: 3,
      updated_movies: 3,
      unmatched_folders: [],
      duration_ms: 12,
    })
    renderPage()
    await screen.findByDisplayValue('/mnt/media')
    fireEvent.click(screen.getByRole('button', { name: '扫描目录' }))
    expect(await screen.findByText(/已刮削 3/)).toBeInTheDocument()
  })
})
