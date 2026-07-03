import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StorageConfigPage from '../src/pages/storage/config/StorageConfigPage'
import {
  fetchStorageConfig,
  testStorageConnection,
  updateStorageConfig,
} from '@/api/storage/storageConfig'

vi.mock('@/api/storage/storageConfig', () => ({
  fetchStorageConfig: vi.fn(),
  updateStorageConfig: vi.fn(),
  testStorageConnection: vi.fn(),
}))

function renderPage() {
  return render(
    <AntApp>
      <StorageConfigPage />
    </AntApp>,
  )
}

describe('StorageConfigPage', () => {
  beforeEach(() => {
    vi.mocked(fetchStorageConfig).mockResolvedValue({
      enabled: true,
      grpc_host: 'localhost:9798',
      api_token: '************1234',
      api_token_configured: true,
      request_timeout_seconds: 60,
      connect_timeout_seconds: 10,
      download_root_folder: '/Downloads',
      target_folder: '/Movies',
      use_task_subfolder: true,
      auto_create_target_folder: true,
      single_filename_template: '{code}{ext}',
      multi_filename_template: '{code}{ext}',
      operation_delay_min: 0.5,
      operation_delay_max: 1.5,
      download_poll_interval_min: 5,
      download_poll_interval_max: 15,
      retry_delay_min: 10,
      retry_delay_max: 30,
      max_step_retries: 3,
      download_max_poll_count: 10,
      minimum_video_size_mb: 100,
      video_extensions: ['.mp4', '.mkv'],
      excluded_filename_keywords: [],
      keep_subtitles: true,
      keep_cover_images: true,
      delete_empty_folders: true,
    })
    vi.mocked(updateStorageConfig).mockResolvedValue({
      enabled: true,
      grpc_host: 'localhost:9798',
      api_token: '************9999',
      api_token_configured: true,
      request_timeout_seconds: 60,
      connect_timeout_seconds: 10,
      download_root_folder: '/Downloads',
      target_folder: '/Movies',
      use_task_subfolder: true,
      auto_create_target_folder: true,
      single_filename_template: '{code}{ext}',
      multi_filename_template: '{code}{ext}',
      operation_delay_min: 0.5,
      operation_delay_max: 1.5,
      download_poll_interval_min: 5,
      download_poll_interval_max: 15,
      retry_delay_min: 10,
      retry_delay_max: 30,
      max_step_retries: 3,
      download_max_poll_count: 10,
      minimum_video_size_mb: 100,
      video_extensions: ['.mp4', '.mkv'],
      excluded_filename_keywords: [],
      keep_subtitles: true,
      keep_cover_images: true,
      delete_empty_folders: true,
    })
    vi.mocked(testStorageConnection).mockResolvedValue({
      grpc_reachable: true,
      grpc_error: null,
      api_authorized: true,
      api_error: null,
      download_root_exists: true,
      download_root_error: null,
      target_folder_accessible: true,
      target_folder_error: null,
    })
  })

  it('renders storage config sections from the original project', async () => {
    renderPage()

    expect(await screen.findByText('服务配置')).toBeInTheDocument()
    expect(screen.getByText('目录配置')).toBeInTheDocument()
    expect(screen.getByText('文件命名')).toBeInTheDocument()
    expect(screen.getByText('任务执行')).toBeInTheDocument()
    expect(screen.getByText('文件筛选')).toBeInTheDocument()
    // API token field should be present
    expect(screen.getByPlaceholderText('输入新的 API Token（留空则不修改）')).toBeInTheDocument()
  })

  it('saves a new token without sending the masked token as the secret', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText('服务配置')).toBeInTheDocument()
    await user.type(screen.getByPlaceholderText('输入新的 API Token（留空则不修改）'), 'new-token-9999')
    await user.click(screen.getByText('保存配置'))

    await waitFor(() => {
      expect(updateStorageConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          api_token: 'new-token-9999',
          grpc_host: 'localhost:9798',
        }),
      )
    })
  })

  it('shows connection test result', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText('服务配置')).toBeInTheDocument()
    await user.click(screen.getByText('测试连接'))

    expect(await screen.findByText('测试结果')).toBeInTheDocument()
    expect(screen.getAllByText('通过')).toHaveLength(4)
  })
})

it('exports storage config route in the router tree', async () => {
  const { router } = await import('../src/routes')

  expect(router.routesByPath['/storage/config']).toBeDefined()
})
