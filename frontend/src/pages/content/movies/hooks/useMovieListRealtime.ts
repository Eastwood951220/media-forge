import { useEffect } from 'react'
import type { MovieStorageUpdate } from './useMovieList'
import { subscribeRealtime } from '@/realtime/eventSourceClient'
import type { MovieScrapingUpdatedPayload, MovieStorageUpdatedPayload, RealtimeEvent } from '@/realtime/types'

// A bulk storage sync publishes one event per movie. Coalesce a burst into a
// single state update so a large sync does not re-render the table per movie.
const STORAGE_UPDATE_FLUSH_MS = 100

export function useMovieListRealtime(
  applyStorageUpdates: (updates: MovieStorageUpdate[]) => void,
  applyScrapingUpdates?: (updates: Array<{ movie_id: string; scraping_status: 'scraped' | 'not_scraped' | null; scraping_checked_at?: string | null }>) => void,
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

    const unsubscribeStorage = subscribeRealtime<MovieStorageUpdatedPayload>(
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

    const unsubscribeScraping = subscribeRealtime<MovieScrapingUpdatedPayload>(
      'movie.scraping.updated',
      (event: RealtimeEvent<MovieScrapingUpdatedPayload>) => {
        applyScrapingUpdates?.([event.payload])
      },
    )

    return () => {
      unsubscribeStorage()
      unsubscribeScraping()
      if (flushTimer !== undefined) {
        window.clearTimeout(flushTimer)
      }
    }
  }, [applyStorageUpdates, applyScrapingUpdates])
}
