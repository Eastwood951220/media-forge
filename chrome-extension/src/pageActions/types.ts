export type PageActionTaskChoice = {
  id: string
  name: string
}

export type PageActionRunResult = {
  task_id: string
  task_name: string
  run_id: string
  crawl_mode: 'temporary' | 'full' | 'incremental'
  accepted: boolean
  runtime_error: string | null
  url_entry_id: string | null
  url_added: boolean | null
}

export type PageActionMessage =
  | { type: 'page_action.list_tasks' }
  | { type: 'page_action.temporary_run'; taskId: string; detailUrl: string }
  | {
      type: 'page_action.quick_create_run'
      name: string
      pageName: string
      listUrl: string
    }
  | {
      type: 'page_action.add_url_run'
      taskId: string
      pageName: string
      listUrl: string
    }
  | { type: 'page_action.open_run'; runId: string }

export type PageActionResponse<T> =
  | { ok: true; data: T }
  | { ok: false; error: { code: string; message: string; data?: unknown } }

export function isPageActionMessage(value: unknown): value is PageActionMessage {
  if (!value || typeof value !== 'object' || !('type' in value)) return false
  return [
    'page_action.list_tasks',
    'page_action.temporary_run',
    'page_action.quick_create_run',
    'page_action.add_url_run',
    'page_action.open_run',
  ].includes(String(value.type))
}
