# Add Less Support & Reorganize src/ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Less CSS preprocessor support and reorganize `src/` so only `App.tsx` and `main.tsx` live at the root level — all other files move to purpose-named subdirectories (`src/styles/`, `src/types/`) or `tests/`.

**Architecture:** Two independent changes: (1) install `less` + configure Vite Less preprocessor; (2) move loose `src/` files into `src/styles/`, `src/types/`, and `tests/`, updating imports and config paths accordingly.

**Tech Stack:** Less 4.x, Vite 8 CSS preprocessor options

## Global Constraints

- `src/` root must contain ONLY `main.tsx` and `App.tsx` after the refactor
- All existing functionality must continue working (tsc, lint, build, test)
- Tailwind CSS 4 `@import "tailwindcss"` stays in `.css` (not converted to Less)
- Less is added for future `.less` component styles
- No TypeScript errors, no ESLint errors, smoke test passes after every task

---

### Task 1: Add Less support

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.ts:33-35`
- Reinstall: `frontend/node_modules/`, `frontend/package-lock.json`

**Interfaces:**
- Produces: Less preprocessor available for `.less` imports in Vite dev/build

- [ ] **Step 1: Install less devDependency**

Run: `cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npm install -D less`

Expected: `less` added to `devDependencies` in `package.json`.

- [ ] **Step 2: Update vite.config.ts — add Less preprocessor options**

Current (lines 33-35):
```typescript
  css: {
    preprocessorOptions: {},
  },
```

Replace with:
```typescript
  css: {
    preprocessorOptions: {
      less: {
        javascriptEnabled: true,
        modifyVars: {},
      },
    },
  },
```

- [ ] **Step 3: Verify Vite loads**

Run: `cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx vite --version`

Expected: Prints Vite version, no config errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f package.json package-lock.json vite.config.ts
git commit -m "chore: add Less preprocessor support"
```

---

### Task 2: Move CSS to `src/styles/` and update import

**Files:**
- Move: `frontend/src/app.css` → `frontend/src/styles/app.css`
- Modify: `frontend/src/App.tsx:1`

**Interfaces:**
- Consumes: existing `app.css` content
- Produces: `src/styles/app.css`, `App.tsx` imports from `'./styles/app.css'`

- [ ] **Step 1: Create styles directory and move file**

```bash
mkdir -p frontend/src/styles
mv frontend/src/app.css frontend/src/styles/app.css
```

- [ ] **Step 2: Update App.tsx CSS import**

Change line 1 from:
```typescript
import './app.css'
```
To:
```typescript
import './styles/app.css'
```

- [ ] **Step 3: Verify tsc + build**

Run: `cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b && npm run build 2>&1 | tail -3`

Expected: Zero type errors, build succeeds.

- [ ] **Step 4: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/styles/app.css src/App.tsx
git rm --cached src/app.css 2>/dev/null
git add -f src/app.css 2>/dev/null  # if git rm fails, force re-stage the deletion
git commit -m "refactor: move app.css to src/styles/"
```

---

### Task 3: Move type declarations to `src/types/`

**Files:**
- Move: `frontend/src/env.d.ts` → `frontend/src/types/env.d.ts`
- Move: `frontend/src/auto-imports.d.ts` → `frontend/src/types/auto-imports.d.ts`
- Modify: `frontend/vite.config.ts:25` (auto-import dts path)

**Interfaces:**
- Produces: type declarations in `src/types/`, auto-import dts path updated

- [ ] **Step 1: Create types directory and move files**

```bash
mkdir -p frontend/src/types
mv frontend/src/env.d.ts frontend/src/types/env.d.ts
mv frontend/src/auto-imports.d.ts frontend/src/types/auto-imports.d.ts
```

- [ ] **Step 2: Update vite.config.ts auto-import dts path**

Change line 25 from:
```typescript
      dts: 'src/auto-imports.d.ts',
```
To:
```typescript
      dts: 'src/types/auto-imports.d.ts',
```

- [ ] **Step 3: Regenerate auto-imports.d.ts at new path**

Run: `cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx vite build 2>&1 | tail -5`

The auto-import plugin generates the `.d.ts` file during build. Verify it exists at the new path:

```bash
ls frontend/src/types/auto-imports.d.ts
```

Expected: File exists.

- [ ] **Step 4: Verify tsc**

Run: `cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b`

Expected: Zero type errors (type declarations are still inside `src/` which is included by tsconfig).

- [ ] **Step 5: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/types/env.d.ts src/types/auto-imports.d.ts vite.config.ts
git rm --cached src/env.d.ts src/auto-imports.d.ts 2>/dev/null
git add -f src/env.d.ts src/auto-imports.d.ts 2>/dev/null
git commit -m "refactor: move type declarations to src/types/"
```

---

### Task 4: Move test files to `tests/` and update configs

**Files:**
- Move: `frontend/src/App.test.tsx` → `frontend/tests/App.test.tsx`
- Move: `frontend/src/test-setup.ts` → `frontend/tests/setup.ts`
- Modify: `frontend/vitest.config.ts:8` (setupFiles path)
- Modify: `frontend/tsconfig.app.json:27` (include array)
- Modify: `frontend/tests/App.test.tsx` (import paths)

**Interfaces:**
- Consumes: `App` from `../src/App`, `routeTree` from `../src/routeTree.gen`, `queryClient` from `../src/lib/query-client`
- Produces: tests at `tests/`, vitest and tsconfig updated

- [ ] **Step 1: Create tests directory and move files**

```bash
mkdir -p frontend/tests
mv frontend/src/App.test.tsx frontend/tests/App.test.tsx
mv frontend/src/test-setup.ts frontend/tests/setup.ts
```

- [ ] **Step 2: Update tests/App.test.tsx import paths**

The moved file needs updated relative imports. Change:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { createMemoryHistory } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { routeTree } from './routeTree.gen'
import { queryClient } from './lib/query-client'

function renderApp() {
  const history = createMemoryHistory({ initialEntries: ['/'] })
  const router = createRouter({
    routeTree,
    context: { queryClient },
    history,
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

describe('App smoke test', () => {
  it('renders the Media Forge heading', async () => {
    renderApp()

    await waitFor(() => {
      expect(screen.getByText(/media forge/i)).toBeInTheDocument()
    })
  })
})
```

To:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { createMemoryHistory } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { routeTree } from '../src/routeTree.gen'
import { queryClient } from '../src/lib/query-client'

function renderApp() {
  const history = createMemoryHistory({ initialEntries: ['/'] })
  const router = createRouter({
    routeTree,
    context: { queryClient },
    history,
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

describe('App smoke test', () => {
  it('renders the Media Forge heading', async () => {
    renderApp()

    await waitFor(() => {
      expect(screen.getByText(/media forge/i)).toBeInTheDocument()
    })
  })
})
```

(The only changes are `'./routeTree.gen'` → `'../src/routeTree.gen'` and `'./lib/query-client'` → `'../src/lib/query-client'`)

- [ ] **Step 3: Update vitest.config.ts setupFiles path**

Change line 8 from:
```typescript
    setupFiles: ['./src/test-setup.ts'],
```
To:
```typescript
    setupFiles: ['./tests/setup.ts'],
```

- [ ] **Step 4: Update tsconfig.app.json include to cover tests**

Change line 27 from:
```json
  "include": ["src"]
```
To:
```json
  "include": ["src", "tests"]
```

- [ ] **Step 5: Run tests — verify they pass**

Run: `cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx vitest run`

Expected: 1 test passes.

- [ ] **Step 6: Verify tsc + build**

Run: `cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b && npm run build 2>&1 | tail -3`

Expected: Zero type errors, build succeeds.

- [ ] **Step 7: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f tests/App.test.tsx tests/setup.ts vitest.config.ts tsconfig.app.json
git rm --cached src/App.test.tsx src/test-setup.ts 2>/dev/null
git add -f src/App.test.tsx src/test-setup.ts 2>/dev/null
git commit -m "refactor: move tests to tests/ directory, update configs"
```

---

### Task 5: Final verification

**Files:** (none — verification only)

- [ ] **Step 1: Run full verification suite**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npx tsc -b && echo "TSC: OK"
npx eslint . && echo "LINT: OK"
npm run build && echo "BUILD: OK"
npx vitest run && echo "TEST: OK"
```

Expected: All four pass.

- [ ] **Step 2: Verify src/ root only has App.tsx and main.tsx**

```bash
ls frontend/src/
```

Expected output should show ONLY `App.tsx` and `main.tsx` as files (subdirectories are fine):
```
App.tsx
main.tsx
assets/
components/
lib/
routes/
stores/
styles/
types/
```

- [ ] **Step 3: Commit if any fix was needed**

If fixes were required in Step 1, commit them. Otherwise, skip.

```
git add -A
git commit -m "chore: final verification after src/ reorg"
```
