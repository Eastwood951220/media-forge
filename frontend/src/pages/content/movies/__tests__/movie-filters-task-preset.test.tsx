import { App } from 'antd'
import { renderHook, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useMovieFilters } from '../hooks/useMovieFilters'
import { getTaskDict } from '@/api/crawler/crawlTask'

vi.mock('@/api/movie', () => ({
  fetchFilters: vi.fn().mockResolvedValue([]),
}))

vi.mock('@/api/crawler/crawlTask', () => ({
  getTaskDict: vi.fn().mockResolvedValue([]),
}))

function wrapper({ children }: PropsWithChildren) {
  return <App>{children}</App>
}

function setSearch(search: string) {
  window.history.replaceState({}, '', search)
}

describe('useMovieFilters URL task preset seeding', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setSearch('/content/movies')
  })

  it('seeds the task filter from the URL task_id immediately on mount', async () => {
    setSearch('/content/movies?task_id=task-9')
    vi.mocked(getTaskDict).mockResolvedValue([{ id: 'task-9', name: '任务九' }] as never)

    const { result } = renderHook(() => useMovieFilters({ enabled: true, filterConfig: {} }), { wrapper })

    // Seeded synchronously on the first render — no dependency on async loads.
    expect(result.current.form.selectedTask).toBe('task-9')

    await waitFor(() => expect(result.current.optionsLoaded).toBe(true))
    expect(result.current.form.selectedTask).toBe('task-9')
  })

  it('leaves the task filter empty when the URL has no task_id', async () => {
    const { result } = renderHook(() => useMovieFilters({ enabled: true, filterConfig: {} }), { wrapper })

    expect(result.current.form.selectedTask).toBeUndefined()

    await waitFor(() => expect(result.current.optionsLoaded).toBe(true))
    expect(result.current.form.selectedTask).toBeUndefined()
  })
})
