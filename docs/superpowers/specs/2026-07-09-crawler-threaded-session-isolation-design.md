# Crawler Threaded Session Isolation Design

## Context

The threaded crawler list phase currently runs URL collection in a `ThreadPoolExecutor`.
Each worker thread calls scraper callbacks that close over the main worker
SQLAlchemy `Session`. In production this can leave the shared session in a
prepared transaction state. The list phase then raises:

```text
This session is in 'prepared' state; no further SQL can be emitted within this transaction.
```

When that happens, `future.result()` fails in `_run_list_phase`, the run is
marked failed, and the detail phase never starts even though the list scraper
already collected tasks.

## Goal

Keep the existing threaded crawler behavior while making list-phase worker
threads independent from the main crawler `Session`.

The fix is scoped to the refactor and optimization of the existing crawler
runtime. It does not add new crawler features or change crawl semantics.

## Non-Goals

- Do not redesign the crawler engine.
- Do not merge threaded and callback-based runtimes.
- Do not move list-phase dedupe semantics out of the scraper.
- Do not change incremental/full mode behavior.
- Do not add new UI behavior.

## Proposed Approach

Use short-lived isolated SQLAlchemy sessions for database work executed inside
list-phase worker threads.

`_run_list_phase` will keep the main `db` session for main-thread writes after
`future.result()` returns. Worker-thread callbacks will no longer reference that
session directly.

The threaded runtime will expose small helper functions for worker-thread DB
operations:

- Check existing movie codes with an isolated session.
- Append `source_task_id` for already existing movies with an isolated session
  and commit.
- Write list-phase log events without using the main session from the worker
  thread.

Each helper opens a session from the configured session factory, performs one
small unit of work, commits when needed, rolls back on failure, and closes the
session.

## Data Flow

1. `execute_threaded_crawl` starts list phase.
2. `_run_list_phase` submits one worker future per task URL.
3. Each worker thread calls `spider.collect_detail_tasks_for_url`.
4. The scraper calls DB callbacks during list dedupe.
5. Each DB callback uses its own short-lived session.
6. The worker returns collected task items.
7. The main thread persists returned detail tasks with the main `db` session.
8. After all URL futures finish, `_run_detail_phase` starts normally.

## Error Handling

Worker-thread DB callbacks should not poison the main worker session.

If isolated DB work fails, the isolated session rolls back and closes. The
exception can still propagate through the future, preserving the current
failure behavior for real DB errors. The important behavioral change is that a
worker-thread session failure cannot leave the main crawler session unusable.

## Testing

Add regression coverage in `backend/tests/test_crawler_threaded_runtime.py`.

The test should prove that list-phase callbacks do not receive or use the main
session:

- Build a fake spider that exercises `db_check_callback`.
- Make the main session fail if it is used from that callback path.
- Provide an isolated session factory for threaded callback DB work.
- Run `execute_threaded_crawl`.
- Assert that the list phase finishes, the detail phase starts, and detail rows
  are saved.

Existing worker and crawler runtime tests should continue to pass.

## Acceptance Criteria

- A threaded list run that performs DB dedupe can proceed into the detail phase.
- No worker-thread callback reuses the main crawler SQLAlchemy `Session`.
- A prepared-state failure in one isolated callback session does not poison the
  main run-finalization session.
- Regression tests cover the session isolation behavior.
