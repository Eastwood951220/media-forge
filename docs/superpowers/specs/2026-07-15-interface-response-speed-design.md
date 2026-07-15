# Interface Response Speed Optimization Design

## Context

Media Forge currently serves the dashboard and key list pages through a mix of backend aggregation endpoints and frontend stateful `useEffect` requests. The observed target is to improve perceived and actual response speed for the homepage and list interfaces without changing user-facing behavior.

The relevant surfaces are:

- Dashboard overview: `GET /api/dashboard/overview`
- Crawler task list and runtime statuses: `GET /api/crawler/tasks`, `GET /api/crawler/tasks/statuses`
- Crawler run list and run detail task list: `GET /api/crawler/runs`, `GET /api/crawler/runs/{id}/tasks`
- Movie list: `GET /api/content/movies`
- Storage task list and subtask list: `GET /api/storage/tasks`, `GET /api/storage/tasks/{id}/subtasks`

The current code already has TanStack Query configured globally, but these pages mostly use manual `useState` and `useEffect` loading. On the backend, several paths use repeated counts, broad object loading, or Python-side filtering that can grow linearly with data volume.

## Goals

- Reduce backend work for dashboard and list endpoints by using database-side aggregation, pagination, and targeted indexes.
- Reduce repeated frontend requests by moving dashboard and list loading to TanStack Query.
- Preserve current API response shapes, routes, table behavior, filters, realtime updates, and user-visible actions.
- Keep the first implementation focused on refactor and optimization of existing behavior, not new product features.

## Non-Goals

- No redesign of page layout or navigation.
- No replacement of the existing request wrapper.
- No speculative new dashboard widgets, list columns, or modules.
- No mandatory cursor pagination in the first phase; offset/page pagination remains unless a query path clearly requires deeper change.

## Recommended Approach

Use a two-layer optimization:

1. Backend query optimization for endpoints whose cost grows with total data size.
2. Frontend query orchestration with TanStack Query for caching, deduplication, precise invalidation, and stale-data retention.

This balances speed gains with implementation risk. It avoids a larger data model redesign while addressing the main bottlenecks found in the current code.

## Backend Design

### Dashboard Overview

Keep `GET /api/dashboard/overview` as a single aggregate endpoint. Internally, reduce it to database aggregations and small result sets:

- Crawler task totals, enabled count, and disabled count should use grouped or conditional aggregate queries instead of multiple independent full counts where practical.
- Run status distribution, seven-day trend, and recent runs should remain separate lightweight queries, but should use indexes matching owner/task filtering and created-time ordering.
- Movie totals and storage status counts should not load every `Movie` row into Python. Move storage status counting to SQL expressions over persisted columns such as `storage_summary` where possible.
- Storage task status distribution and recent tasks should filter by owner and use an index that supports owner plus created-time ordering.
- Preserve `partial_errors` behavior so one failed section degrades instead of failing the whole dashboard.

If a specific movie storage status cannot be expressed safely in SQL, the first phase should optimize the common persisted-state cases and leave a clearly isolated fallback path for the unsupported case.

### Crawler Task List

Keep `GET /api/crawler/tasks` response unchanged. Optimize the latest-run lookup:

- The current repository loads all historical runs for the visible task IDs and selects the latest in Python.
- Replace this with a database-side latest-per-task query, using either a window function, `DISTINCT ON` for PostgreSQL, or a grouped subquery compatible with the project test database.
- Ensure pagination and keyword search behavior remain unchanged.

The runtime status endpoint may stay separate in the first phase. A later phase may merge list rows and runtime snapshots if the split remains a measurable bottleneck.

### Crawler Run Lists

Keep current pagination and filters. Add or verify indexes that match:

- Global run list ordering by `created_at desc`
- Task-scoped run list by `task_id`, optional `status`, and `created_at desc`
- Detail task list by `run_id`, optional `status`, and `created_at asc`

The run detail task summary should continue to use status aggregation rather than row-by-row counting.

### Movie List

Keep `GET /api/content/movies` response unchanged. Improve high-cost paths:

- Avoid Python fallback for PostgreSQL filters that can be expressed through existing array and JSON fields.
- Keep database pagination for normal search, rating, date, array, and source task filters.
- Investigate the storage-status fallback and move common statuses to SQL predicates over `storage_summary`.
- Avoid per-row task lookups during movie serialization by batching `source_task_ids` to storage locations for the current page.
- Preserve selected magnets and current movie serialization fields.

SQLite-specific fallback behavior used by tests can remain, but PostgreSQL production paths should avoid full table loads where possible.

### Storage Task Lists

Keep response shapes unchanged. Optimize repository queries:

- Filter main task list by `created_by` before status and keyword conditions.
- Add or verify an index supporting `created_by, created_at desc` and `created_by, status, created_at desc`.
- Keep subtask list scoped to `main_task_id`, ordered by `created_at asc`, with a matching index.

Authorization checks must remain in place for detail and subtask routes.

### Indexes and Migrations

Add Alembic migrations for missing indexes rather than relying only on model metadata. Candidate indexes include:

- `crawl_runs(task_id, created_at desc)`
- `crawl_runs(task_id, status, created_at desc)`
- `crawl_runs(created_at desc)` if the global run list is frequently used
- `storage_main_tasks(created_by, created_at desc)`
- `storage_main_tasks(created_by, status, created_at desc)`
- Any movie JSON expression or GIN index only if the corresponding SQL predicate demonstrably uses it

Avoid duplicate indexes where existing definitions already cover the query.

## Frontend Design

### Query Keys

Use TanStack Query for dashboard and list data. Query keys should include only the state that changes the result:

- `['dashboard', 'overview']`
- `['crawlerRuns', { skip, limit, taskId, status }]`
- `['crawlerTasks', { skip, limit, keyword }]`
- `['crawlerTaskRuntimeStatuses']`
- `['movies', filters, page, pageSize, sortBy, sortOrder]`
- `['storageTasks', { page, limit, status, keyword }]`
- `['storageSubtasks', mainTaskId, { page, limit }]`

Query keys should be created through small helpers or colocated constants when reused by mutations and realtime handlers.

### Page Hooks

Replace manual loading state in these page hooks with query state:

- `useDashboardOverview`
- `RunListPage` data loading, or a new `useCrawlerRunList`
- `useTaskListData`
- `useMovieList`
- `useStorageTaskList`

The UI should keep existing loading, refreshing, empty, and error behavior. When cached data exists, background refetch failures should not clear the page.

### Mutations and Invalidation

Action handlers should use mutations and invalidate only affected queries:

- Crawler run stop, restart, and delete invalidate crawler run list and relevant task runtime status.
- Crawler task update, delete, and run invalidate crawler task list and runtime status.
- Movie storage sync invalidates the active movie list query.
- Storage task stop, restart, and delete invalidate storage task list and relevant detail query.
- Dashboard refresh invalidates only `['dashboard', 'overview']`.

Where the mutation returns enough data to update the current row, update query cache directly and still allow a background refetch when needed.

### Realtime Updates

Realtime SSE handlers should prefer cache updates over immediate whole-page reloads:

- For visible crawler run rows, patch status and error fields in the current `crawlerRuns` cache.
- For crawler task runtime status changes, patch `crawlerTaskRuntimeStatuses`.
- For visible storage task rows, patch counters and status in the current `storageTasks` cache.
- If an event lacks enough information or affects an unseen page, ignore it and rely on the next invalidation/refetch.

This keeps the UI responsive while avoiding unnecessary list reloads.

## Error Handling and Degradation

- Keep backend `success` and `paginated` response envelopes unchanged.
- Preserve dashboard section-level fallback and `partial_errors`.
- On first load failure with no cached data, show the existing error or empty-state path and a retry control where one exists.
- On background refetch failure with cached data, keep stale data visible and show lightweight feedback only when useful.
- Mutation failures should not optimistically alter local state unless rollback is implemented.
- Unsupported movie storage-status SQL cases should remain isolated fallback paths and be documented for follow-up optimization.

## Testing Plan

### Backend

- Dashboard overview tests should verify aggregate values, partial fallback behavior, and movie storage counts.
- Crawler task list tests should verify pagination, keyword search, latest run selection, and that historical runs do not change the latest result.
- Crawler run and run detail task tests should verify pagination, filters, summaries, and response shape.
- Movie list tests should cover normal SQL-backed filters, storage status filters, sorting, pagination, and serialization of storage locations.
- Storage task list tests should verify owner scoping, pagination, status filtering, keyword filtering, and subtask listing.
- Migration tests or manual Alembic verification should confirm new indexes apply cleanly.

### Frontend

- Dashboard hook/page tests should cover initial loading, successful data display, refresh, and failure with cached data.
- List page tests should cover query key changes from pagination, filters, and sorting.
- Mutation tests should confirm the intended query invalidations.
- Realtime tests should confirm cache patching for visible rows without forcing full reloads.

## Verification

Run focused tests during implementation, then broader checks before completion:

- Backend: `source .venv/bin/activate && cd backend && python -m pytest tests/ -v`
- Frontend: `cd frontend && npm run build`
- Frontend focused tests for modified pages where available

Performance acceptance should compare before and after behavior on representative local data:

- Dashboard overview should avoid loading all movies and should return from aggregate queries.
- List endpoints should not perform work proportional to all historical rows when returning one page.
- Page revisit and tab switching should reuse cached data and avoid redundant loading spinners.
- Actions and realtime events should update visible state quickly while keeping eventual backend consistency.

## Rollout Order

1. Add backend query tests around current behavior.
2. Optimize dashboard and movie-list high-cost queries.
3. Optimize crawler task latest-run and storage/crawler list indexes.
4. Convert dashboard and one list page to TanStack Query as the pattern.
5. Convert remaining list pages and realtime handlers.
6. Run backend and frontend verification.

