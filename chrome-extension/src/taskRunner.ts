import {
  type AgentTaskEventPayload,
  type AgentTaskFailedPayload,
  type AgentTerminalMessage,
  type AssignedTask,
  type TaskRunnerDeps,
} from './protocol'

export async function waitForTabComplete(
  tabId: number,
  deadlineAt: number,
  deps: Pick<TaskRunnerDeps, 'waitForComplete' | 'now'>,
): Promise<void> {
  const remaining = deadlineAt - deps.now()
  if (remaining <= 0) {
    throw new Error('deadline_exceeded')
  }
  await deps.waitForComplete(tabId, deadlineAt)
}

function makeEvent(
  task: AssignedTask,
  phase: string,
  code: string,
  message: string,
  level: AgentTaskEventPayload['level'] = 'info',
  details: Record<string, unknown> = {},
): AgentTaskEventPayload {
  return {
    agent_task_id: task.agent_task_id,
    attempt: task.attempt,
    phase,
    level,
    code,
    message,
    details,
  }
}

function failedMessage(
  task: AssignedTask,
  code: AgentTaskFailedPayload['code'],
  message: string,
): AgentTerminalMessage {
  return {
    id: `failed_${task.agent_task_id}`,
    type: 'agent.task_failed',
    payload: {
      agent_task_id: task.agent_task_id,
      attempt: task.attempt,
      phase: 'task.execution',
      code,
      message,
    },
  }
}

function isDetailSnapshotReady(snapshot: { page_kind: string; fragments: Record<string, string> }): boolean {
  if (snapshot.page_kind !== 'detail') return true
  const detail = String(snapshot.fragments.detail || '')
  const title = String(snapshot.fragments.title || '')
  return Boolean(
    detail.trim()
      && /video-detail/.test(detail)
      && (/(current-title|<strong)/.test(detail) || title.trim()),
  )
}

export async function runAssignedTask(
  task: AssignedTask,
  deps: TaskRunnerDeps,
): Promise<AgentTerminalMessage> {
  const deadlineAt = Date.parse(task.execution_deadline_at)
  if (Number.isNaN(deadlineAt)) {
    return failedMessage(task, 'agent_page_load_failed', 'invalid_execution_deadline')
  }

  deps.emitEvent(makeEvent(task, 'tab.opening', 'tab_opening', '正在打开浏览器标签页'))
  let tabId: number | undefined
  try {
    const tab = await deps.createTab(task.url)
    tabId = tab.id
    if (tabId == null) {
      throw new Error('tab_create_failed')
    }
  } catch {
    return failedMessage(task, 'agent_tab_create_failed', '无法创建浏览器标签页')
  }

  try {
    deps.emitEvent(makeEvent(task, 'tab.opened', 'tab_opened', '浏览器标签页已打开', 'info', { tab_id: tabId }))

    deps.emitEvent(makeEvent(task, 'page.loading', 'page_loading', '等待页面加载', 'info', { tab_id: tabId }))
    await waitForTabComplete(tabId, deadlineAt, deps)
    deps.emitEvent(makeEvent(task, 'page.loaded', 'page_loaded', '页面加载完成', 'info', { tab_id: tabId }))

    deps.emitEvent(makeEvent(task, 'snapshot.collecting', 'snapshot_collecting', '正在采集页面', 'info', { tab_id: tabId }))
    const { snapshot } = await deps.collectSnapshot(tabId)
    if (!snapshot) {
      throw new Error('snapshot_collection_failed')
    }
    if (task.page_kind === 'detail' && !isDetailSnapshotReady(snapshot)) {
      throw new Error('detail_dom_not_ready')
    }
    deps.emitEvent(makeEvent(task, 'snapshot.collected', 'snapshot_collected', '页面采集完成', 'info', { tab_id: tabId }))

    deps.emitEvent(makeEvent(task, 'snapshot.uploading', 'snapshot_uploading', '正在上传快照', 'info', { tab_id: tabId }))
    const cookies = await deps.collectCookies()
    return {
      id: `snapshot_${task.agent_task_id}`,
      type: 'agent.page_snapshot',
      payload: {
        agent_task_id: task.agent_task_id,
        attempt: task.attempt,
        snapshot,
        cookies,
      },
    }
  } catch (error) {
    const code = error instanceof Error && error.message === 'deadline_exceeded'
      ? 'agent_page_load_failed'
      : error instanceof Error && error.message === 'detail_dom_not_ready'
        ? 'agent_detail_dom_not_ready'
      : 'agent_snapshot_failed'
    const message = error instanceof Error ? error.message : 'unknown_error'
    return failedMessage(task, code, message)
  } finally {
    await deps.removeTab(tabId)
  }
}
