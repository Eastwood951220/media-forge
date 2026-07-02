import { request } from '@/request'
import type { Movie } from './types'
import type { PaginatedResponse } from '../crawlTask/types'

const BASE_URL = '/api/content/movies'

export function getMovies(params?: {
  skip?: number
  limit?: number
  keyword?: string
  source_task_name?: string
  sort_by?: string
  sort_order?: string
}): Promise<PaginatedResponse<Movie>> {
  return request.get<PaginatedResponse<Movie>>(BASE_URL, params)
}

export function getMovie(movieId: string): Promise<Movie> {
  return request.get<Movie>(`${BASE_URL}/${movieId}`)
}
