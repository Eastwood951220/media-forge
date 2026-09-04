# Crawler Batch Task Creation And Queued Status Design

## Context

The crawler task list (`/crawler/tasks`) renders static task data from
`GET /api/crawler/tasks` and runtime state from the frontend
`useCrawlerRuntimeStore`. Runtime state is hydrated and updated by crawler
realtime events such as `crawler.task.status.updated`.

When a user starts another task while a crawler run is already active, the run
record page can show the new run as queued, but the task list card can remain
idle until the page is refreshed or a later realtime snapshot arrives. The task
list submit path currently invalidates run lists after a successful start, but
it does not immediately update the per-task runtime store.

Task creation currently supports one task per create form. The form can hold
multiple URL entries for one task and can auto-fetch missing URL names through
`POST /api/crawler/tasks/extract-name`, but users still need to manually create
each task, task name, and storage location. The requested batch flow should let
the user paste URLs only; save should fetch each URL's name and create one task
per URL using that name for both the task name and storage location.

## Goals

- Make a newly submitted crawler run appear as `排队中` in the task list
  immediately after the start request succeeds.
- Add a batch-create entry point from the crawler task list.
- Let users paste multiple URLs into a left-side drawer without manually
  fetching URL names.
- Save one independent crawler task per pasted URL.
- Use each fetched URL name as both the task name and storage location.
- Increase `storage_location` capacity so fetched names are not truncated.
- Return per-URL success and failure details so partial failures are clear and
  retryable.
- Reuse existing URL source/type detection and name extraction behavior where
  practical.

## Non-Goals

- Do not change crawler execution scheduling or queue semantics.
- Do not auto-start the created batch tasks after saving.
- Do not merge multiple pasted URLs into a single task.
- Do not remove or redesign the existing single-task create/edit route.
- Do not change storage provider folder planning beyond accepting longer
  `storage_location` values.
- Do not add a separate preview step before save.

## Queued Status Fix

After `runCrawlTask` or `createTaskUrlRun` succeeds, the frontend should
optimistically upsert a task runtime snapshot for that task:

- `task_id`: selected task id
- `runtime_status`: `queued`
- `latest_run_id`: run id returned by the start endpoint when available
- `state_updated_at`: current client timestamp
- `last_run_at`: current client timestamp

The existing realtime event stream remains the source of truth. Later
`crawler.task.status.updated` events and runtime snapshots can overwrite the
optimistic state with `running`, `idle`, `stopped`, or a corrected queued
snapshot.

The backend currently returns accepted run action data from run creation. If the
frontend type does not expose the run id clearly, add a typed response for task
run submissions instead of relying on `CrawlRun`.

## Batch Create API

Add `POST /api/crawler/tasks/batch` before the `/{task_id:uuid}` routes.

Request shape:

```json
{
  "urls": ["https://example.test/path"],
  "has_magnet": true,
  "has_chinese_sub": false,
  "sort_type": 0,
  "is_skip": false
}
```

Response shape:

```json
{
  "created": [
    {
      "url": "https://example.test/path",
      "task": {
        "id": "uuid",
        "name": "Fetched Name",
        "storage_location": "Fetched Name",
        "urls": []
      }
    }
  ],
  "failed": [
    {
      "url": "https://example.test/bad",
      "reason": "不支持的 URL 来源"
    }
  ],
  "created_count": 1,
  "failed_count": 1
}
```

The actual `task` payload should reuse the normal task serializer so frontend
types stay consistent.

## Backend Behavior

Normalize input URLs by trimming whitespace and dropping empty lines. Reject the
request if no usable URLs remain. Treat duplicate pasted URLs as per-item
failures after the first occurrence so one duplicate does not abort the entire
batch.

For each unique URL:

1. Determine source from the URL.
2. Detect URL type using the same rules as the frontend and existing crawler
   task utilities. JavBus detail URLs may default to `detail`.
3. Call the existing name extraction path with the normalized URL and detected
   type.
4. If the name is empty or extraction fails, record a failed item with the
   reason and continue processing the next URL.
5. Build a single `TaskUrlEntryCreate` with the requested default flags,
   detected `url_type`, and fetched `url_name`.
6. Use the fetched name as both `name` and `storage_location`.
7. If the task name conflicts with an existing task owned by the user or a
   previous successful item in the same batch, append a numeric suffix such as
   `Name (2)`, `Name (3)`, and use that same final value for
   `storage_location`.
8. Create the task through the existing repository/service path and include the
   serialized task in the created result.

Database work should allow partial success. A failure on one URL should roll
back only that item and then continue. Successfully created tasks should remain
created even when later items fail.

## Storage Location Length

Increase crawler task `storage_location` from 10 characters to 200 characters:

- `backend/app/models/crawl_task.py`: `String(200)`
- `backend/app/schemas/crawl_task.py`: `max_length=200`
- Alembic migration: alter `crawl_tasks.storage_location` to length 200
- Frontend type remains `string`

This keeps storage locations aligned with fetched names while avoiding silent
truncation. No existing value needs data migration because existing values
already fit inside the new limit.

## Frontend Behavior

Add a `批量新建` button to the task list toolbar near `新建任务`.

Clicking it opens a left-side Ant Design `Drawer`. The drawer contains:

- A multiline URL input where each non-empty line is one task URL.
- Shared default URL options:
  - has magnet
  - has Chinese subtitle
  - sort type
  - initial enabled/disabled state
- A save button with loading state.

The drawer intentionally does not include task name, storage location, or manual
`获取名称` controls. Save performs name extraction automatically on the backend.

On successful response:

- Show a summary message with created and failed counts.
- Invalidate crawler task list queries.
- Keep the drawer open if there are failed items.
- Replace the textarea contents with only failed URLs so the user can edit and
  retry them.
- Close the drawer when all items succeed.

## Error Handling

- Empty URL input: show a field validation error and do not submit.
- Duplicate URL lines: submit only the first occurrence and report later
  duplicates as failed results.
- Unsupported source/type: record a failed item with a readable reason.
- Name extraction blocked or failed: record a failed item with the backend
  reason.
- Task-name conflict: auto-suffix and continue.
- Unexpected backend error before any item is processed: show the request error
  and leave the drawer contents unchanged.

## Data Flow

```text
TaskListPage
  -> opens BatchTaskCreateDrawer
  -> POST /api/crawler/tasks/batch
  -> CrawlerTaskService.batch_create_tasks
  -> extract_task_name per URL
  -> CrawlTaskRepository.create_with_urls per success
  -> response with created and failed items
  -> invalidate task list queries
  -> close drawer or keep failed URLs for retry
```

Queued status flow:

```text
Task card run click
  -> POST run endpoint
  -> accepted run action response
  -> optimistic useCrawlerRuntimeStore.upsertTaskRuntime(queued)
  -> invalidate run list queries
  -> realtime task status event corrects final state
```

## Testing

Backend focused tests:

- Batch create succeeds for multiple valid URLs and creates one task per URL.
- Batch create uses fetched name for both task name and storage location.
- Existing task name conflicts receive numeric suffixes.
- Duplicate input URLs return failed duplicate items while the first creates.
- Name extraction failure returns a failed item without aborting other URLs.
- Empty batch request is rejected.
- `storage_location` accepts values longer than the old 10-character limit.

Frontend focused tests:

- Task list toolbar opens the batch-create drawer.
- Empty drawer input blocks submit.
- Submitting multiple URLs calls the batch API with normalized URLs and default
  options.
- All-success response closes the drawer and invalidates task lists.
- Partial failure response keeps the drawer open with only failed URLs.
- Starting a normal task upserts queued runtime state immediately.
- Starting a URL subset run upserts queued runtime state immediately.

Verification commands:

```bash
cd backend && python -m pytest tests/ -v
cd frontend && pnpm test -- src/pages/crawler/tasks
cd frontend && pnpm build
```

## Acceptance Criteria

- Starting a task while another crawler run is active immediately shows that
  task as `排队中` in the task list without a page refresh.
- Batch-create users can paste multiple URLs and save without manually fetching
  URL names.
- Each successful URL creates a separate crawler task.
- Created task names and storage locations come from extracted URL names.
- Names longer than 10 characters are accepted as storage locations.
- Partial failures are visible, readable, and retryable from the same drawer.
- Existing single-task create/edit behavior continues to work.
