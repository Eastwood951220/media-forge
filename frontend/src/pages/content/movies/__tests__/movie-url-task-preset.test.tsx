import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useMovieUrlTaskPreset } from '../hooks/useMovieUrlTaskPreset'

function setSearch(search: string) {
  window.history.replaceState({}, '', search)
}

describe('useMovieUrlTaskPreset', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setSearch('/content/movies')
  })

  it('applies the task preset once options are ready and clears the URL param', () => {
    setSearch('/content/movies?task_id=task-9')
    const patchForm = vi.fn()

    const { rerender } = renderHook(
      ({ enabled }) => useMovieUrlTaskPreset({ enabled, patchForm }),
      { initialProps: { enabled: false } },
    )

    // Not ready yet: the preset must not be consumed or applied.
    expect(patchForm).not.toHaveBeenCalled()
    expect(window.location.search).toBe('?task_id=task-9')

    rerender({ enabled: true })

    expect(patchForm).toHaveBeenCalledTimes(1)
    expect(patchForm).toHaveBeenCalledWith({ selectedTask: 'task-9' })
    expect(window.location.search).toBe('')
  })

  it('ignores URLs without a task preset', () => {
    const patchForm = vi.fn()

    const { rerender } = renderHook(
      ({ enabled }) => useMovieUrlTaskPreset({ enabled, patchForm }),
      { initialProps: { enabled: false } },
    )
    rerender({ enabled: true })

    expect(patchForm).not.toHaveBeenCalled()
  })

  it('applies the preset only once per page view', () => {
    setSearch('/content/movies?task_id=task-9')
    const patchForm = vi.fn()

    const { rerender } = renderHook(
      ({ enabled }) => useMovieUrlTaskPreset({ enabled, patchForm }),
      { initialProps: { enabled: true } },
    )
    rerender({ enabled: true })

    expect(patchForm).toHaveBeenCalledTimes(1)
    expect(patchForm).toHaveBeenCalledWith({ selectedTask: 'task-9' })
  })
})
