import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useMovieTaskUrlSync } from '../hooks/useMovieTaskUrlSync'

function setSearch(search: string) {
  window.history.replaceState({}, '', search)
}

function resetSearch(search: string) {
  setSearch(search)
  // setSearch itself goes through the spied replaceState; drop that recording.
  vi.mocked(window.history.replaceState).mockClear()
}

describe('useMovieTaskUrlSync', () => {
  let replaceSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    setSearch('/content/movies')
    replaceSpy = vi.spyOn(window.history, 'replaceState')
  })

  afterEach(() => {
    replaceSpy.mockRestore()
  })

  it('keeps a matching URL preset untouched on mount', () => {
    resetSearch('/content/movies?task_id=task-1')

    renderHook(() => useMovieTaskUrlSync({ selectedTask: 'task-1' }))

    expect(replaceSpy).not.toHaveBeenCalled()
    expect(window.location.search).toBe('?task_id=task-1')
  })

  it('writes the task parameter when the filter diverges from the URL', () => {
    const { rerender } = renderHook(
      ({ selectedTask }) => useMovieTaskUrlSync({ selectedTask }),
      { initialProps: { selectedTask: 'task-1' as string | undefined } },
    )

    // No URL preset on mount: seeding the filter writes the parameter.
    expect(replaceSpy).toHaveBeenCalledWith({}, '', 'http://localhost:3000/content/movies?task_id=task-1')
    expect(window.location.search).toBe('?task_id=task-1')

    rerender({ selectedTask: 'task-2' })
    expect(window.location.search).toBe('?task_id=task-2')
  })

  it('removes the task parameter when the filter is cleared', () => {
    resetSearch('/content/movies?task_id=task-1')

    const { rerender } = renderHook(
      ({ selectedTask }) => useMovieTaskUrlSync({ selectedTask }),
      { initialProps: { selectedTask: 'task-1' as string | undefined } },
    )
    expect(replaceSpy).not.toHaveBeenCalled()

    rerender({ selectedTask: undefined })
    expect(replaceSpy).toHaveBeenCalledWith({}, '', 'http://localhost:3000/content/movies')
    expect(window.location.search).toBe('')
  })

  it('preserves unrelated URL parameters', () => {
    resetSearch('/content/movies?foo=bar&task_id=task-1')

    const { rerender } = renderHook(
      ({ selectedTask }) => useMovieTaskUrlSync({ selectedTask }),
      { initialProps: { selectedTask: 'task-1' as string | undefined } },
    )
    expect(replaceSpy).not.toHaveBeenCalled()

    rerender({ selectedTask: undefined })
    expect(window.location.search).toBe('?foo=bar')
  })
})
