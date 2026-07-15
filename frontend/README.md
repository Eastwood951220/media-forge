# Media Forge Frontend

React single-page application for Media Forge. It provides initialization,
authentication, dashboard, crawler, content, and storage management views for
the FastAPI backend.

## Stack

- React 19 + TypeScript 6
- Vite 8
- Ant Design 6
- Tailwind CSS 4 through `@tailwindcss/vite`
- TanStack Router 1.x for routing
- TanStack Query 5.x for server state
- Zustand 5 for client state
- Axios for HTTP requests
- Vitest + React Testing Library for tests

## Quick Start

Run commands from `frontend/`:

```bash
npm install
npm run dev
```

The Vite dev server uses port `18643` and proxies `/api` to
`http://localhost:18642`.

Common scripts:

```bash
npm run dev
npm run build
npm run preview
npm run lint
npm test
npm run test:ui
npm run test:coverage
```

## Source Layout

```text
src/
  api/          Backend API modules and DTO types
  assets/       Static assets imported by the app
  components/   Shared UI components
  enums/        Shared enums
  hooks/        Shared React hooks
  layout/       Main shell, sidebar, header, tags view, route cache
  lib/          Shared library setup such as TanStack Query client
  pages/        Route pages grouped by business module
  realtime/     Server-sent event client and realtime event types
  request/      Axios instance, interceptors, transform, cache, cancel helpers
  routes/       TanStack Router route tree, guards, route tag metadata
  stores/       Zustand stores
  styles/       Global styles and view transition styles
  types/        Generated and global type declarations
  utils/        Shared utilities
```

Use `@/` for imports from `src/`; the alias is configured in
`vite.config.ts`.

## Application Shell

`src/App.tsx` wires global styles, the TanStack Query client, and the router.
It also synchronizes theme variables to `<html>` and checks initialization
status before rendering unauthenticated routes.

Authenticated pages render inside `src/layout/`:

- `Sidebar/` defines the main navigation groups: 仪表盘, 爬虫, 存储, 内容管理.
- `Header/` shows the current route title, theme toggle, user identity, and logout.
- `TagsView/` tracks visited route tabs and tab actions.
- `routeCache.tsx` wraps routed pages with `keepalive-for-react`; `/login` and
  `/init` are excluded from route caching.

## Routes And Pages

Routes are declared manually in `src/routes/index.tsx`. Route titles and cache
keys are centralized in `src/routes/tags.ts`.

Current route modules:

| Route | Page | Purpose |
| --- | --- | --- |
| `/init` | `pages/init/InitPage.tsx` | First-run PostgreSQL and Redis configuration |
| `/login` | `pages/login/LoginPage.tsx` | Authentication |
| `/` | `pages/dashboard/DashboardPage.tsx` | Dashboard overview |
| `/crawler/tasks` | `pages/crawler/tasks/TaskListPage.tsx` | Crawler task list and runtime actions |
| `/crawler/tasks/new` | `pages/crawler/tasks/TaskFormPage.tsx` | Create crawler task |
| `/crawler/tasks/$id/edit` | `pages/crawler/tasks/TaskFormPage.tsx` | Edit crawler task |
| `/crawler/runs` | `pages/crawler/runs/RunListPage.tsx` | Crawler run history |
| `/crawler/runs/$id` | `pages/crawler/runs/RunDetailPage.tsx` | Run logs, task summary, retry actions |
| `/crawler/config` | `pages/crawler/config/ConfigPage.tsx` | Crawler and cookie configuration |
| `/content/movies` | `pages/content/movies/MovieListPage.tsx` | Movie list, filters, storage sync, push actions |
| `/storage/config` | `pages/storage/config/StorageConfigPage.tsx` | CloudDrive2/storage target configuration |
| `/storage/tasks` | `pages/storage/tasks/StorageTaskListPage.tsx` | Storage main task list |
| `/storage/tasks/$id` | `pages/storage/tasks/StorageTaskDetailPage.tsx` | Storage task detail and subtasks |
| `/storage/tasks/subtasks/$id` | `pages/storage/tasks/StorageSubTaskDetailPage.tsx` | Storage subtask detail, files, logs, timeline |

`src/routes/-guards.ts` owns initialization and authentication guards. Layout
routes require both initialization and authentication.

## API Modules

API modules live under `src/api/` and should export typed functions rather than
calling Axios directly from pages.

Current API groups:

- `init/`: initialization config and connection tests.
- `login/`: login and logout.
- `dashboard/`: dashboard overview.
- `crawlTask/`: crawler task CRUD, stats, runtime status, temporary runs.
- `crawlerRun/`: run list/detail/logs/task summaries, stop/restart/retry.
- `crawler/crawlerConfig/`: crawler config and cookies config.
- `movie/`: movie list/detail/filter config, delete, storage sync.
- `storage/storageConfig/`: storage config and connection test.
- `storage/storageIndex/`: storage index status and refresh.
- `storage/storageTasks/`: storage push creation and task/subtask detail APIs.

The shared request layer is `src/request/`. It adds token injection, GET
parameter normalization, repeat-submit checks, cancellation, optional GET cache,
response transformation, and error handling. Use `request.get/post/put/delete`
or the base `request(config)` helper from API modules.

## State And Realtime

Zustand stores:

- `useAuthStore`: token and authentication state, synchronized with cookies.
- `useThemeStore`: light/dark mode and primary color.
- `useTagsViewStore`: visited route tabs and tab close/reset operations.

TanStack Query client defaults are in `src/lib/query-client.ts`: five-minute
query stale time, one query retry, no refetch on window focus, and no mutation
retry.

Realtime updates use server-sent events in `src/realtime/eventSourceClient.ts`.
Feature pages subscribe to events from their hooks and should trigger local
query invalidation or targeted state refresh when receiving update events.

## Page Module Pattern

Page modules are organized by business domain:

- Keep route entry components at the module root, for example
  `pages/storage/tasks/StorageTaskListPage.tsx`.
- Put page-local presentational components in `components/`.
- Put page-local data and interaction hooks in `hooks/`.
- Put constants in `constants/` and pure helpers in `utils/`.
- Keep tests close to the module in `__tests__/` when the test is tightly
  coupled to page behavior.

Prefer extracting reusable table/list behavior to `src/components/` only after
more than one module needs it. `components/BaseListPage/` is the current shared
list-page abstraction.

## Styling

Global styles live in `src/styles/`. Component and page styles use CSS modules
with `.module.less`.

Theme state is applied through both Ant Design `ConfigProvider` tokens and
document-level variables:

- `data-theme` on `<html>` is used by global CSS.
- `--app-primary-color` is updated from `useThemeStore`.

## Testing

Vitest runs in `jsdom` with setup from `tests/setup.ts`.

Run all tests:

```bash
npm test
```

Run focused tests by path:

```bash
npm test -- src/request/__tests__/transform.test.ts
npm test -- src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx
```

Before shipping frontend changes, run at least:

```bash
npm run build
npm test
```
