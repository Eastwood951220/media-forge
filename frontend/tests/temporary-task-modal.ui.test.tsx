import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TemporaryTaskModal from '../src/pages/crawler/tasks/components/TemporaryTaskModal'

function renderModal(props?: Partial<React.ComponentProps<typeof TemporaryTaskModal>>) {
  const onSubmit = vi.fn().mockResolvedValue(undefined)
  const onCancel = vi.fn()
  const onReloadTasks = vi.fn()
  render(
    <AntApp>
      <TemporaryTaskModal
        open
        tasks={[{ id: 'task-1', name: '任务A' }]}
        tasksLoading={false}
        tasksError={null}
        submitting={false}
        onCancel={onCancel}
        onReloadTasks={onReloadTasks}
        onSubmit={onSubmit}
        {...props}
      />
    </AntApp>,
  )
  return { onSubmit, onCancel, onReloadTasks }
}

describe('TemporaryTaskModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('submits selected task and normalized detail urls', async () => {
    const { onSubmit } = renderModal()

    await userEvent.click(screen.getByLabelText('归属任务'))
    await userEvent.click(await screen.findByText('任务A'))
    await userEvent.type(screen.getByPlaceholderText(/请输入 JavDB 详情页 URL/), ' https://javdb.com/v/abc123 ')
    await userEvent.click(screen.getByRole('button', { name: '创建临时任务' }))

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        task_id: 'task-1',
        detail_urls: ['https://javdb.com/v/abc123'],
      })
    })
  })

  it('supports adding and removing url rows while keeping one row', async () => {
    renderModal()

    const urlInputs = screen.getAllByPlaceholderText(/请输入 JavDB 详情页 URL/)
    expect(urlInputs).toHaveLength(1)

    const addButton = screen.getByRole('button', { name: /新增详情页/ })
    await userEvent.click(addButton)
    expect(screen.getAllByPlaceholderText(/请输入 JavDB 详情页 URL/)).toHaveLength(2)

    const deleteButtons = screen.getAllByRole('button', { name: /删除详情页/ })
    await userEvent.click(deleteButtons[0])
    expect(screen.getAllByPlaceholderText(/请输入 JavDB 详情页 URL/)).toHaveLength(1)
  })

  it('blocks invalid urls before submit', async () => {
    const { onSubmit } = renderModal()

    await userEvent.click(screen.getByLabelText('归属任务'))
    await userEvent.click(await screen.findByText('任务A'))

    const urlInput = screen.getByPlaceholderText(/请输入 JavDB 详情页 URL/)
    await userEvent.type(urlInput, 'https://javdb.com/actors/abc')

    const submitButton = screen.getByRole('button', { name: '创建临时任务' })
    await userEvent.click(submitButton)

    await waitFor(() => {
      expect(onSubmit).not.toHaveBeenCalled()
    })
  })

  it('keeps modal open and disables submit when task dictionary loading failed', async () => {
    const { onReloadTasks } = renderModal({
      tasks: [],
      tasksError: '任务列表加载失败',
    })

    expect(screen.getByText('任务列表加载失败')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '创建临时任务' })).toBeDisabled()

    const reloadButton = screen.getByRole('button', { name: /重新加载/ })
    await userEvent.click(reloadButton)
    expect(onReloadTasks).toHaveBeenCalled()
  })
})
