# Crawler Run Task Summary Split Design

## Context

The crawler run detail page currently loads paginated detail tasks from
`GET /api/crawler/runs/{run_id}/tasks`. That response includes both the table
data (`rows`, `total`) and the top summary metrics (`summary`). This couples
table pagination and filters to statistics that are meant to describe the
whole run.

The current realtime hook also tries to update summary metrics from
`crawler.run.detail.updated` events by comparing changed tasks with the tasks
already visible in the current page. That works only when the changed detail
task is already loaded in the table. It is not reliable for newly created
detail tasks, tasks outside the current page, or tasks excluded by current
filters.

## Goals

- Split crawler run detail task list data and task summary statistics into two
  backend interfaces.
- Keep summary semantics unchanged: statistics cover all visible detail tasks
  for the run, not the current table filter or keyword.
- During active crawling, update summary metrics from EventSource events.
- Outside active crawling, or when realtime data is incomplete, load summary
  metrics from the database.
- Preserve the existing run detail table behavior, including pagination,
  filtering, keyword search, and retry actions.

## Non-Goals

- Do not change crawler run lifecycle behavior.
- Do not change task status labels or table layout.
- Do not add new product features outside the existing run detail page.
- Do not change the hidden incremental skip rule except to reuse it for the new
  summary endpoint and event payload.

## Backend Design

### Task List Endpoint

`GET /api/crawler/runs/{run_id}/tasks` becomes a pure paginated list endpoint.
It returns the existing paginated shape:

```json
{
  "rows": [],
  "total": 0
}
```

The endpoint keeps its current query parameters:

- `page`
- `size`
- `status`
- `keyword`

The `total` field remains the count after the current table filters are
applied. The response no longer includes `summary`.

### Task Summary Endpoint

Add `GET /api/crawler/runs/{run_id}/tasks/summary`.

The endpoint returns `RunTaskSummary` through the existing success envelope:

```json
{
  "data": {
    "total": 0,
    "pending_crawl": 0,
    "crawling": 0,
    "saved": 0,
    "skipped": 0,
    "crawl_failed": 0,
    "save_failed": 0,
    "completed": 0,
    "waiting": 0,
    "failed": 0
  }
}
```

The summary is computed from all visible detail tasks for the run. It does not
apply table `status` or `keyword` filters. For incremental runs, it keeps the
existing behavior that hides legacy `skipped` rows whose error is
`already_exists`.

The endpoint returns `404` when the run does not exist and uses the same
authentication requirements as the existing task list endpoint.

### Realtime Event Payload

Extend `publish_run_detail_updated` so each `crawler.run.detail.updated` event
includes a complete `summary` field:

```json
{
  "run_id": "run-id",
  "tasks": [],
  "refresh_tasks": true,
  "reason": "url_completed",
  "summary": {
    "total": 10,
    "pending_crawl": 2,
    "crawling": 1,
    "saved": 5,
    "skipped": 0,
    "crawl_failed": 1,
    "save_failed": 1,
    "completed": 5,
    "waiting": 3,
    "failed": 2
  }
}
```

The event summary uses the same helper as the summary endpoint. This makes
runtime summary updates independent of which table page the browser has loaded.

## Frontend Design

### API Layer

Update the crawler run API module:

- `getCrawlerRunTasks` returns only `PaginatedResponse<CrawlRunDetailTask>`.
- Add `getCrawlerRunTaskSummary(runId)`.
- Keep the existing `RunTaskSummary` type.
- Update `CrawlerRunDetailUpdatedPayload` to include optional `summary`.

### State Hook

`useRunDetail` owns separate fetch functions:

- `fetchTasks` loads the paginated table and updates `tasks` and `taskTotal`.
- `fetchTaskSummary` loads the summary endpoint and updates `taskSummary`.
- `resyncSnapshot` refreshes run, logs, tasks, and summary.

Initial page load fetches run, logs, tasks, and summary. Changing table filters
or pagination calls only `fetchTasks`, because summary is not filter-scoped.

### Realtime Hook

`useRunDetailRealtime` handles summary updates as follows:

- For `crawler.run.detail.updated` matching the current run, if
  `payload.summary` exists, replace `taskSummary` with that value.
- If `payload.refresh_tasks` is true, refresh the task list only.
- If an older event arrives without `summary`, call `fetchTaskSummary` to
  resync from the database rather than relying on current-page status
  transitions.
- When `crawler.run.updated` moves the run to `completed`, `failed`, or
  `stopped`, refresh run, logs, tasks, and summary from the backend.
- When `system.resync_required` is received, refresh the full snapshot,
  including summary.

The existing current-page incremental summary calculation can be removed. It is
less accurate than full summary payloads and creates different behavior based
on which page is loaded.

### Component Boundary

`RunTaskTable` keeps receiving `summary` as a prop and keeps the current visual
layout. The change is data ownership only: summary comes from either the
summary endpoint or EventSource payload, not from the task list endpoint.

## Error Handling

- Task list failures affect the table loading state only.
- Summary fetch failures leave the previous summary visible and can surface a
  lightweight message if the existing request layer already reports errors.
- Realtime events without summary are treated as incomplete and trigger a
  database summary refresh.
- Reconnect and resync flows use the existing `system.resync_required`
  mechanism.

## Tests

Backend tests:

- Add coverage for `GET /api/crawler/runs/{run_id}/tasks/summary`.
- Adjust task list endpoint tests so they no longer expect `summary` in the
  paginated response.
- Keep coverage that summary hides incremental `already_exists` skip rows.
- Add or update realtime event tests so `crawler.run.detail.updated` includes
  a complete `summary`.

Frontend tests:

- Mock `getCrawlerRunTaskSummary` in run detail tests.
- Verify initial page load fetches summary separately from tasks.
- Verify table pagination, status filter, and keyword search do not refetch or
  rewrite summary from the task list response.
- Verify a `crawler.run.detail.updated` event with `summary` updates the
  metric tiles.
- Verify terminal run updates and `system.resync_required` refresh summary from
  the endpoint.
- Verify old-style detail events without `summary` trigger a summary refetch.

## Acceptance Criteria

- `GET /api/crawler/runs/{run_id}/tasks` no longer returns `summary`.
- `GET /api/crawler/runs/{run_id}/tasks/summary` returns the existing
  `RunTaskSummary` shape.
- During an active run, summary tiles update from EventSource summary payloads.
- After run completion, stop, failure, reconnect, or resync, summary is loaded
  from the database endpoint.
- Existing list pagination, filters, retry actions, and logs continue to work.
- Backend and frontend tests cover the split interfaces and realtime summary
  behavior.
