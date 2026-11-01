import { request } from '@/request'
import { baseURL } from '@/request/instance'
import { getToken } from '@/utils/auth'
import type { Movie, MovieDeleteMode, MovieDeleteResult, MovieListResponse, MovieMagnetRefreshPayload, MovieMagnetRefreshResponse, MovieStorageStatus } from './types'

export type { Movie, MovieDeleteMode, MovieDeleteResult, MovieListResponse, MovieMagnetRefreshPayload, MovieMagnetRefreshResponse, MovieStorageStatus, StorageLocation } from './types'

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
  scraping_status?: string
  jellyfin_watch_status?: string
  jellyfin_last_played_from?: string
  jellyfin_last_played_to?: string
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

export async function fetchScrapedMovieCover(id: string, signal?: AbortSignal, version?: string | null): Promise<Blob> {
  const token = getToken()
  if (!token) throw new Error('Not authenticated')
  const versionQuery = version ? `?v=${encodeURIComponent(version)}` : ''
  const response = await fetch(`${baseURL.replace(/\/$/, '')}${BASE_URL}/${encodeURIComponent(id)}/scraped-cover${versionQuery}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!response.ok) throw new Error('Scraped cover unavailable')
  return response.blob()
}

export interface MovieStorageSyncPayload {
  movie_ids?: string[]
  filters?: MovieQueryParams
}

export interface MovieStorageSyncResult {
  movie_id: string
  status: MovieStorageStatus
  found_count: number
  checked_targets: string[]
  locations: Record<string, unknown>[]
}

export interface MovieStorageSyncResponse {
  total: number
  stored_count: number
  not_stored_count: number
  results: MovieStorageSyncResult[]
}

export function syncMovieStorageStatus(payload: MovieStorageSyncPayload): Promise<MovieStorageSyncResponse> {
  return request.post<MovieStorageSyncResponse>(`${BASE_URL}/storage-sync`, payload)
}

export function syncMovieStorageStatusFromCd2(movieId: string): Promise<MovieStorageSyncResult> {
  return request.post<MovieStorageSyncResult>(`${BASE_URL}/${movieId}/storage-sync/cd2`)
}

export interface MovieDeletePayload {
  movie_ids: string[]
  mode: MovieDeleteMode
}

export function deleteMovies(payload: MovieDeletePayload): Promise<MovieDeleteResult> {
  return request.post<MovieDeleteResult>(`${BASE_URL}/delete`, payload)
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

export function refreshMovieMagnets(payload: MovieMagnetRefreshPayload): Promise<MovieMagnetRefreshResponse> {
  return request.post<MovieMagnetRefreshResponse>(`${BASE_URL}/magnet-refresh`, payload)
}
