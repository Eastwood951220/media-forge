import { useEffect } from 'react'
import type { Movie } from '@/api/movie/types'
import { connectRealtime, subscribeRealtime } from '@/realtime/eventSourceClient'
import type { MovieStorageUpdatedPayload, RealtimeEvent } from '@/realtime/types'

export function useMovieListRealtime(
  updateMovie: (movieId: string, updater: (movie: Movie) => Movie) => void,
) {
  useEffect(() => {
    connectRealtime()
    const unsubscribe = subscribeRealtime<MovieStorageUpdatedPayload>(
      'movie.storage.updated',
      (event: RealtimeEvent<MovieStorageUpdatedPayload>) => {
        updateMovie(event.payload.movie_id, (movie) => ({
          ...movie,
          storage_status: String(event.payload.storage_summary.storage_status || 'not_stored') as Movie['storage_status'],
          storage_summary: {
            ...movie.storage_summary,
            ...event.payload.storage_summary,
          },
        }))
      },
    )
    return unsubscribe
  }, [updateMovie])
}
