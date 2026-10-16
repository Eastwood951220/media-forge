import { useEffect } from 'react'
import type { MovieStorageUpdate } from './useMovieList'
import { subscribeRealtime } from '@/realtime/eventSourceClient'
import type { MovieStorageUpdatedPayload, RealtimeEvent } from '@/realtime/types'

// A bulk storage sync publishes one event per movie. Coalesce a burst into a
// single state update so a large sync does not re-render the table per movie.
const STORAGE_UPDATE_FLUSH_MS = 100

export function useMovieListRealtime(
  applyStorageUpdates: (updates: MovieStorageUpdate[]) => void,
) {
  useEffect(() => {
    let pending: MovieStorageUpdate[] = []
    let flushTimer: number | undefined

    const flush = () => {
      flushTimer = undefined
      const batch = pending
      pending = []
      if (batch.length > 0) applyStorageUpdates(batch)
    }

    const unsubscribe = subscribeRealtime<MovieStorageUpdatedPayload>(
      'movie.storage.updated',
      (event: RealtimeEvent<MovieStorageUpdatedPayload>) => {
        pending.push({
          movie_id: event.payload.movie_id,
          storage_summary: event.payload.storage_summary,
        })
        if (flushTimer === undefined) {
          flushTimer = window.setTimeout(flush, STORAGE_UPDATE_FLUSH_MS)
        }
      },
    )

    return () => {
      unsubscribe()
      if (flushTimer !== undefined) {
        window.clearTimeout(flushTimer)
      }
    }
  }, [applyStorageUpdates])
}
