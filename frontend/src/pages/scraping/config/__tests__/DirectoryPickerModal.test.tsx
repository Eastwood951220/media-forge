import { App as AntApp } from 'antd'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DirectoryPickerModal from '../components/DirectoryPickerModal'
import { listScrapingDirectories } from '@/api/scraping/scrapingConfig'

vi.mock('@/api/scraping/scrapingConfig', () => ({
  listScrapingDirectories: vi.fn(),
}))

function renderModal(initialPath: string) {
  return render(
    <AntApp>
      <DirectoryPickerModal
        open
        initialPath={initialPath}
        onCancel={() => undefined}
        onSelect={() => undefined}
      />
    </AntApp>,
  )
}

describe('DirectoryPickerModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(listScrapingDirectories).mockResolvedValue({
      path: '/mnt/media',
      parent: '/mnt',
      entries: [{ name: 'Movies', path: '/mnt/media/Movies' }],
      roots: [{ name: '/mnt', path: '/mnt' }],
      truncated: false,
    })
  })

  it('falls back to the default directory when the configured path is invalid', async () => {
    vi.mocked(listScrapingDirectories)
      .mockRejectedValueOnce(new Error('目录不存在'))
      .mockResolvedValueOnce({
        path: '/',
        parent: null,
        entries: [{ name: 'mnt', path: '/mnt' }],
        roots: [{ name: '/', path: '/' }],
        truncated: false,
      })

    renderModal('/gone')

    expect(await screen.findByText('目录不存在，已打开默认目录')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'mnt' })).toBeInTheDocument()
    expect(listScrapingDirectories).toHaveBeenNthCalledWith(1, '/gone', false)
    expect(listScrapingDirectories).toHaveBeenNthCalledWith(2, undefined, false)
  })

  it('reloads the current folder when hidden folders are shown', async () => {
    renderModal('/mnt/media')
    const toggle = await screen.findByRole('switch', { name: '显示隐藏文件夹' })
    fireEvent.click(toggle)

    await waitFor(() =>
      expect(listScrapingDirectories).toHaveBeenLastCalledWith('/mnt/media', true),
    )
  })

  it('navigates to the parent folder', async () => {
    renderModal('/mnt/media')
    await screen.findByRole('button', { name: 'Movies' })
    fireEvent.click(screen.getByRole('button', { name: '上级目录' }))

    await waitFor(() =>
      expect(listScrapingDirectories).toHaveBeenLastCalledWith('/mnt', false),
    )
  })
})
