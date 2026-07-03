export type StorageMode = 'single' | 'multiple'
export type StorageMainTaskStatus = 'queued' | 'running' | 'stopping' | 'stopped' | 'completed' | 'failed'

export interface StorageMainTask {
  id: string
  alias: string
  display_name: string
  source: 'single' | 'batch'
  storage_mode: StorageMode
  status: StorageMainTaskStatus
  total_count: number
  success_count: number
  failed_count: number
  skipped_count: number
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  error_message?: string | null
}

export interface StorageSubTask {
  id: string
  main_task_id: string
  movie_id: string
  movie_code: string
  movie_title: string
  status: string
  step: string
  storage_mode: string
  selected_storage_location?: string | null
  target_locations: string[]
  download_path: string
  target_paths: string[]
  magnet_attempts: Record<string, unknown>[]
  current_magnet_id?: string | null
  current_magnet_url: string
  renamed_files: Record<string, unknown>[]
  moved_files: Record<string, unknown>[]
  skipped_files: Record<string, unknown>[]
  result: Record<string, unknown>
  skip_reason?: string | null
  error_message?: string | null
  queued_at?: string | null
  started_at?: string | null
  finished_at?: string | null
}

export interface StorageTaskLog {
  timestamp: string
  level: string
  message: string
  context: Record<string, unknown>
}

export interface StorageSinglePushPayload {
  movie_id: string
  alias?: string
  storage_mode: StorageMode
  selected_storage_location?: string
}

export interface StorageBatchPushPayload {
  movie_ids: string[]
  alias?: string
  storage_mode: StorageMode
}
