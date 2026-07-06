import { useEffect } from 'react'

export function useMovieUrlDetail(showDetail: (movieId: string) => void) {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const movieId = params.get('id')
    if (!movieId) return
    showDetail(movieId)
    const url = new URL(window.location.href)
    url.searchParams.delete('id')
    window.history.replaceState({}, '', url.toString())
  }, [showDetail])
}
