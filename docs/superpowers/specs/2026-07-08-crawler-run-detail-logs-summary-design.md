# Crawler Run Detail Logs and Summary Design

Date: 2026-07-08

## Goal

Improve the crawler run detail page so it shows useful detail-stage activity
while a run is active:

- Detail crawl events appear in the existing run log timeline.
- The child task list refreshes once after each URL list worker finishes.
- The top of the child task area shows full-run task counts: total, completed,
  waiting, skipped, failed, and related raw status counts.

This design is scoped to crawler run detail visibility. It does not add per-task
log storage or unrelated crawler behavior changes.

## Confirmed Decisions

- Detail logs should be written into the existing run-level log timeline.
- Do not add separate per-child-task logs for this change.
- Statistics must come from the backend and represent the whole run, not only
  the current table page.
- The child task list should refresh after each URL finishes creating its
  detail tasks.

## Current State

The backend stores run logs in JSONL files and exposes them through
`GET /api/crawler/runs/{run_id}/logs`. Realtime log appends use
`crawler.run.log.appended`.

The child task table uses `GET /api/crawler/runs/{run_id}/tasks`, which
currently returns paginated `rows` and `total`. The frontend merges
`crawler.run.detail.updated` events into the current page and calls
`fetchTasks()` only when the event cannot be safely merged into the visible page.

The run detail page has a run summary card and a child task table, but it does
not show full-run child task status counts above the table.

## Backend API

Extend `GET /api/crawler/runs/{run_id}/tasks` to return a `summary` object in
addition to the existing paginated rows:

```json
{
  "rows": [],
  "total": 50,
  "summary": {
    "total": 120,
    "pending_crawl": 30,
    "crawling": 4,
    "saved": 70,
    "skipped": 10,
    "crawl_failed": 5,
    "save_failed": 1,
    "completed": 80,
    "waiting": 34,
    "failed": 6
  }
}
```

Definitions:

- `total`: all child tasks for the run, independent of current filters and
  pagination.
- `pending_crawl`, `crawling`, `saved`, `skipped`, `crawl_failed`,
  `save_failed`: raw status counts for the whole run.
- `completed`: `saved + skipped`.
- `waiting`: `pending_crawl + crawling`.
- `failed`: `crawl_failed + save_failed`.

The existing response `total` remains the filtered total used by table
pagination. The new `summary.total` is the full-run count.

If a run has no child tasks, all summary counts are `0`.

## Detail Logs

The runtime should write detail-stage events to the existing run log stream with
`append_run_log_for_run`.

Required log events:

- Detail starts.
- Detail is skipped because the movie already exists.
- Detail crawl succeeds.
- Detail crawl fails.
- Movie save succeeds.
- Movie save fails.

Messages should stay short and readable in Chinese. Examples:

- `[任务A][URL: 演员A] 详情开始: code=AAA-001 name=...`
- `[任务A][URL: 演员A] 详情完成: code=AAA-001`
- `[任务A][URL: 演员A] 详情失败: code=AAA-001 error=...`
- `[任务A][URL: 演员A] 跳过已存在影片: code=AAA-001`

Each detail log should include context when available:

- `detail_id`
- `code`
- `source_url`
- `source_url_name`
- `detail_status`

Existing run log behavior and final log reloads remain unchanged.

## URL Completion Refresh

After one list URL finishes and its discovered child tasks have been persisted,
the backend should publish a realtime signal for the run detail page to refresh
the child task list.

Use the existing `crawler.run.detail.updated` event and extend its payload with:

```json
{
  "run_id": "...",
  "tasks": [],
  "refresh_tasks": true,
  "reason": "url_completed"
}
```

The frontend should call `fetchTasks()` when it receives a matching
`crawler.run.detail.updated` event with `refresh_tasks: true`. This refreshes
the current page, current filters, and the new summary object.

Normal detail row updates should continue to use the existing local merge path.
The refresh flag is only for events where a page-level refetch is more reliable
than local row merging.

## Frontend UI

`useRunDetail` should keep a `taskSummary` state updated by `fetchTasks()`.

`RunTaskTable` should render a compact summary strip above the filters/table.
It should show at least:

- 总数
- 完成数
- 等待数
- 跳过数
- 失败数

The UI may also show raw counts such as 已保存, 待爬取, 爬取失败, 保存失败 if
space allows, but the primary display should remain compact and scannable.

The counts must use backend `summary`; they must not be calculated from the
current table page.

When a run reaches `completed`, `failed`, or `stopped`, the realtime handler
should refresh both logs and tasks so the final table and summary converge even
if a URL completion refresh event was missed.

## Error Handling

If summary aggregation fails, the `/tasks` request should fail instead of
returning misleading partial counts.

If a realtime-triggered `fetchTasks()` fails, the frontend should keep the
current table and summary and wait for the next realtime event or manual page
reload. Existing request error behavior is sufficient.

If a detail log is missing optional context fields, the log should still be
written with the message and available context.

## Testing

Backend tests should cover:

- `/tasks` returns `summary`.
- `summary` is independent of status filter, keyword filter, page, and size.
- `summary` aggregates `pending_crawl`, `crawling`, `saved`, `skipped`,
  `crawl_failed`, and `save_failed` correctly.
- Detail start, skip, success, crawl failure, save success, and save failure
  are written to run logs with useful context.
- URL completion publishes `crawler.run.detail.updated` with
  `refresh_tasks: true` and `reason: "url_completed"`.

Frontend tests should cover:

- API types support the task summary response.
- The run detail page renders total, completed, waiting, skipped, and failed
  counts from backend summary.
- Receiving `crawler.run.detail.updated` with `refresh_tasks: true` calls
  `fetchTasks()`.
- Receiving a terminal `crawler.run.updated` event refreshes logs and tasks.

## Out of Scope

- Per-child-task log storage or a child-task log drawer.
- Changing crawler execution order or queue semantics.
- Changing movie persistence or storage task behavior.
- Replacing the existing run JSONL log system.
