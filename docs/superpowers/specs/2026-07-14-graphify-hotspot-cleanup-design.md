# Graphify Hotspot Cleanup Design

## Context

The current root graphify report in `graphify-out/GRAPH_REPORT.md` was built
from commit `cda80331`, which matches the current repository HEAD at the time
of this design. Older dated graph outputs under `graphify-out/2026-07-14/` are
stale and should not drive this round.

Earlier graphify-guided work has already split several large modules:

- crawler runtime helpers;
- movie magnet and persistence helpers;
- movie storage status helpers;
- movie list hooks and components;
- frontend request submodules.

The next pass should therefore be a medium-scope cleanup, not a broad rewrite.
It should focus on current graphify high-outdegree hotspots, remove only
verified dead or redundant code, and keep all public behavior stable.

## Goals

- Use current graphify hotspots to prioritize cleanup work.
- Thin high-outdegree backend and frontend modules without changing behavior.
- Remove dead code, unused exports, obsolete compatibility wrappers, and
  generated cache files only after reference checks prove they are safe.
- Improve cohesion by moving pure or narrowly scoped logic out of orchestration
  modules.
- Preserve existing tests and add focused tests only where extracted logic
  needs direct coverage.

## Non-Goals

- No database schema or Alembic migration changes.
- No API route, response shape, status code, event name, or UI behavior changes.
- No storage provider behavior changes.
- No crawler scraping semantics changes.
- No generated protobuf/gRPC changes.
- No committing graphify output artifacts.
- No speculative feature work beyond the existing `jav-scrapling` refactor and
  optimization scope.

## Recommended Approach

Use a graphify-hotspot-first cleanup with conservative deletion rules.

The implementation should prioritize files that remain high-outdegree in the
current filtered graph report, then apply reference checks before deleting or
moving code. Refactors should be thin module-boundary improvements: routers
stay HTTP-only, services stay public orchestration entry points, and helper
modules own pure or narrowly scoped behavior.

This approach fits the requested medium scope. It improves coupling where the
graph shows pressure while avoiding a deep rewrite of already-refactored areas.

## Backend Design

### Crawler Runtime

`backend/app/modules/crawler/runtime/threaded.py` and
`backend/app/modules/crawler/runtime/service.py` remain graphify hotspots. Some
of that coupling is expected because they are runtime entry points, so the
cleanup should avoid splitting them into excessive layers.

Target boundaries:

- `threaded.py`
  - Keep thread lifecycle, fallback execution, and worker process boundaries.
  - Move reusable run status and queue snapshot assembly into narrower helper
    functions or modules if current code duplicates those concerns.

- `service.py`
  - Keep the public `CrawlerRunService` application-service interface.
  - Extract pure helper logic for restart/retry detail selection, temporary
    detail run setup, and worker-start idempotence if those concerns are still
    embedded in methods.

- Existing runtime modules
  - Keep `executor.py`, `callbacks.py`, `detail_index.py`, `progress.py`, and
    `finalize.py` as the current behavior boundaries.
  - Only remove unused imports, obsolete wrappers, or duplicated logic after
    `rg` reference checks.

The crawler runtime verification should include existing worker/runtime tests
that cover run creation, queue behavior, retry, restart, threaded completion,
and realtime update behavior.

### Movies Router

`backend/app/modules/content/movies/router.py` is still a high-outdegree file.
It should become a thinner FastAPI boundary.

Target boundaries:

- Router keeps:
  - route declarations;
  - FastAPI dependencies;
  - query and body parameter declarations;
  - response wrapping;
  - HTTP exception translation.

- Service/helper modules own:
  - filter config read/write wrappers;
  - batch and single storage sync orchestration;
  - delete request validation and dispatch;
  - storage index missing error translation where it is not HTTP-specific.

Existing route paths, parameters, response fields, and status behavior must stay
unchanged.

Verification should include content movie API tests, movie persistence tests,
and any storage-sync tests affected by moved logic.

### Storage Index

`backend/app/modules/storage/index/store.py` is a graphify god node because it
is a core store abstraction. The cleanup should reduce internal bulk without
splitting file IO across too many modules.

Target boundaries:

- `StorageIndexStore` keeps:
  - public store API;
  - atomic JSON file reads and writes;
  - temp index lifecycle;
  - metadata persistence.

- Extract pure helpers when useful for:
  - tree construction from records;
  - record insertion into the tree;
  - known code folder path extraction;
  - metadata merge/finalization.

`router.py`, `background.py`, and `refresh.py` should retain their current
external behavior. Cleanup should focus on duplicate status payload assembly and
refresh-start error handling if those are repeated.

Verification should include storage index store, refresh, and API tests.

## Frontend Design

### Movie List Page

`frontend/src/pages/content/movies/MovieListPage.tsx` is already partially
split but should be reduced to page composition.

Target boundaries:

- Page keeps:
  - composing filter bar, table, drawers, and modal components;
  - wiring hooks together;
  - passing controlled props and callbacks.

- Hooks/helpers own:
  - batch delete and storage push actions;
  - detail drawer opening;
  - URL detail parameter synchronization;
  - refresh, selection clear, and modal close coordination where duplicated.

No filter fields, table columns, action labels, or URL parameter semantics
should change.

### Request Layer

`frontend/src/request/index.ts` is a high-outdegree public entry point. That is
acceptable, but it should not contain unnecessary internal policy details.

Target boundaries:

- Preserve `request.get`, `request.post`, `request.put`, `request.delete`, and
  existing external request API behavior.
- Move pure internals such as header construction, repeat strategy selection,
  and method wrapper construction into private helpers if they remain embedded
  in the entry file.
- Keep interceptors, error handling, request cache, request cancellation, and
  repeat-submit semantics unchanged.

Verification should include request transform tests, lint, and type checking.

### Crawler Run Task Table

`frontend/src/pages/crawler/runs/components/RunTaskTable.tsx` mixes table
composition, toolbar controls, column rendering, selection state integration,
and retry confirmation logic.

Target boundaries:

- `RunTaskTable.tsx`
  - Keep table composition and controlled props.

- New or existing focused modules may own:
  - toolbar filters and batch retry controls;
  - column definitions and status rendering;
  - single-row and batch retry confirmation helpers.

Retry confirmation text, button enabled states, filter options, column
semantics, and table pagination behavior must stay unchanged.

## Dead Code And Redundancy Rules

Code may be deleted only when one of these is true:

- `rg` proves an export, function, or compatibility wrapper has no production
  references and no meaningful public contract.
- A duplicate implementation can be replaced by an existing helper without
  changing call behavior.
- Generated cache files such as `__pycache__` or `.pyc` are untracked or safely
  removable from the repository.

When a candidate is referenced only from tests, decide whether the test is
covering a public contract. If the contract is still useful, keep the code or
move the test to the new public boundary instead of deleting blindly.

## Execution Order

1. Establish the baseline.
   - Check `git diff` and identify files with pre-existing uncommitted changes.
   - Run the graphify hotspot analyzer against the current root graph.
   - Use `rg` for all deletion candidates.

2. Backend cleanup.
   - Start with `storage/index` because the scope is narrow and tests are
     concentrated.
   - Then thin `content/movies/router.py`.
   - Finally handle `crawler/runtime/service.py` and `threaded.py`.

3. Frontend cleanup.
   - Start with `request/index.ts`.
   - Then split `RunTaskTable.tsx`.
   - Finish with `MovieListPage.tsx`, because it has more current workspace
     churn.

4. Final cleanup and verification.
   - Remove only verified dead code and generated cache artifacts.
   - Run targeted backend and frontend tests.
   - Run broader build/type/lint checks where practical.

## Verification Plan

Backend:

- `python -m pytest backend/tests/test_graphify_hotspots.py -v`
- crawler runtime and worker tests affected by runtime changes;
- content movie API and persistence tests affected by router/service changes;
- storage index store, refresh, and API tests affected by store/router changes.

Frontend:

- `npm run lint`
- request transform tests;
- movie list tests affected by page controller or hook changes;
- crawler run detail/table tests affected by task table extraction;
- `npm run build` for TypeScript and production build validation.

If any verification fails because of pre-existing workspace state, document the
exact failing command and reason before proceeding.

## Acceptance Criteria

- Current graphify high-outdegree hotspot files have thinner, clearer
  responsibilities.
- All deleted code has reference-check evidence.
- Public API, route, response, event, task execution, storage sync, and UI
  behavior remain unchanged.
- No generated protobuf/gRPC files or graphify output artifacts are committed.
- Relevant backend and frontend tests pass, or unrelated pre-existing failures
  are clearly recorded.
