import { request } from '@/request'
import type { Movie, MovieListResponse } from './types'

export type { Movie, MovieListResponse, StorageLocation } from './types'

const BASE_URL = '/api/content/movies'

interface PaginatedMovies {
  rows: Movie[]
  total: number
}

export type FilterType = 'actor' | 'tag' | 'director' | 'maker' | 'series'

export interface FilterItemConfig {
  visible: boolean
  order: number
  defaultValue?: unknown
}

export interface MovieFilterConfigResponse {
  _key?: string
  filters: Record<string, FilterItemConfig>
  updated_at?: string
}

export interface MovieQueryParams {
  source_task_id?: string
  search?: string
  page?: number
  limit?: number
  sort_by?: string
  sort_order?: number
  rating_min?: number
  rating_max?: number
  actors?: string
  actors_not?: string
  actors_count_min?: number
  actors_count_max?: number
  tags?: string
  tags_not?: string
  director?: string
  director_not?: string
  maker?: string
  maker_not?: string
  series?: string
  series_not?: string
  release_date_from?: string
  release_date_to?: string
  created_at_from?: string
  created_at_to?: string
  storage_status?: string
}

export function fetchMovies(params: MovieQueryParams): Promise<MovieListResponse> {
  return request.get<PaginatedMovies>(BASE_URL, params).then((res) => {
    const page = params.page ?? 1
    const limit = params.limit ?? 20
    return {
      items: res.rows,
      total: res.total,
      page,
      limit,
      total_pages: Math.max(1, Math.ceil(res.total / limit)),
    }
  })
}

export function fetchMovie(id: string): Promise<Movie> {
  return request.get<Movie>(`${BASE_URL}/${id}`)
}

export function getMovies(params?: MovieQueryParams): Promise<PaginatedMovies> {
  return request.get<PaginatedMovies>(BASE_URL, params)
}

export function getMovie(id: string): Promise<Movie> {
  return fetchMovie(id)
}

export function fetchTaskNames(): Promise<{ name: string }[]> {
  return request.get<{ name: string }[]>(`${BASE_URL}/task-names`)
}

export function fetchFilters(type: FilterType): Promise<string[]> {
  return request.get<string[]>(`${BASE_URL}/filters`, { type })
}

export function fetchMovieFilterConfig(): Promise<MovieFilterConfigResponse> {
  return request.get<MovieFilterConfigResponse>(`${BASE_URL}/filter-config`)
}


export function updateMovieFilterConfig(filters: Record<string, FilterItemConfig>): Promise<{ success: boolean }> {
  return request.put<{ success: boolean }>(`${BASE_URL}/filter-config`, { filters })
}
