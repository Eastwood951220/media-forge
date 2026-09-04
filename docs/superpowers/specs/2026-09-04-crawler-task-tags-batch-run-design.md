# Crawler Task Tags And Batch Run Design

## Context

Crawler tasks currently have task-level metadata (`name`, `storage_location`,
`is_skip`) and one or more URL entries. The task create/edit page can create or
update one task, the task list can filter only by pagination parameters, and
each task card can start one run at a time.

Users need a reusable task-tag system:

- New and edited tasks can have multiple type tags.
- Users can choose existing tags or create custom tags while editing.
- The task list can filter by selected tags.
- Filtering by multiple tags uses all-match semantics.
- Users can select multiple tasks and start crawler runs for the selected set
  after choosing incremental or full mode.

## Goals

- Add persistent, per-user crawler task tags.
- Let each crawler task have multiple tags.
- Let task creation, task editing, and batch task creation bind tags by name.
- Reuse existing tags in selects and create missing custom tags during save.
- Return tags in task list and task detail responses.
- Filter the task list by selected tag names using all-match semantics.
- Add task-list selection and batch run submission for selected tasks.
- Prompt for crawl mode before batch run submission.
- Return per-task success and failure details for batch run.
- Optimistically mark successfully accepted batch-run tasks as `queued` in the
  frontend runtime store.
- Save database-change SQL files under the repository root `sql/` directory.

## Non-Goals

- Do not add global tag management screens.
- Do not add tag colors in this iteration.
- Do not support tag deletion or renaming in this iteration.
- Do not change crawler scheduling, queue capacity, or run execution semantics.
- Do not auto-select all filtered tasks across all pages; selection applies to
  currently loaded task cards.
- Do not merge selected tasks into one crawler run. Each selected task creates
  its own run.

## Data Model

Use normalized tables instead of storing tags as JSON on `crawl_tasks`.

`crawl_task_tags`:

- `id`: UUID primary key
- `owner_id`: owning user
- `name`: tag name, max length 50
- timestamps
- unique constraint on `(owner_id, name)`
- index on `(owner_id, name)`

`crawl_task_tag_links`:

- `task_id`: foreign key to `crawl_tasks.id`, cascade delete
- `tag_id`: foreign key to `crawl_task_tags.id`, cascade delete
- unique constraint on `(task_id, tag_id)`
- indexes on `task_id` and `tag_id`

Tag names are normalized by trimming whitespace and dropping empty values.
Within one task, duplicate names are collapsed. Tags are user-scoped; two users
may use the same tag name independently.

## API Design

### Tag Dictionary

Add `GET /api/crawler/tasks/tags`.

Response:

```json
[
  { "id": "uuid", "name": "VR" },
  { "id": "uuid", "name": "演员" }
]
```

The endpoint returns tags owned by the current user ordered by name.

### Task Create, Update, Detail, And List

Extend task payloads:

```json
{
  "name": "Task",
  "storage_location": "Task",
  "tag_names": ["VR", "演员"],
  "urls": []
}
```

Extend task responses:

```json
{
  "id": "uuid",
  "name": "Task",
  "storage_location": "Task",
  "tags": [
    { "id": "uuid", "name": "VR" }
  ],
  "urls": []
}
```

Create and update accept `tag_names`. Save behavior:

- Existing tag names are reused.
- Missing tag names are created for the current user.
- Task tag links are replaced by the normalized requested set.
- Omitting `tag_names` on update leaves tags unchanged.
- Passing `tag_names: []` removes all tags from the task.

Extend `GET /api/crawler/tasks` with repeated `tag_names` query params:

```text
GET /api/crawler/tasks?page=1&size=20&tag_names=VR&tag_names=演员
```

Filtering is all-match: a task is returned only if it has every selected tag.
The filter applies before pagination and total counting.

### Batch Task Creation

Extend `POST /api/crawler/tasks/batch` with `tag_names`.

All successfully created tasks receive the same normalized tag set. Existing
partial-success behavior remains unchanged.

### Batch Run

Add `POST /api/crawler/tasks/batch-run`.

Request:

```json
{
  "task_ids": ["uuid"],
  "crawl_mode": "incremental"
}
```

Response:

```json
{
  "accepted": [
    { "task_id": "uuid", "run_id": "uuid" }
  ],
  "failed": [
    { "task_id": "uuid", "reason": "禁用任务不能执行" }
  ],
  "accepted_count": 1,
  "failed_count": 1
}
```

Backend behavior:

- Reject an empty `task_ids` list.
- Collapse duplicate task ids.
- For each task, verify ownership.
- Reject disabled tasks per item.
- Create one run per accepted task with the selected crawl mode.
- Return failures per task without aborting the whole request.

## Frontend Design

### Task Form

Add a tags field near task name and storage location.

Use Ant Design `Select` with `mode="tags"`:

- Options come from `GET /api/crawler/tasks/tags`.
- Existing tags are selectable.
- New custom tag text can be entered directly.
- Values are `tag_names`.
- Form submit sends normalized tag names.
- Edit mode loads existing task tags.

### Batch Task Create Drawer

Add an optional tags field to the existing batch create drawer.

All URLs created from that drawer receive the selected/new custom tags. The
drawer continues to avoid manual task-name and storage-location inputs.

### Task List Filtering

Add a compact multi-tag filter in the task-list toolbar.

Behavior:

- Options come from the tag dictionary endpoint.
- Multiple selected tags use all-match filtering.
- Changing filters resets pagination to page 1.
- Query keys include selected `tag_names` so TanStack Query caches correctly.
- Clearing filters shows all tasks.

### Task Card Display

Show task tags in each card, near the existing metadata area.

Suggested display:

- Render up to three tags inline.
- If more exist, show a `+N` popover with all tags.
- Tasks without tags show `-`.

### Selection And Batch Run

Task list cards support selection:

- Add a checkbox on each card.
- Selection is disabled when runtime snapshot is not ready.
- Selection is disabled for skipped tasks and non-idle tasks.
- Keep selected ids in `TaskListPage`.
- Clear selections when page, filter, or page size changes.

Toolbar behavior:

- Show selected count.
- Enable `批量爬取` only when at least one selectable task is selected.
- Clicking `批量爬取` opens a modal to choose `增量爬取` or `全量爬取`.
- Confirm submits `POST /api/crawler/tasks/batch-run`.
- For accepted results, upsert queued runtime snapshots with returned run ids.
- Show a result summary. If failures exist, include readable failure reasons.
- Invalidate crawler run lists after submission.

## Data Flow

Task tag save:

```text
TaskFormPage / BatchTaskCreateDrawer
  -> tag_names
  -> crawler task API
  -> normalize names
  -> get-or-create tags for owner
  -> replace task tag links
  -> serialize task with tags
```

Task list filter:

```text
TaskListPage selected tag names
  -> GET /api/crawler/tasks?tag_names=A&tag_names=B
  -> repository filters tasks having both A and B
  -> paginated rows with tags
```

Batch run:

```text
selected task ids
  -> mode confirm modal
  -> POST /api/crawler/tasks/batch-run
  -> create one run per accepted task
  -> frontend marks accepted tasks queued
  -> realtime events correct final runtime state
```

## Error Handling

- Empty tag names are ignored.
- Duplicate tag names are collapsed.
- Too-long tag names are rejected with validation errors.
- Unknown filter tag names return zero rows.
- Empty batch-run selection is rejected.
- Disabled, missing, foreign-owner, running, or otherwise invalid tasks are
  reported as per-item failures in batch-run responses.
- If all selected tasks fail, the request still returns a structured result so
  the frontend can show every reason.

## Database And SQL Files

Add Alembic migration for both tag tables and indexes.

Also save equivalent SQL under the root `sql/` folder, for example:

```text
sql/20260904_add_crawler_task_tags.sql
```

The SQL file should create:

- `crawl_task_tags`
- `crawl_task_tag_links`
- unique constraints
- supporting indexes

## Testing

Backend tests:

- Create task with new tags creates tags and links.
- Create task with existing tags reuses them.
- Update task replaces tags.
- Update task with omitted `tag_names` keeps existing tags.
- List and detail responses include tags.
- Tag dictionary returns current user's tags only.
- Task list all-match filtering returns only tasks with every selected tag.
- Batch task creation applies tags to each created task.
- Batch run creates one run per accepted selected task.
- Batch run returns per-task failures for skipped or missing tasks.

Frontend tests:

- Task form loads tag options and submits custom tag names.
- Edit form displays existing task tags.
- Batch create drawer submits selected/custom tag names.
- Task list filter calls list API with selected `tag_names` and resets page.
- Task cards render tags and overflow popover.
- Card checkbox selection tracks selected task ids.
- Batch run modal chooses incremental/full and calls the batch-run API.
- Accepted batch-run tasks are optimistically marked `queued`.
- Failed batch-run items show a readable result summary.

Verification commands:

```bash
cd backend && python -m pytest tests/test_crawler_tasks_api.py tests/test_crawl_tasks_api.py tests/test_crawler_task_url_subset_run.py -v
cd frontend && pnpm test -- src/pages/crawler/tasks
cd frontend && pnpm build
```

## Acceptance Criteria

- Users can add multiple tags when creating or editing a crawler task.
- Users can choose existing tags or type new custom tags.
- A task can have multiple tags.
- Task list cards show assigned tags.
- The task list can filter by multiple tags using all-match semantics.
- Users can select multiple idle enabled tasks on the current page.
- Users can batch start selected tasks after choosing incremental or full mode.
- Batch-run successes immediately show as queued in the task list.
- Batch-run failures are visible per task.
- Database table changes are represented in Alembic and in a root `sql/` file.
