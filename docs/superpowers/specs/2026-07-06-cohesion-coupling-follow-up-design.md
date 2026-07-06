# Cohesion And Coupling Follow-Up Design

## Context

The recent structure work has already split crawler runtime helpers, storage file
finder modules, movie query modules, and several frontend pages. The current
code still has four areas where responsibilities remain bundled:

- storage worker orchestration and file operations;
- crawler task HTTP router behavior;
- frontend realtime pages;
- frontend shell and request infrastructure.

This design keeps the existing behavior and public APIs stable. It only changes
module boundaries to improve cohesion and reduce coupling.

## Goals

- Make worker lifecycle, storage task processing, provider lifecycle, and movie
  storage synchronization independently understandable.
- Keep crawler task routers as thin HTTP boundaries.
- Move frontend realtime subscription and state merge logic out of page
  components.
- Split frontend shell/request infrastructure so UI side effects, request
  transforms, and cache/tag behavior are isolated.
- Preserve current routes, API response shapes, database schema, event names,
  UI behavior, and storage/crawler execution semantics.

## Non-Goals

- No database schema or Alembic migration changes.
- No new API endpoints or response shape changes.
- No route, sidebar, visual layout, or Ant Design component redesign.
- No new state management or request libraries.
- No storage provider behavior changes.
- No crawler scraping behavior changes.

## Recommended Approach

Use one implementation plan with four sequential phases:

1. Storage worker cohesion.
2. Crawler task router service extraction.
3. Frontend realtime page extraction.
4. Frontend infrastructure boundary cleanup.

This order stabilizes the backend execution paths before moving frontend
subscription and infrastructure logic. Each phase should be independently
testable and committable.

## Phase 1: Storage Worker Cohesion

### Current Problem

`backend/app/modules/storage/worker/runner.py` still owns worker lifecycle,
task processing, provider creation, subtask error handling, main task
recalculation, and movie storage status synchronization.

`backend/app/modules/storage/worker/steps.py` owns the full subtask pipeline,
magnet attempt flow, target path planning, existing-target fallback, and
success/failure finalization.

`backend/app/modules/storage/worker/file_ops.py` mixes rename behavior,
move/copy behavior, target existence checks, verification, and cleanup.

### Target Boundaries

- `worker/runner.py`
  - Starts the worker thread.
  - Claims main task IDs.
  - Runs the worker loop.
  - Delegates individual main task processing.

- `worker/task_processor.py`
  - Loads one `StorageMainTask`.
  - Applies default config values.
  - Iterates queued subtasks.
  - Handles subtask success/failure bookkeeping.
  - Recomputes and publishes main task counts.

- `worker/provider_session.py`
  - Opens and closes CloudDrive2 provider sessions.
  - Converts provider construction failures into existing subtask failure state.

- `worker/movie_sync.py`
  - Synchronizes movie storage status after subtask completion, failure, or skip.
  - Publishes `movie.storage.updated`.
  - Keeps content/movie knowledge out of `runner.py`.

- `worker/attempts.py`
  - Builds magnet dictionaries from movie records.
  - Orders magnet candidates.
  - Appends magnet attempt records.

- `worker/target_planning.py`
  - Computes download folder, preview filename, code folder, and target paths.

- `worker/rename_ops.py`
  - Owns rename target detection and `rename_selected_videos`.

- `worker/move_ops.py`
  - Owns target path construction, target existence checks, and
    `move_renamed_videos`.

- `worker/verify_ops.py`
  - Owns moved/copied file verification.

- `worker/cleanup_ops.py`
  - Owns download folder cleanup.

`file_ops.py` may become a temporary facade during the transition, but it must
not retain duplicated implementations after the phase is complete.

### Data Flow

`runner claim main task -> task_processor load config/subtasks -> provider_session open provider -> StorageWorkerContext -> execute_subtask_pipeline -> target_planning -> download/poll/recover -> scan/classify -> rename_ops -> move_ops -> verify_ops -> cleanup_ops -> movie_sync -> publish events`

## Phase 2: Crawler Task Router Service Extraction

### Current Problem

`backend/app/modules/crawler/tasks/router.py` currently mixes HTTP boundary
code with URL validation, database integrity error translation, task
serialization, extract-name scraping, runtime run creation, delete mode
validation, and storage provider creation for cloud deletion.

The router also directly imports scraper internals for `/extract-name`, which
makes the HTTP layer know crawler implementation details.

### Target Boundaries

- `tasks/service.py`
  - Application service for list/get/create/update/run/delete operations.
  - Owns repository and runtime service orchestration.

- `tasks/serializers.py`
  - Owns `CrawlTaskRead` conversion.
  - Merges latest run status into task read models.

- `tasks/validation.py`
  - Owns URL uniqueness checks.
  - Owns delete mode validation.
  - Owns duplicate-name preflight checks for create and update operations.

- `tasks/errors.py`
  - Parses `IntegrityError` constraint names.
  - Converts known constraint failures to existing HTTP status and messages.

- `tasks/name_extractor.py`
  - Owns search URL parsing.
  - Owns JAVDB page fetching and section name parsing.
  - Preserves current security-check and failure behavior.

- `tasks/provider.py`
  - Opens storage provider only for delete modes that require cloud cleanup.
  - Ensures client close behavior remains centralized.

### Data Flow

`router -> service/validation/name_extractor/provider -> repository/runtime/delete_service -> serializers -> success/paginated`

The router should keep only FastAPI dependencies, query/body declarations,
status codes, and response wrappers.

## Phase 3: Frontend Realtime Page Extraction

### Current Problem

Several page components still contain data fetching, realtime subscriptions,
event filtering, state merging, table column definitions, and UI rendering in
the same file. The highest-value candidates are:

- `frontend/src/pages/crawler/runs/RunDetailPage.tsx`;
- `frontend/src/pages/crawler/tasks/TaskListPage.tsx`;
- `frontend/src/pages/storage/tasks/StorageTaskDetailPage.tsx`;
- `frontend/src/pages/storage/tasks/StorageTaskListPage.tsx`;
- any remaining realtime logic in storage subtask detail or movie list pages.

### Target Boundaries

For crawler run detail:

- `crawler/runs/hooks/useRunDetail.ts`
  - Loads run, logs, and detail tasks.
  - Owns stop/restart actions.
  - Exposes `resyncSnapshot`.

- `crawler/runs/hooks/useRunDetailRealtime.ts`
  - Subscribes to `crawler.run.updated`.
  - Subscribes to `crawler.run.detail.updated`.
  - Subscribes to `crawler.run.log.appended`.
  - Subscribes to `system.resync_required`.
  - Preserves the current status and keyword filtering behavior.

- `crawler/runs/components/RunSummaryCard.tsx`
  - Renders run metadata and stop/restart controls.

- `crawler/runs/components/RunTaskTable.tsx`
  - Renders task filters and table.

- `crawler/runs/utils/status.ts`
  - Owns run/detail status labels and colors.

For crawler task list and storage task pages, use the same pattern:

- page files compose hooks and components;
- hooks own query and realtime behavior;
- components own cards, filters, tables, and action controls;
- utils own status labels, columns, and formatting.

### Realtime Rules

Keep existing event names and merge semantics:

- `crawler.run.updated`;
- `crawler.run.detail.updated`;
- `crawler.run.log.appended`;
- `crawler.task.status.updated`;
- `storage.main.updated`;
- `storage.main.deleted`;
- `storage.sub.updated`;
- `storage.sub.log.appended`;
- `system.resync_required`;
- `movie.storage.updated`.

Hooks may wrap these subscriptions, but they must not rename events or broaden
their scope.

## Phase 4: Frontend Infrastructure Boundary Cleanup

### TagsView

`frontend/src/layout/TagsView/index.tsx` mixes route registration, tag action
behavior, cache destruction, context menu positioning, and rendering.

Target boundaries:

- `useTagsViewRegistration`
  - Adds the current route to the visited tags store.
  - Applies the whitelist.

- `useTagsViewActions`
  - Owns close current, close others, close left, close right, close all, and
    refresh behavior.
  - Owns cache key destruction decisions.

- `useTagsContextMenu`
  - Owns menu open/close state and viewport clamping.

- `TagsBar`
  - Renders the tag strip.

- `TagsContextMenu`
  - Renders menu items and disabled states.

- `tagsViewUtils`
  - Owns removed-cache-key calculation and small pure helpers.

### Request Layer

`frontend/src/request/transform.ts` currently mixes response unwrapping,
business-code handling, session-expiry UI, auth store mutation, network error
normalization, and notification side effects.

Target boundaries:

- `request/session.ts`
  - Builds login redirect URL.
  - Owns the single relogin modal guard.
  - Calls auth logout.

- `request/businessError.ts`
  - Owns business code message lookup.
  - Creates `BusinessError` instances.

- `request/networkError.ts`
  - Normalizes Axios/network errors.
  - Extracts FastAPI `detail` payloads and wrapped backend errors.

- `request/responseTransform.ts`
  - Owns native/blob/arraybuffer returns.
  - Owns paginated response pass-through.
  - Owns normal data unwrap.
  - Delegates error/session side effects to the modules above.

The request behavior must stay compatible with current callers, including
`showError=false`, `isReturnNativeResponse`, `isTransformResponse`,
blob/arraybuffer, paginated responses, and `BusinessError`.

## Error Handling

- Storage worker provider creation failures still mark the subtask failed and
  write the existing log message.
- Storage subtask exceptions still log through `context.log`, publish subtask
  updates, and synchronize movie storage status.
- Target already exists, rename target already exists, no moved files, and
  cleanup failure branches keep their current warning/skip behavior.
- Crawler task duplicate name and duplicate URL failures keep their current
  HTTP statuses and messages.
- `/extract-name` keeps the current search URL parsing, security-check
  handling, and generic failure message behavior.
- Request layer 401 handling keeps the current relogin modal semantics.
- Realtime hooks keep current event filters and resync conditions.

## Testing Strategy

Each phase should add or preserve focused regression coverage before changing
structure.

### Storage Worker

- Verify provider lifecycle behavior for successful open, construction failure,
  and client close.
- Verify main task and subtask status transitions still match current behavior.
- Verify movie storage status sync after completed, failed, and skipped
  subtasks.
- Verify rename, move, verify, and cleanup helpers preserve current outputs and
  log side effects.

### Crawler Task Router

- Verify create/update duplicate task names.
- Verify duplicate task URLs.
- Verify `extract-name` for search URLs and JAVDB parsing failure paths.
- Verify disabled task run rejection.
- Verify delete mode validation and cloud-provider delete path close behavior.

### Frontend Realtime Pages

- Verify realtime run updates update the run card.
- Verify detail updates merge, remove, or keep rows according to status and
  keyword filters.
- Verify log appended events append logs.
- Verify `system.resync_required` triggers reload/resync.
- Verify extracted components render the same controls and table data.

### Frontend Infrastructure

- Verify TagsView close current, close others, close left, close right, close
  all, refresh, and cache-destroy behavior.
- Verify request transform success unwrap, paginated unwrap, native response,
  transformed response, blob/arraybuffer, 401, `showError=false`, FastAPI
  `detail`, wrapped backend errors, and network errors.

## Acceptance Criteria

- Existing API paths and frontend routes are unchanged.
- Existing event names and realtime subscription semantics are unchanged.
- `runner.py` no longer directly owns provider construction details or movie
  storage status sync.
- `file_ops.py` is either removed or reduced to a thin compatibility facade
  without duplicate implementations.
- `crawler/tasks/router.py` no longer imports scraper internals or storage
  provider construction details directly.
- Realtime page files primarily compose hooks and components instead of owning
  subscription internals.
- `TagsView/index.tsx` primarily composes hooks and presentational components.
- Request transform behavior is split into cohesive modules without changing
  caller-facing behavior.
- Relevant backend pytest suites, frontend Vitest tests, frontend lint, and
  frontend build pass for the touched areas.

## Implementation Notes

- Keep each phase independently committable.
- Prefer facade modules only when needed to preserve existing imports during a
  phase.
- Delete duplicate implementations once consumers are rewired.
- Do not stage unrelated historical plan/spec files.
