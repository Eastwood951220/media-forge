import { useEffect, useRef } from 'react'
import type { MovieFilterConfig } from '@/api/movie/types'
import { parseSortDefault } from '../utils/sort'

interface UseMoviePageSortDefaultArgs {
  loaded: boolean
  config: MovieFilterConfig | undefined
  resetSort: (sort: { sortBy: string; sortOrder: number }) => void
}

export function useMoviePageSortDefault({ loaded, config, resetSort }: UseMoviePageSortDefaultArgs) {
  const configSortParsed = useRef(false)

  useEffect(() => {
    if (!loaded || configSortParsed.current) return
    const sortDefault = parseSortDefault(config)
    if (sortDefault) {
      resetSort(sortDefault)
      configSortParsed.current = true
    }
  }, [loaded, config, resetSort])
}
