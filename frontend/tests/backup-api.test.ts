import { describe, expect, it, vi, beforeEach } from 'vitest'
import { request } from '@/request'
import {
  getBackupConfig,
  getBackupDownloadUrl,
  startBackupExport,
  updateBackupConfig,
} from '@/api/backup'

vi.mock('@/request', () => ({
  request: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}))

describe('backup api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('reads and updates backup config', async () => {
    vi.mocked(request.get).mockResolvedValueOnce({ enabled: false, groups: ['movies'] })
    vi.mocked(request.put).mockResolvedValueOnce({ enabled: true, groups: ['movies'] })

    await expect(getBackupConfig()).resolves.toEqual({ enabled: false, groups: ['movies'] })
    await expect(updateBackupConfig({ enabled: true, groups: ['movies'] })).resolves.toEqual({ enabled: true, groups: ['movies'] })

    expect(request.get).toHaveBeenCalledWith('/api/backup/config')
    expect(request.put).toHaveBeenCalledWith('/api/backup/config', { enabled: true, groups: ['movies'] })
  })

  it('starts export and builds encoded download urls', async () => {
    vi.mocked(request.post).mockResolvedValueOnce({ job_id: 'job-1' })

    await expect(startBackupExport({ groups: ['movies'], include_sensitive: false })).resolves.toEqual({ job_id: 'job-1' })

    expect(request.post).toHaveBeenCalledWith('/api/backup/export', { groups: ['movies'], include_sensitive: false })
    expect(getBackupDownloadUrl('a b.mfbackup')).toBe('/api/backup/files/a%20b.mfbackup/download')
  })
})
