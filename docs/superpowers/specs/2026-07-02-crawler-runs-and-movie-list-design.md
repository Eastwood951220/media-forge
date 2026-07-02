# Crawler Runs and Movie List Design

Date: 2026-07-02

## Goal

Migrate the relevant `jav-scrapling` crawler execution and content movie viewing behavior into Media Forge without expanding scope beyond the current refactor.

This design adds:

- Manual incremental and full crawl execution from the existing crawler task list.
- A crawler run record module with run history, run detail, stop, and restart controls.
- Redis-backed runtime queue, progress, stop, and subtask state management.
- Durable PostgreSQL records for runs, detail subtasks, movies, movie magnets, and movie filters.
- A read-only content management movie list.

This design does not add scheduled crawls, batch-run-all, single-page crawl, movie deletion, movie marking, storage push, magnet selection, or export features.

## Existing Context

Media Forge currently has crawler task CRUD under `/api/crawler/tasks` and a React task list/form under `/crawler/tasks`. The scraper package already contains `MovieService`, JavDB spider logic, movie persistence repositories, and task schema utilities migrated from `jav-scrapling`.

The current repository does not yet have the durable content models required by those scraper repositories. The implementation must add the minimal `Movie`, `MovieMagnet`, and `MovieFilter` models plus Alembic migration before crawler persistence and the movie list can work reliably.

`jav-scrapling` has useful prior art for `crawl_runs`, `crawl_run_detail_tasks`, run list/detail APIs, run restart, and the content movie list. Media Forge should reuse the behavior and naming where appropriate, but adjust execution so Redis is the runtime authority for queue/progress/stop state and startup never auto-runs interrupted work.

## Recommended Architecture

Use PostgreSQL for durable records and Redis for runtime coordination.

PostgreSQL stores:

- `crawl_tasks` and `crawl_task_urls`, already present.
- `crawl_runs`, one row per manual run or restart.
- `crawl_run_detail_tasks`, one row per detail-page subtask.
- `movies`, `movie_magnets`, and `movie_filters`, migrated minimally for crawler persistence and read-only browsing.

Redis stores:

- A crawler run queue.
- Current running run id / worker lock.
- Stop signals.
- Run progress snapshots.
- Detail subtask status snapshots.

The backend owns a crawler runtime service that bridges Redis state, PostgreSQL records, and `scraper.services.MovieService`. API routers should remain thin and call this service instead of embedding worker logic directly in route handlers.

## Manual Execution

The existing task list remains the place to create, edit, delete, search, and enable or disable crawl tasks. Each row gains two actions:

- `增量爬取`
- `全量爬取`

Only one selected task is started per click. There is no first-version `运行全部启用任务` control.

Clicking either action calls:

`POST /api/crawler/tasks/{task_id}/run`

with:

```json
{ "crawl_mode": "incremental" }
```

or:

```json
{ "crawl_mode": "full" }
```

The backend validates the task and Redis availability before creating a queued run. If Redis is unavailable, the API returns an error and does not create a stuck `queued` record.

On success, the UI shows that the run was queued and navigates to `/crawler/runs`.

## Run Records

Add a crawler run module:

- `GET /api/crawler/runs`
- `GET /api/crawler/runs/{run_id}`
- `GET /api/crawler/runs/{run_id}/tasks`
- `POST /api/crawler/runs/{run_id}/stop`
- `POST /api/crawler/runs/{run_id}/restart`
- `GET /api/crawler/runs/queue-status`

Run statuses:

- `queued`
- `running`
- `completed`
- `failed`
- `stopped`

Detail subtask statuses:

- `pending_crawl`
- `crawled`
- `crawl_failed`
- `saved`
- `save_failed`
- `skipped`

`crawl_runs` minimum schema fields:

- `task_id`
- `task_name`
- `status`
- `crawl_mode`
- `queued_at`
- `started_at`
- `finished_at`
- `result`
- `error`
- `resumed_from`

`crawl_run_detail_tasks` minimum schema fields:

- `run_id`
- `task_name`
- `code`
- `source_url`
- `source_name`
- `status`
- `error`
- `item_data`
- `created_at`
- `crawled_at`
- `saved_at`

## Restart Semantics

The run list and detail page use the button label `重启`.

`重启` is available for `stopped` and `failed` runs when unfinished detail subtasks exist.

A restart does not blindly rerun completed work. It creates a new `crawl_runs` row with:

- `status=queued`
- same task id and task name
- same crawl mode
- `resumed_from=<old_run_id>`

The new run continues only unfinished detail subtasks from the previous run.

Unfinished subtasks are:

- `pending_crawl`
- `crawl_failed`
- `save_failed`
- any stopped/interrupted subtask that never reached a terminal saved/skipped state

Completed subtasks are not reprocessed:

- `saved`
- `skipped`

The old run stays unchanged as history. The new run records the restart attempt and final outcome.

Restart copies unfinished detail rows into the new run. The old run's detail rows remain unchanged so the stopped or failed history stays inspectable exactly as it happened.

## Incremental vs Full Crawl

`incremental` mode follows the existing scraper behavior: when existing movies are detected, the crawler can stop or skip according to the configured incremental threshold.

`full` mode does not stop early merely because a movie already exists. It still avoids duplicate movie insertion. If a movie already exists, the crawler updates or preserves source task attribution and marks the relevant detail subtask as skipped or saved according to the persistence result.

Both modes should keep database writes idempotent by using unique movie code/source URL and movie magnet dedupe constraints.

## Runtime Lifecycle

Startup must never auto-execute crawler work.

On backend startup:

- Do not start a crawler worker.
- Clear crawler Redis runtime keys for active queue, running lock, stop signals, and volatile progress snapshots.
- Mark PostgreSQL `queued` and `running` runs as `stopped`.
- Set an error/message such as `服务重启，任务已停止，需手动重启`.

On backend shutdown:

- Set the current run stop signal in Redis if a run is active.
- Give the worker a short graceful window to observe the stop signal.
- Mark any still-active run as `stopped`.
- Close Redis and PostgreSQL connections.

The worker only starts after a manual run or restart request enqueues a run.

Stop is cooperative. The worker checks the Redis stop key between list-page batches, before detail-page work, between detail-page tasks, and around persistence. A single in-flight network request is not force-killed, but no new detail task should start after stop is observed.

## Crawler Worker Flow

For a new manual run:

1. Create `crawl_runs` as `queued`.
2. Enqueue the run id in Redis.
3. Start the crawler worker if not already running.
4. Worker claims the run and marks PostgreSQL and Redis status as `running`.
5. List-page crawling creates detail subtasks in PostgreSQL and updates Redis progress snapshots.
6. Detail-page crawling updates each subtask to `crawled`, `crawl_failed`, `saved`, `save_failed`, or `skipped`.
7. Movie and magnet data are persisted through scraper repositories.
8. Completion summarizes totals into `crawl_runs.result`.
9. Final status becomes `completed`, `failed`, or `stopped`.

For a restarted run:

1. Create a new `crawl_runs` row with `resumed_from`.
2. Prepare unfinished detail subtasks for that new run.
3. Skip list-page discovery.
4. Run detail-page processing only for unfinished subtasks.
5. Persist movies/magnets idempotently and update final result.

## Frontend Design

Navigation adds:

- `爬虫 / 运行记录`
- `内容管理 / 电影列表`

Task list changes:

- Keep the existing page style and controls.
- Add row actions for `增量爬取` and `全量爬取`.
- Show queued success and navigate to run records.
- Show compact queue status, but do not turn the task list into the run detail surface.

Run list:

- Columns: task name, crawl mode, status, progress, queued time, started time, finished time, actions.
- `running` rows show `停止`.
- `stopped` and `failed` rows show `重启` when unfinished subtasks exist.
- All rows allow opening detail.

Run detail:

- Summary area: task name, mode, status, progress, result totals, error.
- Detail task table: code, source title, source URL, status, error, created/crawled/saved timestamps.
- Filters: status and keyword.
- No first-version per-subtask retry button.

Movie list:

- Route: `/content/movies`.
- API: `GET /api/content/movies` and `GET /api/content/movies/{movie_id}`.
- List fields: cover, code, title, rating, release date, duration, actors, tags, source task names, created time.
- Support pagination, keyword search, source task filter, and sorting.
- Detail drawer is read-only and shows basic movie fields plus magnet list.
- No delete, mark, storage push, magnet selection, or export controls.

## API Response Shape

Media Forge should keep its existing shared response envelope style for new APIs:

- Lists return `rows` and `total` where the current frontend convention expects it.
- Single-object actions return the object or result under `data`.
- Error responses go through existing FastAPI exception handlers.

If adapting old `jav-scrapling` frontend code that expects `items`, normalize it in the new Media Forge API/client layer instead of changing existing shared response conventions.

## Error Handling

Redis unavailable:

- Run creation and restart fail before creating a queued run.
- API message should clearly say task runtime is unavailable.

Detail crawl failure:

- Mark only that subtask as `crawl_failed`.
- Continue other subtasks unless a stop signal exists.

Movie persistence failure:

- Mark subtask as `save_failed`.
- Preserve `item_data` when available so restart can retry persistence.

Run-level exception:

- Mark run as `failed`.
- Store `error`.
- Preserve generated detail subtasks.

User stop:

- Set Redis stop key.
- Mark final run status `stopped` once the worker observes stop or shutdown cleanup runs.

Service restart:

- Normalize interrupted `queued` and `running` records to `stopped`.
- Require manual `重启`.

## Testing Strategy

Backend API tests:

- Creating an incremental and full run from a task.
- Redis unavailable prevents creating a stuck queued run.
- Listing runs and fetching run detail.
- Listing detail subtasks with status and keyword filters.
- Stopping a running run.
- Restarting a stopped or failed run with unfinished subtasks.
- Startup cleanup marks `queued` and `running` as `stopped` and does not enqueue work.
- Movie list pagination, search, source task filtering, sorting, and detail read.

Runtime tests:

- Redis queue enqueue/claim/finish behavior.
- Current run lock.
- Stop signal set/read/clear.
- Progress snapshot write/read.
- Runtime cleanup removes active keys.

Crawler integration tests with mocked spider callbacks:

- Detail subtasks are created from list-page batches.
- Successful detail saves become `saved`.
- Crawl errors become `crawl_failed`.
- Persistence errors become `save_failed` and keep `item_data`.
- Restart skips saved/skipped subtasks and processes only unfinished subtasks.

Frontend tests:

- Task list renders incremental/full buttons and calls the run API.
- Successful manual run navigates to `/crawler/runs`.
- Run list renders status/progress and shows `停止` or `重启` for eligible states.
- Run detail renders subtask table and filters.
- Movie list renders read-only data and detail drawer without mutation controls.

## Out of Scope

- Scheduled crawler runs.
- Batch running all enabled tasks.
- Single-page crawl.
- Per-subtask retry buttons.
- Movie deletion.
- Movie marking.
- Movie storage synchronization or push.
- Magnet selection.
- Magnet export.
- New product features unrelated to migrating and stabilizing `jav-scrapling` behavior.
