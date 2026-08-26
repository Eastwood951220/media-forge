# AGENTS.md

This file provides guidance to Codex when working with code in this repository.

<!-- CCG-FAST-CONTEXT-START -->
## fast-context MCP

For any task that requires understanding code context, exploratory search, or
natural-language code location, prefer
`mcp__fast-context__fast_context_search` before broad manual searches.
<!-- CCG-FAST-CONTEXT-END -->

## Project Overview

Media Forge is a full-stack media processing application. It includes a FastAPI
backend, a React/Vite frontend, a Python crawler package, shared Python
libraries, and a Chrome browser extension used by crawler agent workflows.

## Planning Scope

- Keep implementation plans anchored to existing Media Forge behavior and the
  current repository structure.
- Do not invent or add speculative features, product expansions, or unrelated
  modules unless the user explicitly requests them.
- Plans should describe only the work needed to preserve, improve, integrate,
  or verify existing behavior, plus directly necessary tests and documentation.
- When executing a plan, do not create or use a Git worktree. Work in this
  checkout and create or switch ordinary Git branches when isolation is needed.

## Git Workflow and Commit Filtering

- Never create or use a Git worktree for this repository.
- Use ordinary Git branches only when branch isolation is required.
- At the end of completed work, automatically create commits grouped by
  functional change, even when the task was not executed from a written plan,
  unless the user explicitly asks not to commit.
- Stage intended source files explicitly instead of using broad commands such
  as `git add .` or `git add -A`, because already tracked files are not
  excluded by `.gitignore`.
- Before every commit, inspect `git diff --cached --name-only` to confirm only
  intended files are staged.
- Do not remove existing test files or Superpowers documents from Git tracking
  unless the user explicitly requests that separate repository cleanup.

## Top-Level Directory Structure

```
backend/          # FastAPI server, API modules, Alembic migrations, backend tests
frontend/         # React 19 SPA built with Vite, TypeScript, Ant Design, Tailwind
scraper/          # Python crawler package: fetchers, spiders, pipelines, task schemas
shared/           # Shared Python package for database, runtime config, logging, schemas
chrome-extension/ # Chrome extension for browser-assisted crawler agent workflows
docs/             # Documentation, specs, and implementation plans
data/             # Local runtime data, configs, cookies, logs, and mount targets
output/           # Docker image tar output
```

## Environment

- **Python**: Use the system or configured project Python directly. Do not
  assume a repository-managed virtual environment is required.
- **Backend dependencies**: Install from `backend/requirements.txt`.
- **Frontend**: Use Node.js plus pnpm in `frontend/`.
- **Chrome extension**: Use Node.js plus pnpm in `chrome-extension/`.
- **Docker**: `make docker-build-amd64` and `make docker-build-arm64` build
  single-container packages that serve the frontend through the backend.
- **Development ports**: frontend development server uses `18643`; backend
  service uses `18642` in the documented local setup.

## Backend

**Stack:** Python 3.12+ + FastAPI + SQLAlchemy 2.0 + Alembic + asyncpg.

**Major folders:**

- `backend/app/main.py` creates the FastAPI application and wires routers,
  middleware, exception handling, and startup behavior.
- `backend/app/core/` contains configuration, dependencies, exception handlers,
  and auth/security helpers.
- `backend/app/modules/` contains feature API modules:
  `auth`, `dashboard`, `health`, `init`, `realtime`, `content`, `crawler`, and
  `storage`.
- `backend/app/modules/crawler/` contains crawler-facing API and runtime
  integration areas: agent, config, runs, runtime, and tasks.
- `backend/app/modules/storage/` contains storage config, indexing, runtime,
  task APIs, and worker logic.
- `backend/app/models/` contains backend ORM/domain models for users, crawler
  tasks/runs/agents, storage tasks, and enums.
- `backend/app/repositories/` contains persistence helpers and repository
  abstractions.
- `backend/app/schemas/` contains Pydantic request/response schemas shared by
  backend routes.
- `backend/alembic/` contains database migrations.
- `backend/scripts/` contains operational scripts such as database
  initialization.
- `backend/tests/` contains backend pytest tests.

**Common commands** (run from repository root unless noted):

```bash
pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --reload --port 18642
cd backend && alembic upgrade head
cd backend && python scripts/init_db.py
cd backend && python -m pytest tests/ -v
```

On first run, the frontend redirects to `/init` to configure PostgreSQL and
Redis. After saving configuration, restart the backend so it reconnects using
the stored settings.

## Frontend

**Stack:** React 19 + Vite 8 + TypeScript 6 + Ant Design 6 + Tailwind CSS 4 +
TanStack Router 1.x.

**Key libraries:**

- TanStack Query for server state; Zustand for client/UI state.
- Axios through the local request layer for HTTP.
- @dnd-kit for drag and drop, @antv/g2 for charts, Monaco Editor for JSON
  editing, and keepalive-for-react for route caching.
- Vitest and React Testing Library for tests.

**Major folders:**

- `frontend/src/routes/` defines the TanStack Router tree, route guards, route
  titles, and route cache keys.
- `frontend/src/layout/` contains the authenticated shell: sidebar, header,
  tags view, and keep-alive outlet.
- `frontend/src/pages/` contains route-level feature modules:
  `dashboard`, `init`, `login`, `crawler`, `content/movies`, and `storage`.
- `frontend/src/pages/crawler/` contains crawler task, run, config, and shared
  UI code.
- `frontend/src/pages/storage/` contains storage config, task list/detail,
  subtask, hook, and utility code.
- `frontend/src/pages/content/movies/` contains movie list/detail, filters,
  constants, hooks, tests, and helpers.
- `frontend/src/api/` contains typed API wrappers and query key/invalidation
  helpers. Pages should call API modules rather than importing Axios directly.
- `frontend/src/request/` owns the Axios instance, token injection, request
  cancellation, repeat-submit checks, optional GET cache, response transforms,
  and error handling.
- `frontend/src/stores/` contains Zustand stores for auth, theme, and tags view
  state.
- `frontend/src/realtime/` contains the server-sent events client used by page
  hooks for live updates.
- `frontend/src/components/` is for shared components. Keep page-specific
  components under the relevant page module until reused.
- `frontend/tests/` contains frontend test setup and cross-cutting tests.

**Routing:**

- Public routes: `/init`, `/login`.
- Authenticated layout routes include `/`, `/crawler/tasks`,
  `/crawler/tasks/new`, `/crawler/tasks/$id/edit`, `/crawler/runs`,
  `/crawler/runs/$id`, `/crawler/config`, `/content/movies`,
  `/storage/config`, `/storage/tasks`, `/storage/tasks/$id`, and
  `/storage/tasks/subtasks/$id`.
- `frontend/src/routes/-guards.ts` owns initialization and auth checks.
- `frontend/src/routes/tags.ts` owns route tab metadata. Update it when adding
  routes that need meaningful tab titles or custom cache keys.

**Frontend conventions:**

- Keep route entry pages named `*Page.tsx` at the module root.
- Put page-local presentational components in `components/`, page-local hooks
  in `hooks/`, constants in `constants/`, and pure helpers in `utils/`.
- Use the `@/` alias for imports from `frontend/src`.
- Use CSS modules with `.module.less` for page/component styles and keep global
  styles in `frontend/src/styles/`.
- Use TanStack Query for backend state and Zustand only for client/UI state.
- Keep realtime subscriptions inside page/module hooks and invalidate or
  refresh the narrowest affected state.
- When adding or changing frontend behavior, update `frontend/README.md` if
  module structure, routes, scripts, or core conventions change.

**Commands** (run from `frontend/`):

```bash
pnpm install
pnpm dev
pnpm build
pnpm preview
pnpm lint
pnpm test
pnpm test:ui
pnpm test:coverage
```

**Verification:**

- For frontend code changes, run `pnpm build` and focused
  `pnpm test -- <path>` tests where practical.
- For shared request/routing/layout changes, run the broader `pnpm test` when
  practical.

## Scraper

The `scraper/` package contains crawler implementation code used by backend
crawler workflows.

**Major folders:**

- `scraper/config/` contains crawler settings, logging configuration, and site
  configuration.
- `scraper/core/` contains crawler constants, exceptions, security/access-state
  handling, throttling, and utility functions.
- `scraper/fetchers/` contains site fetcher abstractions and concrete fetcher
  implementations.
- `scraper/pipelines/` contains base and movie pipelines for processing parsed
  crawler results.
- `scraper/spiders/` contains the spider base classes, plugin/registry code,
  and site-specific spiders.
- `scraper/spiders/javbus/` contains JavBus parser and spider code.
- `scraper/spiders/javdb/` contains JavDB constants, URL helpers, schema,
  parser, and spider code.
- `scraper/tasks/` contains crawler task schemas and task utility functions.
- `scraper/cookies/` contains cookie management logic; `scraper/cookies/storage/`
  contains local cookie files used in development.
- `scraper/tests/` contains crawler unit tests.

**Verification:**

```bash
python -m pytest scraper/tests -v
```

## Shared Python Package

The `shared/` package contains reusable Python code imported by backend and
scraper modules.

**Major folders:**

- `shared/runtime_config.py` loads runtime configuration shared across
  processes.
- `shared/common/` contains generic helpers such as datetime utilities.
- `shared/database/` contains PostgreSQL config, SQLAlchemy session handling,
  custom types, and shared database models.
- `shared/database/models/` contains shared ORM model declarations.
- `shared/integrations/` contains integration code; storage provider
  integrations live under `shared/integrations/storage_providers/`.
- `shared/logging/` contains file logging, handler setup, and JSONL logging
  utilities.
- `shared/schemas/` contains common Pydantic schema definitions.

## Chrome Extension

The `chrome-extension/` project is a Vite/TypeScript Chrome extension for
browser-assisted crawler agent workflows.

**Major files and folders:**

- `chrome-extension/manifest.json` defines the Chrome extension manifest.
- `chrome-extension/src/background.ts` contains the extension background entry.
- `chrome-extension/src/content.ts` contains the content script entry.
- `chrome-extension/src/popup.ts` and `chrome-extension/popup.html` implement
  the popup UI.
- `chrome-extension/src/options.ts` and `chrome-extension/options.html`
  implement the options UI.
- `chrome-extension/src/agentClient.ts` contains backend/agent communication.
- `chrome-extension/src/protocol.ts` contains message and protocol types.
- `chrome-extension/src/taskRunner.ts` contains browser task execution logic.
- `chrome-extension/src/diagnostics.ts` contains diagnostic helpers.
- `chrome-extension/scripts/verify-agent-extension.mjs` verifies built
  extension output.
- `chrome-extension/dist/` contains generated build output and should not be
  edited by hand.

**Commands** (run from `chrome-extension/`):

```bash
pnpm install
pnpm build
pnpm typecheck
pnpm test
node scripts/verify-agent-extension.mjs
```

## General Verification Guidance

- Match verification scope to the touched area.
- Backend/API changes: run focused pytest tests first, then broader backend
  tests when behavior crosses modules.
- Scraper changes: run focused `scraper/tests` tests for the affected spider,
  fetcher, pipeline, or task utilities.
- Frontend changes: run `pnpm build` and focused Vitest tests.
- Chrome extension changes: run `pnpm typecheck`, `pnpm test`, `pnpm build`,
  and the extension verification script when practical.
