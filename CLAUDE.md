# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Media Forge — a full-stack media processing application.

## Directory Structure

```
backend/     # Server-side application (empty — not yet scaffolded)
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
