# Media Forge Frontend — Design Spec

> **Date:** 2026-07-01
> **Status:** Approved
> **Scope:** Scaffold a fully configured React SPA in `frontend/`

## Goal

Create the Media Forge frontend — a React 19 SPA with a comprehensive toolchain and dependency setup, ready for feature development. The scaffold includes routing, state management, UI framework, rich text editing, drag-and-drop, HTTP client, and testing infrastructure — all wired together with a "hello world" smoke test proving the toolchain works.

## Architecture

The frontend is a standalone Vite 8 project under `frontend/`, independent of the Python backend. It uses TanStack Router for file-based routing, Zustand for client state, TanStack Query for server state, Ant Design 6 for the component library, Tailwind CSS 4 for utility styling, and Tiptap 3 for rich text editing.

**Pattern:** Providers wrap the app at entry (`main.tsx`) — RouterProvider, QueryClientProvider, Ant Design ConfigProvider. Pages live in `routes/`, shared components in `components/`, and stores in `stores/`.

## File Structure

```
frontend/
├── index.html                  # Vite entry HTML with root div
├── package.json                # Dependencies and npm scripts
├── vite.config.ts              # Vite 8: React, Tailwind 4, SVG icons, auto-import plugins
├── tsconfig.json               # TypeScript 6 project references
├── tsconfig.app.json           # App compiler options (paths, strict)
├── tsconfig.node.json          # Vite config compiler options
├── eslint.config.ts            # ESLint 10 flat config
├── postcss.config.ts           # PostCSS with autoprefixer (if needed)
├── .gitignore                  # Node, IDE, env files
├── public/
│   └── favicon.svg             # Simple placeholder favicon
├── src/
│   ├── main.tsx                # Entry: providers (Query, Router, AntD, Zustand devtools) → render
│   ├── App.tsx                 # Root layout: <Outlet /> wrapped with app shell
│   ├── app.css                 # Tailwind 4 directives (@import "tailwindcss") + global resets
│   ├── vite-env.d.ts           # Vite client type reference
│   ├── routeTree.gen.ts        # TanStack Router auto-generated route tree
│   ├── routes/
│   │   └── __root.tsx          # Root route: defines the top-level layout/loader
│   ├── stores/
│   │   └── .gitkeep            # Zustand stores go here
│   ├── lib/
│   │   ├── axios.ts            # Axios instance with baseURL, interceptors, error handling
│   │   └── query-client.ts     # TanStack Query client with defaults
│   └── components/
│       └── .gitkeep            # Shared components go here
└── src/
    └── __tests__/
        └── App.test.tsx        # Smoke test: renders "Media Forge" heading
```

## Tech Stack (Pinned Versions)

### Runtime Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| react | ^19.2.6 | UI library |
| react-dom | ^19.2.6 | DOM renderer |
| @tanstack/react-router | ^1.170.4 | Type-safe file-based routing |
| @tanstack/react-query | ^5.100.11 | Server state / caching |
| zustand | ^5.0.13 | Client state management |
| antd | ^6.4.3 | Component library |
| @ant-design/icons | ~6.2.3 | Icon set |
| @tiptap/react | ^3.27.1 | Rich text editor |
| @tiptap/starter-kit | ^3.27.1 | Tiptap default extensions |
| @tiptap/extension-image | ^3.27.1 | Image support |
| @tiptap/extension-link | ^3.27.1 | Link support |
| @tiptap/extension-placeholder | ^3.27.1 | Placeholder text |
| @tiptap/pm | ^3.27.1 | ProseMirror runtime |
| @dnd-kit/core | ^6.3.1 | Drag-and-drop engine |
| @dnd-kit/sortable | ^10.0.0 | Sortable list DnD |
| @dnd-kit/utilities | ^3.2.2 | DnD helpers |
| axios | ^1.16.1 | HTTP client |
| tailwindcss | ^4.3.0 | Utility-first CSS |
| tailwind-merge | ^3.6.0 | Tailwind class merging |
| tw-animate-css | ^1.4.0 | Tailwind animation utilities |
| clsx | ^2.1.1 | Conditional class names |
| date-fns | ^4.2.1 | Date utilities |
| dayjs | ^1.11.21 | Date library (Ant Design peer) |
| lodash | ^4.18.1 | General utilities |
| file-saver | ^2.0.5 | Client-side file download |
| crypto-js | ^4.2.0 | Client-side crypto |
| js-cookie | ^3.0.7 | Cookie management |
| jsencrypt | ^3.5.4 | RSA encryption |
| rc-tree | ^5.13.1 | Tree component (AntD peer) |
| react-json-view-lite | ^2.5.0 | JSON display component |

### Dev Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| vite | ^8.0.12 | Build tool |
| @vitejs/plugin-react | ^6.0.1 | React Fast Refresh |
| @tailwindcss/vite | ^4.3.0 | Tailwind 4 Vite plugin |
| typescript | ~6.0.2 | Type checker |
| @types/react | ^19.2.14 | React type defs |
| @types/react-dom | ^19.2.3 | React DOM type defs |
| @types/node | ^24.12.3 | Node type defs |
| @types/lodash | ^4.17.24 | Lodash type defs |
| @types/crypto-js | ^4.2.2 | CryptoJS type defs |
| @types/file-saver | ^2.0.7 | FileSaver type defs |
| @types/js-cookie | ^3.0.6 | JSCookie type defs |
| eslint | ^10.3.0 | Linter |
| @eslint/js | ^10.0.1 | ESLint JS plugin |
| typescript-eslint | ^8.59.2 | TS lint rules |
| eslint-plugin-react-hooks | ^7.1.1 | Hooks lint rules |
| eslint-plugin-react-refresh | ^0.5.2 | HMR-aware lint rules |
| globals | ^17.6.0 | Global variable defs |
| less | ^4.6.4 | Less preprocessor |
| autoprefixer | ^10.5.0 | CSS vendor prefixes |
| unplugin-auto-import | ^21.0.0 | Auto-import React/hooks |
| vite-plugin-svg-icons-ng | ^1.9.1 | SVG sprite generation |
| vitest | ^3 (latest) | Test runner |
| @testing-library/react | ^16 (latest) | React test utilities |
| @testing-library/jest-dom | ^6 (latest) | DOM matchers |
| @testing-library/user-event | ^14 (latest) | User interaction simulation |
| jsdom | ^26 (latest) | DOM environment for tests |

## Key Configuration Decisions

### Vite 8 + Tailwind CSS 4

Tailwind CSS 4 uses a CSS-first configuration model — no `tailwind.config.ts` file. The `@tailwindcss/vite` plugin handles processing. Imported in `app.css` via `@import "tailwindcss"`.

### TanStack Router

File-based routing with generated `routeTree.gen.ts`. The root route at `routes/__root.tsx` defines the top-level layout. Requires a `RouterProvider` in `main.tsx`.

### Ant Design 6

CSS-in-JS by default — no Less configuration needed for theming. The `ConfigProvider` wraps the app for locale/theme settings. `@ant-design/icons` provides the icon set via tree-shakeable imports.

### unplugin-auto-import

Auto-imports `React`, `useState`, `useEffect`, `useCallback`, `useMemo`, `useRef` from React, plus `create` from Zustand. Reduces import boilerplate across the codebase.

### TypeScript 6

Project references pattern: `tsconfig.json` references `tsconfig.app.json` (src code) and `tsconfig.node.json` (Vite config). Strict mode enabled. Path alias `@/` mapped to `src/`.

### ESLint 10

Flat config format (`eslint.config.ts`). Includes type-aware linting via `typescript-eslint`, React hooks plugin, and React Refresh plugin for HMR-safe code.

## NPM Scripts

```json
{
  "dev": "vite",
  "build": "tsc -b && vite build",
  "preview": "vite preview",
  "lint": "eslint .",
  "test": "vitest",
  "test:ui": "vitest --ui",
  "test:coverage": "vitest --coverage"
}
```

## What's NOT in Scope (Deferred)

These decisions will be made when their features are implemented:

- **Ant Design theme customization** — default theme is fine until UX design defines brand tokens
- **Authentication flow** — auth provider / guards added when backend auth exists
- **E2E testing** — Playwright or Cypress added when user flows exist
- **PWA / service workers** — added if offline support is needed
- **i18n** — added when multi-language support is required
- **Storybook** — added when component library grows
- **CI/CD** — added when repo has a CI platform configured

## Success Criteria

1. `npm run dev` starts a Vite dev server on localhost
2. Browser shows a simple "Media Forge" page with Ant Design styling
3. `npm run build` produces an optimized production build
4. `npm run test` runs the smoke test and passes
5. `npm run lint` runs ESLint with zero errors
6. Route navigation works (at least the root `/` route renders)
