# Media Forge Codebase Optimization Design

Date: 2026-07-05

## Context

Media Forge is a refactor and optimization of the original `jav-scrapling`
project. The current codebase already has domain-oriented modules for crawler,
storage, content movies, realtime events, and shared integrations, but several
migration-era seams remain:

- legacy backend routes coexist with the newer domain routes;
- old crawler-specific SSE code coexists with the unified realtime stream;
- frontend request infrastructure has an unused early axios client alongside the
  active `frontend/src/request` layer;
- large routers and worker services contain HTTP handling, query logic,
  serialization, provider lifecycle, and business orchestration in the same
  files;
- the crawler runtime still calls the legacy `scraper` package directly.

This design covers the first optimization phase only. It focuses on low-risk
cleanup and boundary preparation, not a large rewrite.

## Goals

- Remove code that is confirmed unused by frontend references and backend tests.
- Delete old APIs that are not used by the current frontend and are not covered
  by backend tests.
- Reduce obvious coupling in the highest-traffic backend modules without
  changing database schema or user-visible behavior.
- Preserve current frontend routes, screens, refresh behavior, and request
  semantics.
- Establish a cleaner base for later crawler/storage/content refactors.

## Non-Goals

- Do not redesign the UI.
- Do not change database schema or Alembic migrations.
- Do not migrate all frontend data loading to TanStack Query in this phase.
- Do not rewrite the storage worker pipeline.
- Do not fully decouple backend crawler runtime from the `scraper` package yet.
- Do not introduce speculative features outside the current `jav-scrapling`
  migration and optimization scope.

## Approach

Use a minimal-risk cleanup and boundary-preparation pass.

The phase removes confirmed dead code, then extracts small cohesive units from
large files where the extraction can be verified by existing tests. Behavior
changes are intentionally avoided except for removing old, unreferenced APIs.

## Backend Design

### Legacy API Removal

Remove legacy backend entry points only after reference searches and tests
confirm they are unused:

- `backend/app/modules/movies/router.py`, mounted at `/api/movies`;
- `backend/app/modules/crawler/events/*`, mounted at `/api/crawler/stream`.

The current frontend uses `/api/content/movies` for movie pages and
`/api/events/stream` for realtime events. If implementation discovers test
coverage or code references to the old routes, the route will be marked as
deprecated instead of deleted in this phase.

### Content Movie Module

Keep `backend/app/modules/content/movies/router.py` responsible for HTTP
concerns only:

- request parameters;
- dependency injection and authentication;
- translating domain errors into `HTTPException`;
- returning `success` and `paginated` responses.

Move cohesive logic into same-domain modules:

- `queries.py`: movie filtering, sorting, pagination, and filter value lookup;
- `serializers.py`: movie and magnet response payload assembly, including
  source task storage locations;
- `storage_sync_service.py`: storage provider creation, storage status sync,
  event publication, commit coordination, and provider client closing.

The existing Python-side movie filtering can remain in phase one. It is a known
performance target for a later phase, but changing it now would increase risk.

### Storage Provider Lifecycle

Provider creation and closing currently appears in several places as a repeated
pattern:

1. load storage config;
2. create CloudDrive client;
3. wrap it in `CloudDrive2Gateway`;
4. use provider;
5. close the client in a `finally` block.

Introduce a small helper or context manager in the storage config domain to
centralize this lifecycle. Use it only where the replacement is mechanical and
well covered, such as movie storage sync and movie cloud delete paths.

The storage worker pipeline remains functionally unchanged. Large-step
decomposition of `backend/app/modules/storage/worker/steps.py` is deferred
unless a pure helper can be moved without affecting execution order.

### Crawler Runtime

Do not rewrite crawler runtime execution in phase one. The runtime still calls
`scraper.services.movie_service.MovieService` and scraper repositories.

Allowed cleanup:

- remove the old crawler SSE route and event bus if unused;
- remove clearly dead fallback branches only when tests prove they are not part
  of expected behavior;
- record the direct `scraper` dependency as a phase-two boundary target.

## Frontend Design

### Request Layer

Delete `frontend/src/lib/axios.ts` if reference search confirms it is unused.
The active request layer remains `frontend/src/request`.

Clean `frontend/src/api/movie/index.ts` by removing exported functions that are
unreferenced or point to unavailable legacy endpoints, such as compatibility
helpers around old movie APIs. Keep the functions used by the current movie
page, detail drawer, storage sync, delete action, and filter configuration.

### Realtime Layer

Delete old crawler-only SSE files if unused:

- `frontend/src/api/crawler/sse.ts`;
- `frontend/src/hooks/useCrawlerSSE`.

Keep `frontend/src/realtime/eventSourceClient.ts` as the single active frontend
realtime client. Do not change page subscription behavior in phase one.

### Page State

Keep existing page-level hooks and polling behavior. In particular,
`useMovieList` keeps its 10 second polling interval to avoid changing visible
refresh behavior. A later phase can replace polling with TanStack Query
invalidation and realtime-driven refreshes.

## Error Handling And Robustness

Phase one robustness improvements are narrow and behavior-preserving:

- guarantee provider clients are closed through a shared lifecycle helper;
- keep storage sync and delete operations wrapped in rollback-aware error paths;
- preserve current HTTP status handling for unsupported delete modes and cloud
  delete failures;
- avoid silent changes to realtime reconnection and polling semantics.

## Testing And Verification

Before deleting any old module, run reference searches with `rg` for imports,
route paths, and public function names.

After implementation, run:

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

If the full suite shows that a supposedly dead API is still part of expected
behavior, keep it and document it as deprecated instead of deleting it.

## Rollout Order

1. Confirm dead-code candidates with `rg`.
2. Remove unused frontend request/SSE files and stale movie API exports.
3. Remove unused backend legacy routers and their `main.py` includes.
4. Extract content movie query and serialization helpers.
5. Introduce the storage provider lifecycle helper and apply it in narrow,
   covered paths.
6. Run backend and frontend verification.

## Deferred Work

- Move movie filtering from Python-side full-list scans to SQL-backed query
  composition where possible.
- Decouple crawler runtime from the `scraper` package through an adapter
  interface.
- Split storage worker steps by pipeline phase after current behavior is locked
  down by focused tests.
- Adopt TanStack Query consistently for frontend server state.
- Replace polling with realtime event invalidation where practical.
