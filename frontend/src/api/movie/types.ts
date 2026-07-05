export type MovieStorageStatus = 'not_stored' | 'storing' | 'stored'

export interface MovieMagnet {
  _id: string
  id: string
  movie_id?: string
  magnet?: string
  magnet_url: string
  name: string
  title?: string
  size?: string | number
  size_mb?: number
  size_text: string
  file_count?: number | null
  file_text?: string
  tags?: string[]
  has_chinese_sub: boolean
  date: string
  dedupe_key?: string
  weight?: number
  selected: boolean
}

export interface StorageLocation {
  path: string
  target_folder: string
  exists?: boolean
}

export interface Movie {
  _id: string
  id: string
  code: string
  source_url: string
  source_name: string
  cover: string
  release_date: string | null
  duration: number
  director: string
  maker: string
  series: string
  rating: number | null
  actors: string[]
  tags: string[]
  source_task_name?: string
  source_task_names: string[]
  storage_locations?: string[]
  marked: boolean
  storage_status: MovieStorageStatus
  storage_summary: {
    last_status?: MovieStorageStatus
    storage_status?: MovieStorageStatus
    locations?: StorageLocation[]
    synced_at?: string
    [key: string]: unknown
  }
  raw_detail: Record<string, unknown>
  magnets?: MovieMagnet[]
  selected_magnet_dedupe_key?: string | null
  has_chinese_sub?: boolean
  size?: number | string
  magnet?: string
  created_at: string | null
  updated_at: string | null
}

export interface MovieListResponse {
  items: Movie[]
  total: number
  page: number
  limit: number
  total_pages: number
}

export interface SelectOption<T = string> {
  value: T
  label: string
}

export type MovieFilterField =
  | 'actors' | 'tags' | 'director' | 'maker' | 'series'
  | 'actorsNot' | 'tagsNot' | 'directorNot' | 'makerNot' | 'seriesNot'
  | 'storageStatus' | 'ratingMin' | 'ratingMax'
  | 'actorsCountMin' | 'actorsCountMax'
  | 'releaseDateFrom' | 'releaseDateTo'
  | 'createdAtFrom' | 'createdAtTo' | 'sortBy'

export interface MovieFilterConfigValue {
  visible: boolean
  order: number
  defaultValue?: unknown
}

export type MovieFilterConfig = Partial<Record<MovieFilterField, MovieFilterConfigValue>>
