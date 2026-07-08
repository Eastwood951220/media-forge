# Crawler Multi-URL Logs And Detail List Performance Design

Date: 2026-07-08

## Context

Crawler tasks can contain multiple URLs. During a run, the current logs make it
hard to tell which URL entry is being processed because list and detail logs
mostly include only the task name, page number, code, or source name. Detail
tasks already carry `_task_url_name` in memory after list collection, but that
context is not consistently included in logs or persisted detail task rows.

The run detail page also loads a limited detail-task snapshot and lets Ant
Design paginate it locally. This is not enough for runs with thousands of detail
tasks: the browser has to sort and render too much state during realtime
updates, and the table only contains the first backend page.

The reported crawl progression issue is scoped to one `CrawlTask` with multiple
URLs. It is not a queue-level issue between different crawler runs.

## Goals

- Make list and detail crawler logs identify the current URL entry by
  `url_name`.
- Persist and expose URL-entry context on crawl run detail tasks so the UI can
  display which configured URL produced each child task.
- Keep multi-URL crawling sequential within one task, and ensure normal
  per-URL termination continues to the next URL.
- Optimize the crawler run detail task table for thousands of rows using
  server-side pagination.
- Preserve existing run lifecycle, retry, stop, realtime, and movie persistence
  behavior.

## Non-Goals

- Do not change queue scheduling between different crawler runs.
- Do not split one crawler task into separate URL-level runs.
- Do not redesign the run detail page beyond the child task table behavior and
  source URL context needed for this issue.
- Do not change JavDB parsing rules or movie persistence rules.

## Approach

Use a minimal closed-loop fix.

1. Add a stable display label for each task URL:
   `url_name`, falling back to `url_type`, then the final URL or original URL.
2. Include that label in list and detail crawler logs.
3. Persist the URL label and URL metadata on `CrawlRunDetailTask`.
4. Return the new fields from the run detail tasks API.
5. Convert the frontend run detail child task table to controlled server-side
   pagination.
6. Add regression tests for multi-URL progression and large-list paging.

This keeps the crawler architecture intact while making the failing behavior
observable and testable.

## Backend Design

### URL Context In The Spider

`scraper/spiders/javdb/javdb_spider.py` will format URL-aware log prefixes when
processing a configured task URL. For example:

```text
[任务名][URL: 演员A] 正在获取列表页 2/50
[任务名][URL: 演员A] 列表页 2 完成: 本页=20条(去重后)
[任务名][URL: 标签B] 当前 URL 达到增量阈值，停止该 URL 后续列表页，继续下一个 URL
```

The detail phase will use the `_task_url_name` already attached to each detail
task and include it in processing, skipped, completed, failed, and security
verification logs. Existing log levels stay the same.

### Multi-URL Progression

`collect_all_detail_tasks()` remains sequential:

1. process URL entry 1;
2. stop that URL on empty page, max page, incremental threshold, or stop signal;
3. continue to URL entry 2 unless the stop signal is set;
4. dedupe codes across all URL entries in the run.

Only an explicit stop signal can terminate the whole task early. Empty pages,
incremental threshold hits, and max page completion terminate only the current
URL entry.

### Detail Task Persistence

`CrawlRunDetailTask` will gain persisted URL-entry context fields:

- `source_url_name`: display name from `_task_url_name`;
- `task_url`: original configured URL from `_task_url`;
- `task_final_url`: generated list URL from `_task_final_url`;
- `task_url_type`: configured URL type from `_task_url_type`.

The callback that creates detail task rows will copy these values from the
detail task payload. Detail retry conversion will preserve them when converting
database rows back to spider task dictionaries.

The API schema for run detail tasks will expose the same fields. The keyword
filter will continue matching code and source name, and will also match
`source_url_name` so users can filter by configured URL name.

### Database Migration

Add one Alembic migration for the nullable fields above. Existing rows remain
valid. No data backfill is required because old runs did not persist this
context; the UI will display `-` when the value is absent.

## Frontend Design

### API Types

`CrawlRunDetailTask` gains optional URL context fields matching the backend
schema.

### Server-Side Pagination

`useRunDetail` will maintain:

- `taskPage`;
- `pageSize`;
- `taskTotal`;
- `statusFilter`;
- `keyword`.

`fetchTasks()` will request:

```text
skip=(taskPage - 1) * pageSize
limit=pageSize
status=statusFilter
keyword=keyword
```

Changing status, keyword, or page size resets the table to page 1. The table
pagination becomes controlled with `current`, `pageSize`, and `total`.

### Realtime Updates

Realtime detail updates will update rows only when the changed row is already on
the current page and still matches the active filters. The hook will refresh the
current page when an update is not already present on the current page but
matches the active filters, or when an existing row changes so it no longer
matches the active filters. This keeps table membership and totals aligned
without accumulating all rows in memory.

Retry controls remain compatible with pagination:

- retry one row uses the visible row ID;
- retry selected rows uses selected visible failed rows;
- retry all failed rows continues to call the backend with `retry_all: true` and
  does not depend on loading every failed row in the browser.

### Table Display

The child task table will add a compact source URL column that displays
`source_url_name` with fallback to `task_url_type` or `-`. Existing code, source
name, status, error, and retry columns remain.

## Error Handling

- If URL context fields are missing, logs fall back to URL type or URL string.
- If a detail task was created before this migration, the frontend displays `-`
  for source URL context.
- If a page request fails, existing loading/error message behavior applies.
- Stop requests continue to reset unfinished detail rows as before.
- Detail retry continues to process only pending retry rows and preserves URL
  context where available.

## Testing Strategy

### Backend

- Spider unit test: two URL entries where the first URL ends normally and the
  second URL is still requested.
- Spider log test: list logs and detail logs include each URL entry's
  `url_name`.
- Runtime callback/API test: created `CrawlRunDetailTask` rows persist URL
  context and `/api/crawler/runs/{run_id}/tasks` returns it.
- API pagination test: `skip`, `limit`, `status`, and `keyword` return the
  expected slice and total, including keyword match on `source_url_name`.
- Detail retry test: retry rows keep URL context when converted back to spider
  task dictionaries.

### Frontend

- Run detail test: initial child task request includes `skip=0` and
  `limit=pageSize`.
- Pagination test: changing page requests the matching backend slice instead of
  locally paging all loaded rows.
- Filter test: status or keyword changes reset to page 1 and call the API with
  the filter.
- Retry test: `retry_all` still sends `{ retry_all: true }` without requiring all
  failed rows to be loaded.

## Verification

Run backend tests:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_engine.py tests/test_crawler_runs_api.py tests/test_crawler_run_logs.py -v
```

Run focused frontend tests:

```bash
cd frontend
npm test -- --run src/pages/crawler/runs
```

Run broader verification if the focused tests pass:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/ -v

cd frontend
npm run build
npm run lint
```
