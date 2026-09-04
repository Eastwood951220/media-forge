import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ScheduleFormDrawer from '../components/ScheduleFormDrawer'

function renderDrawer() {
  return render(
    <ScheduleFormDrawer
      open
      taskOptions={[{ id: 'task-1', name: 'Task 1' }]}
      submitting={false}
      onCancel={vi.fn()}
      onSubmit={vi.fn()}
    />,
  )
}

describe('ScheduleFormDrawer', () => {
  it('requires a weekday for weekly schedules', async () => {
    const user = userEvent.setup()
    renderDrawer()

    await user.type(screen.getByLabelText('名称'), 'Nightly')
    await user.click(screen.getByText('每周'))
    await user.click(screen.getByRole('button', { name: '保存' }))

    expect(await screen.findByText('请选择至少一天')).toBeInTheDocument()
  })

  it('clears the weekday error when switching back to daily', async () => {
    const user = userEvent.setup()
    renderDrawer()

    await user.type(screen.getByLabelText('名称'), 'Nightly')
    await user.click(screen.getByText('每周'))
    await user.click(screen.getByRole('button', { name: '保存' }))
    expect(await screen.findByText('请选择至少一天')).toBeInTheDocument()

    await user.click(screen.getByText('每天'))

    await waitFor(() => {
      expect(screen.queryByText('请选择至少一天')).not.toBeInTheDocument()
    })
  })

  it('uses a segmented storage mode and only shows the location input for single mode', async () => {
    const user = userEvent.setup()
    renderDrawer()

    await user.click(screen.getByLabelText('执行后自动存储'))
    expect(await screen.findByText('存储方式')).toBeInTheDocument()

    // Default mode is "single" so the location input is visible.
    expect(await screen.findByLabelText('存储位置')).toBeInTheDocument()

    // Switching to "multiple" hides the location input.
    await user.click(screen.getByText('多盘'))
    await waitFor(() => {
      expect(screen.queryByLabelText('存储位置')).not.toBeInTheDocument()
    })

    // Switching back to "single" restores it.
    await user.click(screen.getByText('单盘'))
    expect(await screen.findByLabelText('存储位置')).toBeInTheDocument()
  })
})
