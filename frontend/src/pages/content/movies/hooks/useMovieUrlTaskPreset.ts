import { useEffect, useRef } from 'react'
import type { MovieFilterState } from '../utils/movieFilter'

type UseMovieUrlTaskPresetOptions = {
  /** Whether task options have finished loading (filter bar is ready). */
  enabled: boolean
  patchForm: (payload: Partial<MovieFilterState>) => void
}

/**
 * Applies a one-shot "preset" from the URL (?task_id=<id>) onto the task
 * filter. Mirrors useMovieUrlDetail: the parameter is consumed once and
 * removed from the URL so a refresh or later filter edits do not silently
 * re-apply the preset.
 */
export function useMovieUrlTaskPreset({ enabled, patchForm }: UseMovieUrlTaskPresetOptions) {
  const consumedRef = useRef(false)

  useEffect(() => {
    if (!enabled || consumedRef.current) return
    const params = new URLSearchParams(window.location.search)
    const taskId = params.get('task_id')
    if (!taskId) return
    consumedRef.current = true
    patchForm({ selectedTask: taskId })
    const url = new URL(window.location.href)
    url.searchParams.delete('task_id')
    window.history.replaceState({}, '', url.toString())
  }, [enabled, patchForm])
}
