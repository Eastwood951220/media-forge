import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ScheduleFormDrawer from '../components/ScheduleFormDrawer'

describe('ScheduleFormDrawer', () => {
  it('requires a weekday for weekly schedules', async () => {
    const user = userEvent.setup()
    render(
      <ScheduleFormDrawer
        open
        taskOptions={[{ id: 'task-1', name: 'Task 1' }]}
        submitting={false}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />,
    )

    await user.type(screen.getByLabelText('名称'), 'Nightly')
    await user.click(screen.getByText('每周'))
    await user.click(screen.getByRole('button', { name: '保存' }))

    expect(await screen.findByText('请选择至少一天')).toBeInTheDocument()
  })
})
