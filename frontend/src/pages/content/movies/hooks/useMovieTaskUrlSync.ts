import { useEffect, useRef } from 'react'

type UseMovieTaskUrlSyncOptions = {
  selectedTask: string | undefined
}

/**
 * Keeps the ?task_id URL parameter in sync with the movie list task filter.
 *
 * Unlike a one-shot "consume the parameter" preset, the parameter stays in the
 * URL while the task filter is active so that keep-alive remounts (and page
 * refreshes) re-seed the filter instead of silently losing it. The parameter is
 * removed only when the user clears or changes the task filter.
 */
export function useMovieTaskUrlSync({ selectedTask }: UseMovieTaskUrlSyncOptions) {
  const mountedRef = useRef(false)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const currentTaskId = params.get('task_id') ?? undefined

    if (!mountedRef.current) {
      // Initial mount: the URL already matches the seeded filter state, so
      // only write the URL when the filter subsequently diverges from it.
      mountedRef.current = true
      if (selectedTask === currentTaskId) return
    }

    const url = new URL(window.location.href)
    if (selectedTask) {
      url.searchParams.set('task_id', selectedTask)
    } else {
      url.searchParams.delete('task_id')
    }
    window.history.replaceState({}, '', url.toString())
  }, [selectedTask])
}
