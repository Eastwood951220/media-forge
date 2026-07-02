export interface MovieMagnet {
  id: string
  magnet_url: string
  name: string
  size_text: string
  has_chinese_sub: boolean
  date: string
  selected: boolean
}

export interface Movie {
  id: string
  code: string | null
  source_url: string | null
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
  source_task_names: string[]
  storage_summary: Record<string, unknown>
  raw_detail: Record<string, unknown>
  magnets?: MovieMagnet[]
  created_at: string
  updated_at: string | null
}
