# Crawler Task URL Subset Run Design

## Goal

Add a per-task `URL 爬取` action on the crawler task list. The action lets the
user select one or more URLs already configured on that task, choose
`增量爬取` or `全量爬取`, and submit a normal crawler run scoped to only those
selected task URLs.

## Current Context

The crawler task list currently supports:

- whole-task runs through `POST /api/crawler/tasks/{task_id}/run`;
- stop and restart for active/stopped runs;
- a global `临时任务` modal that accepts manually entered JavDB detail-page URLs
  and creates a `crawl_mode = "temporary"` detail-only run.

This feature is different from `临时任务`. It does not accept hand-entered detail
URLs. It uses the existing URL entries under a selected `CrawlTask`, such as
actor/list/search URLs, and runs the normal list-to-detail crawler flow for the
selected subset.

## Scope

In scope:

- Add a `URL 爬取` action to each crawler task card.
- Let the user multi-select existing URLs from that task.
- Let the user choose `incremental` or `full`.
- Create a normal `CrawlRun` attached to the task.
- Preserve current stop, restart, realtime status, run list, run detail, logs,
  duplicate handling, and movie persistence behavior.
- Keep frontend orchestration in a dedicated hook.

Out of scope:

- No support for manually entered URLs in this modal.
- No support for raw movie codes.
- No new persistent task type.
- No changes to the existing global `临时任务` detail-page workflow.
- No automatic navigation to the run detail page after submit.

## Backend API

Add:

```http
POST /api/crawler/tasks/{task_id}/url-run
```

Request:

```json
{
  "url_ids": [
    "uuid-of-task-url-1",
    "uuid-of-task-url-2"
  ],
  "crawl_mode": "incremental"
}
```

Response:

- Standard success envelope with `CrawlRunRead` in `data`.
- The returned run has `status = "queued"`.
- The returned run has `task_id` set to the selected task.
- The returned run has `crawl_mode = "incremental"` or `"full"`.

## Backend Validation

Validation rules:

- `task_id` must belong to the current user.
- Disabled tasks cannot create URL subset runs.
- `url_ids` must contain at least one item.
- Duplicate `url_ids` are rejected.
- Every `url_id` must belong to the selected task.
- `crawl_mode` must be `incremental` or `full`.

Recommended error messages:

- Missing or unauthorized task: `404 Task not found`.
- Disabled task: `400 禁用任务不能执行`.
- Empty URL selection: `400 至少选择 1 条任务 URL`.
- Duplicate URL selection: `400 任务 URL 不能重复选择`.
- URL from another task or missing URL: `400 选择的 URL 不属于该任务`.
- Invalid mode: existing Pydantic validation for `incremental | full`.
- Runtime enqueue failure: `503 任务运行时不可用: ...`.

## Backend Data Flow

Add a request model, for example:

```python
class CrawlTaskUrlRunCreate(BaseModel):
    url_ids: list[uuid.UUID] = Field(..., min_length=1)
    crawl_mode: Literal["incremental", "full"]
```

Add `CrawlerTaskService.create_url_subset_run(task_id, data, owner_id)`.

When valid:

1. Load the owned task with its URL entries.
2. Validate that the selected URL IDs are non-empty, unique, and all belong to
   the task.
3. Create a queued `CrawlRun` through a new runtime service method or an
   extended `create_run` method.
4. Keep `crawl_mode` as the selected `incremental` or `full`.
5. Store a run-scoped immutable selection snapshot in `run.result`:

```json
{
  "url_subset": true,
  "selected_task_url_ids": [
    "uuid-of-task-url-1",
    "uuid-of-task-url-2"
  ],
  "selected_task_url_count": 2
}
```

The task configuration itself is not modified.

## Runtime Behavior

The crawler worker should continue to process a normal `CrawlRun`. During task
adaptation, it should check whether the run has `result.url_subset = true`.

If yes:

1. Read `selected_task_url_ids` from `run.result`.
2. Filter the task's URL entries to only those IDs.
3. Preserve the original task URL order.
4. Build the scraper task from the filtered URLs.
5. Run the existing list collection and detail processing phases.

Run detail rows should continue to include the existing `task_url`,
`task_final_url`, `task_url_type`, and source URL name fields, so run detail
pages remain traceable to the selected task URL.

Restart behavior should reuse the same `run.result` snapshot. Restarting a URL
subset run must run the same selected URL subset again.

## Frontend UX

Add a `URL 爬取` button to each crawler task card.

Availability:

- Enabled only when the task runtime status is `idle`.
- Disabled when the task is skipped/disabled.
- Disabled when the task has no URL entries.
- Follows the same runtime availability rules as the current whole-task `爬取`
  action.

Clicking opens a modal:

- Title: `URL 爬取 - {任务名}`.
- Field 1: `选择 URL`
  - Ant Design `Select` with `mode="multiple"`.
  - Options come from `task.urls`.
  - Labels prefer `url_name`; fallback to the raw URL.
  - Options should expose useful secondary context such as `url_type`,
    `has_magnet`, and `has_chinese_sub`.
  - Options preserve task URL order.
  - User must select at least one URL.
- Field 2: `爬取模式`
  - Select with `增量爬取` and `全量爬取`.
  - Default value: `incremental`.
- Submit button: `开始爬取`.

On success:

- Show `URL 爬取任务已提交`.
- Close the modal.
- Reset modal state.
- Refresh crawler task runtime statuses.
- Stay on the task list.

On failure:

- Keep the modal open.
- Show the backend error message.

## Frontend Structure

Add a dedicated hook:

```text
frontend/src/pages/crawler/tasks/hooks/useTaskUrlRun.ts
```

Responsibilities:

- hold the currently selected task;
- open and close the modal;
- track submitting state;
- call `createTaskUrlRun(task.id, payload)`;
- show success/error messages;
- call `onSubmitted`, which should refresh runtime statuses.

The hook should expose a small interface:

```ts
{
  selectedTask: CrawlTask | null
  open: boolean
  submitting: boolean
  openTaskUrlRun: (task: CrawlTask) => void
  closeTaskUrlRun: () => void
  submitTaskUrlRun: (values: TaskUrlRunFormValues) => Promise<void>
}
```

Add a modal component:

```text
frontend/src/pages/crawler/tasks/components/TaskUrlRunModal.tsx
```

Responsibilities:

- render the form;
- validate URL selection and crawl mode;
- emit form values to the hook;
- not call APIs directly;
- not refresh the list directly.

Modify existing frontend files:

- `frontend/src/api/crawlTask/types.ts`
  - add `TaskUrlRunCreateParams`.
- `frontend/src/api/crawlTask/index.ts`
  - add `createTaskUrlRun(taskId, payload)`.
- `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
  - initialize `useTaskUrlRun({ onSubmitted: fetchRuntimeStatuses })`;
  - pass `openTaskUrlRun` to task cards;
  - render `TaskUrlRunModal`.
- `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`
  - add `onUrlRun(task)`;
  - render the per-card `URL 爬取` button.

## Design Alternatives Considered

### Recommended: URL IDs stored as a run snapshot

The request sends `url_ids`, and the run stores the selected IDs in
`run.result`. This keeps task configuration unchanged, preserves ownership
validation, makes restarts deterministic, and keeps the run visible in normal
run pages.

### Send full URL objects in the request

This would avoid a backend lookup for task URLs, but it duplicates task URL
data and weakens validation. It also makes it easier for the frontend to submit
URLs that are not part of the task.

### Reuse the existing temporary detail run endpoint

This conflicts with current temporary-run semantics. The existing endpoint is
for hand-entered JavDB detail-page URLs and skips list collection. The new
feature needs configured task URLs and the normal list-to-detail flow.

## Error Handling

Backend:

- Return `400` for empty, duplicate, or foreign URL selections.
- Return `400` for disabled tasks.
- Return `404` for missing or unauthorized tasks.
- Roll back and return `503` when runtime queueing fails.

Frontend:

- Validate empty URL selection before submit.
- Disable submit while submitting.
- Keep the modal open on API failure.
- Use backend error messages when available.
- Disable the button for tasks that cannot be run.

## Testing

Backend tests:

- `POST /api/crawler/tasks/{task_id}/url-run` creates a queued run with
  `crawl_mode = incremental`.
- Full mode is accepted.
- `run.result` contains `url_subset`, selected IDs, and selected count.
- Empty URL selection fails.
- Duplicate URL selection fails.
- URL ID from another task fails.
- Disabled task fails.
- Another user's task fails.
- Runtime task adapter filters to the selected URL IDs and preserves task URL
  order.
- Restart keeps the original selected URL subset.

Frontend tests:

- Task cards render `URL 爬取` for idle enabled tasks with URLs.
- `URL 爬取` is unavailable for disabled, active, or URL-less tasks.
- Clicking the button opens `TaskUrlRunModal` for that task.
- Modal renders URL options from `task.urls`.
- URL multi-select and mode select submit `{ url_ids, crawl_mode }`.
- Default mode is `incremental`.
- Empty URL selection blocks submit.
- Successful submit calls `createTaskUrlRun`, closes the modal, shows success,
  and refreshes runtime statuses.
- Failed submit keeps the modal open and shows the error.

## Acceptance Criteria

- Each eligible task card has a `URL 爬取` action.
- The modal selects one or more URLs from that task and a crawl mode.
- Submitting creates a normal queued crawler run attached to the task.
- Only the selected task URLs are crawled.
- Existing run list, run detail, stop, restart, logs, realtime status, duplicate
  handling, and movie persistence continue to work.
- Existing global `临时任务` behavior is unchanged.

## Self-Review

- Placeholder scan: no unfinished placeholders remain.
- Internal consistency: the design consistently treats this as a URL subset
  normal run, not a temporary detail run.
- Scope check: the feature is bounded to one backend API, runtime task URL
  filtering, one frontend hook, one modal, and task-card integration.
- Ambiguity check: URL source, selection rules, mode behavior, restart behavior,
  frontend hook ownership, and non-goals are explicit.
