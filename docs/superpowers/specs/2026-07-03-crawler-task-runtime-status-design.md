# Crawler Task Runtime Status Design

## Goal

Make the crawler task list reflect the current runtime state of every task, using run records as the source of truth.

The task list should:

- Show every task as idle, running, queued, or stopped.
- Update through EventSource when a task's latest run changes state.
- Allow run and delete actions only while a task is idle.
- Show stop for running or queued tasks.
- Show restart for stopped tasks.
- Replace the top task enablement statistics with runtime status statistics.

This design stays within the current crawler refactor scope. It does not add scheduled crawls, batch run-all behavior, a new queue model, or unrelated media operations.

## Current Context

Media Forge already has:

- Crawler task CRUD under `backend/app/modules/crawler/tasks/router.py`.
- Crawler run records and stop/restart APIs under `backend/app/modules/crawler/runs/router.py`.
- Runtime status changes published as realtime events from `backend/app/modules/crawler/runtime/service.py`.
- A user-scoped EventSource endpoint at `GET /api/events/stream`.
- A frontend EventSource client in `frontend/src/realtime/eventSourceClient.ts`.
- A task list page that currently displays `last_run_status` but does not use it as an action gate.

The existing task list stats endpoint reports enabled and disabled counts. The requested behavior needs counts by runtime state instead.

## Status Model

Do not add a runtime status column to `crawl_tasks`. The task runtime status is derived from the task's latest `crawl_runs` row.

Mapping:

| Latest run status | Task runtime status | Label |
| --- | --- | --- |
| `queued` | `queued` | 排队中 |
| `running` | `running` | 运行中 |
| `stopped` | `stopped` | 停止中 |
| `completed` | `idle` | 空闲中 |
| `failed` | `idle` | 空闲中 |
| no run | `idle` | 空闲中 |

The snapshot payload should retain `latest_run_status` separately from `runtime_status`. This keeps the task list simple while preserving the latest run result for future hints or diagnostics.

## Backend Design

Add a small service or repository helper that produces task runtime snapshots for the current owner.

Each task snapshot should include:

- `task_id`
- `runtime_status`
- `latest_run_id`
- `latest_run_status`
- `last_run_at`

Add `GET /api/crawler/tasks/statuses`.

Response shape:

```json
{
  "tasks": [
    {
      "task_id": "uuid",
      "runtime_status": "idle",
      "latest_run_id": "uuid",
      "latest_run_status": "completed",
      "last_run_at": "2026-07-03T00:00:00"
    }
  ],
  "stats": {
    "total": 10,
    "idle": 7,
    "running": 1,
    "queued": 1,
    "stopped": 1
  }
}
```

The existing `GET /api/crawler/tasks/stats` can either be updated to this runtime shape or left for compatibility while the frontend moves to the new endpoint. The implementation plan should prefer the least disruptive path after checking call sites.

## Realtime Events

Reuse the current user-scoped realtime stream, `GET /api/events/stream`.

Add a realtime event:

- Event name: `crawler.task.status.updated`
- Scope: `crawler.task`
- Resource id: task id
- Payload: one task runtime snapshot

Publish this event whenever a run changes status in a way that affects the task list:

- run created as `queued`
- worker marks run `running`
- stop marks run `stopped`
- worker completes run as `completed`
- worker fails run as `failed`
- restart moves a stopped run back to `queued`

The existing `crawler.run.updated` event remains unchanged for run list and run detail pages.

If the event queue overflows or the EventSource connection errors, the existing `system.resync_required` event remains the recovery path. The task list should refetch the task list and runtime status snapshot.

## Action Rules

Task list action availability:

| Runtime status | Run | Stop | Restart | Delete | Edit | Toggle enabled |
| --- | --- | --- | --- | --- | --- | --- |
| `idle` | yes, unless disabled | no | no | yes | yes | yes |
| `queued` | no | yes | no | no | no | no |
| `running` | no | yes | no | no | no | no |
| `stopped` | no | no | yes | no | no | no |

Disabled tasks remain unable to run while idle, but can still be edited, deleted, or enabled.

Stopping and restarting from the task list should call the existing run APIs with `latest_run_id`:

- `POST /api/crawler/runs/{run_id}/stop`
- `POST /api/crawler/runs/{run_id}/restart`

If a task has no `latest_run_id`, stop and restart controls must not render.

The delete endpoint should also reject deletion when the derived task runtime status is not `idle`. Frontend gating is not enough because callers can invoke the API directly.

## Frontend Design

Update the task list page to load two pieces of data:

1. `GET /api/crawler/tasks` for task cards.
2. `GET /api/crawler/tasks/statuses` for runtime state and stats.

Merge runtime snapshots by task id in the page layer and pass the merged data into `TaskListCards`.

Render the top stats as:

- 总数
- 空闲中
- 运行中
- 排队中
- 停止中

Render task status tags from `runtime_status`, not directly from `last_run_status`.

Subscribe to:

- `crawler.task.status.updated`: update the matching task's runtime snapshot and recompute stats, or refetch the status snapshot if recomputation would be ambiguous.
- `system.resync_required`: refetch task list and status snapshot.

After run, stop, restart, delete, edit, or enable-toggle operations, refresh the affected list data to avoid transient mismatch if an event arrives late.

The task list should not become a run detail surface. It only needs the latest run state and action controls.

## Error Handling

- If the status snapshot request fails, keep the task cards visible and show a clear error message. Disable run-sensitive actions until status is known.
- If stop or restart fails, show the backend error message and refresh the runtime status snapshot.
- If EventSource fails, rely on `system.resync_required` plus normal page refresh behavior.
- If a non-idle task is deleted through the API, return `400` with a message explaining that only idle tasks can be deleted.

## Testing

Backend tests should cover:

- Latest run status to task runtime status mapping.
- Runtime stats counts.
- `GET /api/crawler/tasks/statuses`.
- Delete rejection for `queued`, `running`, and `stopped` task runtime states.
- Publishing `crawler.task.status.updated` when run status changes.

Frontend tests should cover:

- Top runtime stats rendering.
- Task card status labels.
- Button availability for `idle`, `queued`, `running`, and `stopped`.
- Stop and restart using `latest_run_id`.
- Realtime `crawler.task.status.updated` updates a task card.
- `system.resync_required` refetches task and status snapshots.

## Non-Goals

- No new persisted task runtime status column.
- No scheduled crawler runs.
- No batch run-all control.
- No per-detail-task retry from the task list.
- No change to run detail status semantics.
