export interface ActressRecentMovie {
  id: string
  _id?: string
  code: string
  title: string
  cover: string
  release_date: string | null
}

export interface ActressExternalLink {
  id: string
  _id?: string
  task_id: string
  source: string
  label: string
  url: string
  url_type: string
  url_name: string
}

export interface ActressProfile {
  id: string
  _id?: string
  display_name: string
  reading: string
  aliases: string[]
  canonical_names: string[]
  source_url: string
  source_site: string
  source_task_ids: string[]
  source_task_url_ids: string[]
  external_links?: ActressExternalLink[]
  tags: string[]
  image_url: string
  debut_date: string | null
  birth_date: string | null
  height_cm: number | null
  bust_cm: number | null
  waist_cm: number | null
  hip_cm: number | null
  cup: string
  birthplace: string
  blood_type: string
  hobbies: string
  biography: string
  exclusive_maker: string
  sns_links: Array<Record<string, unknown>>
  representative_works: Array<Record<string, unknown>>
  similar_actresses: Array<Record<string, unknown>>
  raw_profile: Record<string, unknown>
  last_fetched_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ActressProfileDetail extends ActressProfile {
  recent_movies: ActressRecentMovie[]
  external_links: ActressExternalLink[]
}

export interface ActressListResponse {
  items: ActressProfile[]
  total: number
  page: number
  limit: number
  total_pages: number
}

export interface ActressQueryParams {
  page?: number
  limit?: 8 | 16 | 24 | 40
  keyword?: string
  source_task_id?: string
  cup?: string
  height_range?: string
  age_range?: string
  bust_range?: string
  waist_range?: string
  hip_range?: string
  tags?: string
}

export interface ActressTagsUpdatePayload {
  tags: string[]
}

export interface ActressFetchFromTaskPayload {
  task_id: string
  task_url_id: string
  avjoho_url?: string
}

export interface ActressFetchFromTaskResult {
  matched: boolean
  profiles: ActressProfile[]
  candidates: string[]
  message: string
}
