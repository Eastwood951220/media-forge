# Fast List Page/Size Count Split Design

## Context

The crawler task list, crawler run list, and storage task list still feel slow after the first interface-speed pass. The current implementation has three performance patterns that should be corrected together:

- The crawler task frontend still calls `GET /api/crawler/tasks` without pagination and separately calls `/statuses` for all tasks.
- The crawler run list and storage task list are paginated, but their list endpoints synchronously calculate an exact `count()` before returning rows.
- SQLAlchemy relationships such as `CrawlRun.detail_tasks` and `StorageMainTask.subtasks` use `selectin`, so list queries can load large child collections that the list UI does not display.

The desired behavior is now explicit: prioritize showing list rows first, split realtime totals into separate endpoints, and standardize all list pagination parameters as `page` and `size`. No legacy `skip` or `limit` compatibility is required for these three list surfaces.

## Goals

- Make the three list endpoints return the current page quickly without synchronous exact totals.
- Standardize frontend and backend list parameters on `page` and `size`.
- Split total counts into dedicated endpoints that load after the rows.
- Keep existing visible actions, columns, filters, and realtime updates.
- Avoid loading large related collections in list endpoints.
- Preserve authorization and owner scoping.

## Non-Goals

- No cursor pagination in this phase.
- No UI redesign beyond pagination behavior needed for `has_more` and delayed totals.
- No compatibility layer for `skip` or `limit` on the optimized list paths.
- No changes to detail pages except where shared API types require mechanical updates.

## API Contract

### List Response

The optimized list endpoints return only page rows and page navigation metadata:

```json
{
  "rows": [],
  "page": 1,
  "size": 20,
  "has_more": true
}
```

The backend determines `has_more` by fetching `size + 1` rows and trimming the extra row before serialization. The list endpoint must not run a synchronous exact `count()`.

### Count Response

Each list gets a dedicated count endpoint:

- `GET /api/crawler/tasks/count?keyword=...`
- `GET /api/crawler/runs/count?task_id=...&status=...`
- `GET /api/storage/tasks/count?status=...&keyword=...`

Each count endpoint returns the exact total for the same filters as its list endpoint. The frontend treats this as secondary data and must not block row rendering on it.

### Pagination Parameters

All three list endpoints use:

- `page`: 1-based page number.
- `size`: page size.

The frontend API wrappers, query keys, hooks, and pages should remove `skip` and `limit` for these surfaces.

## Backend Design

### Crawler Task List

`GET /api/crawler/tasks` changes from optional `skip`/`limit` to required-default `page`/`size`.

Repository behavior:

- Filter by `owner_id`.
- Apply optional `keyword`.
- Order by `created_at desc`.
- Fetch `size + 1` rows with `offset=(page - 1) * size`.
- Return `rows` and `has_more`.

Runtime status behavior:

- The list response should include or derive runtime information only for the visible page task IDs.
- The all-task `/statuses` path should not be used by the list page for initial rendering.
- Aggregate runtime stats remain available through a separate stats/count-style endpoint and load independently.

The task list currently displays URL names in cards, so the list path may continue loading task URLs for visible rows only. It should not load data for tasks outside the current page.

### Crawler Run List

`GET /api/crawler/runs` changes to `page`/`size` and no longer calls `query.count()`.

Query behavior:

- Join or otherwise scope through `CrawlTask` so only runs belonging to the current user are visible.
- Apply optional `task_id` and `status` filters.
- Order by `CrawlRun.created_at desc`.
- Fetch `size + 1` rows and return `has_more`.
- Prevent `detail_tasks` from loading in the list response, for example with `noload(CrawlRun.detail_tasks)` or a list-specific selected-column query.

`GET /api/crawler/runs/count` performs the same owner and filter conditions, then returns the exact total.

### Storage Task List

`GET /api/storage/tasks` changes to `page`/`size` and no longer calculates total inline.

Query behavior:

- Filter by `created_by == current_user.id`.
- Apply optional `status` and `keyword`.
- Order by `created_at desc`.
- Fetch `size + 1` rows and return `has_more`.
- Prevent `subtasks` from loading in the list response, for example with `noload(StorageMainTask.subtasks)` or a list-specific selected-column query.

`GET /api/storage/tasks/count` performs the same filter conditions and returns the exact total.

### Indexes

Existing migration `20260715_0001_add_interface_speed_indexes.py` already adds several indexes for crawler runs and storage tasks. This implementation should verify whether the following are present and add a new Alembic migration only for missing indexes:

- `crawl_tasks(owner_id, created_at DESC)` for the paged crawler task list.
- `crawl_tasks(owner_id, name)` or an appropriate text-search strategy only if keyword search is shown to need it.
- `crawl_runs(task_id, created_at DESC)` and `crawl_runs(task_id, status, created_at DESC)` for run filters.
- `storage_main_tasks(created_by, created_at DESC)` and `storage_main_tasks(created_by, status, created_at DESC)` for storage task filters.

Avoid duplicate indexes when an existing index already covers the query.

## Frontend Design

### Query Model

All three pages should use TanStack Query instead of manual `useEffect + useState` list loading.

Query keys should use `page` and `size`:

- `crawlerTasks.list({ page, size, keyword })`
- `crawlerTasks.count({ keyword })`
- `crawlerRuns.list({ page, size, task_id, status })`
- `crawlerRuns.count({ task_id, status })`
- `storageTasks.list({ page, size, status, keyword })`
- `storageTasks.count({ status, keyword })`

Use cached previous data while page or size changes, so the table or card grid does not blank unnecessarily.

### Rendering Behavior

The list rows render as soon as the list query succeeds.

Totals render independently:

- While count is loading, show a lightweight loading label such as `统计中`.
- After count succeeds, show `共 N 条`.
- If count fails but rows loaded, keep rows visible and show a non-blocking count failure state.

Pagination should use `has_more` for next-page availability before the exact count arrives. Once the count arrives, existing total display can be restored.

### Realtime Updates

Realtime events should patch visible cached rows where possible:

- Crawler task status updates patch visible task runtime state and visible stats if loaded.
- Crawler run updates patch visible run status and error fields.
- Storage task updates patch visible storage task status and counters.

Events that may change ordering or page membership can invalidate the current list query, but should not trigger a full all-list reload.

### Actions

Stop, restart, delete, run, and toggle actions keep their current behavior. After mutation success:

- Patch the current row when the response contains enough data.
- Invalidate the current page list query.
- Invalidate the matching count query only when the action can change total count.

## Error Handling

- A list query failure with no cached rows should use the page's existing error or empty-state behavior.
- A count query failure must not hide list rows.
- Background refetch failures keep stale rows visible.
- Backend list endpoints should validate `page >= 1` and `size` within the same maximum used by the current UI.
- Owner scoping failures should continue returning not found or empty results, not cross-user data.

## Testing Plan

### Backend

- Crawler task list returns `page`, `size`, `rows`, and `has_more` without inline `total`.
- Crawler task list accepts `page/size` and uses only visible task IDs for runtime enrichment.
- Crawler run list scopes by current user and does not return another user's runs.
- Crawler run list returns `has_more` and does not load `detail_tasks`.
- Storage task list returns `has_more` and does not load `subtasks`.
- Count endpoints match the filters used by their list endpoints.
- Existing stop, restart, delete, and run tests still pass.

### Frontend

- API wrappers send `page/size`, not `skip/limit`.
- Each list renders rows before the count query completes.
- Count failures do not clear list rows.
- Pagination uses `has_more` while total is pending.
- Realtime updates patch the visible cache for task/run/storage status changes.

## Verification

Run focused backend tests for the modified modules:

```bash
source .venv/bin/activate && cd backend && python -m pytest tests/test_crawler_tasks_api.py tests/test_crawler_runs_api.py tests/test_storage_tasks_api.py -v
```

Run frontend checks after updating the pages:

```bash
cd frontend && npm run build
```

Add or run focused Vitest coverage for the three list pages when practical.

## Rollout Order

1. Update backend list contracts to `page/size`, `has_more`, and count endpoints.
2. Add tests for count split, owner scoping, and no child-collection preloading.
3. Update frontend API wrappers and query keys.
4. Convert crawler task list to paged TanStack Query and page-only runtime status.
5. Convert crawler run list and storage task list to TanStack Query with count split.
6. Verify backend tests and frontend build.
