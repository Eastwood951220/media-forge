import type { AgentEvent, AgentWorkItem } from '@/api/crawler/crawlerAgent/types'

/** One execution timeline: a work item plus its ordered events (ascending). */
export interface AgentWorkTimeline {
  workItem: AgentWorkItem | null
  events: AgentEvent[]
}

function eventSortKey(event: AgentEvent): string {
  return `${event.created_at}|${event.id}`
}

/**
 * Merge incoming events into the current list, replacing by id and keeping the
 * newest events first (created_at DESC, id DESC). Optionally cap the result.
 */
export function mergeAgentEvents(
  current: AgentEvent[],
  incoming: AgentEvent[] = [],
  options: { limit?: number } = {},
): AgentEvent[] {
  const byId = new Map<string, AgentEvent>()
  for (const event of current) {
    byId.set(event.id, event)
  }
  for (const event of incoming) {
    byId.set(event.id, event)
  }
  const merged = [...byId.values()].sort((a, b) =>
    eventSortKey(b).localeCompare(eventSortKey(a)),
  )
  return options.limit && merged.length > options.limit
    ? merged.slice(0, options.limit)
    : merged
}

/**
 * Group run-scoped events under their work items. Events without a work_item_id
 * are collected into a single unscoped timeline group. Each group's events are
 * sorted oldest first. Events from other runs are dropped.
 */
export function groupAgentEvents(
  workItems: AgentWorkItem[],
  events: AgentEvent[],
): AgentWorkTimeline[] {
  const runIds = new Set(workItems.map((item) => item.run_id))
  const byWorkItem = new Map<string, AgentEvent[]>()
  const unscoped: AgentEvent[] = []

  for (const event of events) {
    if (event.run_id && !runIds.has(event.run_id)) {
      continue
    }
    if (event.work_item_id) {
      const list = byWorkItem.get(event.work_item_id) ?? []
      list.push(event)
      byWorkItem.set(event.work_item_id, list)
    } else {
      unscoped.push(event)
    }
  }

  const timelines: AgentWorkTimeline[] = []
  for (const item of workItems) {
    const itemEvents = byWorkItem.get(item.id) ?? []
    if (itemEvents.length === 0 && unscoped.length === 0) {
      continue
    }
    timelines.push({
      workItem: item,
      events: [...itemEvents].sort((a, b) =>
        eventSortKey(a).localeCompare(eventSortKey(b)),
      ),
    })
  }
  if (unscoped.length > 0) {
    timelines.push({
      workItem: null,
      events: [...unscoped].sort((a, b) =>
        eventSortKey(a).localeCompare(eventSortKey(b)),
      ),
    })
  }
  return timelines
}
