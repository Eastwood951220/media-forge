import type { PageContext } from './pageContext'
import type { PageActionRunResult, PageActionTaskChoice } from './types'

export type PageActionKind = 'temporary' | 'quick-create' | 'add-existing'

export type PageActionModal = {
  kind: PageActionKind
  dialog: HTMLElement
  form: HTMLFormElement
  taskSelect: HTMLSelectElement | null
  nameInput: HTMLInputElement | null
  submitButton: HTMLButtonElement
  error: HTMLElement
  nameError: HTMLElement | null
  result: HTMLElement
  openRunButton: HTMLButtonElement
}

export type PageActionUi = {
  host: HTMLElement
  root: ShadowRoot
  actionButton: (action: PageActionKind) => HTMLButtonElement | null
  openModal: (kind: PageActionKind, trigger: HTMLElement) => PageActionModal
  closeModal: () => void
  setTaskChoices: (modal: PageActionModal, choices: PageActionTaskChoice[]) => void
  setBusy: (modal: PageActionModal, busy: boolean) => void
  showError: (modal: PageActionModal, message: string, field?: 'name') => void
  showResult: (modal: PageActionModal, result: PageActionRunResult) => void
  destroy: () => void
}

const STYLES = `
  :host { all: initial; color-scheme: light; }
  *, *::before, *::after { box-sizing: border-box; }
  .mf-toolbar {
    position: fixed; right: 18px; top: clamp(96px, 28vh, 280px); z-index: 2147483645;
    display: grid; gap: 10px; width: min(230px, calc(100vw - 32px));
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  button, input, select { font: inherit; }
  button { cursor: pointer; }
  .mf-action {
    min-height: 44px; border: 1px solid rgba(15, 23, 42, .12); border-radius: 12px;
    padding: 10px 14px; display: flex; align-items: center; gap: 9px;
    color: #fff; background: #2563eb; box-shadow: 0 8px 24px rgba(15, 23, 42, .22);
    font-weight: 700; text-align: left;
  }
  .mf-action.secondary { background: #0f766e; }
  button:hover:not(:disabled) { filter: brightness(1.06); }
  button:focus-visible, input:focus-visible, select:focus-visible {
    outline: 3px solid #f59e0b; outline-offset: 2px;
  }
  button:disabled { cursor: wait; opacity: .65; }
  svg { width: 20px; height: 20px; flex: 0 0 auto; fill: none; stroke: currentColor; stroke-width: 2; }
  .mf-backdrop {
    position: fixed; inset: 0; z-index: 2147483646; display: grid; place-items: center;
    padding: 20px; background: rgba(15, 23, 42, .56);
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .mf-dialog {
    width: min(520px, 100%); max-height: min(720px, calc(100vh - 40px)); overflow: auto;
    border-radius: 16px; padding: 22px; background: #fff; color: #172033;
    box-shadow: 0 24px 64px rgba(15, 23, 42, .32);
  }
  .mf-head { display: flex; justify-content: space-between; gap: 16px; align-items: start; }
  h2 { margin: 0; font-size: 20px; line-height: 1.3; }
  .mf-close { min-width: 44px; min-height: 44px; border: 0; border-radius: 10px; background: #eef2f7; }
  .mf-context { margin: 16px 0; padding: 12px; border-radius: 10px; background: #f8fafc; }
  .mf-context strong { display: block; margin-bottom: 4px; }
  .mf-url { color: #475569; overflow-wrap: anywhere; font-size: 13px; }
  .mf-field { display: grid; gap: 6px; margin-top: 14px; }
  label { font-weight: 700; }
  input, select {
    width: 100%; min-height: 44px; border: 1px solid #94a3b8; border-radius: 9px;
    padding: 9px 11px; color: #172033; background: #fff;
  }
  .mf-mode { display: inline-flex; width: fit-content; border-radius: 999px; padding: 5px 10px;
    color: #1e3a8a; background: #dbeafe; font-weight: 700; }
  .mf-error { min-height: 20px; margin-top: 8px; color: #b42318; font-weight: 650; }
  .mf-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
  .mf-actions button { min-height: 44px; border: 0; border-radius: 9px; padding: 9px 16px; font-weight: 700; }
  .mf-cancel { color: #334155; background: #e2e8f0; }
  .mf-submit, .mf-open-run { color: #fff; background: #2563eb; }
  .mf-result { margin-top: 18px; }
  .mf-result h3 { margin: 0 0 8px; font-size: 18px; }
  .mf-result p { margin: 5px 0; }
  [hidden] { display: none !important; }
  @media (max-width: 560px) {
    .mf-toolbar { right: 12px; top: auto; bottom: 18px; width: calc(100vw - 24px); }
    .mf-dialog { padding: 18px; }
  }
  @media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; } }
`

const ICON = `
  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/><circle cx="12" cy="12" r="9"/></svg>
`

function actionLabel(action: PageActionKind): string {
  if (action === 'temporary') return '加入临时任务'
  if (action === 'quick-create') return '快速创建并全量爬取'
  return '加入已有任务并增量爬取'
}

function modalTitle(kind: PageActionKind): string {
  if (kind === 'temporary') return '加入临时任务'
  if (kind === 'quick-create') return '快速创建并全量爬取'
  return '加入已有任务并增量爬取'
}

function modeLabel(kind: PageActionKind): string {
  if (kind === 'temporary') return '临时爬取'
  if (kind === 'quick-create') return '全量爬取'
  return '增量爬取'
}

function focusable(dialog: HTMLElement): HTMLElement[] {
  return Array.from(
    dialog.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hidden && !element.closest('[hidden]'))
}

export function createPageActionUi(context: PageContext): PageActionUi {
  const host = document.createElement('div')
  host.id = 'media-forge-page-actions'
  const root = host.attachShadow({ mode: 'closed' })
  const style = document.createElement('style')
  style.textContent = STYLES
  root.append(style)

  const toolbar = document.createElement('div')
  toolbar.className = 'mf-toolbar'
  toolbar.setAttribute('role', 'toolbar')
  toolbar.setAttribute('aria-label', 'Media Forge 页面操作')
  const actions: PageActionKind[] = context.kind === 'detail'
    ? ['temporary']
    : ['quick-create', 'add-existing']
  for (const action of actions) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = `mf-action${action === 'add-existing' ? ' secondary' : ''}`
    button.dataset.action = action
    button.setAttribute('aria-label', actionLabel(action))
    button.innerHTML = `${ICON}<span>${actionLabel(action)}</span>`
    toolbar.append(button)
  }
  root.append(toolbar)
  document.body.append(host)

  let activeModal: PageActionModal | null = null
  let invokingButton: HTMLElement | null = null

  const closeModal = () => {
    root.querySelector('.mf-backdrop')?.remove()
    activeModal = null
    const restore = invokingButton
    invokingButton = null
    restore?.focus()
  }

  const openModal = (kind: PageActionKind, trigger: HTMLElement): PageActionModal => {
    closeModal()
    invokingButton = trigger
    const backdrop = document.createElement('div')
    backdrop.className = 'mf-backdrop'
    const dialog = document.createElement('section')
    dialog.className = 'mf-dialog'
    dialog.setAttribute('role', 'dialog')
    dialog.setAttribute('aria-modal', 'true')
    dialog.setAttribute('aria-labelledby', 'mf-page-action-title')

    const head = document.createElement('div')
    head.className = 'mf-head'
    const title = document.createElement('h2')
    title.id = 'mf-page-action-title'
    title.textContent = modalTitle(kind)
    const topClose = document.createElement('button')
    topClose.type = 'button'
    topClose.className = 'mf-close'
    topClose.dataset.action = 'close-modal'
    topClose.setAttribute('aria-label', '关闭弹窗')
    topClose.textContent = '关闭'
    topClose.addEventListener('click', closeModal)
    head.append(title, topClose)

    const contextBox = document.createElement('div')
    contextBox.className = 'mf-context'
    const contextName = document.createElement('strong')
    contextName.textContent = context.pageName
    const contextUrl = document.createElement('div')
    contextUrl.className = 'mf-url'
    contextUrl.textContent = context.normalizedUrl
    contextBox.append(contextName, contextUrl)

    const form = document.createElement('form')
    form.noValidate = true
    let taskSelect: HTMLSelectElement | null = null
    let nameInput: HTMLInputElement | null = null
    let nameError: HTMLElement | null = null

    if (kind === 'quick-create') {
      const field = document.createElement('div')
      field.className = 'mf-field'
      const label = document.createElement('label')
      label.htmlFor = 'mf-task-name'
      label.textContent = '任务名称'
      nameInput = document.createElement('input')
      nameInput.id = 'mf-task-name'
      nameInput.name = 'task-name'
      nameInput.value = context.pageName
      nameInput.maxLength = 200
      nameInput.autocomplete = 'off'
      nameInput.setAttribute('aria-describedby', 'mf-name-error')
      nameError = document.createElement('div')
      nameError.id = 'mf-name-error'
      nameError.className = 'mf-error'
      nameError.dataset.role = 'name-error'
      nameError.setAttribute('role', 'alert')
      field.append(label, nameInput, nameError)
      form.append(field)
    } else {
      const field = document.createElement('div')
      field.className = 'mf-field'
      const label = document.createElement('label')
      label.htmlFor = 'mf-task-id'
      label.textContent = '选择任务'
      taskSelect = document.createElement('select')
      taskSelect.id = 'mf-task-id'
      taskSelect.name = 'task-id'
      taskSelect.disabled = true
      const loading = document.createElement('option')
      loading.textContent = '正在加载任务…'
      loading.value = ''
      taskSelect.append(loading)
      field.append(label, taskSelect)
      form.append(field)
    }

    const modeField = document.createElement('div')
    modeField.className = 'mf-field'
    const modeHeading = document.createElement('span')
    modeHeading.textContent = '爬取模式'
    const mode = document.createElement('span')
    mode.className = 'mf-mode'
    mode.dataset.role = 'mode'
    mode.textContent = modeLabel(kind)
    modeField.append(modeHeading, mode)
    form.append(modeField)

    const error = document.createElement('div')
    error.className = 'mf-error'
    error.dataset.role = 'error'
    error.setAttribute('role', 'alert')
    error.setAttribute('aria-live', 'assertive')
    form.append(error)

    const buttons = document.createElement('div')
    buttons.className = 'mf-actions'
    const cancel = document.createElement('button')
    cancel.type = 'button'
    cancel.className = 'mf-cancel'
    cancel.textContent = '取消'
    cancel.addEventListener('click', closeModal)
    const submitButton = document.createElement('button')
    submitButton.type = 'submit'
    submitButton.className = 'mf-submit'
    submitButton.textContent = '确认并开始'
    buttons.append(cancel, submitButton)
    form.append(buttons)

    const result = document.createElement('div')
    result.className = 'mf-result'
    result.dataset.role = 'result'
    result.hidden = true
    const resultTitle = document.createElement('h3')
    const resultMessage = document.createElement('p')
    resultMessage.dataset.role = 'result-message'
    const resultTask = document.createElement('p')
    resultTask.dataset.role = 'result-task'
    const resultRun = document.createElement('p')
    resultRun.dataset.role = 'result-run'
    const resultActions = document.createElement('div')
    resultActions.className = 'mf-actions'
    const openRunButton = document.createElement('button')
    openRunButton.type = 'button'
    openRunButton.className = 'mf-open-run'
    openRunButton.dataset.action = 'open-run'
    openRunButton.textContent = '查看运行详情'
    const resultClose = document.createElement('button')
    resultClose.type = 'button'
    resultClose.className = 'mf-cancel'
    resultClose.textContent = '关闭'
    resultClose.addEventListener('click', closeModal)
    resultActions.append(openRunButton, resultClose)
    result.append(resultTitle, resultMessage, resultTask, resultRun, resultActions)

    dialog.append(head, contextBox, form, result)
    backdrop.append(dialog)
    root.append(backdrop)
    backdrop.addEventListener('click', (event) => {
      if (event.target === backdrop) closeModal()
    })
    dialog.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeModal()
        return
      }
      if (event.key !== 'Tab') return
      const controls = focusable(dialog)
      if (!controls.length) return
      const first = controls[0]
      const last = controls[controls.length - 1]
      if (event.shiftKey && root.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && root.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    })

    activeModal = {
      kind,
      dialog,
      form,
      taskSelect,
      nameInput,
      submitButton,
      error,
      nameError,
      result,
      openRunButton,
    }
    ;(nameInput ?? (taskSelect && !taskSelect.disabled ? taskSelect : topClose)).focus()
    return activeModal
  }

  const setTaskChoices = (modal: PageActionModal, choices: PageActionTaskChoice[]) => {
    if (!modal.taskSelect || activeModal !== modal) return
    modal.taskSelect.replaceChildren()
    const placeholder = document.createElement('option')
    placeholder.value = ''
    placeholder.textContent = choices.length ? '请选择任务' : '暂无可用任务'
    modal.taskSelect.append(placeholder)
    for (const choice of choices) {
      const option = document.createElement('option')
      option.value = choice.id
      option.textContent = choice.name
      modal.taskSelect.append(option)
    }
    modal.taskSelect.disabled = choices.length === 0
    if (!choices.length) {
      modal.error.textContent = '暂无已启用任务，请先在 Media Forge 中创建或启用任务。'
    }
  }

  const setBusy = (modal: PageActionModal, busy: boolean) => {
    modal.form.setAttribute('aria-busy', String(busy))
    modal.submitButton.disabled = busy
    modal.submitButton.textContent = busy ? '正在提交…' : '确认并开始'
  }

  const showError = (modal: PageActionModal, message: string, field?: 'name') => {
    if (field === 'name' && modal.nameError) {
      modal.nameError.textContent = message
      modal.nameInput?.setAttribute('aria-invalid', 'true')
      modal.nameInput?.focus()
      return
    }
    modal.error.textContent = message
    modal.error.tabIndex = -1
    modal.error.focus()
  }

  const showResult = (modal: PageActionModal, resultValue: PageActionRunResult) => {
    modal.form.hidden = true
    modal.result.hidden = false
    const title = modal.result.querySelector('h3')!
    title.textContent = resultValue.accepted ? '任务已创建' : '运行已创建，但启动失败'
    const message = modal.result.querySelector<HTMLElement>('[data-role="result-message"]')!
    if (!resultValue.accepted) {
      message.textContent = resultValue.runtime_error || '请前往 Media Forge 查看运行状态。'
    } else if (modal.kind === 'add-existing') {
      message.textContent = resultValue.url_added
        ? '已加入任务并开始增量爬取'
        : '该页面已在任务中，已开始增量爬取'
    } else {
      message.textContent = modal.kind === 'temporary' ? '已开始临时爬取' : '已开始全量爬取'
    }
    modal.result.querySelector<HTMLElement>('[data-role="result-task"]')!.textContent =
      `任务：${resultValue.task_name}`
    modal.result.querySelector<HTMLElement>('[data-role="result-run"]')!.textContent =
      `运行 ID：${resultValue.run_id}`
    modal.openRunButton.focus()
  }

  return {
    host,
    root,
    actionButton: (action) => root.querySelector<HTMLButtonElement>(`[data-action="${action}"]`),
    openModal,
    closeModal,
    setTaskChoices,
    setBusy,
    showError,
    showResult,
    destroy: () => {
      closeModal()
      host.remove()
    },
  }
}
