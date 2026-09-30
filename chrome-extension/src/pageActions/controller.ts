import type { PageContext } from './pageContext'
import type {
  PageActionMessage,
  PageActionResponse,
  PageActionRunResult,
  PageActionTaskChoice,
} from './types'
import { createPageActionUi } from './ui'
import type { PageActionKind, PageActionModal, PageActionUi } from './ui'

export type PageActionDeps = {
  sendMessage: (message: PageActionMessage) => Promise<PageActionResponse<unknown>>
}

export type PageActionMount = {
  host: HTMLElement
  root: ShadowRoot
  destroy: () => void
}

let activeMount: PageActionMount | null = null
let lastContext: PageContext | null = null
let lastDeps: PageActionDeps | null = null

function errorMessage(response: Extract<PageActionResponse<unknown>, { ok: false }>): string {
  return response.error.message || '操作失败，请稍后重试'
}

async function loadTaskChoices(
  ui: PageActionUi,
  modal: PageActionModal,
  deps: PageActionDeps,
): Promise<void> {
  try {
    const response = await deps.sendMessage({ type: 'page_action.list_tasks' })
    if (response.ok) {
      ui.setTaskChoices(modal, response.data as PageActionTaskChoice[])
    } else {
      ui.showError(modal, errorMessage(response))
    }
  } catch {
    ui.showError(modal, '无法加载任务列表，请确认扩展后台正在运行')
  }
}

function bindModalWorkflow(
  ui: PageActionUi,
  modal: PageActionModal,
  context: PageContext,
  deps: PageActionDeps,
): void {
  let busy = false
  let runId: string | null = null
  modal.openRunButton.addEventListener('click', () => {
    if (!runId) return
    void deps.sendMessage({ type: 'page_action.open_run', runId })
  })
  modal.form.addEventListener('submit', (event) => {
    event.preventDefault()
    if (busy) return
    let message: PageActionMessage
    if (modal.kind === 'quick-create') {
      const name = modal.nameInput?.value.trim() ?? ''
      if (!name) {
        ui.showError(modal, '请输入任务名称', 'name')
        return
      }
      message = {
        type: 'page_action.quick_create_run',
        name,
        pageName: context.pageName,
        listUrl: context.normalizedUrl,
      }
    } else {
      const taskId = modal.taskSelect?.value ?? ''
      if (!taskId) {
        ui.showError(modal, '请选择一个已启用任务')
        return
      }
      message = modal.kind === 'temporary'
        ? { type: 'page_action.temporary_run', taskId, detailUrl: context.url }
        : {
            type: 'page_action.add_url_run',
            taskId,
            pageName: context.pageName,
            listUrl: context.normalizedUrl,
          }
    }
    busy = true
    ui.setBusy(modal, true)
    void deps.sendMessage(message).then((response) => {
      if (response.ok) {
        const result = response.data as PageActionRunResult
        runId = result.run_id
        ui.showResult(modal, result)
      } else {
        const field = response.error.code === 'duplicate_task_name' ? 'name' : undefined
        ui.showError(modal, errorMessage(response), field)
      }
    }).catch(() => {
      ui.showError(modal, '无法连接扩展后台，请重新加载扩展后再试')
    }).finally(() => {
      busy = false
      ui.setBusy(modal, false)
    })
  })
}

function openWorkflow(
  ui: PageActionUi,
  action: PageActionKind,
  trigger: HTMLElement,
  context: PageContext,
  deps: PageActionDeps,
): void {
  const modal = ui.openModal(action, trigger)
  bindModalWorkflow(ui, modal, context, deps)
  if (action !== 'quick-create') void loadTaskChoices(ui, modal, deps)
}

function createMount(context: PageContext, deps: PageActionDeps): PageActionMount | null {
  document.getElementById('media-forge-page-actions')?.remove()
  if (context.kind === 'home' || context.kind === 'unsupported') return null
  const ui = createPageActionUi(context)
  for (const action of ['temporary', 'quick-create', 'add-existing'] as const) {
    const button = ui.actionButton(action)
    button?.addEventListener('click', () => openWorkflow(ui, action, button, context, deps))
  }
  return { host: ui.host, root: ui.root, destroy: ui.destroy }
}

export function mountPageActions(
  context: PageContext,
  deps: PageActionDeps,
): PageActionMount | null {
  const unchanged =
    activeMount?.host.isConnected &&
    lastDeps === deps &&
    lastContext?.kind === context.kind &&
    lastContext.url === context.url &&
    lastContext.normalizedUrl === context.normalizedUrl &&
    lastContext.pageName === context.pageName
  if (unchanged) return activeMount
  activeMount?.destroy()
  lastContext = context
  lastDeps = deps
  activeMount = createMount(context, deps)
  return activeMount
}

export function refreshPageActions(): PageActionMount | null {
  if (!lastContext || !lastDeps) return null
  activeMount?.destroy()
  activeMount = createMount(lastContext, lastDeps)
  return activeMount
}
