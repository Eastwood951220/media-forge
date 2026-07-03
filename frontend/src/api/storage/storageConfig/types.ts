export interface StorageConfig {
  enabled: boolean
  grpc_host: string
  api_token: string
  api_token_configured: boolean
  request_timeout_seconds: number
  connect_timeout_seconds: number
  download_root_folder: string
  target_folder: string
  use_task_subfolder: boolean
  auto_create_target_folder: boolean
  single_filename_template: string
  multi_filename_template: string
  operation_delay_min: number
  operation_delay_max: number
  download_poll_interval_min: number
  download_poll_interval_max: number
  retry_delay_min: number
  retry_delay_max: number
  max_step_retries: number
  download_max_poll_count: number
  minimum_video_size_mb: number
  video_extensions: string[]
  excluded_filename_keywords: string[]
  keep_subtitles: boolean
  keep_cover_images: boolean
  delete_empty_folders: boolean
}

export type StorageConfigUpdate = Partial<Omit<StorageConfig, 'api_token_configured'>>

export interface StorageTestResult {
  grpc_reachable: boolean
  grpc_error: string | null
  api_authorized: boolean
  api_error: string | null
  download_root_exists: boolean
  download_root_error: string | null
  target_folder_accessible: boolean
  target_folder_error: string | null
}
