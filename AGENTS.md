# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

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
doc/         # Documentation
.venv/       # Python virtual environment (venv, Python 3.x)
```

## Environment

- **Python virtual environment**: `.venv/` at project root. Activate with `source .venv/bin/activate`.
- **Frontend**: Node.js 22+ project in `frontend/`. Run `cd frontend && npm install` to set up, then `npm run dev` to start the development server.
- No build system, package manager, or test framework configured yet for backend.

## Frontend

**Stack:** React 19 + Vite 8 + TypeScript 6 + Ant Design 6 + Tailwind CSS 4 + TanStack Router 1.x

**Key Libraries:**
- TanStack Query 5.x (server state), Zustand 5 (client state), Axios (HTTP)
- Tiptap 3 (rich text editor), @dnd-kit (drag-and-drop)
- Vitest 3 + React Testing Library (testing)

**Scripts** (run from `frontend/`):
- `npm run dev` — Start Vite dev server
- `npm run build` — Type-check + production build
- `npm run preview` — Preview production build
- `npm run lint` — ESLint
- `npm test` — Vitest (single run)
- `npm run test:ui` — Vitest UI
- `npm run test:coverage` — Vitest with coverage report

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
