# Crawler List Refresh Design

## Context

The crawler task list and run list are rendered inside the authenticated
keep-alive route outlet. When a user leaves and re-enters either list page, the
page component is restored from cache instead of remounting. The frontend query
client also keeps query data fresh for five minutes, so TanStack Query does not
automatically fetch updated list data during normal route re-entry.

This causes a visible stale-data problem in the crawler workflow: after starting
a task from the task list, navigating to the run list can show the previously
cached run list without the newly created run.

## Goals

- Show the latest run entry after a task, temporary task, or task URL run is
  submitted from the task list.
- Refresh the task list and run list when their cached route page becomes active
  again.
- Preserve existing keep-alive UX, including current pagination and in-page
  state.
- Keep the change scoped to crawler task/run list freshness. Do not change
  global query defaults or unrelated pages.

## Non-Goals

- Do not remove route keep-alive caching.
- Do not lower the global query stale time.
- Do not manually synthesize or insert new runs into cached run-list pages.
- Do not change backend realtime event contracts.

## Proposed Approach

Use a small frontend-only freshness boundary:

1. Add a focused hook that runs a callback when a keep-alive route page becomes
   active again. It should use `keepalive-for-react`'s `useEffectOnActive`
   support and skip the initial mount so the normal first query load remains
   unchanged.
2. In the task list data hook, invalidate crawler run list and count queries
   after any action that creates a run:
   - normal task run
   - temporary task run
   - task URL run
3. In the task list page, refresh the current task list when the cached page is
   reactivated.
4. In the run list page, refresh the current run list and run count when the
   cached page is reactivated.

This keeps mutation-side invalidation and page-side refetch responsibilities
separate. Creating a run declares that run-list data has changed; the run list
itself decides how to refresh its current view when shown.

## Data Flow

Task list run submission:

1. User starts a run from `/crawler/tasks`.
2. The API returns the created `CrawlRun`.
3. The task list refreshes runtime status as it does today.
4. The task list invalidates all `crawlerRuns` list queries and the
   `crawlerRuns` count query.
5. If the user opens `/crawler/runs`, cached query data is already stale and the
   list refetches. If the run list page was already cached, its active-page
   refresh also fetches the current page and count.

Cached page re-entry:

1. The user switches back to `/crawler/tasks` or `/crawler/runs`.
2. keep-alive activates the cached component.
3. The page's activation hook calls its existing refresh function.
4. Current pagination is preserved because the page component state is not
   destroyed.

## Error Handling

Activation refreshes should use existing TanStack Query request handling. They
should not add new blocking UI or toast messages, because re-entry refresh is a
background freshness operation. The existing loading indicators can continue to
reflect `isFetching` where already wired.

Submission actions should keep their existing success and error messages. A run
creation failure should not invalidate run-list queries, because no new run was
created.

## Testing

Add focused frontend tests:

- Task list data hook invalidates crawler run list/count queries after a
  successful normal run submission.
- Temporary task and task URL submission paths trigger the same run-list
  invalidation through their submit handlers.
- Run list page activation refetches the current list and count while preserving
  pagination state.
- Existing task-list and run-list query tests continue to pass.

Run verification from `frontend/`:

- Focused Vitest tests for crawler task/run list modules.
- `npm run build`.

