# Media Forge BC Phase Follow-Up Optimization Design

Date: 2026-07-06

## Context

Media Forge has completed the first codebase cleanup pass and the crawler
runtime decoupling pass. The active backend no longer depends on
`scraper.services.movie_service` or `scraper.database.repositories`, and the
deprecated crawler SSE route has been removed.

The remaining BC phase optimization targets are now concentrated in four areas:

- active-code legacy cleanup after route and crawler migration;
- the large storage worker step module;
- the storage task service boundary;
- Python-side movie list filtering and pagination.

This design keeps scope anchored to the `jav-scrapling` migration and
optimization goals. It does not add new product behavior.

## Goals

- Remove remaining active-code legacy entry points and misleading old names.
- Split storage worker steps into smaller modules with clear responsibilities.
- Reduce `StorageTaskService` coupling by moving creation, skip rules, target
  location resolution, and serialization into focused helpers.
- Move safe movie list filters, sorting, counting, and pagination toward SQL
  execution while preserving current API behavior.
- Keep each phase independently testable, committable, and revertible.

## Non-Goals

- Do not redesign the frontend.
- Do not change API response shapes.
- Do not change database schema or Alembic migrations.
- Do not change CloudDrive2 provider behavior, retry policy, or step names.
- Do not rewrite scraper parsing logic.
- Do not remove historical docs or plans that record previous decisions.
- Do not make PostgreSQL-only query behavior mandatory for SQLite tests.

## Overall Approach

Use one BC optimization track with four independent implementation phases:

1. Legacy cleanup.
2. Storage worker module split.
3. Storage task service boundary cleanup.
4. Movie query SQL pushdown.

The order is intentional. Legacy cleanup removes noise first. Worker splitting
then tackles the largest backend complexity hotspot. Storage task service
cleanup follows because it shares the storage domain but is a separate boundary.
Movie query SQL pushdown comes last because it is performance-oriented and has
more dialect-specific behavior.

Each phase should have focused regression tests and a dedicated commit.

## Phase C: Legacy Cleanup

### Scope

Remove confirmed remaining legacy artifacts from active code:

- `frontend/src/routes/index.tsx` route named `legacyCrawlTasksRoute`;
- frontend `/crawl-tasks` redirect;
- empty backend package `backend/app/modules/movies/__init__.py`;
- generated local `backend/app/modules/movies/__pycache__` files;
- active-code comments or test fake names that still describe the new crawler
  engine boundary as `MovieService`.

Keep existing deletion regression tests for removed backend APIs:

- `/api/movies` remains removed;
- `/api/crawler/stream` remains removed.

### Behavior

The official routes remain unchanged:

- crawler tasks: `/crawler/tasks` and `/api/crawler/tasks`;
- content movies: `/content/movies` and `/api/content/movies`;
- realtime: `/api/events/stream`.

No frontend navigation entry should point at `/crawl-tasks` after cleanup.

### Verification

Reference checks should return no active-code matches for:

- `legacyCrawlTasksRoute`;
- `/crawl-tasks`;
- `backend.app.modules.movies`;
- `app.modules.movies`;

Backend legacy removal tests and frontend build should pass.

## Phase A: Storage Worker Module Split

### Current Problem

`backend/app/modules/storage/worker/steps.py` is over 850 lines and mixes:

- magnet submission;
- download polling and recovery;
- file scanning and classification;
- target existence checks;
- rename and move/copy operations;
- verification;
- subtask result state updates;
- pipeline orchestration.

This makes local changes risky because behavior, side effects, and state
transitions are interleaved in one file.

### Target Modules

Keep `backend/app/modules/storage/worker/steps.py` as the public orchestration
entry point. Move cohesive behavior into new same-package modules:

- `download.py`
  - submit offline downloads;
  - classify submit-task-exists errors;
  - poll task download folders;
  - recover existing downloaded video files.
- `target_files.py`
  - list target folders;
  - detect already-existing expected target files;
  - copy existing target files to missing multi-location targets.
- `file_ops.py`
  - scan downloaded files;
  - rename selected videos;
  - move or copy renamed files;
  - verify moved and copied files;
  - clean task download folders.
- `results.py`
  - mark subtask skipped for target-exists cases;
  - mark subtask skipped for rename-name-exists cases;
  - mark success for copied-from-existing-target cases;
  - provide small result helpers for repeated state writes.
- `steps.py`
  - keep `execute_current_magnet_attempt`;
  - keep `execute_subtask_pipeline`;
  - coordinate the modules above.

### Data Contracts

Use small dataclasses for cross-step results instead of expanding ad hoc dict
contracts:

- `DownloadDiscoveryResult`;
- `ExistingTargetFilesResult`;
- `MoveRenamedVideosResult`.

The dataclasses should contain only data needed by later steps. They should not
hold database sessions or provider clients.

`StorageWorkerContext` remains the dependency container for database, provider,
config, subtask, owner, logging, and event publishing.

### Behavior Preservation

Do not change:

- storage step names;
- log message meaning;
- CloudDrive2 calls;
- polling intervals or retry counts;
- target path layout;
- rename filename policy;
- selected magnet order;
- storage status sync in the worker runner.

The split is structural. Any behavior change discovered during implementation
must be covered by an explicit test and called out separately.

### Verification

Move or add focused tests for:

- submit failure logging;
- polling until file appears;
- submit-task-exists recovery;
- target exists skip;
- multi-target copy from an existing target;
- rename target exists handling;
- verification failure.

Keep `backend/tests/test_storage_worker_pipeline.py` as an integration-style
regression for the full step path.

## Phase D: Storage Task Service Boundary Cleanup

### Current Problem

`backend/app/modules/storage/tasks/service.py` combines:

- application service methods used by routers;
- main task and subtask creation;
- skip reason classification;
- target location resolution from source crawl tasks;
- response serialization;
- movie storage summary updates;
- worker enqueue/start side effects.

The service should remain the application facade, but its internal helpers
should be moved behind clearer boundaries.

### Target Modules

Create focused modules under `backend/app/modules/storage/tasks/`:

- `creation.py`
  - create main tasks;
  - create subtasks;
  - generate aliases;
  - update movie storage summary during creation.
- `skip_rules.py`
  - `classify_storage_skip(movie) -> str | None`;
  - own `movie_not_found`, `movie_marked`, `no_magnets`, and
    `no_magnet_url`.
- `target_locations.py`
  - `resolve_target_locations(db, movie, source, selected_storage_location)`.
- `serializers.py`
  - `storage_main_task_to_dict(task) -> dict`;
  - `storage_subtask_to_dict(task) -> dict`.

Keep `service.py` as the router-facing facade:

- `create_single_push`;
- `create_batch_push`;
- `stop_main_task`;
- `restart_main_task`;
- `delete_main_task`;
- response helper delegation.

### Coupling Rules

- `StorageTaskService` may coordinate repository, config service, runtime, and
  worker startup.
- Skip rules should not depend on DB sessions.
- Target location resolution may depend on the DB session and crawl task model.
- Serializers should not publish events, commit transactions, or read config.
- Creation helpers may use `StorageTaskRepository` but should not start worker
  threads directly.

### Verification

Add or migrate tests for:

- skip rule classification;
- target location resolution for single and batch push;
- serializers preserving response shape;
- single push and batch push API behavior;
- restart and delete behavior.

Existing `backend/tests/test_storage_tasks_api.py` remains the API contract
backstop.

## Phase B: Movie Query SQL Pushdown

### Current Problem

`backend/app/modules/content/movies/queries.py` currently loads all movies, then
filters, sorts, and paginates in Python. This preserves behavior but will not
scale as the movie table grows.

### Target Shape

Keep `MovieListFilters` as the input DTO and introduce query-building helpers:

- `build_movie_list_statement(filters, sort_by, sort_order)`;
- `count_movies_for_statement(db, statement)`;
- `list_movies_page(...)` as the public facade used by the router.

The public function can choose SQL-only execution or SQL prefilter plus Python
fallback depending on active filters and database dialect.

### SQL Pushdown Candidates

Push down these filters first:

- keyword search over `code`, `source_name`, `director`, `maker`, `series`;
- `rating_min` and `rating_max`;
- `release_date_from` and `release_date_to`;
- `created_at_from` and `created_at_to`;
- `director`, `director_not`;
- `maker`, `maker_not`;
- `series`, `series_not`;
- safe sorting using `ALLOWED_SORT_FIELDS`;
- SQL count, offset, and limit when no fallback filters are active.

PostgreSQL-specific pushdown can be added with dialect guards:

- `source_task_id` array membership;
- actor and tag include/exclude;
- actor count min/max.

SQLite test fallback should remain available for array-like fields because the
project test database may not support the same PostgreSQL operators.

### Fallback Rules

Keep Python fallback for filters that are not yet safe across dialects:

- `storage_status` derived from `storage_summary`;
- array filters when running under SQLite;
- any dialect-specific expression that cannot be generated safely.

Fallback should happen after SQL prefiltering, not before. The result shape and
sort behavior must match the current contract.

### Parameter Robustness

Keep current broad API behavior in this phase. Do not introduce a stricter
validation model unless existing tests already require it.

If implementation encounters invalid date strings, it should preserve current
behavior as closely as practical and add tests for the chosen behavior.

### Verification

Add focused tests for:

- SQL-pushed keyword, rating, date, scalar filters;
- count and pagination behavior;
- sort field allowlist;
- fallback behavior for storage status and SQLite array filters.

Keep the existing original filter contract test passing unchanged.

## Cross-Phase Error Handling

- Deleted legacy routes should fail clearly with existing 404 behavior.
- Storage worker split should preserve existing non-fatal cleanup failures.
- Storage task creation should continue to classify skipped subtasks rather than
  failing a whole main task when a single movie is unusable.
- Movie query fallback should prefer correct results over incomplete SQL
  pushdown.

## Testing Strategy

Each phase should run focused tests for its touched domain.

Before final completion, run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/ -v
```

```bash
cd frontend
npm test -- --run
npm run build
npm run lint
```

If a full frontend test or lint command is not available in the local
environment, record the failure reason in the implementation handoff.

## Rollout Order

1. Phase C: remove active-code legacy artifacts.
2. Phase A: split storage worker steps while preserving pipeline behavior.
3. Phase D: extract storage task service helpers.
4. Phase B: push movie list filtering and pagination toward SQL.

Each phase should end with reference checks, focused tests, and a dedicated
commit.

## Success Criteria

- Active code contains no remaining `/crawl-tasks` legacy redirect or
  `backend.app.modules.movies` references.
- `storage/worker/steps.py` becomes a compact orchestration module instead of a
  mixed implementation module.
- `StorageTaskService` reads as an application facade instead of a holder for
  unrelated helper logic.
- Movie list queries avoid full-table Python filtering for simple common
  filters.
- Existing backend and frontend behavior remains unchanged from the user's
  perspective.
