# Crawler Threaded Queue Design

Date: 2026-07-08

## Goal

Change crawler execution from a single-threaded in-memory flow to a configurable
multi-threaded flow:

- List phase: one worker claims one configured URL, crawls all pages for that
  URL sequentially, then claims the next URL.
- Detail phase: after all list workers finish, detail workers claim pending
  detail tasks in order.
- List and detail worker counts are configurable in crawler config.

The design preserves the existing Media Forge crawler behavior and runtime
model. It does not introduce distributed crawling or unrelated product features.

## Confirmed Decisions

- Use separate config fields for list and detail concurrency:
  `LIST_MAX_WORKERS` and `DETAIL_MAX_WORKERS`.
- Keep strict two-phase execution: all list URL crawling must finish before any
  detail task crawling starts.
- Use a persistent queue model for detail tasks. Detail workers claim rows from
  `crawl_run_detail_tasks` instead of sharing an in-memory task list.
- Keep the implementation scoped to the current backend process. Multiple
  processes or distributed workers are out of scope.

## Architecture

The run entry point remains the existing crawler runtime flow:

`execute_run -> crawler engine/runtime coordinator -> JavdbSpider`

The engine gains a coordinator-style execution path that manages two worker
pools. Spider parsing and fetch logic remains responsible for page-level work,
while the runtime layer owns persistent task state, progress, logs, and final
run status.

Each worker uses its own SQLAlchemy `Session`. Workers must not share the
session, ORM objects, or `DetailTaskIndex` created by the main run session. This
keeps database writes thread-safe and avoids cross-thread ORM state corruption.

## Configuration

Add these fields to crawler config:

- `LIST_MAX_WORKERS`: integer, minimum `1`, default `1`.
- `DETAIL_MAX_WORKERS`: integer, minimum `1`, default `1`.

They are stored in the existing `data/configs/crawler.conf` flow, exposed by
`/api/crawler/config`, and editable on the frontend crawler config page.

Existing defaults keep current serial behavior until the user increases worker
counts.

## List Phase

The list phase creates a thread pool with up to `LIST_MAX_WORKERS` workers.

Each worker:

1. Claims one URL entry from the crawl task URL set.
2. Crawls that URL sequentially from page 1 through `MAX_LIST_PAGES`, using the
   existing page URL builder, parser, delay, security-check, stop-check, and
   incremental-threshold behavior.
3. Persists parsed detail items into `crawl_run_detail_tasks`.
4. Stops only the current URL when the incremental existing threshold is reached.
5. Returns per-URL statistics for final result aggregation.

URL-level failures are logged and recorded in list-phase statistics. A failure
for one URL does not stop other list workers unless the run is stopped or a
run-level unrecoverable error occurs.

## Detail Task Persistence

List workers persist detail rows as they discover them:

- New crawlable item: `pending_crawl`
- Existing item kept in full mode: `skipped`
- Existing item ignored in incremental mode: no detail row is created, but the
  existing movie still receives the current source task id

Run-level deduplication must prevent duplicate detail rows for the same run. The
dedupe key should prefer `code` when present and fall back to `source_url`.

If the current database model lacks a constraint that can enforce this safely
under concurrent list workers, implementation must add either:

- a database uniqueness constraint suitable for the run-level dedupe key, or
- a small transactional claim/create helper that serializes duplicate-sensitive
  row creation.

The chosen implementation must make concurrent duplicate discovery deterministic:
only one detail row is created, and duplicate discoveries do not fail the run.

## Detail Phase

The detail phase starts only after all list workers finish.

The detail phase creates a thread pool with up to `DETAIL_MAX_WORKERS` workers.
Each detail worker loops until no work remains or the run is stopped.

To claim work, a worker:

1. Opens its own database session.
2. Finds the next row for the current run with `status = 'pending_crawl'`,
   ordered by `created_at asc`.
3. Marks that row as `crawling` inside the same transaction.
4. Commits the claim before fetching.

After claiming a row, the worker reconstructs the spider detail task dict from
the persisted row fields and crawls the detail page.

Successful detail crawl:

- Parses the detail page.
- Runs the existing movie pipeline.
- Saves or updates the movie and magnets.
- Marks the detail row `saved`.
- Writes progress, logs, and realtime update events.

Failed detail crawl:

- Marks the detail row `crawl_failed`.
- Stores an error summary.
- Writes progress, logs, and realtime update events.
- Does not stop other detail workers.

Rows with `skipped` status are not claimed by detail workers. Existing
already-exists behavior, including source task id updates, must be preserved.

## Stop, Restart, and Retry

Stop:

- `stop_run` continues to set the Redis stop flag.
- List workers check the stop flag before each page.
- Detail workers check the stop flag before claiming, before fetch, and after
  fetch/parse where practical.
- On stopped or interrupted finalization, rows left in `crawling` are reset to
  `pending_crawl` so a restart can continue.

Restart:

- If detail phase has started, unfinished details are reset to `pending_crawl`
  and the restarted run enters the detail worker pool directly.
- If detail phase has not started, existing detail rows for the run are cleared
  and the run starts from the list phase.

Failed detail retry:

- `retry_failed_details` continues to mark selected failed rows as
  `pending_crawl` and enqueue the run.
- A run with pending retry rows and `detail_retry` result metadata skips list
  collection and starts the detail worker pool directly.

## Result and Progress Semantics

Run progress remains based on persisted detail rows:

- total: created detail rows, including skipped rows when they are persisted.
- skipped: rows skipped because the movie already exists.
- saved: rows successfully saved to the movie store.
- failed: rows that fail detail crawling or saving.

Final run result should include list-phase URL statistics, detail counts, and
the stopped flag. A run with partial URL list failures may still finish if it
processed at least one detail row or produced meaningful skipped/saved results.
If every list URL fails and no detail rows are available, the run should fail.

## Error Handling

Security verification keeps the current wait-and-retry behavior. In the threaded
model it blocks only the current worker, not the entire phase.

Database write failures in one worker must roll back that worker session and log
the failure. They should not corrupt other workers. A run-level failure should
be used only when the coordinator cannot safely continue.

Unexpected worker exceptions are captured, logged with URL or detail context,
and included in run result statistics.

## Testing

Backend tests should cover:

- `LIST_MAX_WORKERS` and `DETAIL_MAX_WORKERS` defaults, config read/write, and
  API validation.
- List workers process URLs concurrently while each URL's pages remain
  sequential.
- The list phase completes before detail workers start.
- Concurrent list workers do not create duplicate detail rows for the same run.
- Detail workers claim `pending_crawl` rows in `created_at asc` order and move
  rows through `pending_crawl -> crawling -> saved` or `crawl_failed`.
- Stopping a run resets unfinished `crawling` rows to `pending_crawl`.
- Failed detail retry skips list collection and uses the detail worker pool.
- Worker count `1` preserves existing serial behavior.

Frontend tests should cover:

- The crawler config page renders both new worker count inputs.
- Saving config includes `LIST_MAX_WORKERS` and `DETAIL_MAX_WORKERS`.

## Out of Scope

- Distributed workers across multiple backend processes or machines.
- Redis-backed detail task queues.
- New crawler sites or new crawler task types.
- Changes to movie filtering, storage tasks, or unrelated frontend workflows.
