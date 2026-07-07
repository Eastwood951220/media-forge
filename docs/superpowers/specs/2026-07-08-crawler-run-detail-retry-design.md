# Crawler Run Detail Retry Design

## Goal

Add retry controls to the crawler run detail page for child detail tasks that failed during crawling.

The feature should let the user retry failed detail tasks inside the original run record, without creating a new `crawl_runs` row. It supports:

- Retrying one failed child task from its table row.
- Selecting multiple failed child tasks and retrying them together.
- Retrying all child tasks whose status is `crawl_failed`.

This stays within the crawler refactor scope. It does not add scheduling, retry history, a new queue model, or retry support for persistence failures.

## Current Context

Media Forge already has:

- Run detail UI in `frontend/src/pages/crawler/runs/RunDetailPage.tsx`.
- Child task table UI in `frontend/src/pages/crawler/runs/components/RunTaskTable.tsx`.
- Run detail state and actions in `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`.
- Crawler run APIs under `backend/app/modules/crawler/runs/router.py`.
- Run restart and stop behavior in `backend/app/modules/crawler/runtime/service.py`.
- Detail-only restart execution in `backend/app/modules/crawler/runtime/executor.py`.
- Detail status updates published through `crawler.run.detail.updated`.

The existing run restart API is run-level and only works for stopped or failed runs. It can reset unfinished child tasks, but it does not provide row-level or selected failed-task retry from the run detail page.

## Status Scope

Only `crawl_failed` child tasks are retryable.

`save_failed` is deliberately excluded because that means the crawler already fetched item data and failed during persistence. Retrying those rows as crawler failures could hide database or data-normalization problems behind repeated network crawling.

Retry actions are only available when the parent run is in an ended state:

- `completed`
- `failed`
- `stopped`

Retry actions are not available while the run is `queued` or `running`, because a second worker mutating the same run and detail rows would create ambiguous state and progress updates.

## Backend API

Add a retry endpoint:

```text
POST /api/crawler/runs/{run_id}/tasks/retry
```

Request body:

```json
{
  "detail_ids": ["uuid-1", "uuid-2"],
  "retry_all": false
}
```

Rules:

- `retry_all=true` retries every `crawl_failed` child task in that run and ignores `detail_ids`.
- `retry_all=false` requires a non-empty `detail_ids` list.
- Every selected detail row must belong to the run.
- Every selected detail row must have status `crawl_failed`.
- If no retryable rows are found, return `400`.

The response returns the updated `CrawlRunRead` payload, matching the existing stop and restart endpoints.

## Backend Service

Add a service method such as:

```python
CrawlerRunService.retry_failed_details(run_id, detail_ids=None, retry_all=False)
```

The method should:

1. Load and validate the run.
2. Reject runs that are not in `completed`, `failed`, or `stopped`.
3. Select either all `crawl_failed` details for the run or the requested detail IDs.
4. Reject invalid selections before mutating any rows.
5. Reset selected detail rows for the next detail-only execution:
   - `status = "pending_crawl"`
   - `error = None`
   - `item_data = None`
   - `crawled_at = None`
   - `saved_at = None`
6. Reset the original run in place:
   - `status = "queued"`
   - `queued_at = now`
   - `started_at = None`
   - `finished_at = None`
   - `error = None`
   - `result = None`
7. Commit the database transaction.
8. Clear the old stop flag.
9. Enqueue the same run ID.
10. Ensure the crawler worker is started.
11. Publish run and detail update events.
12. Append a run log recording whether the user retried one row, selected rows, or all failed rows, plus the retry count.

The method must not create a new `crawl_runs` row.

## Executor Semantics

The existing detail-only restart branch should be adjusted so selected retry does not accidentally retry unrelated historical failures.

Currently the executor treats `pending_crawl`, `crawl_failed`, and `save_failed` as restartable detail statuses. For selected failed-task retry, the service only changes selected rows to `pending_crawl`; unselected `crawl_failed` rows remain `crawl_failed`.

The detail-only execution branch should use `pending_crawl` rows as the execution set. That keeps the selected retry scope exact:

- Single-row retry executes one selected row.
- Batch retry executes the selected rows.
- Retry-all first converts all `crawl_failed` rows to `pending_crawl`, so all failed crawler rows execute.
- Unselected historical `crawl_failed` rows do not run.

This change also keeps `save_failed` out of crawler retry.

## Frontend API

Add a client function:

```ts
retryCrawlerRunTasks(runId, {
  detail_ids?: string[]
  retry_all?: boolean
}): Promise<CrawlRun>
```

This function posts to `/api/crawler/runs/{runId}/tasks/retry`.

## Frontend Interaction

Update the run detail page and child task table:

- Pass the current run status into `RunTaskTable`.
- Add row selection to the table.
- Only `crawl_failed` rows are selectable.
- Only ended runs show or enable retry controls.
- Add a row action for `crawl_failed` rows: `重新爬取`.
- Add a batch action: `重新爬取选中项`.
- Add a global action: `重新爬取全部失败`.
- Confirm retry actions with `Modal.confirm`.
- After a successful retry:
  - Show a success message.
  - Clear selected row keys.
  - Call the existing `resyncSnapshot()` helper.
- If retry fails:
  - Show the backend error message.
  - Refresh the run snapshot to recover from stale UI state.

`useRunDetail` should own the retry handlers and retry loading state, similar to the existing stop and restart handlers.

Realtime handling can stay on the existing event stream:

- `crawler.run.updated` updates the parent run status.
- `crawler.run.detail.updated` updates child rows as they move from `pending_crawl` to `saved`, `crawl_failed`, or `save_failed`.

## Error Handling

Backend responses:

- Missing run: `404`.
- Run is `queued` or `running`: `400`, with a message that running tasks cannot retry failed child tasks.
- Empty selected retry request: `400`.
- Detail IDs that do not belong to the run: `400`.
- Selected detail rows that are not `crawl_failed`: `400`.
- No `crawl_failed` rows for retry-all: `400`.
- Redis or enqueue failure: keep the existing runtime failure behavior and surface it as `503` from the router.

Frontend behavior:

- Display backend error messages directly.
- Disable duplicate retry clicks while the retry request is in flight.
- Refresh the detail snapshot after success or failure.

## Testing

Backend tests should cover:

- Retrying one `crawl_failed` detail row updates that row to `pending_crawl` and queues the original run.
- Retrying selected failed rows updates only those rows.
- `retry_all=true` updates all `crawl_failed` rows in the run.
- Unselected `crawl_failed` rows are not executed by the detail-only executor.
- `save_failed`, `saved`, and `skipped` rows cannot be selected for crawler retry.
- Running and queued parent runs reject retry.
- Detail rows from another run reject retry.
- Runtime calls clear the stop flag and enqueue the existing run ID.
- Run and detail realtime events are published after mutation.

Frontend tests should cover:

- Retry controls only render or enable for ended runs.
- Only `crawl_failed` rows can be selected.
- Single-row retry sends one `detail_id`.
- Selected retry sends selected `detail_ids`.
- Retry-all sends `retry_all=true`.
- Successful retry clears selection and resyncs the snapshot.
- Failed retry displays the backend error and resyncs the snapshot.

## Non-Goals

- Do not create a new run record.
- Do not add retry history tables or per-attempt detail records.
- Do not retry `save_failed` rows.
- Do not change movie persistence behavior.
- Do not change task-list runtime status rules.
- Do not change list-stage crawling behavior.

## Acceptance Criteria

- A completed, failed, or stopped run detail page lets the user retry one, selected, or all `crawl_failed` child tasks.
- Queued or running runs do not allow failed-child retry.
- Retrying selected failures reuses the original run ID and moves the run back to `queued`.
- Only selected rows are retried unless the user chooses retry-all.
- Existing realtime updates keep the run detail page in sync while the retry is executing.
- Existing run-level restart behavior remains available and semantically separate.
