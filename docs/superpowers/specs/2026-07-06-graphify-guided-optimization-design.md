# Graphify-Guided Optimization Design

## Context

The project has a `graphify-out` directory with graph reports generated on
July 6, 2026. The report is useful, but the current root `graph.json` was built
at commit `df7424c`, while the current workspace is already at a later commit.
Several previously reported hotspots have been refactored since that graph was
generated.

The current graph is also noisy. Generated CloudDrive2 protobuf/gRPC files are
the top two graph nodes, and test files inflate several communities. Those
nodes are valuable for completeness but not useful when deciding runtime code
structure.

This design first improves graphify signal quality, then uses the graph output
as a guide for targeted code structure cleanup.

## Goals

- Make graphify reports better reflect runtime application structure.
- Add a repeatable local hotspot analysis step for graphify output.
- Refactor current code hotspots that are still valid after comparing the old
  graph to the current code.
- Remove duplicated or dead code only after reference checks prove it is safe.
- Increase robustness through focused backend and frontend tests.

## Non-Goals

- No database schema or Alembic migration changes.
- No API route or response shape changes.
- No frontend route, visible layout, or copy changes.
- No scraper behavior changes.
- No storage provider behavior changes.
- No changes to generated protobuf/gRPC code.
- No committing `graphify-out` analysis artifacts.

## Phase 1: Graphify Signal Cleanup

### `.graphifyignore`

Update `.graphifyignore` so graphify excludes noise that should not drive
architecture decisions:

- `shared/integrations/storage_providers/clouddrive2/proto/`
  - Generated protobuf/gRPC files currently dominate the graph.
- `backend/tests/`
- `frontend/src/**/__tests__/`
- `scraper/tests/`
  - Tests should not affect runtime coupling metrics.
- `graphify-out/`
- cache, build, coverage, dependency, environment, and local data directories.

Keep runtime source in scope:

- `backend/app/`
- `frontend/src/`
- `shared/`
- `scraper/`

### Hotspot Analysis Script

Add a lightweight project script such as
`scripts/analyze_graphify_hotspots.py`. It should read a graphify `graph.json`
and print a filtered report:

- graph `built_at_commit`;
- current `git rev-parse HEAD`;
- a clear warning when the graph was built from a different commit;
- top high-degree runtime nodes after excluding tests and generated code;
- top high-outdegree runtime files, which indicate modules that depend on too
  much;
- top high-indegree runtime nodes, which indicate core abstractions or
  over-shared helpers;
- a short top-N list of files requiring manual review.

The script should not replace graphify. It is a deterministic local filter for
graphify output so future optimization work starts from cleaner signals.

### Acceptance

- Generated protobuf/gRPC files no longer appear in the filtered top runtime
  hotspots.
- Test files no longer appear in filtered runtime hotspots.
- Stale graph output is explicitly flagged when the graph commit differs from
  current HEAD.
- The filtered report points to current files that still exist in the
  workspace.

## Phase 2: Crawler Runtime Executor Cleanup

### Current Problem

`backend/app/modules/crawler/runtime/executor.py` still has a large
`execute_run()` function. It owns:

- detail task lookup and in-memory indexing;
- progress state and Redis progress writes;
- crawler callbacks;
- item saved, save failed, crawl failed, already exists, and batch skipped
  handling;
- restart/detail-only branch selection;
- run result aggregation;
- final movie filter sync.

This is a current hotspot in both the old graph and current code.

### Target Boundaries

- `runtime/detail_index.py`
  - Builds and updates `code/source_url -> CrawlRunDetailTask` indexes.
  - Finds a detail task from `task_info` and optional `item_data`.

- `runtime/progress.py`
  - Owns progress counters.
  - Writes progress to `CrawlerRuntimeState`.

- `runtime/callbacks.py`
  - Builds `CrawlCallbacks`.
  - Handles batch-created, item-saved, detail-failed, already-exists, log,
    database-check, and detail-check callbacks.

- `runtime/finalize.py`
  - Counts final detail task statuses.
  - Updates `run.result`, `run.status`, `run.error`, and `run.finished_at`.
  - Publishes final run updates.
  - Runs movie filter sync on successful completion.

- `runtime/executor.py`
  - Validates task existence and task URLs.
  - Selects normal crawl versus detail restart.
  - Calls crawler engine with callbacks.
  - Delegates finalization.

### Robustness

Add tests for callback behavior:

- batch-created creates or updates detail rows;
- saved item persists movie and updates detail row;
- save failure records `save_failed`;
- crawl failure records `crawl_failed`;
- already-exists appends source task ID and preserves skipped counts.

## Phase 3: Storage Worker Step Flow Cleanup

### Current Problem

`backend/app/modules/storage/worker/steps.py` was partially split, but
`execute_current_magnet_attempt()` still coordinates too much:

- submit magnet;
- handle CloudDrive2 `10008 already exists`;
- choose poll versus recover;
- inspect existing targets when download files are not found;
- handle all-target-exist skip;
- handle multi-target copy;
- scan, classify, rename, move, verify, and clean up files.

### Target Boundaries

- `worker/download_flow.py`
  - Submits magnet downloads.
  - Converts submit-task-exists exceptions into an explicit flow result.
  - Chooses polling or recovery search.

- `worker/existing_target_flow.py`
  - Checks target folders when no downloaded file is found.
  - Handles all-target-exist skip.
  - Handles multi-target copy from an existing target.

- `worker/file_pipeline.py`
  - Runs scan, classify, rename, move, verify, cleanup.
  - Returns a structured success/failure result for the attempt.

- `worker/steps.py`
  - Plans the attempt.
  - Calls download flow.
  - Calls existing target fallback when needed.
  - Calls file pipeline when files are available.
  - Keeps subtask-level magnet attempt orchestration.

### Robustness

Add flow-level tests for:

- submit failure;
- already-exists recovery;
- no files and all targets already exist;
- multi-target copy from an existing target;
- no selected videos;
- verify failure;
- successful cleanup and result assignment.

## Phase 4: Movie Persistence And Storage Status Cleanup

### Current Problem

`backend/app/modules/content/movies/persistence.py` mixes magnet parsing,
dedupe, scoring, movie upsert, magnet upsert, best magnet selection, source
task ID append, and filter sync.

`backend/app/modules/content/movies/storage_status.py` mixes status
normalization, storage summary writes, target folder inference, remote storage
scanning, remote entry normalization, video matching, and location dedupe.

### Target Boundaries

- `movies/magnet_identity.py`
  - `extract_info_hash`
  - `build_magnet_dedupe_key`

- `movies/magnet_scoring.py`
  - size parsing;
  - Chinese subtitle detection;
  - magnet weight computation.

- `movies/magnet_persistence.py`
  - magnet normalization;
  - magnet upsert;
  - best magnet selection.

- `movies/movie_persistence.py`
  - movie unique key selection;
  - movie upsert;
  - source task ID append.

- `movies/filter_sync.py`
  - movie filter rebuilding.

- `movies/storage_locations.py`
  - source task storage-location lookup;
  - target folder spec construction;
  - target folder specs from storage subtasks.

- `movies/storage_scan.py`
  - remote entry to dictionary conversion;
  - matching-video predicate;
  - provider target-folder scan.

- `movies/storage_status.py`
  - public facade for existing imports;
  - status normalization;
  - summary write via `set_movie_storage_status`.

### Robustness

Add focused tests for:

- info hash extraction and fallback dedupe key;
- size parsing across KB, MB, GB, TB;
- Chinese subtitle detection;
- magnet normalization skipping empty rows;
- best magnet selection;
- empty movie code target folders;
- invalid source task IDs;
- provider `list_files` exceptions;
- duplicate storage locations;
- non-video and too-small files ignored.

## Phase 5: Frontend Remaining Heavy Pages

### Movie List Page

`frontend/src/pages/content/movies/MovieListPage.tsx` still owns several
behaviors directly:

- sort default parsing;
- URL `?id=` detail opening and query cleanup;
- `movie.storage.updated` realtime merge;
- detail drawer filter click behavior;
- delete confirmation and delete mode state;
- bulk push/delete composition.

Target modules:

- `hooks/useMovieListRealtime.ts`
- `hooks/useMovieListActions.ts`
- `hooks/useMovieUrlDetail.ts`
- `utils/sort.ts`
- `utils/detailFilter.ts`

### Storage Subtask Detail Page

`frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx` still mixes:

- data loading;
- realtime subscriptions;
- status, step, and log-level utilities;
- info cards;
- moved/skipped file cards;
- timeline and log presentation.

Target modules:

- `hooks/useStorageSubTaskDetail.ts`
- `hooks/useStorageSubTaskRealtime.ts`
- `utils/subtaskStatus.ts`
- `components/SubtaskInfoCard.tsx`
- `components/SubtaskFilesCard.tsx`
- reuse or align with existing `SubtaskStepTimeline` and `SubtaskLogList`
  components where present.

### Init Page

`frontend/src/pages/init/InitPage.tsx` still mixes form layout, connection test
parameter mapping, single-connection tests, save-before-test workflow, and
post-save redirect.

Target modules:

- `hooks/useInitConnectionTests.ts`
- `hooks/useInitSubmit.ts`
- `components/PostgresConfigSection.tsx`
- `components/RedisConfigSection.tsx`
- `utils/initParams.ts`

### Robustness

Add frontend tests for:

- movie URL detail open and query cleanup;
- movie storage realtime merge;
- delete mode confirm calls `deleteMovies`;
- reset filters restores defaults and sort;
- storage subtask realtime update and log append;
- storage subtask resync reload;
- timeline error color;
- init page single connection test parameters;
- init save blocked when either test fails;
- init save succeeds only after both tests pass.

## Dead Code And Redundancy Policy

Do not delete code based on graph shape alone. Deletion requires all of:

- `rg` shows no runtime references;
- the candidate is not a public compatibility facade;
- the candidate is not migration code, generated protocol code, test fixture
  code, or explicitly retained documentation;
- tests prove the behavior still passes after removal.

Preferred cleanup targets:

- duplicate implementations left behind after extraction;
- local page helpers that have been moved to hooks/utils;
- stale compatibility exports after all consumers are rewired.

## Verification Strategy

Backend:

- run focused pytest suites for crawler runtime, storage worker, movie
  persistence, and movie storage sync;
- run boundary checks to ensure moved logic is not duplicated in old modules.

Frontend:

- run focused Vitest tests for movie list, storage subtask detail, and init;
- run `npm run build`;
- run `npm run lint`.

Graphify:

- run the hotspot script against the available graph;
- verify stale commit warnings;
- verify generated proto and tests are absent from filtered hotspots.

## Acceptance Criteria

- `.graphifyignore` excludes generated proto, graph output, test trees, cache,
  build output, dependency directories, virtual environments, and local data.
- Hotspot script reports graph commit freshness and filtered top runtime
  hotspots.
- `executor.py`, `steps.py`, movie persistence/status modules, `MovieListPage`,
  `StorageSubTaskDetailPage`, and `InitPage` are thinner after extraction.
- No public API, route, database schema, storage provider behavior, crawler
  behavior, or visible frontend behavior changes.
- No generated protobuf/gRPC files are edited.
- No `graphify-out` files are committed.
