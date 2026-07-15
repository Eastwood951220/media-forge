# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

<!-- CCG-FAST-CONTEXT-START -->
## fast-context MCP

For any task that requires understanding code context, exploratory search, or
natural-language code location, prefer
`mcp__fast-context__fast_context_search` before broad manual searches.
<!-- CCG-FAST-CONTEXT-END -->

## Project Overview

Media Forge — a full-stack media processing application.

This project is a refactor and optimization of
`/Users/eastwood/Code/PycharmProjects/jav-scrapling`.

## Planning Scope

- When writing implementation plans, including plans created with
  `superpowers:writing-plans`, keep scope anchored to the refactor and
  optimization goals of the original `jav-scrapling` project.
- Do not invent or add speculative features, product expansions, or unrelated
  modules unless the user explicitly requests them.
- Plans should describe only the work needed to migrate, preserve, improve, or
  integrate existing behavior, plus directly necessary tests and documentation.

## Directory Structure

```
backend/     # FastAPI server (Python 3.12+, PostgreSQL 18, Redis 8)
frontend/    # React 19 SPA (Vite 8, TypeScript 6, Ant Design 6, Tailwind CSS 4)
shared/      # Shared Python package (shared/__init__.py exists)
docs/        # Documentation, specs, and implementation plans
data/        # Local runtime data/config/log mount target for development
output/      # Docker image tar output
.venv/       # Python virtual environment (venv, Python 3.x)
```

## Environment

- **Python virtual environment**: `.venv/` at project root. Activate with `source .venv/bin/activate`.
- **Frontend**: Node.js 22+ project in `frontend/`. Run `cd frontend && npm install` to set up, then `npm run dev` to start the development server on port `18643`.
- **Backend**: Python dependencies are installed from `backend/requirements.txt`.
- **Docker**: `make docker-build-amd64` and `make docker-build-arm64` build single-container packages that serve the frontend through the backend.

## Frontend

**Stack:** React 19 + Vite 8 + TypeScript 6 + Ant Design 6 + Tailwind CSS 4 + TanStack Router 1.x

**Key Libraries:**
- TanStack Query 5.x (server state), Zustand 5 (client state), Axios (HTTP)
- @dnd-kit (drag-and-drop), @antv/g2 (charts), Monaco Editor
- keepalive-for-react and keepalive-for-react-router (route cache)
- Vitest 3 + React Testing Library (testing)

**Structure:**
- `frontend/src/routes/` defines the TanStack Router tree, route guards, route titles, and route cache keys.
- `frontend/src/layout/` contains the authenticated shell: sidebar, header, tags view, and keep-alive outlet.
- `frontend/src/pages/` is grouped by business module: `dashboard`, `init`, `login`, `crawler`, `content/movies`, and `storage`.
- `frontend/src/api/` contains typed API wrappers. Pages should call API modules rather than importing Axios directly.
- `frontend/src/request/` owns the Axios instance, token injection, request cancellation, repeat-submit checks, optional GET cache, response transform, and error handling.
- `frontend/src/stores/` contains Zustand stores for auth, theme, and tags view state.
- `frontend/src/realtime/` contains the server-sent events client used by page hooks for live updates.
- `frontend/src/components/` is for shared components. Keep page-specific components under the relevant page module until reused.

**Routing:**
- Public routes: `/init`, `/login`.
- Authenticated layout routes: `/`, `/crawler/tasks`, `/crawler/tasks/new`, `/crawler/tasks/$id/edit`, `/crawler/runs`, `/crawler/runs/$id`, `/crawler/config`, `/content/movies`, `/storage/config`, `/storage/tasks`, `/storage/tasks/$id`, `/storage/tasks/subtasks/$id`.
- `frontend/src/routes/-guards.ts` owns initialization and auth checks.
- `frontend/src/routes/tags.ts` owns route tab metadata; update it when adding routes that should display meaningful tab titles or custom cache keys.

**Frontend module conventions:**
- Keep route entry pages named `*Page.tsx` at the module root.
- Put page-local presentational components in `components/`, page-local hooks in `hooks/`, constants in `constants/`, and pure helpers in `utils/`.
- Use the `@/` alias for imports from `frontend/src`.
- Use CSS modules with `.module.less` for page/component styles and keep global styles in `frontend/src/styles/`.
- Use TanStack Query for backend state and Zustand only for client/UI state.
- Keep realtime subscriptions inside page/module hooks and invalidate or refresh the narrowest affected state.
- When adding or changing frontend behavior, update `frontend/README.md` if module structure, routes, scripts, or core conventions change.

**Scripts** (run from `frontend/`):
- `npm run dev` — Start Vite dev server
- `npm run build` — Type-check + production build
- `npm run preview` — Preview production build
- `npm run lint` — ESLint
- `npm test` — Vitest (single run)
- `npm run test:ui` — Vitest UI
- `npm run test:coverage` — Vitest with coverage report

**Verification:**
- For frontend code changes, run `npm run build` and focused `npm test -- <path>` tests where practical.
- For shared request/routing/layout changes, run the broader `npm test` when practical.

## Backend

**Stack:** Python 3.12+ + FastAPI 0.115 + SQLAlchemy 2.0 + Alembic + asyncpg

- JWT token auth (python-jose + passlib/bcrypt)
- Redis 8 for task queue
- Shared utilities in `shared/` package (database session, models, logging)
- Pytest for testing

**Setup:**
```bash
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload --port 8000
```

On first run, the frontend will redirect to `/init` where you can configure
PostgreSQL and Redis connections. After saving, restart the backend to connect.

Once initialized:
```bash
alembic upgrade head                     # Run migrations
python scripts/init_db.py                # Create admin user
```

**Scripts** (run from `backend/`):
- `alembic upgrade head` — Apply database migrations
- `python scripts/init_db.py` — Create tables + seed admin user
- `python -m pytest tests/ -v` — Run backend tests
- `uvicorn app.main:app --reload` — Start development server
