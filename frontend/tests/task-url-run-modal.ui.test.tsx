import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CrawlTask } from '../src/api/crawlTask/types'
import TaskUrlRunModal from '../src/pages/crawler/tasks/components/TaskUrlRunModal'

const task: CrawlTask = {
  id: 'task-1',
  _id: 'task-1',
  name: '任务A',
  storage_location: 'JP',
  urls: [
    {
      id: 'url-1',
      position: 0,
      url: 'https://javdb.com/actors/a',
      url_type: 'actors',
      has_magnet: true,
      has_chinese_sub: false,
      sort_type: 0,
      source: 'javdb',
      final_url: 'https://javdb.com/actors/a',
      url_name: '演员A',
    },
    {
      id: 'url-2',
      position: 1,
      url: 'https://javdb.com/tags/b',
      url_type: 'tags',
      has_magnet: false,
      has_chinese_sub: true,
      sort_type: 0,
      source: 'javdb',
      final_url: 'https://javdb.com/tags/b',
      url_name: null,
    },
  ],
  is_skip: false,
  status: 'pending',
  task_id: null,
  error_message: null,
  total_found: 0,
  total_qualified: 0,
  owner_id: 'owner-1',
  created_at: '2026-07-15T00:00:00Z',
  updated_at: null,
  last_run_at: null,
  last_run_status: null,
}

function renderModal(props?: Partial<React.ComponentProps<typeof TaskUrlRunModal>>) {
  const onSubmit = vi.fn().mockResolvedValue(undefined)
  const onCancel = vi.fn()
  render(
    <AntApp>
      <TaskUrlRunModal
        open
        task={task}
        submitting={false}
        onCancel={onCancel}
        onSubmit={onSubmit}
        {...props}
      />
    </AntApp>,
  )
  return { onSubmit, onCancel }
}

describe('TaskUrlRunModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('submits selected url ids with default incremental mode', async () => {
    const { onSubmit } = renderModal()

    await userEvent.click(screen.getByLabelText('选择 URL'))
    await userEvent.click(await screen.findByText('演员A'))
    await userEvent.click(screen.getByRole('button', { name: '开始爬取' }))

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        url_ids: ['url-1'],
        crawl_mode: 'incremental',
      })
    })
  })

  it('submits full mode when selected', async () => {
    const { onSubmit } = renderModal()

    await userEvent.click(screen.getByLabelText('选择 URL'))
    await userEvent.click(await screen.findByText('演员A'))
    await userEvent.click(screen.getByLabelText('爬取模式'))
    await userEvent.click(await screen.findByText('全量爬取'))
    await userEvent.click(screen.getByRole('button', { name: '开始爬取' }))

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        url_ids: ['url-1'],
        crawl_mode: 'full',
      })
    })
  })

  it('blocks empty url selection', async () => {
    const { onSubmit } = renderModal()

    await userEvent.click(screen.getByRole('button', { name: '开始爬取' }))

    await waitFor(() => {
      expect(onSubmit).not.toHaveBeenCalled()
    })
    expect(await screen.findByText('请选择至少 1 条任务 URL')).toBeInTheDocument()
  })
})
