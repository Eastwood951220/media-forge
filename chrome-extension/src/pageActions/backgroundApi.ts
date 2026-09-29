import type { PageActionMessage, PageActionResponse } from './types'

export type PageActionSettings = {
  backendUrl: string
  token: string
}

export type PageActionBackgroundDeps = {
  fetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
  settings: () => Promise<PageActionSettings | null>
  openTab: (url: string) => Promise<unknown>
}

type BackendEnvelope = {
  code?: number
  msg?: unknown
  data?: unknown
}

type RequestContract = {
  path: string
  method: 'GET' | 'POST'
  body?: Record<string, unknown>
}

function backendBaseUrl(value: string): string {
  return value.replace(/\/+$/, '')
}

function safeMessage(value: unknown, token: string, fallback: string): string {
  if (typeof value !== 'string' || !value.trim()) return fallback
  return value.replaceAll(token, '[REDACTED]').replace(/agt_[A-Za-z0-9_-]+/g, '[REDACTED]')
}

function requestContract(message: Exclude<PageActionMessage, { type: 'page_action.open_run' }>): RequestContract {
  switch (message.type) {
    case 'page_action.list_tasks':
      return { path: '/api/crawler/agent/page-actions/tasks', method: 'GET' }
    case 'page_action.temporary_run':
      return {
        path: '/api/crawler/agent/page-actions/temporary-runs',
        method: 'POST',
        body: { task_id: message.taskId, detail_url: message.detailUrl },
      }
    case 'page_action.quick_create_run':
      return {
        path: '/api/crawler/agent/page-actions/quick-create-runs',
        method: 'POST',
        body: {
          name: message.name,
          page_name: message.pageName,
          list_url: message.listUrl,
        },
      }
    case 'page_action.add_url_run':
      return {
        path: '/api/crawler/agent/page-actions/add-url-runs',
        method: 'POST',
        body: {
          task_id: message.taskId,
          page_name: message.pageName,
          list_url: message.listUrl,
        },
      }
  }
}

function backendError(
  response: Response,
  payload: BackendEnvelope | null,
  token: string,
): PageActionResponse<never> {
  const reason =
    payload?.data &&
    typeof payload.data === 'object' &&
    'reason' in payload.data &&
    typeof payload.data.reason === 'string'
      ? payload.data.reason
      : null
  return {
    ok: false,
    error: {
      code: reason ?? String(payload?.code ?? response.status),
      message: safeMessage(payload?.msg, token, `请求失败 (${response.status})`),
      ...(reason ? { data: { reason } } : {}),
    },
  }
}

export async function handlePageActionMessage<T = unknown>(
  message: PageActionMessage,
  deps: PageActionBackgroundDeps,
): Promise<PageActionResponse<T>> {
  const settings = await deps.settings()
  if (!settings?.backendUrl || !settings.token) {
    return {
      ok: false,
      error: {
        code: 'settings_missing',
        message: '请先配置 Media Forge 地址和 Agent Token',
      },
    }
  }
  const baseUrl = backendBaseUrl(settings.backendUrl)
  if (message.type === 'page_action.open_run') {
    await deps.openTab(`${baseUrl}/crawler/runs/${encodeURIComponent(message.runId)}`)
    return { ok: true, data: { opened: true } as T }
  }

  const contract = requestContract(message)
  let response: Response
  try {
    response = await deps.fetch(`${baseUrl}${contract.path}`, {
      method: contract.method,
      headers: {
        Authorization: `Bearer ${settings.token}`,
        ...(contract.body ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(contract.body ? { body: JSON.stringify(contract.body) } : {}),
    })
  } catch {
    return {
      ok: false,
      error: { code: 'network_error', message: '无法连接 Media Forge 服务' },
    }
  }

  let payload: BackendEnvelope | null = null
  try {
    payload = (await response.json()) as BackendEnvelope
  } catch {
    payload = null
  }
  if (!response.ok) return backendError(response, payload, settings.token)
  if (!payload || !("data" in payload)) {
    return {
      ok: false,
      error: { code: 'invalid_response', message: 'Media Forge 返回了无效响应' },
    }
  }
  return { ok: true, data: payload.data as T }
}
