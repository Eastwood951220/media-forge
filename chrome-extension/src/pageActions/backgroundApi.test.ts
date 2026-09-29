import { describe, expect, it, vi } from 'vitest'

import { handlePageActionMessage } from './backgroundApi'
import { isPageActionMessage } from './types'
import type { PageActionMessage, PageActionRunResult } from './types'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function deps(fetch = vi.fn()) {
  return {
    fetch,
    settings: vi.fn().mockResolvedValue({
      backendUrl: 'http://mf.test/',
      token: 'agt_secret',
    }),
    openTab: vi.fn().mockResolvedValue(undefined),
  }
}

describe('handlePageActionMessage', () => {
  it('rejects unknown messages that only share the page-action prefix', () => {
    expect(isPageActionMessage({ type: 'page_action.unknown' })).toBe(false)
  })

  it('adds Agent authorization only in the background request', async () => {
    const fetch = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, msg: 'success', data: [{ id: 'task-1', name: '任务一' }] }),
    )
    const runtime = deps(fetch)

    const result = await handlePageActionMessage({ type: 'page_action.list_tasks' }, runtime)

    expect(fetch).toHaveBeenCalledWith(
      'http://mf.test/api/crawler/agent/page-actions/tasks',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({ Authorization: 'Bearer agt_secret' }),
      }),
    )
    expect(result).toEqual({ ok: true, data: [{ id: 'task-1', name: '任务一' }] })
    expect(JSON.stringify(result)).not.toContain('agt_secret')
  })

  it('returns a stable error when extension settings are missing', async () => {
    const runtime = deps()
    runtime.settings.mockResolvedValue(null)

    const result = await handlePageActionMessage({ type: 'page_action.list_tasks' }, runtime)

    expect(result).toEqual({
      ok: false,
      error: { code: 'settings_missing', message: '请先配置 Media Forge 地址和 Agent Token' },
    })
    expect(runtime.fetch).not.toHaveBeenCalled()
  })

  it('maps transport failures without exposing the thrown error', async () => {
    const runtime = deps(vi.fn().mockRejectedValue(new Error('agt_secret network detail')))

    const result = await handlePageActionMessage({ type: 'page_action.list_tasks' }, runtime)

    expect(result).toEqual({
      ok: false,
      error: { code: 'network_error', message: '无法连接 Media Forge 服务' },
    })
    expect(JSON.stringify(result)).not.toContain('agt_secret')
  })

  it('maps a duplicate-name backend response to a business error', async () => {
    const runtime = deps(
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            code: 409,
            msg: "任务名称 '演员 A' 已存在",
            data: { reason: 'duplicate_task_name', ignored: 'agt_secret' },
          },
          409,
        ),
      ),
    )

    const result = await handlePageActionMessage(
      {
        type: 'page_action.quick_create_run',
        name: '演员 A',
        pageName: '演员 A',
        listUrl: 'https://javdb.com/actors/A?page=1',
      },
      runtime,
    )

    expect(result).toEqual({
      ok: false,
      error: {
        code: 'duplicate_task_name',
        message: "任务名称 '演员 A' 已存在",
        data: { reason: 'duplicate_task_name' },
      },
    })
    expect(JSON.stringify(result)).not.toContain('agt_secret')
  })

  it.each<{
    message: PageActionMessage
    endpoint: string
    body: unknown
    mode: PageActionRunResult['crawl_mode']
  }>([
    {
      message: {
        type: 'page_action.temporary_run',
        taskId: 'task-1',
        detailUrl: 'https://javdb.com/v/abc',
      },
      endpoint: '/api/crawler/agent/page-actions/temporary-runs',
      body: { task_id: 'task-1', detail_url: 'https://javdb.com/v/abc' },
      mode: 'temporary',
    },
    {
      message: {
        type: 'page_action.quick_create_run',
        name: '演员 A',
        pageName: '演员 A 页面',
        listUrl: 'https://javdb.com/actors/A?page=1',
      },
      endpoint: '/api/crawler/agent/page-actions/quick-create-runs',
      body: {
        name: '演员 A',
        page_name: '演员 A 页面',
        list_url: 'https://javdb.com/actors/A?page=1',
      },
      mode: 'full',
    },
    {
      message: {
        type: 'page_action.add_url_run',
        taskId: 'task-1',
        pageName: '演员 A 页面',
        listUrl: 'https://javdb.com/actors/A?page=1',
      },
      endpoint: '/api/crawler/agent/page-actions/add-url-runs',
      body: {
        task_id: 'task-1',
        page_name: '演员 A 页面',
        list_url: 'https://javdb.com/actors/A?page=1',
      },
      mode: 'incremental',
    },
  ])('posts $message.type using the confirmed contract', async ({ message, endpoint, body, mode }) => {
    const data: PageActionRunResult = {
      task_id: 'task-1',
      task_name: '演员 A',
      run_id: 'run-1',
      crawl_mode: mode,
      accepted: true,
      runtime_error: null,
      url_entry_id: mode === 'incremental' ? 'url-1' : null,
      url_added: mode === 'incremental' ? true : null,
    }
    const fetch = vi.fn().mockResolvedValue(jsonResponse({ code: 200, msg: 'success', data }))
    const runtime = deps(fetch)

    const result = await handlePageActionMessage(message, runtime)

    expect(result).toEqual({ ok: true, data })
    expect(fetch).toHaveBeenCalledWith(
      `http://mf.test${endpoint}`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(body) }),
    )
  })

  it('preserves a partial activation result with its persisted run ID', async () => {
    const data: PageActionRunResult = {
      task_id: 'task-1',
      task_name: '演员 A',
      run_id: 'run-persisted',
      crawl_mode: 'full',
      accepted: false,
      runtime_error: '运行记录已创建，但爬虫运行时启动失败',
      url_entry_id: null,
      url_added: null,
    }
    const runtime = deps(
      vi.fn().mockResolvedValue(jsonResponse({ code: 200, msg: 'success', data })),
    )

    const result = await handlePageActionMessage(
      {
        type: 'page_action.quick_create_run',
        name: '演员 A',
        pageName: '演员 A',
        listUrl: 'https://javdb.com/actors/A?page=1',
      },
      runtime,
    )

    expect(result).toEqual({ ok: true, data })
  })

  it('opens the existing run-detail route in a background tab', async () => {
    const runtime = deps()

    const result = await handlePageActionMessage(
      { type: 'page_action.open_run', runId: 'run-1' },
      runtime,
    )

    expect(runtime.openTab).toHaveBeenCalledWith('http://mf.test/crawler/runs/run-1')
    expect(result).toEqual({ ok: true, data: { opened: true } })
    expect(runtime.fetch).not.toHaveBeenCalled()
  })
})
