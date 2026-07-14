# Temporary Crawler Detail Task Design

## Goal

Add a `临时任务` action beside the existing `新增任务` action on the crawler task list. The action creates a temporary crawler run under an existing task, using one or more JavDB detail-page URLs, and reuses the normal crawler detail parsing and movie persistence path.

## Scope

This feature is limited to temporary detail-page crawling for existing crawler tasks.

- Supported input: JavDB movie detail URLs only, for example `https://javdb.com/v/...`.
- Unsupported input: search/list URLs, arbitrary websites, and raw movie codes.
- The feature does not create a new persistent `CrawlTask`.
- The feature does create a normal `CrawlRun` record attached to the selected existing task.
- The run remains visible in the existing run list and run detail pages.
- The existing detail ingestion path handles movie creation, magnet persistence, duplicate checks, skipped rows, logs, stop, and retry.

## Current Context

Crawler task list data is loaded through `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`, and task dictionary options already exist through `GET /api/crawler/tasks/dict`.

Regular task runs are created by `CrawlerTaskService.run_task()` and `CrawlerRunService.create_run()`. Runtime execution flows through `backend/app/modules/crawler/runtime/threaded.py`. List runs first collect detail tasks into `CrawlRunDetailTask`, then the detail phase calls `run_single_detail_task()`, `MoviePipeline`, and `upsert_movie_with_magnets()`.

This feature should reuse that detail phase by pre-creating `CrawlRunDetailTask` rows for the submitted detail URLs and marking the run as temporary so the worker skips list collection.

## Backend API

Add:

`POST /api/crawler/tasks/temp-run`

Request:

```json
{
  "task_id": "uuid-of-owned-task",
  "detail_urls": [
    "https://javdb.com/v/abc123",
    "https://javdb.com/v/def456"
  ]
}
```

Response:

- Standard success envelope with `CrawlRunRead` in `data`.
- The returned run has `status = "queued"`.
- The returned run has `task_id` set to the selected owner task.
- The returned run has `crawl_mode = "temporary"` or equivalent temporary marker available to backend and frontend.

Validation:

- `task_id` must belong to the current user.
- Disabled tasks cannot create temporary runs.
- `detail_urls` must contain 1 to 50 URLs after trimming.
- Every URL must be a JavDB detail-page URL.
- Duplicate URLs in one request are rejected.
- Validation errors identify the invalid row when possible, for example `第 2 条不是有效的 JavDB 详情页 URL`.

## Backend Data Flow

When the request is valid:

1. Load the selected task and verify ownership.
2. Create a queued `CrawlRun` attached to that task.
3. Mark the run as temporary with `crawl_mode = "temporary"` and `result = {"temporary": true, "detail_url_count": N}`.
4. Insert one `CrawlRunDetailTask` per submitted URL:
   - `status = "pending_crawl"`
   - `source_url = detail_url`
   - `source_name = "临时详情页"` or a stable URL-derived fallback
   - `source_url_name = "临时任务"`
   - `task_url = detail_url`
   - `task_final_url = detail_url`
   - `task_url_type = "temporary_detail"`
5. Enqueue the run through the existing crawler runtime queue.
6. Return the run snapshot.

Runtime execution:

- Temporary runs must skip the list phase even if no previous detail phase has started.
- Temporary runs go directly into `_run_detail_phase()` and process the pre-created pending detail rows.
- Detail processing must use the same `run_single_detail_task() -> MoviePipeline -> upsert_movie_with_magnets()` path as regular runs.
- If the movie already exists, behavior matches regular detail tasks: skip the detail row and append the selected task ID to the movie `source_task_ids`.

## Frontend UX

On the crawler task list:

- Add `临时任务` beside the existing `新增任务` action.
- Clicking `临时任务` opens a modal.
- Opening the modal requests the task dictionary from `/api/crawler/tasks/dict`.
- If loading the dictionary fails, the modal still opens. The task select shows the failure state, submit is disabled, and the modal provides a retry action.

Modal fields:

1. `归属任务`
   - Required.
   - Options are all tasks returned by the task dictionary.
   - If no tasks exist, submission is disabled and the UI tells the user to create a crawler task first.

2. `详情页 URL`
   - Dynamic list of input rows.
   - Starts with one row.
   - Each row accepts one JavDB detail-page URL.
   - Users can add rows.
   - Users can remove rows, but the list never goes below one row.
   - Local validation rejects empty values, duplicates, non-JavDB URLs, and more than 50 URLs.

Submit:

- Button text: `创建临时任务`.
- While submitting, disable the form and button.
- On success:
  - Show `临时任务已提交`.
  - Close the modal.
  - Reset the modal state.
  - Refresh crawler task runtime statuses.
- Do not automatically navigate to the run detail page. The user remains on the task list.

## Error Handling

Backend:

- Missing or unauthorized task: `404 Task not found`.
- Disabled task: `400 禁用任务不能执行`.
- Empty URL list: `400 至少需要 1 条详情页 URL`.
- Invalid URL: `400 第 N 条不是有效的 JavDB 详情页 URL`.
- Duplicate URL: `400 第 N 条详情页 URL 重复`.
- More than 50 URLs: `400 临时任务最多支持 50 条详情页 URL`.
- Runtime enqueue failure: `503 任务运行时不可用: ...`.

Frontend:

- Show local validation errors before calling the API.
- Show backend error messages when the API rejects the request.
- Keep the modal open when submission fails.
- Dictionary loading failure does not close the modal; submit remains disabled until the dictionary loads successfully.

## Design Alternatives Considered

### Recommended: temporary run with pre-created detail rows

This reuses `CrawlRun`, `CrawlRunDetailTask`, queueing, logs, stop/retry controls, and movie persistence. It avoids creating new task records and keeps temporary work inspectable in the run detail UI.

### Separate temporary-task model

This keeps the concept isolated but duplicates queueing, logging, run detail, and retry functionality. It adds unnecessary implementation and maintenance cost.

### Hidden normal `CrawlTask`

This uses the existing task creation API but pollutes the task list or requires hidden-task semantics. It also makes movie ownership ambiguous because the user explicitly wants the run to belong to a selected existing task.

## Testing

Backend tests:

- Successful `POST /api/crawler/tasks/temp-run` creates one queued run and one pending detail row per URL.
- The run is attached to the selected task.
- Runtime enqueue is called.
- Empty URL list fails.
- Non-JavDB detail URL fails.
- Duplicate URL fails.
- Disabled task fails.
- Another user's task fails.
- Temporary runs skip list collection and process pre-created detail rows.
- Existing movies are skipped and have the selected task ID appended to `source_task_ids`.

Frontend tests:

- Task list renders `临时任务` beside `新增任务`.
- Clicking `临时任务` opens the modal and requests the task dictionary.
- Dictionary loading failure keeps the modal open, disables submit, and shows retry.
- Dynamic URL rows support add/remove while preserving at least one row.
- Empty URL, duplicate URL, and non-JavDB URL validation block submit.
- Successful submit calls the new API, shows `临时任务已提交`, closes the modal, and refreshes runtime status.

## Non-Goals

- No support for raw movie codes.
- No support for non-JavDB URLs.
- No new temporary task management page.
- No automatic navigation to run detail after submit.
- No changes to movie storage push behavior.

## Self-Review

- Placeholder scan: no unfinished placeholders remain.
- Internal consistency: the design consistently treats a temporary task as a temporary run attached to an existing task.
- Scope check: the feature is bounded to one backend API, crawler runtime detail-only handling, and one task-list modal.
- Ambiguity check: URL type, duplicate handling, maximum count, navigation behavior, and disabled-task behavior are explicitly defined.
