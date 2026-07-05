# Crawler Runtime Scraper Decoupling Design

Date: 2026-07-06

## Context

The first codebase optimization phase has landed. The legacy `/api/movies`
backend route was removed, old frontend SSE and axios clients were removed, and
content movie query, serialization, and storage sync responsibilities were
partly extracted from the movie router.

The remaining crawler migration hotspots are:

- `/api/crawler/stream` is still mounted through
  `backend/app/modules/crawler/events/router.py` and is marked deprecated.
- `backend/app/modules/crawler/events/*` duplicates the unified realtime system
  under `backend/app/modules/realtime`.
- `backend/app/modules/crawler/runtime/service.py` directly imports and
  instantiates `scraper.services.movie_service.MovieService`.
- Runtime persistence still depends on `scraper.database.repositories.*`.
- The `scraper` package still owns orchestration and database persistence,
  while the target architecture is for it to be a pure crawling/parsing library.

This design covers the next backend-focused optimization phase. It removes the
deprecated crawler SSE stack and fully migrates crawler orchestration and movie
persistence responsibilities out of `scraper`.

## Goals

- Remove the deprecated `/api/crawler/stream` endpoint.
- Remove `backend/app/modules/crawler/events/*` and the old crawler event bus.
- Stop importing `scraper.services.movie_service` from backend runtime code.
- Stop importing `scraper.database.repositories.*` from backend runtime code.
- Move crawler orchestration into backend-defined engine boundaries.
- Move movie, magnet, and filter persistence into backend/content modules.
- Keep current crawler behavior for incremental/full runs, detail restart,
  stopping, existing-movie dedupe, logging, and realtime updates.

## Non-Goals

- Do not redesign the frontend.
- Do not change database schema or Alembic migrations.
- Do not change crawler task API contracts.
- Do not rewrite JavDB spider parsing logic.
- Do not change CloudDrive storage worker behavior.
- Do not optimize movie list SQL filtering in this phase.

## Architecture

### Backend Runtime

`backend/app/modules/crawler/runtime/service.py` remains responsible for run
lifecycle:

- enqueueing and claiming runs;
- setting queued/running/stopped/completed/failed statuses;
- resetting unfinished detail tasks on stop or restart;
- writing runtime progress;
- appending run logs;
- publishing unified realtime events through `backend.app.modules.realtime`;
- coordinating crawler engine callbacks and movie persistence.

It will no longer directly import `scraper.services.*` or
`scraper.database.repositories.*`.

### Crawler Engine

Add `backend/app/modules/crawler/runtime/engine.py`.

This module defines the backend crawler engine port and the JavDB implementation:

- `CrawlerEngine`: protocol for full task crawls and detail-task retries.
- `CrawlCallbacks`: callback bundle used by the engine to report list batches,
  saved items, detail failures, already-existing items, logs, dedupe checks, and
  stop checks.
- `JavdbCrawlerEngine`: backend-owned implementation that directly composes
  `JavdbSpider` and `MoviePipeline`.
- `get_crawler_engine()`: factory used by runtime code and tests.

The logic currently in `scraper/services/movie_service.py` moves into
`JavdbCrawlerEngine`. The engine may still import scraper primitives such as
`JavdbSpider`, `MoviePipeline`, `CookieManager`, `ScraplingFetcher`, and scraper
task schema objects, because those remain part of the pure crawling layer.

### Task Adapter

Add `backend/app/modules/crawler/runtime/task_adapter.py`.

This module translates backend ORM tasks into the lightweight task schema needed
by scraper spider code:

- backend `CrawlTask` and `CrawlTaskUrl` are converted to scraper-compatible task
  dataclasses;
- runtime code does not directly import `scraper.tasks.task_schema`;
- conversion keeps URL order, URL type, final URL, source, magnet/subtitle flags,
  skip flag, and filter configuration.

### Movie Persistence

Add `backend/app/modules/content/movies/persistence.py`.

This module owns the persistence responsibilities currently under
`scraper/database/repositories`:

- insert or reuse a movie by `code` or `source_url`;
- append source task IDs for already-existing movie codes;
- upsert magnets by movie ID and dedupe key;
- compute magnet dedupe keys and weights;
- auto-select the best magnet;
- sync the `movie_filters` cache table.

Runtime code uses this backend persistence module through small functions or a
thin service class, such as:

- `upsert_movie_with_magnets(session, item_data) -> uuid.UUID`;
- `sync_movie_filters(session) -> dict[str, int]`.

### Scraper Package

The scraper package is narrowed to crawling and parsing:

- keep config, cookies, fetchers, spider, parser, pipeline, and task schema;
- remove or stop using `scraper/services/movie_service.py`;
- remove or stop using `scraper/database/repositories/*`;
- migrate tests that validate persistence behavior to backend tests;
- keep scraper tests focused on spider/parser/result/pipeline behavior.

## Data Flow

The run flow stays behaviorally equivalent:

1. `CrawlerRunService.create_run()` creates and enqueues a run.
2. The worker claims the run and calls `_execute_run()`.
3. `_execute_run()` loads the backend `CrawlTask`.
4. `task_adapter` converts the backend task into engine input.
5. `JavdbCrawlerEngine` runs either:
   - list + detail mode through `JavdbSpider.run_task(...)`; or
   - detail retry mode through `JavdbSpider.run_detail_tasks(...)`.
6. Detail completion is cleaned with `MoviePipeline.process_item(...)`.
7. Engine callbacks return events to runtime.
8. Runtime creates or updates `CrawlRunDetailTask` rows.
9. Runtime calls backend movie persistence to save movies and magnets.
10. Runtime publishes unified realtime events through `/api/events/stream`.
11. On completion, runtime syncs movie filter cache through backend persistence.

## Behavior To Preserve

- `incremental` and `full` crawl modes keep the same API semantics.
- `INCREMENTAL_EXIST_THRESHOLD` remains read from crawler config, but the helper
  should live in backend crawler runtime/config code rather than importing
  `scraper.config.settings` from runtime service.
- Detail-phase restart still skips list collection and retries unfinished detail
  tasks only.
- Stop requests still reset unfinished detail tasks to `pending_crawl`.
- Successful detail saves still create movies, upsert magnets, and auto-select
  the best magnet.
- Existing movie codes still append `source_task_ids`.
- Run logs and detail updates still publish through the unified realtime bus.
- Removing `/api/crawler/stream` must not require frontend changes because the
  current frontend uses `/api/events/stream`.

## Deprecated SSE Removal

Remove:

- `backend/app/modules/crawler/events/router.py`;
- `backend/app/modules/crawler/events/bus.py`;
- `backend/app/modules/crawler/events/schemas.py`;
- `backend/app/modules/crawler/events/__init__.py`;
- `crawler_events_router` import and `app.include_router(crawler_events_router)`
  from `backend/app/main.py`.

Update tests:

- remove old event bus/schema tests that only cover the deprecated stack;
- add a regression test that `/api/crawler/stream` returns 404;
- keep and expand `/api/events/stream` tests for auth and realtime formatting.

## Testing Strategy

### Realtime Tests

- Assert `/api/crawler/stream` returns 404.
- Assert `/api/events/stream` still rejects missing or invalid tokens.
- Keep `format_sse_event` and owner-scoped bus tests.

### Engine Tests

Add tests for `JavdbCrawlerEngine` using fake spider and fake pipeline objects:

- `crawl_task()` triggers list-batch and item-saved callbacks;
- `crawl_detail_tasks()` supports detail retry input;
- stop callback returning true produces a stopped result;
- skipped tasks produce the same skipped result shape as before.

### Persistence Tests

Move persistence coverage into backend tests:

- movie insert by code;
- movie reuse by code/source URL;
- source task ID append;
- magnet dedupe and update;
- magnet weight and best-magnet selection;
- movie filter cache sync.

### Runtime Tests

Update runtime tests to inject or monkeypatch backend factories:

- `get_crawler_engine()`;
- `upsert_movie_with_magnets(...)`;
- `sync_movie_filters(...)`.

Existing runtime behavior assertions remain:

- run marked completed after saved item;
- persistence failure marks detail as `save_failed`;
- list-phase dedupe skips existing codes;
- detail-phase dedupe appends source task IDs;
- stop and restart behavior is preserved;
- realtime run/detail/log events still publish through unified realtime.

## Verification

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/ -v
```

Run:

```bash
cd frontend
npm test -- --run
npm run build
npm run lint
```

Run reference checks:

```bash
rg -n "backend\.app\.modules\.crawler\.events|/api/crawler/stream|scraper\.services\.movie_service|scraper\.database\.repositories" backend/app backend/tests frontend/src scraper
```

Expected remaining references:

- none in `backend/app`;
- none in `frontend/src`;
- no runtime dependency on `scraper.services.movie_service` or
  `scraper.database.repositories`;
- historical docs may still mention old paths, but active code and tests should
  not depend on them.

## Rollout Order

1. Remove deprecated crawler SSE route and old event bus tests.
2. Add backend movie persistence module and tests.
3. Add backend crawler task adapter and engine module with engine tests.
4. Update runtime service to use backend engine and persistence factories.
5. Remove scraper service/database repository modules or leave only if active
   scraper tests still require a compatibility shim.
6. Update runtime tests to patch backend boundaries instead of scraper classes.
7. Run full backend and frontend verification.

## Deferred Work

- SQL-backed movie list filtering and pagination.
- Storage worker pipeline decomposition.
- Frontend TanStack Query adoption and realtime invalidation.
- Full removal of scraper task schema if spiders can later accept backend DTOs
  directly.
