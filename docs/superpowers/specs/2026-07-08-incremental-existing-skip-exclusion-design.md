# Incremental Existing Skip Exclusion Design

Date: 2026-07-08

## Context

Incremental crawler runs use a list-phase database check to detect movie codes
that already exist. The current path marks those list items as
`skipped/already_exists`, sends them through `on_tasks_batch_created()`, creates
`CrawlRunDetailTask` rows, increments runtime `total` and `skipped` progress,
and lets final run summaries count them as skipped child tasks.

That makes the child task list and crawl counts include rows that were never
intended to be crawled in this run. The desired behavior is narrower: only
list-phase `already_exists` rows in incremental mode are excluded. Detail
phase `already_exists` rows remain visible as skipped child tasks because those
items already entered the detail processing queue.

## Goals

- In incremental list collection, exclude `already_exists` rows from detail task
  creation.
- Keep list-phase existing rows out of child task lists.
- Keep list-phase existing rows out of runtime progress and run result counts.
- Continue appending the current crawl task ID to existing movies found during
  list-phase dedupe.
- Preserve incremental threshold behavior: the threshold is still based on how
  many existing rows were found on the current list page.
- Preserve detail-phase `already_exists` behavior.

## Non-Goals

- Do not change full crawl behavior. If full crawl currently creates skipped
  detail rows for existing movies, that behavior remains unchanged.
- Do not introduce a new task status such as `ignored`.
- Do not change movie persistence, magnet persistence, or detail retry behavior.
- Do not change the frontend child task table beyond the fact that excluded
  rows no longer appear in API results.

## Behavior

During `crawl_mode == "incremental"` list collection:

1. Parse list page items.
2. Deduplicate items within the URL.
3. Run the existing DB code check.
4. Split the page items into:
   - `existing_tasks`: codes already present in the movie database;
   - `crawlable_tasks`: new rows that become detail tasks.
5. For each existing task, trigger the existing-item callback so the backend can
   append `source_task_ids` and log the skip.
6. Send only `crawlable_tasks` to `on_tasks_batch_created()`.
7. Add only `crawlable_tasks` to `detail_tasks`.
8. Use the original existing count for the incremental threshold check.

The existing tasks are ignored for child task persistence and run counts. They
are not returned from `collect_detail_tasks_for_url()` or
`collect_all_detail_tasks()`.

During detail processing, behavior remains unchanged. If a code is found to
already exist immediately before fetching its detail URL, the detail row is
marked skipped, `source_task_ids` are appended, and run counts include that
skipped row.

## Runtime Callback Semantics

`on_item_already_exists(task_info)` currently handles both list-phase and
detail-phase already-existing items. It will keep that role, but it must not
increment skipped progress when there is no existing `CrawlRunDetailTask` row.

This makes callback behavior explicit:

- detail row exists: mark row `skipped`, append source task ID, increment
  skipped progress if it was not already skipped;
- detail row does not exist: append source task ID and write a log only.

`on_tasks_batch_created(items)` receives only crawlable items for
incremental list batches. Therefore it will not create skipped rows for
list-phase `already_exists` items and will not increment skipped progress for
them.

## Counting

Runtime progress and final run results continue to derive totals from persisted
detail task rows:

- `total_tasks`: count of persisted detail rows;
- `skipped_tasks`: count of persisted rows with status `skipped`;
- per-URL item counts: count only returned detail tasks.

Because list-phase existing rows are no longer persisted or returned, they drop
out of all these counts automatically.

Logs remain available for audit. The crawler logs how many list rows were
already present and ignored, and backend runtime logs source task ID
append events.

## Testing Strategy

### Spider Tests

- Incremental list-phase DB dedupe excludes existing rows from the returned
  detail tasks.
- `on_tasks_batch_created()` receives only crawlable rows.
- `on_item_already_exists()` is called for list-phase existing rows so source
  task ID append remains possible.
- Incremental threshold still stops the current URL when the list page existing
  count reaches the threshold, while preserving any crawlable rows from the same
  page.

### Runtime Tests

- A run with one list-phase existing movie and one new movie creates a detail
  row only for the new movie.
- The existing movie receives the current `source_task_id`.
- Final run result reports no skipped task for the list-phase existing movie.
- Detail-phase existing movie behavior remains unchanged and still reports one
  skipped task.

### Result Tests

- Existing result summarization remains based on detail tasks.
- No new result status is introduced.

## Verification

Run focused backend tests:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py scraper/tests/test_javdb_spider_dedupe_callbacks.py backend/tests/test_crawler_runtime_adapters.py -v
```

Run broader backend tests if focused tests pass:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/ -v
```
