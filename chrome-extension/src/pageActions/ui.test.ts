// @vitest-environment happy-dom

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { mountPageActions, refreshPageActions } from './controller'
import type { PageContext, PageKind } from './pageContext'
import type {
  PageActionMessage,
  PageActionResponse,
  PageActionRunResult,
  PageActionTaskChoice,
} from './types'

const detailContext: PageContext = {
  kind: 'detail',
  url: 'https://javdb.com/v/abc',
  normalizedUrl: 'https://javdb.com/v/abc',
  pageName: '影片 ABC',
}

const listContext: PageContext = {
  kind: 'list',
  url: 'https://javdb.com/actors/A?page=7&t=d#results',
  normalizedUrl: 'https://javdb.com/actors/A?page=1&t=d',
  pageName: '演员 A',
}

const runResult = (overrides: Partial<PageActionRunResult> = {}): PageActionRunResult => ({
  task_id: 'task-1',
  task_name: '任务一',
  run_id: 'run-1',
  crawl_mode: 'full',
  accepted: true,
  runtime_error: null,
  url_entry_id: null,
  url_added: null,
  ...overrides,
})

const tick = () => new Promise((resolve) => setTimeout(resolve, 0))

function ok<T>(data: T): PageActionResponse<T> {
  return { ok: true, data }
}

function mountFor(
  kind: PageKind,
  sendMessage = vi.fn(async () => ok([])),
) {
  const context = kind === 'detail' ? detailContext : { ...listContext, kind }
  return mountPageActions(context, { sendMessage })
}

function click(root: ShadowRoot, selector: string): HTMLElement {
  const element = root.querySelector<HTMLElement>(selector)
  expect(element).not.toBeNull()
  element!.click()
  return element!
}

describe('JavDB page-action UI', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('mounts only the contextual actions and remains idempotent', () => {
    expect(mountFor('home')).toBeNull()

    const detail = mountFor('detail')!
    expect(detail.root.querySelectorAll('[data-action="temporary"]')).toHaveLength(1)
    expect(detail.root.querySelectorAll('[data-action="quick-create"]')).toHaveLength(0)

    const list = mountFor('list')!
    expect(list.root.querySelectorAll('[data-action="quick-create"]')).toHaveLength(1)
    expect(list.root.querySelectorAll('[data-action="add-existing"]')).toHaveLength(1)
    const deps = { sendMessage: vi.fn(async () => ok([])) }
    const firstStableMount = mountPageActions(listContext, deps)!
    const secondStableMount = mountPageActions(listContext, deps)!
    expect(document.querySelectorAll('#media-forge-page-actions')).toHaveLength(1)
    expect(secondStableMount.host).toBe(firstStableMount.host)
  })

  it('remounts after the host document body is replaced', () => {
    mountFor('list')
    document.body.replaceChildren(document.createElement('main'))

    const refreshed = refreshPageActions()!

    expect(document.querySelectorAll('#media-forge-page-actions')).toHaveLength(1)
    expect(refreshed.root.querySelectorAll('[data-action="quick-create"]')).toHaveLength(1)
  })

  it('loads enabled task choices only after opening and submits one detail URL', async () => {
    const choices: PageActionTaskChoice[] = [{ id: 'task-1', name: '启用任务' }]
    const sendMessage = vi.fn(async (message: PageActionMessage) => {
      if (message.type === 'page_action.list_tasks') return ok(choices)
      return ok(runResult({ crawl_mode: 'temporary' }))
    })
    const mount = mountPageActions(detailContext, { sendMessage })!
    expect(sendMessage).not.toHaveBeenCalled()

    click(mount.root, '[data-action="temporary"]')
    expect(mount.root.activeElement).toBe(
      mount.root.querySelector('[data-action="close-modal"]'),
    )
    await tick()

    const select = mount.root.querySelector<HTMLSelectElement>('[name="task-id"]')!
    expect([...select.options].map((option) => option.textContent)).toContain('启用任务')
    select.value = 'task-1'
    mount.root.querySelector<HTMLFormElement>('form')!.requestSubmit()
    await tick()

    expect(sendMessage).toHaveBeenLastCalledWith({
      type: 'page_action.temporary_run',
      taskId: 'task-1',
      detailUrl: detailContext.url,
    })
  })

  it('shows a recoverable error when loading task choices rejects', async () => {
    const sendMessage = vi.fn(async () => {
      throw new Error('background unavailable')
    })
    const mount = mountPageActions(detailContext, { sendMessage })!

    click(mount.root, '[data-action="temporary"]')
    await tick()

    expect(mount.root.querySelector('[role="alert"]')?.textContent).toContain(
      '无法加载任务列表',
    )
  })

  it('keeps an edited quick-create name and attaches a conflict to that field', async () => {
    const sendMessage = vi.fn(async () => ({
      ok: false as const,
      error: { code: 'duplicate_task_name', message: '任务名称已存在' },
    }))
    const mount = mountPageActions(listContext, { sendMessage })!

    click(mount.root, '[data-action="quick-create"]')
    const input = mount.root.querySelector<HTMLInputElement>('[name="task-name"]')!
    expect(input.value).toBe('演员 A')
    input.value = '自定义任务名'
    expect(mount.root.querySelector('[data-role="mode"]')?.textContent).toContain('全量爬取')
    mount.root.querySelector<HTMLFormElement>('form')!.requestSubmit()
    await tick()

    expect(sendMessage).toHaveBeenCalledWith({
      type: 'page_action.quick_create_run',
      name: '自定义任务名',
      pageName: '演员 A',
      listUrl: listContext.normalizedUrl,
    })
    expect(input.value).toBe('自定义任务名')
    expect(mount.root.querySelector('[data-role="name-error"]')?.textContent).toContain(
      '任务名称已存在',
    )
  })

  it.each([
    [true, '已加入任务并开始增量爬取'],
    [false, '该页面已在任务中，已开始增量爬取'],
  ] as const)('submits add-existing and renders url_added=%s', async (urlAdded, message) => {
    const sendMessage = vi.fn(async (request: PageActionMessage) => {
      if (request.type === 'page_action.list_tasks') {
        return ok([{ id: 'task-1', name: '启用任务' }])
      }
      return ok(runResult({
        crawl_mode: 'incremental',
        url_entry_id: 'url-1',
        url_added: urlAdded,
      }))
    })
    const mount = mountPageActions(listContext, { sendMessage })!

    click(mount.root, '[data-action="add-existing"]')
    await tick()
    mount.root.querySelector<HTMLSelectElement>('[name="task-id"]')!.value = 'task-1'
    mount.root.querySelector<HTMLFormElement>('form')!.requestSubmit()
    await tick()

    expect(sendMessage).toHaveBeenLastCalledWith({
      type: 'page_action.add_url_run',
      taskId: 'task-1',
      pageName: '演员 A',
      listUrl: listContext.normalizedUrl,
    })
    expect(mount.root.querySelector('[data-role="result"]')?.textContent).toContain(message)
  })

  it('guards double submit while a request is pending', async () => {
    let resolveRequest!: (value: PageActionResponse<PageActionRunResult>) => void
    const pending = new Promise<PageActionResponse<PageActionRunResult>>((resolve) => {
      resolveRequest = resolve
    })
    const sendMessage = vi.fn(() => pending)
    const mount = mountPageActions(listContext, { sendMessage })!
    click(mount.root, '[data-action="quick-create"]')
    const form = mount.root.querySelector<HTMLFormElement>('form')!

    form.requestSubmit()
    form.requestSubmit()

    expect(sendMessage).toHaveBeenCalledTimes(1)
    expect(form.getAttribute('aria-busy')).toBe('true')
    resolveRequest(ok(runResult()))
    await tick()
  })

  it('shows partial activation and opens the persisted run detail', async () => {
    const sendMessage = vi.fn(async (message: PageActionMessage) => {
      if (message.type === 'page_action.open_run') return ok({ opened: true })
      return ok(runResult({
        accepted: false,
        runtime_error: '运行记录已创建，但启动失败',
      }))
    })
    const mount = mountPageActions(listContext, { sendMessage })!
    click(mount.root, '[data-action="quick-create"]')
    mount.root.querySelector<HTMLFormElement>('form')!.requestSubmit()
    await tick()

    expect(mount.root.querySelector('[data-role="result"]')?.textContent).toContain('启动失败')
    click(mount.root, '[data-action="open-run"]')
    await tick()
    expect(sendMessage).toHaveBeenLastCalledWith({ type: 'page_action.open_run', runId: 'run-1' })
  })

  it('traps focus, closes on Escape, and restores the invoking button', async () => {
    const mount = mountPageActions(listContext, { sendMessage: vi.fn(async () => ok([])) })!
    const trigger = click(mount.root, '[data-action="quick-create"]')
    const dialog = mount.root.querySelector<HTMLElement>('[role="dialog"]')!
    const input = mount.root.querySelector<HTMLInputElement>('[name="task-name"]')!
    const close = mount.root.querySelector<HTMLButtonElement>('[data-action="close-modal"]')!
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(mount.root.activeElement).toBe(input)

    const submit = mount.root.querySelector<HTMLButtonElement>('[type="submit"]')!
    submit.focus()
    dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(mount.root.activeElement).toBe(close)
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await tick()

    expect(mount.root.querySelector('[role="dialog"]')).toBeNull()
    expect(mount.root.activeElement).toBe(trigger)
  })

  it('never places an Agent token in messages or rendered Shadow DOM', async () => {
    const messages: PageActionMessage[] = []
    const sendMessage = vi.fn(async (message: PageActionMessage) => {
      messages.push(message)
      return ok(runResult())
    })
    const mount = mountPageActions(listContext, { sendMessage })!
    click(mount.root, '[data-action="quick-create"]')
    mount.root.querySelector<HTMLFormElement>('form')!.requestSubmit()
    await tick()

    expect(JSON.stringify(messages)).not.toContain('agt_')
    expect(mount.root.textContent).not.toContain('agt_')
  })
})
