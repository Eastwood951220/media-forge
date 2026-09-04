import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from 'antd'
import { describe, expect, it, vi } from 'vitest'
import * as scheduleApi from '@/api/crawler/crawlerSchedule'
import ScheduleListPage from '../ScheduleListPage'

vi.mock('@/api/crawler/crawlTask', () => ({
  getTaskDict: vi.fn().mockResolvedValue([{ id: 'task-1', name: 'Task 1' }]),
}))

describe('ScheduleListPage', () => {
  it('triggers a schedule immediately', async () => {
    const user = userEvent.setup()
    vi.spyOn(scheduleApi, 'getCrawlerSchedules').mockResolvedValue({
      rows: [{
        id: 'schedule-1',
        name: 'Nightly',
        enabled: true,
        schedule_type: 'daily',
        time_of_day: '03:30',
        weekdays: [],
        auto_storage_enabled: false,
        storage_mode: 'single',
        selected_storage_location: null,
        task_count: 1,
        tasks: [],
        last_triggered_at: null,
        next_run_at: null,
        latest_run_status: null,
        created_at: '2026-09-04T00:00:00',
        updated_at: null,
      }],
      total: 1,
      page: 1,
      size: 20,
    })
    const trigger = vi.spyOn(scheduleApi, 'triggerCrawlerSchedule').mockResolvedValue({ schedule_run_id: 'run-1' })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <App>
          <ScheduleListPage />
        </App>
      </QueryClientProvider>,
    )

    await user.click(await screen.findByRole('button', { name: '立即执行' }))

    await waitFor(() => expect(trigger).toHaveBeenCalledWith('schedule-1'))
  })
})
