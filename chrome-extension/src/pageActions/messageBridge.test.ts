import { describe, expect, it, vi } from 'vitest'

import { logPageActionFailure, sendPageActionMessage } from './messageBridge'
import { respondToPageActionMessage } from './backgroundBridge'
import type { PageActionResponse } from './types'

function logger() {
  return { info: vi.fn(), error: vi.fn() }
}

describe('page action message diagnostics', () => {
  it('logs a workflow error without exposing an Agent token', () => {
    const log = logger()

    logPageActionFailure('page_action.quick_create_run', new Error('invalid result agt_secret'), log)

    expect(log.error).toHaveBeenCalledWith(
      '[Media Forge page action] workflow failed',
      'page_action.quick_create_run',
      'invalid result [REDACTED]',
    )
  })

  it('logs a missing background response and rejects instead of hiding the transport failure', async () => {
    const log = logger()
    const send = vi.fn().mockResolvedValue(undefined)

    await expect(sendPageActionMessage({ type: 'page_action.list_tasks' }, send, log))
      .rejects.toThrow('missing_page_action_response')

    expect(log.info).toHaveBeenCalledWith('[Media Forge page action] send', 'page_action.list_tasks')
    expect(log.error).toHaveBeenCalledWith(
      '[Media Forge page action] failed',
      'page_action.list_tasks',
      'missing_page_action_response',
    )
  })

  it('logs a rejected runtime message without exposing an Agent token', async () => {
    const log = logger()
    const send = vi.fn().mockRejectedValue(new Error('Port closed agt_secret'))

    await expect(sendPageActionMessage({ type: 'page_action.list_tasks' }, send, log))
      .rejects.toThrow('Port closed agt_secret')

    expect(JSON.stringify(log.error.mock.calls)).not.toContain('agt_secret')
    expect(log.error).toHaveBeenCalledWith(
      '[Media Forge page action] failed',
      'page_action.list_tasks',
      'Port closed [REDACTED]',
    )
  })

  it('returns a structured response and logs when background processing rejects', async () => {
    const log = logger()
    const respond = vi.fn<(response: PageActionResponse<unknown>) => void>()
    const handle = vi.fn().mockRejectedValue(new Error('storage failed agt_secret'))

    await respondToPageActionMessage({ type: 'page_action.list_tasks' }, handle, respond, log)

    expect(log.info).toHaveBeenCalledWith('[Media Forge page action] received', 'page_action.list_tasks')
    expect(JSON.stringify(log.error.mock.calls)).not.toContain('agt_secret')
    expect(respond).toHaveBeenCalledWith({
      ok: false,
      error: { code: 'background_error', message: '扩展后台处理失败，请查看 Service Worker 控制台' },
    })
  })

  it('logs the background result without logging response data', async () => {
    const log = logger()
    const respond = vi.fn<(response: PageActionResponse<unknown>) => void>()
    const handle = vi.fn().mockResolvedValue({ ok: true, data: { token: 'agt_secret' } })

    await respondToPageActionMessage({ type: 'page_action.list_tasks' }, handle, respond, log)

    expect(respond).toHaveBeenCalledWith({ ok: true, data: { token: 'agt_secret' } })
    expect(JSON.stringify(log.info.mock.calls)).not.toContain('agt_secret')
    expect(log.info).toHaveBeenCalledWith('[Media Forge page action] responded', 'page_action.list_tasks', 'ok')
  })
})
