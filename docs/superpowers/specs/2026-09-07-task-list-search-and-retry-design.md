# Task List Search and Retry Design

## Context

The requested changes cover existing Media Forge crawler, movie, and storage task flows:

- Crawler task list needs one search box that matches task name, URL name, and URL.
- Movie list pagination must return to page 1 when filters change.
- Storage retry should be available only from the storage subtask list, not from the storage main task list.
- Storage main task progress should avoid showing a full red progress bar when a completed task has a small number of failed subtasks.
- Crawler task cards should show whether the latest completed run had failed items.

The attached screenshots are examples of current behavior only. They do not provide executable instructions.

## Goals

1. Add crawler task list keyword search across task name, URL name, and URL in one input.
2. Reset crawler task list pagination to page 1 when the crawler task keyword or tag filter changes.
3. Reset movie list pagination to page 1 whenever effective movie filters change.
4. Add retry actions only in the storage subtask list for failed subtasks.
5. Keep storage main task list actions limited to detail, stop, and delete/restart where currently appropriate, with no retry button.
6. Show partial-failure information in crawler task cards for the latest run.
7. Make storage main task list progress visually balanced when failures are partial.

## Non-Goals

- Do not add storage main task retry actions in the main task list.
- Do not change crawler execution semantics or storage provider behavior beyond re-queuing failed storage subtasks.
- Do not add new navigation routes.
- Do not delete or recreate successful storage subtasks.

## Design

### Crawler Task Search

Extend `CrawlTaskRepository` keyword filtering so `keyword` matches:

- `CrawlTask.name`
- `CrawlTaskUrl.url_name`
- `CrawlTaskUrl.url`

Use an `EXISTS` subquery or relationship `.any(...)` predicate so pagination and counts remain task-based and do not duplicate rows when one task has multiple matching URLs. Keep the existing tag filter behavior and combine it with keyword filtering as an AND.

On the frontend, wire `useTaskListQueryStore.keyword` into `useTaskListData` and render a search input in `TaskListCards` toolbar. The search box submits through the existing `GET /api/crawler/tasks` `keyword` parameter.

When keyword or tag names change, reset the crawler task page to 1 and clear selected task IDs.

### Crawler Latest Run Failure Summary

Extend the crawler task list response with latest-run summary fields derived from the newest `CrawlRun` per task:

- `last_run_status`
- `last_run_at`
- `last_run_total`
- `last_run_failed`

Prefer `CrawlRun.result` summary values when available. Fall back to `CrawlRun.total_failed`-style fields only if present in the model; otherwise leave totals as 0 or null. The UI should show a compact line in each task card such as:

- `上次运行：失败 0 / 总 63` for clean completed runs
- `上次运行：失败 3 / 总 50` with warning styling for partial failures
- `上次运行：失败` for failed whole-run status when detailed counts are unavailable

This summary is informational. The card's runtime status tag continues to come from the realtime runtime snapshot.

### Movie List Pagination Reset

In `useMovieList`, track the effective filter params identity. When it changes after initial load:

- clear selected rows
- set page to `DEFAULT_MOVIE_PAGE`

This makes any filter change reset pagination, including search text, task filter, people/tags filters, date filters, rating filters, and storage status. Sorting already resets page and should keep doing so.

### Storage Subtask Retry

Add a backend endpoint for retrying one failed storage subtask:

`POST /api/storage/tasks/subtasks/{subtask_id}/retry`

The endpoint must:

- verify the parent main task belongs to the current user
- allow only failed subtasks
- reject retry while the parent main task is `queued`, `running`, or `stopping`
- reset the selected subtask to `queued`
- reset retry-sensitive fields such as `step`, `error_message`, `started_at`, `finished_at`, current magnet fields, attempts, and file result arrays
- set the parent main task to `queued`
- recompute parent counts
- enqueue the parent task and start the storage worker
- publish normal storage task update events

The storage worker already processes queued subtasks for a queued main task, so this should reuse the existing worker path instead of creating a new task.

Frontend changes:

- Add `retryStorageSubTask(subtaskId)` API wrapper.
- Add `onRetry` to `StorageSubTaskTable`.
- Show a small retry action only on rows with `status === "failed"`.
- After retry, refresh both the main task summary and subtask list.

### Storage Main Progress Styling

Keep showing progress as completed work divided by total subtasks. Change list progress styling so `failed_count > 0` no longer automatically makes the entire progress bar `exception`.

Recommended UI:

- Use normal progress color for running or mixed completed tasks.
- Keep failed count visible in the meta row.
- Add a compact warning tag or warning-colored failed count when `failed_count > 0`.
- Use exception/red only when the main task status itself is `failed` and all work failed or no success/skipped work exists.

This keeps partial failures visible without making mostly successful completed tasks look entirely broken.

## Error Handling

- Crawler task search with empty or whitespace keyword should behave like no keyword.
- Crawler task URL search should remain case-insensitive.
- Storage subtask retry should return 404 for missing or unauthorized subtasks through parent ownership checks.
- Storage subtask retry should return 400 for non-failed subtasks or active parent tasks.
- Frontend retry failures can rely on the existing request interceptor and should clear loading state.

## Testing

Backend:

- Add or update crawler task repository/API tests covering keyword matches by task name, URL name, and URL, with counts matching rows.
- Add storage task retry service/router tests covering success, non-failed rejection, unauthorized rejection, and active-parent rejection.

Frontend:

- Update crawler task list tests to verify keyword is sent and page resets when the search changes.
- Update movie list hook tests to verify page returns to 1 when filter params change.
- Update storage task page tests to verify retry appears only in subtask rows with failed status and calls the subtask retry API.
- Update storage progress rendering tests or component assertions so partial failures do not render exception progress on completed mixed-success tasks.

Verification commands:

- `cd backend && python -m pytest tests/ -v` for backend changes when practical.
- `cd frontend && pnpm test -- <focused test files>` for focused UI hook/component coverage.
- `cd frontend && pnpm build` for frontend type and build verification.
