# Media Forge Fullstack Structure Follow-Up Design

Date: 2026-07-06

## Context

The BC phase follow-up work has landed several backend improvements:

- storage worker steps were split into smaller modules;
- storage task helper modules were introduced;
- movie list queries now have SQL pushdown and PostgreSQL array handling;
- legacy crawler/movie entry points were removed.

The current code still has a few clear structural issues:

- `backend/app/modules/storage/tasks/service.py` still duplicates logic that now
  exists in `creation.py`, `serializers.py`, `skip_rules.py`, and
  `target_locations.py`;
- `backend/app/modules/crawler/runtime/service.py` still mixes worker lifecycle,
  run service methods, detail state handling, realtime publication, logs, and
  crawl execution callbacks;
- `backend/app/modules/storage/worker/file_finder.py` still combines file
  identity normalization, search result resolution, candidate filtering,
  recursive listing, and search strategy;
- `backend/app/modules/content/movies/queries.py` now works but still owns the
  filter DTO, filter option lookup, SQL builder, fallback matcher, and facade;
- several frontend pages are large enough that local components, hooks, and
  pure utilities should be split out without changing UI behavior.

This design covers a follow-up structure pass. It does not add product
features.

## Goals

- Remove backend duplicate code that remains after previous extraction work.
- Split crawler runtime into modules with clear ownership.
- Split storage file finder into identity, candidate, listing, and search
  strategy modules.
- Split movie query code into filter, option, fallback, SQL builder, and facade
  modules.
- Lightly split large frontend pages into local components, hooks, and utilities
  without changing interaction or visual design.
- Preserve current tests and public imports where practical.

## Non-Goals

- Do not change database schema or Alembic migrations.
- Do not change API response shapes or request parameters.
- Do not change crawler run semantics, crawler detail statuses, or dedupe
  behavior.
- Do not change storage worker behavior, CloudDrive2 calls, retry policy, or
  step names.
- Do not change frontend routes, visual layout, Ant Design component choices,
  or realtime subscription semantics.
- Do not introduce new state management libraries.
- Do not remove historical docs or previous plan files.

## Overall Approach

Use a backend-first sequence with a limited frontend cleanup pass:

1. Finish connecting already-extracted storage task helpers.
2. Split crawler runtime by lifecycle, events, details, and execution.
3. Split storage file finder by data normalization and search flow.
4. Split movie query modules by responsibility.
5. Split frontend large pages only into local modules.

Each phase should preserve public behavior and end with focused tests. The
frontend phase should move code, not redesign screens.

## Phase 1: Storage Task Service Redundancy Cleanup

### Current Problem

`backend/app/modules/storage/tasks/service.py` still contains duplicate code
for logic that already exists in:

- `creation.py`;
- `serializers.py`;
- `skip_rules.py`;
- `target_locations.py`.

This leaves two active implementations for the same behavior, which increases
the chance of future drift.

### Design

Make `StorageTaskService` a true application facade.

It should:

- keep router-facing methods such as `create_single_push`,
  `create_batch_push`, `stop_main_task`, `restart_main_task`, and
  `delete_main_task`;
- call `StorageTaskCreator.create_main_task(...)` from `_create_main_task`;
- own transaction commit, refresh, runtime enqueue, and worker startup after
  creation;
- delegate response serialization to `storage_main_task_to_dict` and
  `storage_subtask_to_dict`;
- keep stop/restart/delete logic in place for this phase.

It should no longer contain:

- `_load_movies`;
- `_create_subtask`;
- `_classify_skip`;
- `_resolve_target_locations`;
- `_update_movie_storage_summary`.

Imports that exist only for deleted private methods should be removed.

### Robustness

Add a regression that proves `StorageTaskService.create_single_push()` creates
tasks through the extracted creator path. Add reference checks to ensure the old
private helpers are gone from `service.py`.

## Phase 2: Crawler Runtime Split

### Current Problem

`backend/app/modules/crawler/runtime/service.py` is still a mixed module. It
contains:

- worker lock and worker loop;
- `CrawlerRunService`;
- interrupted run cleanup;
- run detail state helpers;
- realtime event publication;
- run log append and publication;
- `_execute_run` with nested engine callbacks;
- compatibility-style proxy helpers.

The module is hard to reason about because run lifecycle, event publication,
detail mutation, and crawl execution are all interleaved.

### Target Modules

Create these modules under `backend/app/modules/crawler/runtime/`:

- `worker.py`
  - worker lock and worker running flag;
  - worker start and loop;
  - `process_next_run`;
  - `process_run`;
  - interrupted run cleanup.
- `events.py`
  - run owner lookup;
  - `publish_run_updated`;
  - `publish_run_detail_updated`;
  - `publish_queue_updated`;
  - `append_run_log_for_run`.
- `details.py`
  - detail status constants;
  - `has_detail_phase_started`;
  - `reset_unfinished_detail_tasks_to_pending`;
  - `clear_run_detail_tasks`;
  - `count_run_detail_tasks`;
  - detail row conversion helpers.
- `executor.py`
  - execute a crawl run;
  - build crawler engine callbacks;
  - update run progress;
  - persist crawled movies;
  - sync movie filters after successful completion.
- `service.py`
  - keep `CrawlerRunService`;
  - delegate worker start and execution;
  - keep compatibility imports for `process_next_run`, `process_run`,
    `publish_run_updated`, `publish_run_detail_updated`, and
    `append_run_log_for_run` so current tests and routers can continue
    importing them from `service.py` during this phase.

### Behavior Preservation

Do not change:

- run statuses: `queued`, `running`, `stopped`, `failed`, `completed`;
- detail statuses: `pending_crawl`, `saved`, `skipped`, `crawl_failed`,
  `save_failed`;
- realtime event names or payload shapes;
- engine callback names and argument shapes;
- dedupe checks or source task ID append behavior.

Remove pure proxy functions such as `_read_incremental_threshold_from_conf` and
`_persist_crawled_item` when their direct replacements are already imported.

### Robustness

Focused tests should cover:

- stop and restart;
- detail-phase restart;
- list-stage restart;
- save failure;
- existing movie skipped in list phase;
- existing movie skipped in detail phase;
- realtime run and detail update events.

## Phase 3: Storage File Finder Split

### Current Problem

`backend/app/modules/storage/worker/file_finder.py` owns several separate
responsibilities:

- remote file object normalization;
- virtual search path detection;
- search result original path resolution;
- candidate rejection and accepted file construction;
- recursive listing;
- search and recovery strategies;
- log context assembly.

This makes small fixes to one path risky because the helper names and side
effects are tightly packed.

### Target Modules

Split the file finder into:

- `file_identity.py`
  - raw remote file to dict;
  - virtual search path detection;
  - search-result detection;
  - original path resolution.
- `file_candidates.py`
  - video usability checks;
  - path scope checks;
  - movie code matching;
  - rejection reason construction;
  - accepted candidate append logic.
- `file_listing.py`
  - recursive listing;
  - loop and depth handling;
  - list-based video discovery.
- `file_search.py`
  - `ScopedSearchResult`;
  - scoped search flow;
  - existing file search;
  - recovery search.
- `file_finder.py`
  - thin compatibility facade and public re-exports.

### Behavior Preservation

Do not change:

- `ScopedSearchResult.log_context` keys;
- accepted file dict shape;
- rejected file reason strings;
- `[Search]` virtual path filtering;
- `get_original_path` failure behavior;
- recursive max-depth and loop detection;
- public functions imported by `download.py` and tests.

### Robustness

Add focused tests for candidate rejection reasons and original-path failure.
Keep the existing storage file finder scope tests passing.

## Phase 4: Movie Query Module Split

### Current Problem

`backend/app/modules/content/movies/queries.py` has grown into a mixed module
that contains:

- `MovieListFilters`;
- filter option lookup;
- Python fallback matching;
- parsing helpers;
- SQL builder;
- count helper;
- public `list_movies_page` facade.

The behavior is useful, but future query changes will be safer if the parts are
separated.

### Target Modules

Split movie query code into:

- `filters.py`
  - `MovieListFilters`;
  - `split_csv`;
  - `VALID_FILTER_TYPES`.
- `filter_options.py`
  - SQLite filter value fallback;
  - cache-backed filter values;
  - `list_filter_values`.
- `fallback.py`
  - `movie_matches`;
  - fallback-only helper functions.
- `sql_builder.py`
  - `ALLOWED_SORT_FIELDS`;
  - date and UUID parsing helpers;
  - PostgreSQL array containment helper;
  - fallback detector;
  - statement builder;
  - count helper;
  - sort normalization.
- `queries.py`
  - public `list_movies_page` facade;
  - re-export public names that routers and tests currently import.

### Behavior Preservation

Do not change:

- movie API query parameter semantics;
- filter option response shape;
- SQLite fallback behavior;
- PostgreSQL array query behavior;
- movie API response shape.

### Robustness

Add import-level regression so existing imports from `queries.py` continue to
work. Keep the movie API and query SQL tests passing.

## Phase 5: Frontend Lightweight Splits

### Current Problem

Several frontend page files contain local components, data effects, formatting
helpers, and page composition in one file. This makes changes harder to review,
even when UI behavior is stable.

### Target Splits

Only split local structure. Do not change UI behavior.

For `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`:

- move `UrlEntryCard` to `components/UrlEntryCard.tsx`;
- move submit orchestration into `hooks/useTaskFormSubmit.ts` if it can be done
  without changing form behavior;
- keep route params, form initialization, and navigation in the page.

For `frontend/src/pages/storage/config/StorageConfigPage.tsx`:

- move `SectionTitle` to `components/SectionTitle.tsx`;
- move `SelectTags` to `components/SelectTags.tsx`;
- move `TestResultCard` to `components/TestResultCard.tsx`;
- move `getErrorMessage` to `utils/error.ts`.

For `frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx`:

- move timeline display to `components/SubtaskStepTimeline.tsx`;
- move log list rendering to `components/SubtaskLogList.tsx`;
- move time formatting and step helpers to `utils/format.ts` or
  `utils/steps.ts`.

For `frontend/src/pages/content/movies/MovieListPage.tsx`:

- move realtime subscription effect to `hooks/useMovieListRealtime.ts`;
- move sort default parsing to `utils/sort.ts`;
- keep table, filter bar, drawer, and modal behavior unchanged.

### Constraints

- Keep Ant Design structure and styling unchanged.
- Keep routes unchanged.
- Keep API hook arguments unchanged.
- Keep realtime subscription semantics unchanged.
- Keep modules local to each page unless already shared elsewhere.

### Verification

Run frontend tests, build, and lint. Add small unit tests only for pure utility
functions when they already fit the existing test setup.

## Cross-Cutting Error Handling

- Prefer deleting duplicate code after its extracted replacement is wired into
  callers.
- Preserve existing log messages and realtime payloads unless a test proves the
  current behavior is wrong.
- Keep fallback paths for SQLite tests and PostgreSQL production behavior.
- Stop and fix the owning phase if reference checks show two active
  implementations remain.

## Testing Strategy

Run focused backend tests per phase:

- storage task service and API tests;
- crawler worker/runtime/realtime tests;
- storage file finder and storage worker tests;
- content movie API and query tests.

Run frontend verification after frontend splits:

```bash
cd frontend
npm test -- --run
npm run build
npm run lint
```

Run backend full tests before final handoff:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/ -v
```

## Success Criteria

- `storage/tasks/service.py` no longer duplicates helper logic already present
  in extracted storage task modules.
- `crawler/runtime/service.py` becomes a small service facade instead of the
  executor/event/worker/detail implementation module.
- `storage/worker/file_finder.py` becomes a compatibility facade or thin public
  entrypoint.
- `content/movies/queries.py` becomes a facade over focused query modules.
- Large frontend pages become smaller composition files with local components,
  hooks, and pure utilities split out.
- Public behavior and tests remain stable.
