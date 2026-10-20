import { useCallback } from 'react'
import { App } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import { createScrapingTask } from '@/api/scraping/scrapingTasks'
import { queryKeys } from '@/api/queryKeys'
import type { Movie } from '@/api/movie/types'

export function useMovieScraping() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()

  const scrapeMovies = useCallback(async (movies: Movie[]) => {
    const movieIds = [...new Set(movies.map((movie) => movie._id))]
    if (movieIds.length === 0) return
    try {
      const task = await createScrapingTask(movieIds)
      void queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.all() })
      message.success(`已创建刮削任务，共 ${task.total_count} 部`)
    } catch {
      // error handled by request interceptor
    }
  }, [message, queryClient])

  return { scrapeMovies }
}
