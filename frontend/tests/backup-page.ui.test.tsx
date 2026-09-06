import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from 'antd'
import { render, screen } from '@testing-library/react'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import type { PropsWithChildren } from 'react'

import BackupPage from '@/pages/backup/BackupPage'
import styles from '@/pages/backup/BackupPage.module.less'

const originalGetComputedStyle = window.getComputedStyle.bind(window)
beforeAll(() => {
  vi.stubGlobal('getComputedStyle', (elt: Element) => originalGetComputedStyle(elt))
})
afterAll(() => {
  vi.unstubAllGlobals()
})

vi.mock('@/api/backup', () => ({
  getBackupConfig: vi.fn().mockResolvedValue({
    enabled: false,
    backup_dir: '/tmp/backups',
    schedule_type: 'daily',
    time_of_day: '03:30',
    weekdays: [],
    groups: ['movies', 'tasks', 'config'],
    include_sensitive: false,
    retention_count: 10,
  }),
  listBackupFiles: vi.fn().mockResolvedValue([]),
  startBackupExport: vi.fn(),
  inspectBackupFile: vi.fn(),
  startBackupRestore: vi.fn(),
  restoreLocalBackup: vi.fn(),
  deleteBackupFile: vi.fn(),
  getBackupJob: vi.fn(),
  getBackupDownloadUrl: vi.fn((name: string) => `/api/backup/files/${name}/download`),
  updateBackupConfig: vi.fn(),
}))

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={client}>
      <App>{children}</App>
    </QueryClientProvider>
  )
}

describe('BackupPage', () => {
  it('renders manual restore and automatic backup areas', async () => {
    render(<BackupPage />, { wrapper })

    expect(await screen.findByText('手动备份')).toBeInTheDocument()
    expect(screen.getByText('恢复备份')).toBeInTheDocument()
    expect(screen.getByText('自动备份')).toBeInTheDocument()
    expect(screen.getAllByText('电影数据').length).toBeGreaterThan(0)
    expect(screen.getAllByText('任务与定时').length).toBeGreaterThan(0)
    expect(screen.getAllByText('配置').length).toBeGreaterThan(0)
  })

  it('uses a compact actions column and a wide file list panel', async () => {
    const { container } = render(<BackupPage />, { wrapper })

    expect(await screen.findByText('手动备份')).toBeInTheDocument()
    expect(container.querySelector(`.${styles.actionPanel}`)).toBeInTheDocument()
    expect(container.querySelector(`.${styles.contentPanel}`)).toBeInTheDocument()

    const filePanel = container.querySelector(`.${styles.filePanel}`)
    expect(filePanel).toBeInTheDocument()
    expect(filePanel).toHaveTextContent('近期备份文件')
    expect(filePanel?.querySelector('.ant-table')).toBeInTheDocument()
  })
})
