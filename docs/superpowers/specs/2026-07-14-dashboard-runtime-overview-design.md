# Dashboard Runtime Overview Design

## Context

The current dashboard is a static placeholder that describes a generic media
pipeline. It does not reflect Media Forge's current modules:

- crawler task configuration and runtime status;
- crawler runs and queue state;
- content movie library and storage status;
- storage push tasks;
- storage index metadata;
- recent failures and operational alerts.

The redesigned homepage must be a real runtime overview. It should answer, on
first load, whether the system is healthy, whether work is queued or running,
how much content exists, and whether storage indexing is usable.

## Goals

- Replace static dashboard metrics with real data.
- Keep the dashboard focused on existing Media Forge behavior.
- Provide a single fast overview endpoint for homepage data.
- Use Ant Design and existing layout conventions.
- Add `@antv/g2` for lightweight diagnostic charts.
- Support light and dark themes.
- Avoid speculative product features or mock metrics.

## Non-Goals

- Do not add new crawler, movie, or storage workflows.
- Do not turn the homepage into a marketing or welcome page.
- Do not add broad analytics beyond the data needed for operational status.
- Do not make frontend charts depend on fake fallback data.

## Recommended Direction

Use an operations-first dashboard layout.

The first screen should prioritize health, queue pressure, task status, content
coverage, storage index health, and recent failures. Charts should support
diagnosis but should not dominate the first screen.

## Backend API

Add a new module:

```text
backend/app/modules/dashboard/
```

Expose:

```http
GET /api/dashboard/overview
```

The endpoint aggregates existing state without introducing new business
actions. It should return one payload that the homepage can load with a single
request.

### Response Shape

The response should include:

```json
{
  "system_status": "healthy",
  "refreshed_at": "2026-07-14T00:00:00Z",
  "crawler": {
    "task_stats": {
      "total": 0,
      "enabled": 0,
      "disabled": 0
    },
    "runtime_stats": {
      "total": 0,
      "idle": 0,
      "running": 0,
      "queued": 0,
      "stopped": 0
    },
    "queue": {
      "queue_size": 0,
      "is_running": false,
      "current_run_id": null,
      "stop_requested": false
    }
  },
  "runs": {
    "status_distribution": [],
    "daily_trend": [],
    "recent": []
  },
  "content": {
    "movie_total": 0,
    "storage_status": {
      "stored": 0,
      "storing": 0,
      "not_stored": 0
    }
  },
  "storage": {
    "task_status_distribution": [],
    "recent_tasks": [],
    "index": {
      "status": "never_built",
      "category_count": 0,
      "code_folder_count": 0,
      "video_count": 0,
      "completed_at": null,
      "errors": []
    }
  },
  "alerts": [],
  "partial_errors": []
}
```

Exact TypeScript and Python schema names can be adjusted during implementation,
but the API should keep these semantic groups.

### Status Derivation

Derive `system_status` from existing state:

- `error`: storage index failed with errors, recent crawler/storage failures
  exist, or the current run/task is in a failed state.
- `warning`: queue is non-empty for active work, storage index has never been
  built, stop is requested, or runtime includes stopped tasks.
- `busy`: crawler or storage work is currently running without failures.
- `healthy`: no failures, no blocking warnings, and no active backlog.

If multiple conditions match, use the highest severity:

```text
error > warning > busy > healthy
```

### Partial Failures

The overview endpoint should degrade per section. If one sub-query fails, the
endpoint should still return available sections and append a `partial_errors`
entry with:

- `section`: stable section key, such as `content` or `storage.index`;
- `message`: user-safe error summary.

Unexpected top-level failures can still return the existing global error
format.

## Frontend Data Layer

Add:

```text
frontend/src/api/dashboard/index.ts
frontend/src/api/dashboard/types.ts
```

Add `getDashboardOverview()` and response interfaces. The page should not call
six independent list endpoints directly. It should use a single query:

```text
useDashboardOverview
```

The hook should support:

- initial loading;
- manual refresh;
- retry after failure;
- optional short refetch interval only if it follows existing query patterns.

## Page Layout

Replace the existing static dashboard with four vertical zones.

### 1. Status Header

Title: `运行态总览`

Content:

- overall status badge;
- refreshed time;
- manual refresh button.

Use these Ant Design icons:

- `CheckCircleOutlined`: healthy;
- `SyncOutlined`: busy;
- `WarningOutlined`: warning;
- `CloseCircleOutlined`: error.

### 2. Metric Cards

Render four compact metric cards:

1. `采集队列`
   - icon: `CloudSyncOutlined` or `SearchOutlined`;
   - shows running and queued counts.
2. `任务配置`
   - icon: `UnorderedListOutlined`;
   - shows enabled tasks and total tasks.
3. `影片库`
   - icon: `VideoCameraOutlined`;
   - shows movie total and stored ratio.
4. `存储索引`
   - icon: `DatabaseOutlined`;
   - shows index status, video count, and category count.

Metric cards should use Ant Design tokens and keep an 8px border radius.

### 3. Diagnostic Charts

Add `@antv/g2`.

Use G2 directly through the `Chart` lifecycle inside React components. Do not
use the old `g2-react` wrapper.

Render two charts:

- crawler run status distribution, using a bar or stacked bar chart;
- recent 7-day crawler run trend, using a line or area chart for completed and
  failed runs.

Chart colors must be stable:

- running or queued: blue;
- completed: green;
- failed: red;
- stopped, skipped, or neutral states: gray or orange.

Charts must show an empty state when no data exists. They must not render mock
data.

### 4. Recent Work And Alerts

Left side:

- tabs for `最近采集运行` and `最近存储任务`;
- each row shows name, status tag, time, and a link to the relevant detail page.

Right side:

- `需要关注` list;
- include recent failed crawler runs, failed storage tasks, and storage index
  errors;
- show a healthy empty state when no alerts exist.

## Component Breakdown

Keep dashboard files focused:

```text
frontend/src/pages/dashboard/
  DashboardPage.tsx
  DashboardPage.module.less
  components/
    DashboardStatusHeader.tsx
    DashboardMetricCards.tsx
    DashboardCharts.tsx
    DashboardRecentTabs.tsx
    DashboardAlerts.tsx
  hooks/
    useDashboardOverview.ts
```

Responsibilities:

- `DashboardPage`: layout and data hook wiring only.
- `DashboardStatusHeader`: status badge, refresh time, refresh action.
- `DashboardMetricCards`: metric configuration and card rendering.
- `DashboardCharts`: G2 lifecycle, resize, destroy, and empty state.
- `DashboardRecentTabs`: recent crawler/storage work.
- `DashboardAlerts`: alert list and empty state.

## Loading And Error States

- Initial load shows Ant Design `Skeleton` while preserving layout dimensions.
- Full overview request failure shows `Alert` and retry button.
- Section-level `partial_errors` show small degraded-state indicators in the
  affected card or panel.
- Empty sections use `Empty`.
- The page must not fall back to the old static dashboard data.

## Styling

- Keep the existing operational console style.
- Use Chinese labels for dashboard text.
- Avoid marketing hero composition.
- Avoid oversized decorative cards.
- Preserve responsive behavior for desktop and mobile widths.
- Maintain light and dark theme support.
- Keep cards at 8px radius or less.

## Testing

Backend tests:

- empty database overview;
- normal overview with crawler, content, and storage data;
- `system_status` severity precedence;
- partial failure response shape.

Frontend tests:

- renders title and four metric cards from mocked overview data;
- renders alert empty state;
- renders full request failure and retry action;
- renders chart empty states when chart data is empty;
- does not render old static placeholder copy.

Verification:

- run targeted backend pytest for dashboard tests;
- run dashboard frontend tests;
- run `npm run build` from `frontend/`.

## Acceptance Criteria

- `/` displays real Media Forge runtime data from `GET /api/dashboard/overview`.
- The dashboard shows overall health, crawler queue/runtime, task config,
  movie totals, storage status, storage index status, recent work, and alerts.
- G2 charts render only from real overview data and show empty states otherwise.
- Backend and frontend tests cover the new overview behavior.
- Existing crawler, movie, and storage workflows remain unchanged.
