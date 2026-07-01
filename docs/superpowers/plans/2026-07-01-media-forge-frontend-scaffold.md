# Media Forge Frontend Scaffold — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold a fully configured React 19 SPA in `frontend/` with Vite 8, TypeScript 6, TanStack Router, Ant Design 6, Tailwind CSS 4, Zustand, Tiptap, and a smoke test proving the toolchain works.

**Architecture:** Standalone Vite project under `frontend/`. Providers (Router, Query, AntD) wrap the app at `main.tsx`. File-based routing via TanStack Router with auto-generated route tree. Zustand stores in `stores/`, shared components in `components/`, library wrappers in `lib/`.

**Tech Stack:** React 19, Vite 8, TypeScript 6, Ant Design 6, Tailwind CSS 4, TanStack Router 1.x, TanStack Query 5.x, Zustand 5, Tiptap 3, @dnd-kit, Axios, Vitest 3, React Testing Library, ESLint 10

## Global Constraints

- Node.js 22+ required
- All deps exactly as specified in the [design spec](../specs/2026-07-01-media-forge-frontend-design.md)
- Tailwind CSS 4 uses `@import "tailwindcss"` in CSS (no `tailwind.config.ts`)
- TypeScript project references pattern (tsconfig.json → tsconfig.app.json + tsconfig.node.json)
- ESLint 10 flat config format (eslint.config.ts)
- unplugin-auto-import for React, hooks, Zustand auto-imports
- TanStack Router file-based routing with generated route tree
- Frontend is self-contained in `frontend/` — independent from Python backend
- No TypeScript errors, no ESLint errors, smoke test passes before completion

---

### Task 1: Create `package.json` with all dependencies

**Files:**
- Create: `frontend/package.json`

**Interfaces:**
- Produces: `package.json` with exact dependencies from design spec + Vitest/RTL

- [ ] **Step 1: Write package.json**

```json
{
  "name": "media-forge-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "eslint .",
    "test": "vitest",
    "test:ui": "vitest --ui",
    "test:coverage": "vitest --coverage"
  },
  "dependencies": {
    "@ant-design/icons": "~6.2.3",
    "@dnd-kit/core": "^6.3.1",
    "@dnd-kit/sortable": "^10.0.0",
    "@dnd-kit/utilities": "^3.2.2",
    "@tanstack/react-query": "^5.100.11",
    "@tanstack/react-router": "^1.170.4",
    "@tiptap/extension-image": "^3.27.1",
    "@tiptap/extension-link": "^3.27.1",
    "@tiptap/extension-placeholder": "^3.27.1",
    "@tiptap/pm": "^3.27.1",
    "@tiptap/react": "^3.27.1",
    "@tiptap/starter-kit": "^3.27.1",
    "antd": "^6.4.3",
    "axios": "^1.16.1",
    "clsx": "^2.1.1",
    "crypto-js": "^4.2.0",
    "date-fns": "^4.2.1",
    "dayjs": "^1.11.21",
    "file-saver": "^2.0.5",
    "js-cookie": "^3.0.7",
    "jsencrypt": "^3.5.4",
    "lodash": "^4.18.1",
    "rc-tree": "^5.13.1",
    "react": "^19.2.6",
    "react-dom": "^19.2.6",
    "react-json-view-lite": "^2.5.0",
    "tailwind-merge": "^3.6.0",
    "tailwindcss": "^4.3.0",
    "tw-animate-css": "^1.4.0",
    "zustand": "^5.0.13"
  },
  "devDependencies": {
    "@eslint/js": "^10.0.1",
    "@tailwindcss/vite": "^4.3.0",
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/crypto-js": "^4.2.2",
    "@types/file-saver": "^2.0.7",
    "@types/js-cookie": "^3.0.6",
    "@types/lodash": "^4.17.24",
    "@types/node": "^24.12.3",
    "@types/react": "^19.2.14",
    "@types/react-dom": "^19.2.3",
    "@vitejs/plugin-react": "^6.0.1",
    "autoprefixer": "^10.5.0",
    "eslint": "^10.3.0",
    "eslint-plugin-react-hooks": "^7.1.1",
    "eslint-plugin-react-refresh": "^0.5.2",
    "globals": "^17.6.0",
    "jsdom": "^26.0.0",
    "less": "^4.6.4",
    "typescript": "~6.0.2",
    "typescript-eslint": "^8.59.2",
    "unplugin-auto-import": "^21.0.0",
    "vite": "^8.0.12",
    "vite-plugin-svg-icons-ng": "^1.9.1",
    "vitest": "^3.1.1"
  }
}
```

- [ ] **Step 2: Create `.gitignore` for frontend directory**

```gitignore
# Dependencies
node_modules/

# Build output
dist/

# TanStack Router generated files
.tanstack/

# Environment
.env
.env.local
.env.*.local

# IDE
*.tsbuildinfo
```

- [ ] **Step 3: Install dependencies**

Run: `cd frontend && npm install`

Expected: Dependencies install without errors, `node_modules/` created, `package-lock.json` generated.

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/.gitignore
git commit -m "chore: scaffold frontend package.json with all dependencies"
```

---

### Task 2: Create TypeScript configuration

**Files:**
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.app.json`
- Create: `frontend/tsconfig.node.json`

**Interfaces:**
- Produces: `tsconfig.json` (project references), `tsconfig.app.json` (app code), `tsconfig.node.json` (Vite config)

- [ ] **Step 1: Write tsconfig.json (root — references only)**

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

- [ ] **Step 2: Write tsconfig.app.json (app source)**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,

    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "noEmit": true,

    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true,

    "jsx": "react-jsx",

    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Write tsconfig.node.json (Vite + tool config files)**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,

    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "noEmit": true,

    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true
  },
  "include": ["vite.config.ts", "eslint.config.ts", "vitest.config.ts"]
}
```

- [ ] **Step 4: Verify TypeScript config is valid**

Run: `cd frontend && npx tsc --showConfig -p tsconfig.app.json 2>&1 | head -5`

Expected: Prints resolved config without errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/tsconfig.json frontend/tsconfig.app.json frontend/tsconfig.node.json
git commit -m "chore: add TypeScript 6 project references config"
```

---

### Task 3: Create Vite configuration

**Files:**
- Create: `frontend/vite.config.ts`

**Interfaces:**
- Consumes: `tsconfig.node.json` (for type checking the config file itself)
- Produces: Vite 8 config with all plugins wired

- [ ] **Step 1: Write vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { createSvgIconsPlugin } from 'vite-plugin-svg-icons-ng'
import AutoImport from 'unplugin-auto-import/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    createSvgIconsPlugin({
      iconDirs: [path.resolve(process.cwd(), 'src/assets/icons')],
      symbolId: 'icon-[dir]-[name]',
    }),
    AutoImport({
      imports: [
        'react',
        {
          zustand: ['create'],
        },
      ],
      dts: 'src/auto-imports.d.ts',
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  css: {
    preprocessorOptions: {
      less: {
        javascriptEnabled: true,
      },
    },
  },
})
```

- [ ] **Step 2: Verify Vite config is valid**

Run: `cd frontend && npx vite --version`

Expected: Prints Vite version without config errors (config isn't loaded by `--version`, but installs are confirmed).

- [ ] **Step 3: Commit**

```bash
git add frontend/vite.config.ts
git commit -m "chore: add Vite 8 config with React, Tailwind 4, SVG, and auto-import plugins"
```

---

### Task 4: Create ESLint configuration

**Files:**
- Create: `frontend/eslint.config.ts`

**Interfaces:**
- Produces: ESLint 10 flat config with type-aware linting

- [ ] **Step 1: Write eslint.config.ts**

```typescript
import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'

export default tseslint.config(
  { ignores: ['dist', '.tanstack', 'src/routeTree.gen.ts'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  }
)
```

- [ ] **Step 2: Verify ESLint config loads**

Run: `cd frontend && npx eslint --help 2>&1 | head -3`

Expected: Prints ESLint help text, no config errors at load time.

- [ ] **Step 3: Commit**

```bash
git add frontend/eslint.config.ts
git commit -m "chore: add ESLint 10 flat config with TypeScript and React hooks rules"
```

---

### Task 5: Create HTML entry point and static assets

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/public/favicon.svg`

**Interfaces:**
- Produces: HTML entry point with root div, simple favicon

- [ ] **Step 1: Write index.html**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <title>Media Forge</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 2: Write public/favicon.svg**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <text y=".9em" font-size="90">🎬</text>
</svg>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html frontend/public/favicon.svg
git commit -m "chore: add HTML entry point and favicon"
```

---

### Task 6: Create CSS entry (Tailwind CSS 4 directives + global styles)

**Files:**
- Create: `frontend/src/app.css`

**Interfaces:**
- Consumes: Tailwind CSS 4 Vite plugin (from Task 3)
- Produces: CSS file with Tailwind directives, consumed by `main.tsx` import

- [ ] **Step 1: Write src/app.css**

```css
@import "tailwindcss";
@import "tw-animate-css";

/* Global resets and base styles */
body {
  margin: 0;
  padding: 0;
}

#root {
  min-height: 100vh;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app.css
git commit -m "chore: add Tailwind CSS 4 global styles"
```

---

### Task 7: Create library utilities (Axios + React Query)

**Files:**
- Create: `frontend/src/lib/axios.ts`
- Create: `frontend/src/lib/query-client.ts`

**Interfaces:**
- Produces:
  - `axios` — AxiosInstance with `baseURL: '/api'`, auth interceptor
  - `queryClient` — QueryClient with default staleTime/retry

- [ ] **Step 1: Write src/lib/axios.ts**

```typescript
import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.request.use(
  (config) => {
    // Auth token will be injected here when auth is implemented
    return config
  },
  (error) => Promise.reject(error)
)

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Centralized error handling will go here
    return Promise.reject(error)
  }
)

export default apiClient
```

- [ ] **Step 2: Write src/lib/query-client.ts**

```typescript
import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
})
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/axios.ts frontend/src/lib/query-client.ts
git commit -m "feat: add Axios instance and React Query client"
```

---

### Task 8: Create root route and App shell

**Files:**
- Create: `frontend/src/routes/__root.tsx`
- Create: `frontend/src/App.tsx`

**Interfaces:**
- Produces:
  - `__root.tsx` — TanStack Router root route, wraps children in Ant Design `ConfigProvider`
  - `App.tsx` — Vite entry wrapper that imports `app.css`, renders `<Outlet />` via router

- [ ] **Step 1: Write src/routes/__root.tsx**

```typescript
import { createRootRoute, Outlet } from '@tanstack/react-router'
import { ConfigProvider, App as AntApp } from 'antd'

export const Route = createRootRoute({
  component: () => (
    <ConfigProvider>
      <AntApp>
        <Outlet />
      </AntApp>
    </ConfigProvider>
  ),
})
```

- [ ] **Step 2: Write src/App.tsx**

```typescript
import './app.css'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { routeTree } from './routeTree.gen'
import { queryClient } from './lib/query-client'
import { QueryClientProvider } from '@tanstack/react-query'

const router = createRouter({
  routeTree,
  context: {
    queryClient,
  },
  defaultPreload: 'intent',
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

export default App
```

> **Note:** `routeTree.gen.ts` does not exist yet. TanStack Router requires a `vite` plugin (or manual generation) to produce this file. The router won't work until that is wired. We handle this in Task 9.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/__root.tsx frontend/src/App.tsx
git commit -m "feat: add root route with Ant Design ConfigProvider and App shell"
```

---

### Task 9: Add TanStack Router Vite plugin and generate route tree

**Files:**
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/routeTree.gen.ts` (placeholder, will be auto-generated on first dev run)

**Interfaces:**
- Consumes: `__root.tsx` route definition
- Produces: `routeTree.gen.ts` auto-generated by the router's vite plugin

- [ ] **Step 1: Add TanStack Router Vite plugin declaration to package.json devDependencies**

Check that `@tanstack/router-plugin` is needed. TanStack Router 1.x uses `@tanstack/router-vite-plugin` or the newer `@tanstack/router-plugin`.

Run: `cd frontend && npm ls @tanstack/react-router 2>&1 | head -5`

The `@tanstack/router-plugin` package is the companion to `@tanstack/react-router`. Install it:

Run: `cd frontend && npm install -D @tanstack/router-plugin@^1.170.4`

Expected: Installs the router Vite plugin.

- [ ] **Step 2: Update vite.config.ts to add the router plugin**

Read `frontend/vite.config.ts` and add the import and plugin:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { createSvgIconsPlugin } from 'vite-plugin-svg-icons-ng'
import AutoImport from 'unplugin-auto-import/vite'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [
    TanStackRouterVite(),
    react(),
    tailwindcss(),
    createSvgIconsPlugin({
      iconDirs: [path.resolve(process.cwd(), 'src/assets/icons')],
      symbolId: 'icon-[dir]-[name]',
    }),
    AutoImport({
      imports: [
        'react',
        {
          zustand: ['create'],
        },
      ],
      dts: 'src/auto-imports.d.ts',
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  css: {
    preprocessorOptions: {
      less: {
        javascriptEnabled: true,
      },
    },
  },
})
```

> **Note:** `TanStackRouterVite()` must come BEFORE `react()` in plugins array — it needs to handle route file transformation before React processes them.

- [ ] **Step 3: Generate the route tree**

Run: `cd frontend && npx vite build --mode development 2>&1 | tail -10`

The first `vite dev` or build with the plugin will generate `src/routeTree.gen.ts` automatically. If that doesn't work, run the dev server briefly:

```bash
cd frontend && timeout 5 npx vite 2>&1 || true
```

Then check: `ls frontend/src/routeTree.gen.ts`

Expected: File exists, contains the generated route tree.

- [ ] **Step 4: Commit**

```bash
git add frontend/vite.config.ts frontend/src/routeTree.gen.ts frontend/package.json frontend/package-lock.json
git commit -m "chore: add TanStack Router Vite plugin and generated route tree"
```

---

### Task 10: Create main.tsx entry point with providers

**Files:**
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/vite-env.d.ts`
- Create: `frontend/src/stores/.gitkeep`
- Create: `frontend/src/components/.gitkeep`
- Create: `frontend/src/assets/icons/.gitkeep`

**Interfaces:**
- Consumes: `App` from `./App.tsx`
- Produces: `main.tsx` — the Vite entry module that renders `<App />` into DOM

- [ ] **Step 1: Write src/vite-env.d.ts**

```typescript
/// <reference types="vite/client" />
```

- [ ] **Step 2: Write src/main.tsx**

```typescript
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'

const rootElement = document.getElementById('root')

if (!rootElement) {
  throw new Error('Root element not found. Ensure index.html contains <div id="root"></div>.')
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>
)
```

- [ ] **Step 3: Create placeholder directories**

```bash
mkdir -p frontend/src/stores
mkdir -p frontend/src/components
mkdir -p frontend/src/assets/icons
touch frontend/src/stores/.gitkeep
touch frontend/src/components/.gitkeep
touch frontend/src/assets/icons/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/main.tsx frontend/src/vite-env.d.ts frontend/src/stores frontend/src/components frontend/src/assets/icons
git commit -m "feat: add main.tsx entry point and placeholder directories"
```

---

### Task 11: Set up Vitest and write the smoke test

**Files:**
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test-setup.ts`
- Create: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `App` from `./App.tsx`, `vitest.config.ts` extends `vite.config.ts`
- Produces: Working test setup with a smoke test

- [ ] **Step 1: Write vitest.config.ts**

```typescript
import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(viteConfig, defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    css: true,
  },
}))
```

- [ ] **Step 2: Write src/test-setup.ts**

```typescript
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 3: Write the failing smoke test**

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

describe('App', () => {
  it('renders the Media Forge application', () => {
    render(<App />)
    // The page should contain "Media Forge" somewhere
    expect(screen.getByText(/media forge/i)).toBeInTheDocument()
  })
})
```

> **Note:** At this point the test will FAIL because `routeTree.gen.ts` won't have a route with "Media Forge" text. That's expected — we're writing the test first (TDD).

- [ ] **Step 4: Update the root route to include greeting text**

Modify `frontend/src/routes/__root.tsx` to add the heading:

```typescript
import { createRootRoute, Outlet } from '@tanstack/react-router'
import { ConfigProvider, App as AntApp, Typography } from 'antd'

const { Title } = Typography

export const Route = createRootRoute({
  component: () => (
    <ConfigProvider>
      <AntApp>
        <div className="p-8">
          <Title level={1}>Media Forge 🎬</Title>
          <Outlet />
        </div>
      </AntApp>
    </ConfigProvider>
  ),
})
```

- [ ] **Step 5: Run the smoke test — verify it passes**

Run: `cd frontend && npx vitest run`

Expected: 1 test passes — renders the greeting including "Media Forge".

- [ ] **Step 6: Commit**

```bash
git add frontend/vitest.config.ts frontend/src/test-setup.ts frontend/src/App.test.tsx frontend/src/routes/__root.tsx
git commit -m "test: add Vitest config and smoke test proving app renders"
```

---

### Task 12: Verify full toolchain — lint, build, type-check

**Files:** (none created, verification only)

- [ ] **Step 1: Run TypeScript type check**

Run: `cd frontend && npx tsc -b`

Expected: Zero type errors.

- [ ] **Step 2: Run ESLint**

Run: `cd frontend && npx eslint .`

Expected: Zero lint errors (or only warnings for `react-refresh/only-export-components`).

- [ ] **Step 3: Run production build**

Run: `cd frontend && npm run build`

Expected: Build succeeds, `dist/` directory created with bundled output.

- [ ] **Step 4: Run all tests**

Run: `cd frontend && npm test`

Expected: All tests pass.

- [ ] **Step 5: Fix any issues found in Steps 1-4**

If type errors: fix source files and re-run `npx tsc -b`.
If lint errors: fix source files and re-run `npx eslint .`.
If build errors: fix and re-run `npm run build`.
Repeat until all four commands pass clean.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: final verification — type check, lint, build, and tests all pass"
```

---

### Task 13: Update project CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md with frontend information**

Read current `CLAUDE.md`, update the frontend line in directory structure from `(empty — not yet scaffolded)` to reflect the scaffolded state, and add a Frontend section:

The edited CLAUDE.md should look like:

```markdown
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
- **Frontend**: Node.js 22+ project in `frontend/`. Run `cd frontend && npm install` to set up, then `npm run dev` to start development server.
- No build system, package manager, or test framework configured yet for backend.

## Frontend

**Stack:** React 19 + Vite 8 + TypeScript 6 + Ant Design 6 + Tailwind CSS 4 + TanStack Router 1.x

**Scripts** (from `frontend/`):
- `npm run dev` — Start Vite dev server
- `npm run build` — Type-check + production build
- `npm run preview` — Preview production build
- `npm run lint` — ESLint
- `npm test` — Vitest
- `npm run test:ui` — Vitest UI
- `npm run test:coverage` — Vitest coverage report
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with frontend scaffold info"
```

---
