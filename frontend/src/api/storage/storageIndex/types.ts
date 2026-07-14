export interface StorageIndexMetadata {
  target_folder: string
  status: 'never_built' | 'running' | 'completed' | 'failed'
  started_at: string | null
  completed_at: string | null
  category_count: number
  code_folder_count: number
  video_count: number
  force_refresh_mode: string
  current_path: string | null
  errors: Array<{ path: string; error: string }>
}

export interface StorageIndexRefreshStartResult {
  started: boolean
  mode: 'full' | 'incremental'
  status: 'running'
  message: string
}
