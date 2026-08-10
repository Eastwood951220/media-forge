# JavDB Chrome Agent Backend Parse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the failed JavDB Playwright browser mode with a real-Chrome extension Agent that sends JavDB page fragments to the backend for parsing, while keeping frontend/backend realtime on EventSource and centralizing crawler runtime state in a Zustand store.

**Architecture:** The UI keeps using `/api/events/stream` and the existing `RealtimeEventBus`. The Chrome extension connects to a new backend Agent WebSocket for task assignment, heartbeat, cookie sync, and page snapshots. Backend parse mode wraps Agent-submitted DOM fragments into parser-compatible pages and reuses existing JavDB parser/persistence code.

**Tech Stack:** Python 3.12+, FastAPI WebSocket, SQLAlchemy 2.0, Alembic, PostgreSQL, Scrapling parser adapters, React 19, TypeScript 6, Zustand 5, Ant Design 6, Chrome Extension Manifest V3.

## Global Constraints

- Keep frontend/backend realtime transport as the existing EventSource stream.
- Use WebSocket only between the Chrome extension Agent and backend.
- Initial supported Agent parse mode is `JAVDB_AGENT_PARSE_MODE=backend`.
- Valid JavDB fetch modes after rollback are `static|agent`.
- Remove Playwright JavDB browser session code, APIs, UI controls, and tests.
- Remove manual JavDB cookie JSON editing from the UI.
- Do not expose raw cookie values in UI or logs.
- Keep JavDB `static` mode as fallback.
- Keep the first implementation scoped to JavDB.
- JavBus behavior must remain unchanged.
- Existing storage and movie realtime hooks continue using EventSource as they do today.

---

## File Structure

### Backend rollback and config

- Modify `backend/app/modules/crawler/config/conf_reader.py`
  - Add `JAVDB_AGENT_PARSE_MODE`.
  - Change valid fetch modes from `static|browser` to `static|agent`.
- Modify `backend/app/modules/crawler/config/schemas.py`
  - Change `JAVDB_FETCH_MODE` literal.
  - Add `JAVDB_AGENT_PARSE_MODE`.
  - Remove JavDB browser-session schema classes.
- Modify `backend/app/modules/crawler/config/router.py`
  - Remove `/javdb-session*` endpoints.
  - Keep cookie test behavior but report Agent status instead of Playwright guidance.
  - Add Agent status/token endpoints once Agent service exists.
- Modify `scraper/fetchers/scrapling_fetcher.py`
  - Remove `JavDBBrowserSession`, `dynamic`, `browser_session`, and browser cookie normalization code.
- Modify `scraper/fetchers/site_fetcher.py`
  - Stop constructing `JavDBBrowserSession`.
  - Keep configured cookies for static fetches.
- Delete `scraper/fetchers/javdb_browser_session.py`.
- Delete `scraper/tests/test_javdb_browser_session.py`.
- Delete or rewrite `scraper/tests/test_scrapling_fetcher_browser_mode.py`.
- Modify `scraper/tests/test_site_fetcher.py`.
- Modify `scraper/tests/test_javdb_spider_access_guard.py`.
- Modify `backend/tests/test_crawler_config_api.py`.

### Frontend runtime state

- Create `frontend/src/stores/useCrawlerRuntimeStore.ts`
  - Central crawler runtime state and store actions.
- Create `frontend/src/realtime/applyRealtimeEvent.ts`
  - Convert EventSource realtime events into store actions.
- Modify `frontend/src/realtime/eventSourceClient.ts`
  - Track connection status via store actions without changing transport.
- Modify `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`
  - Hydrate runtime snapshots into store.
- Modify `frontend/src/pages/crawler/tasks/hooks/useTaskListRealtime.ts`
  - Apply EventSource updates to store.
- Modify `frontend/src/pages/crawler/runs/RunListPage.tsx`
  - Keep query data, also hydrate/update store.
- Modify `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`
  - Hydrate run, logs, details, and summary into store.
- Modify `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`
  - Apply EventSource updates to store.
- Modify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
  - Read active runtime data from store selectors.

### Frontend config UI and API

- Modify `frontend/src/api/crawler/crawlerConfig/types.ts`
  - Add Agent status/token/session response types.
  - Change `JavdbFetchMode` to `static|agent`.
  - Add `JavdbAgentParseMode`.
- Modify `frontend/src/api/crawler/crawlerConfig/index.ts`
  - Remove browser-session API wrappers.
  - Add Agent status/token API wrappers.
- Modify `frontend/src/pages/crawler/config/ConfigPage.tsx`
  - Remove Monaco cookie editor.
  - Remove Playwright browser-session controls.
  - Add Agent status, last heartbeat, last cookie sync, and token rotate controls.
- Modify `frontend/src/pages/crawler/config/ConfigPage.module.less`
  - Remove cookie editor styles when unused.
  - Add compact Agent status styles if needed.

### Backend Agent module

- Create `backend/app/models/crawler_agent.py`
  - `CrawlerAgent`, `CrawlerAgentSession`, `CrawlerAgentWorkItem`.
- Modify `backend/app/models/__init__.py`
  - Import new Agent models for Alembic metadata.
- Create `backend/alembic/versions/20260810_0001_add_crawler_agents.py`
  - Create Agent tables and indexes.
- Create `backend/app/modules/crawler/agent/__init__.py`.
- Create `backend/app/modules/crawler/agent/schemas.py`
  - Pydantic models for HTTP and WebSocket messages.
- Create `backend/app/modules/crawler/agent/auth.py`
  - Token hashing, verification, session creation, expiry checks.
- Create `backend/app/modules/crawler/agent/service.py`
  - Agent status, token rotation, cookie status.
- Create `backend/app/modules/crawler/agent/cookie_sync.py`
  - JavDB-only cookie validation and storage.
- Create `backend/app/modules/crawler/agent/registry.py`
  - In-memory WebSocket connection registry and heartbeat state.
- Create `backend/app/modules/crawler/agent/router.py`
  - HTTP endpoints and WebSocket endpoint.
- Modify `backend/app/main.py`
  - Include Agent router.

### Backend Agent parser and work execution

- Create `backend/app/modules/crawler/agent/parser_bridge.py`
  - Wrap DOM fragments and call existing JavDB parser functions.
- Create `backend/app/modules/crawler/agent/work_items.py`
  - Create, claim, complete, fail, and expire Agent work items.
- Create `backend/app/modules/crawler/agent/runtime.py`
  - Agent-mode list/detail orchestration entry points.
- Modify `backend/app/modules/crawler/runtime/threaded.py`
  - Route JavDB `JAVDB_FETCH_MODE=agent` runs to Agent runtime.
- Modify `scraper/spiders/javdb/javdb_parser.py`
  - Add helper entry points only if fragment wrapper requires clearer parser boundaries.

### Chrome extension

- Create `chrome-extension/manifest.json`.
- Create `chrome-extension/src/background.ts`.
- Create `chrome-extension/src/content.ts`.
- Create `chrome-extension/src/options.html`.
- Create `chrome-extension/src/options.ts`.
- Create `chrome-extension/package.json`.
- Create `chrome-extension/tsconfig.json`.
- Create `chrome-extension/vite.config.ts`.
- Create `chrome-extension/README.md`.

### Tests and docs

- Create `backend/tests/test_crawler_agent_auth.py`.
- Create `backend/tests/test_crawler_agent_cookie_sync.py`.
- Create `backend/tests/test_crawler_agent_ws.py`.
- Create `backend/tests/test_crawler_agent_parser_bridge.py`.
- Create `backend/tests/test_crawler_agent_work_items.py`.
- Create `frontend/src/stores/__tests__/crawler-runtime-store.test.ts`.
- Create `frontend/src/realtime/__tests__/applyRealtimeEvent.test.ts`.
- Modify existing crawler config and crawler page tests.
- Modify `README.md`.
- Modify `frontend/README.md` if extension build commands are added to frontend docs.

---

### Task 1: Roll Back Playwright Browser Mode and Normalize JavDB Config

**Files:**
- Modify: `backend/app/modules/crawler/config/conf_reader.py`
- Modify: `backend/app/modules/crawler/config/schemas.py`
- Modify: `backend/app/modules/crawler/config/router.py`
- Modify: `scraper/fetchers/scrapling_fetcher.py`
- Modify: `scraper/fetchers/site_fetcher.py`
- Modify: `scraper/spiders/javdb/javdb_spider.py`
- Delete: `scraper/fetchers/javdb_browser_session.py`
- Delete: `scraper/tests/test_javdb_browser_session.py`
- Modify: `scraper/tests/test_scrapling_fetcher.py`
- Delete or replace: `scraper/tests/test_scrapling_fetcher_browser_mode.py`
- Modify: `scraper/tests/test_site_fetcher.py`
- Modify: `scraper/tests/test_javdb_spider_access_guard.py`
- Modify: `backend/tests/test_crawler_config_api.py`

**Interfaces:**
- Produces: `CrawlerRuntimeConfig.JAVDB_FETCH_MODE: str` with valid values `static|agent`.
- Produces: `CrawlerRuntimeConfig.JAVDB_AGENT_PARSE_MODE: str` with valid values `backend|extension`.
- Produces: `ScraplingFetcher.get(url, headers=None, cookies=None)` static-only behavior.

- [ ] **Step 1: Write failing config tests**

Add tests to `backend/tests/test_crawler_config_api.py`:

```python
def test_crawler_config_accepts_agent_mode(client, auth_headers):
    response = client.put(
        "/api/crawler/config",
        json={"JAVDB_FETCH_MODE": "agent", "JAVDB_AGENT_PARSE_MODE": "backend"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["JAVDB_FETCH_MODE"] == "agent"
    assert data["JAVDB_AGENT_PARSE_MODE"] == "backend"


def test_crawler_config_rejects_browser_mode(client, auth_headers):
    response = client.put(
        "/api/crawler/config",
        json={"JAVDB_FETCH_MODE": "browser"},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_javdb_session_endpoints_removed(client, auth_headers):
    response = client.get("/api/crawler/config/javdb-session", headers=auth_headers)

    assert response.status_code == 404
```

- [ ] **Step 2: Run config tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_config_api.py -v
```

Expected: failures show `browser` is still accepted, `JAVDB_AGENT_PARSE_MODE` is missing, or `/javdb-session` still exists.

- [ ] **Step 3: Write failing scraper tests**

Update `scraper/tests/test_site_fetcher.py` with static and Agent expectations:

```python
from backend.app.modules.crawler.config.conf_reader import CrawlerRuntimeConfig
from scraper.fetchers.site_fetcher import build_site_fetcher


def test_javdb_agent_mode_does_not_construct_playwright_session(monkeypatch):
    monkeypatch.setattr(
        "scraper.fetchers.site_fetcher.CookieManager.load",
        lambda self: {"locale": "zh"},
    )

    fetcher = build_site_fetcher(
        "javdb",
        CrawlerRuntimeConfig(JAVDB_FETCH_MODE="agent", JAVDB_AGENT_PARSE_MODE="backend"),
    )

    assert fetcher.cookies == {"locale": "zh"}
    assert not hasattr(fetcher, "browser_session")
    assert not getattr(fetcher, "dynamic", False)
```

Update `scraper/tests/test_javdb_spider_access_guard.py` by replacing any `JAVDB_FETCH_MODE="browser"` expectation with `agent` behavior that fails fast with an Agent-specific message:

```python
def test_javdb_agent_mode_reports_agent_unavailable_on_access_block(monkeypatch):
    monkeypatch.setattr(
        "scraper.spiders.javdb.javdb_spider.read_crawler_runtime_config",
        lambda: CrawlerRuntimeConfig(JAVDB_FETCH_MODE="agent", SECURITY_WAIT_SECONDS=120),
    )
    # Use the existing fake blocked page setup from this test module.
```

Use the existing fake page helper in that test file and assert the error message includes `Chrome Agent`.

- [ ] **Step 4: Run scraper tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest scraper/tests/test_site_fetcher.py scraper/tests/test_scrapling_fetcher.py scraper/tests/test_javdb_spider_access_guard.py -v
```

Expected: failures show browser-mode fields and messages still exist.

- [ ] **Step 5: Implement config changes**

Change `backend/app/modules/crawler/config/conf_reader.py`:

```python
CONFIG_KEYS: tuple[str, ...] = (
    "MAX_LIST_PAGES",
    "LIST_MAX_WORKERS",
    "DETAIL_MAX_WORKERS",
    "LIST_PAGE_DELAY_MIN",
    "LIST_PAGE_DELAY_MAX",
    "DETAIL_PAGE_DELAY_MIN",
    "DETAIL_PAGE_DELAY_MAX",
    "SECURITY_WAIT_SECONDS",
    "REQUEST_TIMEOUT",
    "INCREMENTAL_EXIST_THRESHOLD",
    "JAVDB_FETCH_MODE",
    "JAVDB_AGENT_PARSE_MODE",
)

VALID_JAVDB_FETCH_MODES = {"static", "agent"}
VALID_JAVDB_AGENT_PARSE_MODES = {"backend", "extension"}


@dataclass(frozen=True)
class CrawlerRuntimeConfig:
    MAX_LIST_PAGES: int = 50
    LIST_MAX_WORKERS: int = 1
    DETAIL_MAX_WORKERS: int = 1
    LIST_PAGE_DELAY_MIN: float = 4.0
    LIST_PAGE_DELAY_MAX: float = 5.0
    DETAIL_PAGE_DELAY_MIN: float = 2.0
    DETAIL_PAGE_DELAY_MAX: float = 3.0
    SECURITY_WAIT_SECONDS: float = 120.0
    REQUEST_TIMEOUT: int = 30
    INCREMENTAL_EXIST_THRESHOLD: int = 0
    JAVDB_FETCH_MODE: str = "static"
    JAVDB_AGENT_PARSE_MODE: str = "backend"
```

Add a branch in `read_crawler_config_dict()`:

```python
if key == "JAVDB_AGENT_PARSE_MODE":
    mode = str(raw_value).strip().lower()
    result[key] = mode if mode in VALID_JAVDB_AGENT_PARSE_MODES else defaults[key]
    continue
```

Change `backend/app/modules/crawler/config/schemas.py`:

```python
class ConfigUpdate(BaseModel):
    MAX_LIST_PAGES: int | None = Field(None, ge=1, le=100)
    LIST_MAX_WORKERS: int | None = Field(None, ge=1, le=32)
    DETAIL_MAX_WORKERS: int | None = Field(None, ge=1, le=32)
    LIST_PAGE_DELAY_MIN: float | None = Field(None, ge=0)
    LIST_PAGE_DELAY_MAX: float | None = Field(None, ge=0)
    DETAIL_PAGE_DELAY_MIN: float | None = Field(None, ge=0)
    DETAIL_PAGE_DELAY_MAX: float | None = Field(None, ge=0)
    SECURITY_WAIT_SECONDS: float | None = Field(None, ge=0)
    INCREMENTAL_EXIST_THRESHOLD: int | None = Field(None, ge=0)
    REQUEST_TIMEOUT: int | None = Field(None, ge=1)
    JAVDB_FETCH_MODE: Literal["static", "agent"] | None = None
    JAVDB_AGENT_PARSE_MODE: Literal["backend", "extension"] | None = None
```

Remove all `JavDBSession*` schema classes from the same file.

- [ ] **Step 6: Implement fetcher rollback**

Change `scraper/fetchers/scrapling_fetcher.py` to static-only:

```python
from __future__ import annotations

from scrapling.fetchers import Fetcher


class ScraplingFetcher:
    def __init__(
        self,
        headers: dict | None = None,
        cookies: dict | None = None,
        timeout: int = 30,
    ):
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.timeout = timeout

    def get(
        self,
        url: str,
        *,
        headers: dict | None = None,
        cookies: dict | None = None,
    ):
        merged_headers = {**self.headers, **(headers or {})}
        merged_cookies = {**self.cookies, **(cookies or {})}
        return Fetcher.get(
            url,
            headers=merged_headers,
            cookies=merged_cookies,
            timeout=self.timeout,
            impersonate="chrome",
        )
```

Change `scraper/fetchers/site_fetcher.py`:

```python
from __future__ import annotations

from backend.app.modules.crawler.config.conf_reader import CrawlerRuntimeConfig, read_crawler_runtime_config
from scraper.config.sites import JAVBUS_SITE, JAVDB_SITE
from scraper.cookies.cookie_manager import CookieManager
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher


def build_site_fetcher(
    source: str = "javdb",
    runtime_config: CrawlerRuntimeConfig | None = None,
) -> ScraplingFetcher:
    active_config = runtime_config or read_crawler_runtime_config()
    site_config = JAVBUS_SITE if source == "javbus" else JAVDB_SITE
    cookie_manager = CookieManager(site_config["cookie_file"])
    return ScraplingFetcher(
        headers=site_config["headers"],
        cookies=cookie_manager.load(),
        timeout=active_config.REQUEST_TIMEOUT,
    )
```

Delete `scraper/fetchers/javdb_browser_session.py`.

- [ ] **Step 7: Remove browser-session router endpoints**

In `backend/app/modules/crawler/config/router.py`, remove imports and endpoint functions for:

```text
GET /javdb-session
POST /javdb-session/open
POST /javdb-session/close
POST /javdb-session/check
POST /javdb-session/export
DELETE /javdb-session
```

Update the browser-specific failure copy in `test_cookies_config()`:

```python
if not access_state.ok:
    if fetch_mode == "static" and access_state.reason == "http_403":
        message = "JavDB static 模式返回 403，可切换 Agent 模式并通过 Chrome 插件访问"
    elif fetch_mode == "agent":
        message = "JavDB Agent 模式需要 Chrome 插件在线并完成页面采集"
    else:
        message = access_state.message
```

- [ ] **Step 8: Update JavDB access-block messages**

In `scraper/spiders/javdb/javdb_spider.py`, replace `browser_mode` checks with `agent_mode` checks:

```python
agent_mode = runtime_config.JAVDB_FETCH_MODE == "agent"
if agent_mode:
    error_message = (
        f"{prefix} 列表页 {page_no} 需要 Chrome Agent 访问: "
        "请确认 Chrome 插件已连接并同步 JavDB 验证状态"
    )
    self._emit(error_message, log_callback, "ERROR")
    raise AccessBlockedError(error_message, access_state=access_state)
```

Use equivalent detail-page copy:

```python
reason = (
    "JavDB Agent 模式需要 Chrome 插件在线并完成页面采集"
    if agent_mode
    else f"连续访问受限次数={verification_count}: {access_state.message}"
)
```

- [ ] **Step 9: Run rollback tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_config_api.py scraper/tests/test_site_fetcher.py scraper/tests/test_scrapling_fetcher.py scraper/tests/test_javdb_spider_access_guard.py -v
```

Expected: all selected tests pass.

- [ ] **Step 10: Commit rollback**

Run:

```bash
git add backend/app/modules/crawler/config scraper/fetchers scraper/spiders/javdb scraper/tests backend/tests/test_crawler_config_api.py
git rm -f scraper/fetchers/javdb_browser_session.py scraper/tests/test_javdb_browser_session.py scraper/tests/test_scrapling_fetcher_browser_mode.py
git commit -m "refactor: remove javdb playwright browser mode"
```

---

### Task 2: Add Crawler Runtime Store While Keeping EventSource

**Files:**
- Create: `frontend/src/stores/useCrawlerRuntimeStore.ts`
- Create: `frontend/src/stores/__tests__/crawler-runtime-store.test.ts`
- Create: `frontend/src/realtime/applyRealtimeEvent.ts`
- Create: `frontend/src/realtime/__tests__/applyRealtimeEvent.test.ts`
- Modify: `frontend/src/realtime/eventSourceClient.ts`

**Interfaces:**
- Consumes: existing `RealtimeEvent` types from `frontend/src/realtime/types.ts`.
- Produces: `useCrawlerRuntimeStore`.
- Produces: `applyRealtimeEvent(event: RealtimeEvent): void`.

- [ ] **Step 1: Write failing store tests**

Create `frontend/src/stores/__tests__/crawler-runtime-store.test.ts`:

```typescript
import { describe, expect, it, beforeEach } from 'vitest'
import { useCrawlerRuntimeStore } from '../useCrawlerRuntimeStore'

beforeEach(() => {
  useCrawlerRuntimeStore.getState().reset()
})

describe('useCrawlerRuntimeStore', () => {
  it('hydrates task runtime snapshots and replaces stats source state', () => {
    useCrawlerRuntimeStore.getState().hydrateTaskRuntime([
      {
        task_id: 'task-1',
        task_name: 'JavDB',
        runtime_status: 'running',
        latest_run_id: 'run-1',
        latest_run_status: 'running',
        latest_run_error: null,
      },
    ])

    expect(useCrawlerRuntimeStore.getState().runtimeByTaskId['task-1']?.runtime_status).toBe('running')
  })

  it('merges run detail updates by run id and task id', () => {
    useCrawlerRuntimeStore.getState().mergeRunDetails('run-1', [
      {
        id: 'detail-1',
        run_id: 'run-1',
        code: 'ABC-001',
        source_url: 'https://javdb.com/v/abc',
        source_name: 'ABC',
        source_url_name: null,
        task_url: null,
        task_final_url: null,
        task_url_type: null,
        status: 'saved',
        error: null,
        list_item_data: null,
        item_data: null,
        created_at: '2026-08-10T00:00:00Z',
        crawled_at: null,
        saved_at: null,
      },
    ])

    expect(useCrawlerRuntimeStore.getState().detailsByRunId['run-1']['detail-1']?.status).toBe('saved')
  })
})
```

- [ ] **Step 2: Run store tests to verify they fail**

Run:

```bash
cd frontend
npm test -- src/stores/__tests__/crawler-runtime-store.test.ts
```

Expected: module import fails because the store does not exist.

- [ ] **Step 3: Implement crawler runtime store**

Create `frontend/src/stores/useCrawlerRuntimeStore.ts`:

```typescript
import { create } from 'zustand'
import type { CrawlTaskRuntimeSnapshot } from '@/api/crawlTask/types'
import type { CrawlRun, CrawlRunDetailTask, RunLogEntry, RunTaskSummary } from '@/api/crawlerRun/types'

type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'error'

type CrawlerRuntimeState = {
  connectionStatus: ConnectionStatus
  lastConnectedAt: string | null
  lastResyncReason: string | null
  runtimeByTaskId: Record<string, CrawlTaskRuntimeSnapshot>
  runsById: Record<string, CrawlRun>
  detailsByRunId: Record<string, Record<string, CrawlRunDetailTask>>
  logsByRunId: Record<string, RunLogEntry[]>
  summaryByRunId: Record<string, RunTaskSummary>
  setConnectionStatus: (status: ConnectionStatus) => void
  markConnected: () => void
  markResyncRequired: (reason: string) => void
  hydrateTaskRuntime: (snapshots: CrawlTaskRuntimeSnapshot[]) => void
  hydrateRun: (run: CrawlRun) => void
  hydrateRunDetails: (runId: string, tasks: CrawlRunDetailTask[], summary?: RunTaskSummary) => void
  mergeRunDetails: (runId: string, tasks: CrawlRunDetailTask[]) => void
  hydrateRunLogs: (runId: string, logs: RunLogEntry[]) => void
  appendRunLog: (runId: string, log: RunLogEntry) => void
  clearRun: (runId: string) => void
  reset: () => void
}

const initialState = {
  connectionStatus: 'idle' as ConnectionStatus,
  lastConnectedAt: null,
  lastResyncReason: null,
  runtimeByTaskId: {},
  runsById: {},
  detailsByRunId: {},
  logsByRunId: {},
  summaryByRunId: {},
}

export const useCrawlerRuntimeStore = create<CrawlerRuntimeState>()((set) => ({
  ...initialState,
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  markConnected: () => set({ connectionStatus: 'connected', lastConnectedAt: new Date().toISOString() }),
  markResyncRequired: (reason) => set({ lastResyncReason: reason }),
  hydrateTaskRuntime: (snapshots) =>
    set({
      runtimeByTaskId: Object.fromEntries(snapshots.map((snapshot) => [snapshot.task_id, snapshot])),
    }),
  hydrateRun: (run) => set((state) => ({ runsById: { ...state.runsById, [run.id]: run } })),
  hydrateRunDetails: (runId, tasks, summary) =>
    set((state) => ({
      detailsByRunId: {
        ...state.detailsByRunId,
        [runId]: Object.fromEntries(tasks.map((task) => [task.id, task])),
      },
      summaryByRunId: summary ? { ...state.summaryByRunId, [runId]: summary } : state.summaryByRunId,
    })),
  mergeRunDetails: (runId, tasks) =>
    set((state) => ({
      detailsByRunId: {
        ...state.detailsByRunId,
        [runId]: {
          ...(state.detailsByRunId[runId] ?? {}),
          ...Object.fromEntries(tasks.map((task) => [task.id, task])),
        },
      },
    })),
  hydrateRunLogs: (runId, logs) =>
    set((state) => ({
      logsByRunId: { ...state.logsByRunId, [runId]: logs },
    })),
  appendRunLog: (runId, log) =>
    set((state) => ({
      logsByRunId: { ...state.logsByRunId, [runId]: [...(state.logsByRunId[runId] ?? []), log] },
    })),
  clearRun: (runId) =>
    set((state) => {
      const { [runId]: _run, ...runsById } = state.runsById
      const { [runId]: _details, ...detailsByRunId } = state.detailsByRunId
      const { [runId]: _logs, ...logsByRunId } = state.logsByRunId
      const { [runId]: _summary, ...summaryByRunId } = state.summaryByRunId
      return { runsById, detailsByRunId, logsByRunId, summaryByRunId }
    }),
  reset: () => set(initialState),
}))
```

- [ ] **Step 4: Write failing event application tests**

Create `frontend/src/realtime/__tests__/applyRealtimeEvent.test.ts`:

```typescript
import { beforeEach, describe, expect, it } from 'vitest'
import { applyRealtimeEvent } from '../applyRealtimeEvent'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import type { RealtimeEvent } from '../types'

beforeEach(() => {
  useCrawlerRuntimeStore.getState().reset()
})

function event<TPayload>(name: string, payload: TPayload, resourceId: string | null = null): RealtimeEvent<TPayload> {
  return {
    id: `evt-${name}`,
    event: name,
    scope: 'crawler',
    resource_id: resourceId,
    owner_id: 'owner-1',
    payload,
    created_at: '2026-08-10T00:00:00Z',
  }
}

describe('applyRealtimeEvent', () => {
  it('marks EventSource connection as connected', () => {
    applyRealtimeEvent(event('system.connected', { message: 'connected' }))

    expect(useCrawlerRuntimeStore.getState().connectionStatus).toBe('connected')
  })

  it('records resync reason', () => {
    applyRealtimeEvent(event('system.resync_required', { reason: 'queue_overflow' }))

    expect(useCrawlerRuntimeStore.getState().lastResyncReason).toBe('queue_overflow')
  })
})
```

- [ ] **Step 5: Run event application tests to verify they fail**

Run:

```bash
cd frontend
npm test -- src/realtime/__tests__/applyRealtimeEvent.test.ts
```

Expected: module import fails because `applyRealtimeEvent` does not exist.

- [ ] **Step 6: Implement event application helper**

Create `frontend/src/realtime/applyRealtimeEvent.ts`:

```typescript
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import type {
  CrawlerRunDetailUpdatedPayload,
  CrawlerRunLogAppendedPayload,
  CrawlerRunUpdatedPayload,
  CrawlerTaskStatusUpdatedPayload,
  RealtimeEvent,
} from './types'

export function applyRealtimeEvent(event: RealtimeEvent): void {
  const store = useCrawlerRuntimeStore.getState()

  if (event.event === 'system.connected') {
    store.markConnected()
    return
  }

  if (event.event === 'system.resync_required') {
    const reason = String((event.payload as { reason?: unknown }).reason ?? 'unknown')
    store.markResyncRequired(reason)
    return
  }

  if (event.event === 'crawler.task.status.updated') {
    const payload = event.payload as CrawlerTaskStatusUpdatedPayload
    store.hydrateTaskRuntime([
      ...Object.values(useCrawlerRuntimeStore.getState().runtimeByTaskId).filter((item) => item.task_id !== payload.task_id),
      payload,
    ])
    return
  }

  if (event.event === 'crawler.run.updated') {
    store.hydrateRun(event.payload as CrawlerRunUpdatedPayload)
    return
  }

  if (event.event === 'crawler.run.detail.updated') {
    const payload = event.payload as CrawlerRunDetailUpdatedPayload
    store.mergeRunDetails(payload.run_id, payload.tasks)
    if (payload.summary) {
      store.hydrateRunDetails(payload.run_id, Object.values(useCrawlerRuntimeStore.getState().detailsByRunId[payload.run_id] ?? {}), payload.summary)
    }
    return
  }

  if (event.event === 'crawler.run.log.appended') {
    const payload = event.payload as CrawlerRunLogAppendedPayload
    store.appendRunLog(payload.run_id, payload.log)
  }
}
```

- [ ] **Step 7: Wire EventSource client to connection store**

Modify `frontend/src/realtime/eventSourceClient.ts`:

```typescript
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import { applyRealtimeEvent } from './applyRealtimeEvent'
```

In `dispatch()`, call `applyRealtimeEvent(parsed)` before handler dispatch:

```typescript
applyRealtimeEvent(parsed)
for (const handler of handlers.get(eventName) ?? []) {
  handler(parsed)
}
```

In `connectRealtime()`:

```typescript
useCrawlerRuntimeStore.getState().setConnectionStatus('connecting')
```

In `source.onerror`:

```typescript
useCrawlerRuntimeStore.getState().setConnectionStatus('error')
emitLocalResync('connection_error')
```

- [ ] **Step 8: Run frontend store/realtime tests**

Run:

```bash
cd frontend
npm test -- src/stores/__tests__/crawler-runtime-store.test.ts src/realtime/__tests__/applyRealtimeEvent.test.ts
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit runtime store foundation**

Run:

```bash
git add frontend/src/stores frontend/src/realtime
git commit -m "feat: add crawler runtime store"
```

---

### Task 3: Migrate Crawler Pages to Runtime Store Without Changing EventSource

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`
- Modify: `frontend/src/pages/crawler/tasks/hooks/useTaskListRealtime.ts`
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/src/pages/crawler/runs/RunListPage.tsx`
- Modify: `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`
- Modify: `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`
- Modify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- Modify: existing crawler page tests under `frontend/src/pages/crawler/**/__tests__/`

**Interfaces:**
- Consumes: `useCrawlerRuntimeStore` from Task 2.
- Consumes: `applyRealtimeEvent(event)` side effects from Task 2.
- Produces: crawler pages that hydrate and read runtime state from store.

- [ ] **Step 1: Write failing task-list integration test**

Update `frontend/src/pages/crawler/tasks/__tests__/task-list-query.test.tsx` with an assertion that runtime state is hydrated in the store after list data is loaded:

```typescript
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'

it('hydrates task runtime snapshots into crawler runtime store', async () => {
  useCrawlerRuntimeStore.getState().reset()

  renderTaskListPage()

  await screen.findByText('运行中')

  expect(useCrawlerRuntimeStore.getState().runtimeByTaskId['task-1']?.runtime_status).toBe('running')
})
```

Use the existing render helper and mocked task-list response in that test file. If the existing fixture uses another task id, assert that id.

- [ ] **Step 2: Run task-list test to verify it fails**

Run:

```bash
cd frontend
npm test -- src/pages/crawler/tasks/__tests__/task-list-query.test.tsx
```

Expected: assertion fails because task-list data is still only in component state.

- [ ] **Step 3: Hydrate runtime store from task list data**

Modify `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`:

```typescript
import { useEffect } from 'react'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
```

Replace render-time `setState` logic with an effect:

```typescript
const hydrateTaskRuntime = useCrawlerRuntimeStore((state) => state.hydrateTaskRuntime)
const runtimeByTaskId = useCrawlerRuntimeStore((state) => state.runtimeByTaskId)

useEffect(() => {
  if (!listQuery.data?.runtime) return
  hydrateTaskRuntime(listQuery.data.runtime.tasks)
}, [hydrateTaskRuntime, listQuery.data?.runtime])
```

Keep local `stats` only if needed for rendering. Prefer deriving `stats` from `listQuery.data?.runtime.stats ?? initialStats` in this task to avoid a second mutable copy.

- [ ] **Step 4: Simplify task list realtime hook**

Modify `frontend/src/pages/crawler/tasks/hooks/useTaskListRealtime.ts` so it no longer receives `setRuntimeByTaskId` and `setStats`. It should still subscribe to:

```typescript
connectRealtime()

const unsubscribeResync = subscribeRealtime('system.resync_required', () => {
  refreshList()
})
```

The `crawler.task.status.updated` store update is already applied by `eventSourceClient` through `applyRealtimeEvent`.

- [ ] **Step 5: Write failing run-detail hydration test**

Update `frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx` or add a focused test file:

```typescript
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'

it('hydrates run detail data into crawler runtime store', async () => {
  useCrawlerRuntimeStore.getState().reset()

  renderRunDetailPage('run-1')

  await screen.findByText('运行日志')

  expect(useCrawlerRuntimeStore.getState().runsById['run-1']?.id).toBe('run-1')
  expect(Object.keys(useCrawlerRuntimeStore.getState().detailsByRunId['run-1'] ?? {}).length).toBeGreaterThan(0)
})
```

Use the existing mock fixtures in the run-detail tests.

- [ ] **Step 6: Run run-detail test to verify it fails**

Run:

```bash
cd frontend
npm test -- src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx
```

Expected: store hydration assertion fails.

- [ ] **Step 7: Hydrate store from run detail HTTP fetches**

Modify `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`:

```typescript
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
```

Inside `useRunDetail()`:

```typescript
const hydrateRun = useCrawlerRuntimeStore((state) => state.hydrateRun)
const hydrateRunDetails = useCrawlerRuntimeStore((state) => state.hydrateRunDetails)
const hydrateRunLogs = useCrawlerRuntimeStore((state) => state.hydrateRunLogs)
```

Update fetch helpers:

```typescript
const fetchRun = useCallback(async () => {
  if (!id) return
  const data = await getCrawlerRun(id)
  setRun(data)
  hydrateRun(data)
}, [hydrateRun, id])

const fetchLogs = useCallback(async () => {
  if (!id) return
  const data = await getCrawlerRunLogs(id)
  setLogs(data)
  hydrateRunLogs(id, data)
}, [hydrateRunLogs, id])
```

When both tasks and summary are known, call:

```typescript
hydrateRunDetails(id, data.rows, taskSummary)
```

If summary is fetched separately, call:

```typescript
hydrateRunDetails(id, Object.values(useCrawlerRuntimeStore.getState().detailsByRunId[id] ?? {}), data)
```

- [ ] **Step 8: Simplify run detail realtime hook**

Modify `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`:

- keep `connectRealtime()`
- keep resync subscription
- remove direct local mutations that duplicate `applyRealtimeEvent`
- keep terminal-state HTTP refresh behavior

The hook should still call `fetchRun()`, `fetchLogs()`, `fetchTasks()`, and `fetchTaskSummary()` when a run reaches `completed`, `failed`, or `stopped`.

- [ ] **Step 9: Run crawler frontend tests**

Run:

```bash
cd frontend
npm test -- src/pages/crawler/tasks/__tests__/task-list-query.test.tsx src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx src/pages/crawler/runs/__tests__/run-list-query.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 10: Commit page migration**

Run:

```bash
git add frontend/src/pages/crawler frontend/src/stores frontend/src/realtime
git commit -m "refactor: centralize crawler runtime state"
```

---

### Task 4: Add Agent Models, Migration, Auth, and Cookie Sync

**Files:**
- Create: `backend/app/models/crawler_agent.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260810_0001_add_crawler_agents.py`
- Create: `backend/app/modules/crawler/agent/__init__.py`
- Create: `backend/app/modules/crawler/agent/schemas.py`
- Create: `backend/app/modules/crawler/agent/auth.py`
- Create: `backend/app/modules/crawler/agent/cookie_sync.py`
- Create: `backend/app/modules/crawler/agent/service.py`
- Create: `backend/tests/test_crawler_agent_auth.py`
- Create: `backend/tests/test_crawler_agent_cookie_sync.py`

**Interfaces:**
- Produces: `hash_agent_token(token: str) -> str`.
- Produces: `verify_agent_token(token: str, token_hash: str) -> bool`.
- Produces: `sync_javdb_cookies(cookies: list[AgentCookie]) -> CookieSyncResult`.
- Produces: SQLAlchemy models `CrawlerAgent`, `CrawlerAgentSession`, `CrawlerAgentWorkItem`.

- [ ] **Step 1: Write failing Agent auth tests**

Create `backend/tests/test_crawler_agent_auth.py`:

```python
from datetime import UTC, datetime, timedelta

from backend.app.modules.crawler.agent.auth import (
    create_agent_session_id,
    hash_agent_token,
    session_is_expired,
    verify_agent_token,
)


def test_hash_agent_token_verifies_original_token() -> None:
    token_hash = hash_agent_token("agent-secret")

    assert verify_agent_token("agent-secret", token_hash)
    assert not verify_agent_token("wrong-secret", token_hash)


def test_agent_session_expiry_uses_utc_time() -> None:
    now = datetime(2026, 8, 10, tzinfo=UTC)

    assert not session_is_expired(now + timedelta(minutes=1), now=now)
    assert session_is_expired(now - timedelta(seconds=1), now=now)


def test_create_agent_session_id_has_agent_prefix() -> None:
    assert create_agent_session_id().startswith("ags_")
```

- [ ] **Step 2: Run auth tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_auth.py -v
```

Expected: import fails because the Agent auth module does not exist.

- [ ] **Step 3: Add Agent models and migration**

Create `backend/app/models/crawler_agent.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from shared.database.types import CompatibleJSON


class CrawlerAgent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawler_agents"
    __table_args__ = (
        Index("idx_crawler_agents_owner_status", "owner_id", "status"),
        Index("idx_crawler_agents_last_seen", "last_seen_at"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="Chrome Agent")
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="offline", index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_cookie_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)


class CrawlerAgentSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawler_agent_sessions"
    __table_args__ = (
        Index("idx_crawler_agent_sessions_session", "session_id", unique=True),
        Index("idx_crawler_agent_sessions_expires", "expires_at"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crawler_agents.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CrawlerAgentWorkItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawler_agent_work_items"
    __table_args__ = (
        Index("idx_crawler_agent_work_claim", "owner_id", "status", "claimed_until"),
        Index("idx_crawler_agent_work_run_status", "run_id", "status"),
        Index("idx_crawler_agent_work_detail", "detail_task_id"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawl_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    detail_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawl_run_detail_tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    url_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawl_task_urls.id", ondelete="SET NULL"), nullable=True, index=True)
    page_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawler_agents.id", ondelete="SET NULL"), nullable=True, index=True)
    claimed_until: Mapped[datetime | None] = mapped_column(nullable=True)
    error_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result_json: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)
```

Create matching Alembic migration `backend/alembic/versions/20260810_0001_add_crawler_agents.py` with `create_table()` and indexes matching the models. Set `down_revision = "20260727_0001"`.

Modify `backend/app/models/__init__.py`:

```python
from backend.app.models.crawler_agent import CrawlerAgent, CrawlerAgentSession, CrawlerAgentWorkItem
```

- [ ] **Step 4: Implement auth helpers**

Create `backend/app/modules/crawler/agent/auth.py`:

```python
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime


def hash_agent_token(token: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{token}".encode("utf-8")).hexdigest()
    return f"sha256${salt}${digest}"


def verify_agent_token(token: str, token_hash: str) -> bool:
    try:
        algorithm, salt, expected = token_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "sha256":
        return False
    digest = hashlib.sha256(f"{salt}:{token}".encode("utf-8")).hexdigest()
    return secrets.compare_digest(digest, expected)


def create_agent_token() -> str:
    return f"agt_{secrets.token_urlsafe(32)}"


def create_agent_session_id() -> str:
    return f"ags_{secrets.token_urlsafe(32)}"


def session_is_expired(expires_at: datetime, *, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= current
```

- [ ] **Step 5: Write failing cookie sync tests**

Create `backend/tests/test_crawler_agent_cookie_sync.py`:

```python
import json

from backend.app.modules.crawler.agent.cookie_sync import AgentCookie, sync_javdb_cookies


def test_sync_javdb_cookies_writes_only_javdb_domains(monkeypatch, tmp_path):
    cookie_dir = tmp_path / "cookies"
    monkeypatch.setattr("scraper.cookies.cookie_manager.COOKIE_DIR", cookie_dir)

    result = sync_javdb_cookies([
        AgentCookie(name="cf_clearance", value="ok", domain=".javdb.com", path="/"),
        AgentCookie(name="ignored", value="bad", domain="example.com", path="/"),
    ])

    assert result.accepted == 1
    assert result.rejected == 1
    saved = json.loads((cookie_dir / "javdb_cookies.json").read_text(encoding="utf-8"))
    assert saved[0]["name"] == "cf_clearance"
    assert saved[0]["value"] == "ok"


def test_sync_javdb_cookies_redacts_values_in_result(monkeypatch, tmp_path):
    monkeypatch.setattr("scraper.cookies.cookie_manager.COOKIE_DIR", tmp_path / "cookies")

    result = sync_javdb_cookies([
        AgentCookie(name="session", value="secret", domain="javdb.com", path="/"),
    ])

    assert "secret" not in result.model_dump_json()
```

- [ ] **Step 6: Implement cookie sync**

Create `backend/app/modules/crawler/agent/cookie_sync.py`:

```python
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from scraper.config import settings as scraper_paths

JAVDB_COOKIE_FILE = "javdb_cookies.json"


class AgentCookie(BaseModel):
    name: str
    value: str
    domain: str
    path: str = "/"
    expirationDate: float | None = None
    hostOnly: bool = False
    httpOnly: bool = False
    sameSite: str | None = None
    secure: bool = True
    session: bool = False
    storeId: str | None = None


class CookieSyncResult(BaseModel):
    accepted: int
    rejected: int
    cookie_names: list[str] = Field(default_factory=list)


def _cookie_path() -> Path:
    return scraper_paths.COOKIE_DIR / JAVDB_COOKIE_FILE


def _is_javdb_domain(domain: str) -> bool:
    normalized = domain.strip().lower().lstrip(".")
    return normalized == "javdb.com" or normalized.endswith(".javdb.com")


def sync_javdb_cookies(cookies: list[AgentCookie]) -> CookieSyncResult:
    accepted_rows: list[dict] = []
    rejected = 0
    for cookie in cookies:
        if not cookie.name or not _is_javdb_domain(cookie.domain):
            rejected += 1
            continue
        accepted_rows.append(cookie.model_dump())

    path = _cookie_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        __import__("json").dumps(accepted_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return CookieSyncResult(
        accepted=len(accepted_rows),
        rejected=rejected,
        cookie_names=[row["name"] for row in accepted_rows],
    )
```

- [ ] **Step 7: Run Agent auth and cookie tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_auth.py backend/tests/test_crawler_agent_cookie_sync.py -v
```

Expected: all selected tests pass.

- [ ] **Step 8: Run Alembic migration check**

Run:

```bash
source .venv/bin/activate
cd backend
alembic upgrade head
```

Expected: migration applies without SQL errors against the configured development database.

- [ ] **Step 9: Commit Agent model/auth foundation**

Run:

```bash
git add backend/app/models backend/alembic/versions backend/app/modules/crawler/agent backend/tests/test_crawler_agent_auth.py backend/tests/test_crawler_agent_cookie_sync.py
git commit -m "feat: add crawler agent auth and cookie sync"
```

---

### Task 5: Add Agent HTTP APIs and WebSocket Protocol

**Files:**
- Modify: `backend/app/modules/crawler/agent/schemas.py`
- Modify: `backend/app/modules/crawler/agent/service.py`
- Create: `backend/app/modules/crawler/agent/registry.py`
- Create: `backend/app/modules/crawler/agent/router.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_crawler_agent_ws.py`

**Interfaces:**
- Consumes: Agent models and auth helpers from Task 4.
- Produces: `POST /api/crawler/agent/token/rotate`.
- Produces: `GET /api/crawler/agent/status`.
- Produces: `POST /api/crawler/agent/sessions`.
- Produces: `WS /api/crawler/agent/ws?session=...`.

- [ ] **Step 1: Write failing Agent API/WebSocket tests**

Create `backend/tests/test_crawler_agent_ws.py`:

```python
def test_agent_status_defaults_to_offline(client, auth_headers):
    response = client.get("/api/crawler/agent/status", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] in {"offline", "not_configured"}
    assert "raw_token" not in data


def test_agent_session_rejects_invalid_token(client):
    response = client.post("/api/crawler/agent/sessions", json={"token": "bad-token"})

    assert response.status_code == 401


def test_agent_websocket_rejects_invalid_session(client):
    with client.websocket_connect("/api/crawler/agent/ws?session=bad-session") as websocket:
        message = websocket.receive_json()

    assert message["type"] == "server.error"
    assert message["payload"]["reason"] == "invalid_session"
```

- [ ] **Step 2: Run Agent API tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_ws.py -v
```

Expected: route import or 404 failures.

- [ ] **Step 3: Define Agent schemas**

Add to `backend/app/modules/crawler/agent/schemas.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentStatusResponse(BaseModel):
    status: Literal["not_configured", "offline", "online", "busy", "error"]
    agent_id: str | None = None
    name: str | None = None
    last_seen_at: datetime | None = None
    last_cookie_sync_at: datetime | None = None
    version: str | None = None


class AgentTokenRotateResponse(BaseModel):
    token: str
    status: AgentStatusResponse


class AgentSessionCreateRequest(BaseModel):
    token: str
    version: str | None = None
    name: str | None = None


class AgentSessionCreateResponse(BaseModel):
    session: str
    expires_at: datetime


class AgentMessage(BaseModel):
    id: str
    type: str
    sent_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ServerMessage(BaseModel):
    id: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Implement registry**

Create `backend/app/modules/crawler/agent/registry.py`:

```python
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket


@dataclass
class AgentConnection:
    agent_id: str
    owner_id: str
    websocket: WebSocket
    connected_at: datetime
    last_seen_at: datetime


class AgentConnectionRegistry:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._connections: dict[str, AgentConnection] = {}

    async def connect(self, *, agent_id: str, owner_id: str, websocket: WebSocket) -> AgentConnection:
        connection = AgentConnection(
            agent_id=agent_id,
            owner_id=owner_id,
            websocket=websocket,
            connected_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        )
        async with self._lock:
            self._connections[agent_id] = connection
        return connection

    async def disconnect(self, agent_id: str) -> None:
        async with self._lock:
            self._connections.pop(agent_id, None)

    async def touch(self, agent_id: str) -> None:
        async with self._lock:
            connection = self._connections.get(agent_id)
            if connection:
                connection.last_seen_at = datetime.now(UTC)

    async def send(self, agent_id: str, message_type: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            connection = self._connections.get(agent_id)
        if connection:
            await connection.websocket.send_json({
                "id": f"srv_{uuid.uuid4().hex}",
                "type": message_type,
                "payload": payload,
            })


agent_registry = AgentConnectionRegistry()
```

- [ ] **Step 5: Implement Agent router**

Create `backend/app/modules/crawler/agent/router.py` with:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.models.crawler_agent import CrawlerAgent, CrawlerAgentSession
from backend.app.modules.crawler.agent.auth import create_agent_session_id, create_agent_token, hash_agent_token, session_is_expired, verify_agent_token
from backend.app.modules.crawler.agent.registry import agent_registry
from backend.app.modules.crawler.agent.schemas import AgentSessionCreateRequest, AgentSessionCreateResponse, AgentStatusResponse, AgentTokenRotateResponse
from shared.schemas.common import success

router = APIRouter(prefix="/api/crawler/agent", tags=["crawler-agent"])


def _status(agent: CrawlerAgent | None) -> AgentStatusResponse:
    if agent is None:
        return AgentStatusResponse(status="not_configured")
    return AgentStatusResponse(
        status=agent.status, agent_id=str(agent.id), name=agent.name,
        last_seen_at=agent.last_seen_at, last_cookie_sync_at=agent.last_cookie_sync_at,
        version=agent.version,
    )


@router.get("/status")
def get_agent_status(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    agent = db.query(CrawlerAgent).filter(CrawlerAgent.owner_id == current_user.id).order_by(CrawlerAgent.created_at.desc()).first()
    return success(data=_status(agent).model_dump(mode="json"))


@router.post("/token/rotate")
def rotate_agent_token(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    raw_token = create_agent_token()
    agent = db.query(CrawlerAgent).filter(CrawlerAgent.owner_id == current_user.id).order_by(CrawlerAgent.created_at.desc()).first()
    if agent is None:
        agent = CrawlerAgent(owner_id=current_user.id, token_hash=hash_agent_token(raw_token), status="offline")
        db.add(agent)
    else:
        agent.token_hash = hash_agent_token(raw_token)
        agent.status = "offline"
    db.commit()
    db.refresh(agent)
    payload = AgentTokenRotateResponse(token=raw_token, status=_status(agent))
    return success(data=payload.model_dump(mode="json"))


@router.post("/sessions")
def create_agent_session(body: AgentSessionCreateRequest, db: Session = Depends(get_db)) -> dict:
    agents = db.query(CrawlerAgent).all()
    agent = next((item for item in agents if verify_agent_token(body.token, item.token_hash)), None)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")
    session_id = create_agent_session_id()
    expires_at = datetime.now(UTC) + timedelta(minutes=10)
    session = CrawlerAgentSession(agent_id=agent.id, owner_id=agent.owner_id, session_id=session_id, expires_at=expires_at)
    agent.version = body.version or agent.version
    agent.name = body.name or agent.name
    db.add(session)
    db.commit()
    return success(data=AgentSessionCreateResponse(session=session_id, expires_at=expires_at).model_dump(mode="json"))
```

Add WebSocket handling in the same file:

```python
@router.websocket("/ws")
async def agent_ws(websocket: WebSocket, session: str | None = Query(default=None), db: Session = Depends(get_db)) -> None:
    await websocket.accept()
    agent_session = db.query(CrawlerAgentSession).filter(CrawlerAgentSession.session_id == session).first()
    if agent_session is None or session_is_expired(agent_session.expires_at):
        await websocket.send_json({"id": "server_invalid_session", "type": "server.error", "payload": {"reason": "invalid_session"}})
        await websocket.close()
        return
    agent = db.get(CrawlerAgent, agent_session.agent_id)
    if agent is None:
        await websocket.send_json({"id": "server_missing_agent", "type": "server.error", "payload": {"reason": "missing_agent"}})
        await websocket.close()
        return
    agent.status = "online"
    agent.last_seen_at = datetime.now(UTC)
    db.commit()
    await agent_registry.connect(agent_id=str(agent.id), owner_id=str(agent.owner_id), websocket=websocket)
    await websocket.send_json({"id": "server_hello", "type": "server.hello", "payload": {"agent_id": str(agent.id)}})
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "agent.heartbeat":
                await agent_registry.touch(str(agent.id))
                agent.last_seen_at = datetime.now(UTC)
                db.commit()
                await websocket.send_json({"id": f"ack_{message.get('id')}", "type": "server.ack", "payload": {"message_id": message.get("id")}})
    except WebSocketDisconnect:
        pass
    finally:
        await agent_registry.disconnect(str(agent.id))
        agent.status = "offline"
        db.commit()
```

- [ ] **Step 6: Include router**

Modify `backend/app/main.py`:

```python
from backend.app.modules.crawler.agent.router import router as crawler_agent_router
```

Add near crawler routers:

```python
app.include_router(crawler_agent_router)
```

- [ ] **Step 7: Run Agent WebSocket tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_ws.py -v
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit Agent WebSocket foundation**

Run:

```bash
git add backend/app/main.py backend/app/modules/crawler/agent backend/tests/test_crawler_agent_ws.py
git commit -m "feat: add crawler agent websocket"
```

---

### Task 6: Add Backend Parser Bridge for Agent DOM Fragments

**Files:**
- Create: `backend/app/modules/crawler/agent/parser_bridge.py`
- Create: `backend/tests/test_crawler_agent_parser_bridge.py`

**Interfaces:**
- Consumes: `scraper.spiders.javdb.javdb_parser.parse_search_page`.
- Consumes: `scraper.spiders.javdb.javdb_parser.parse_detail_page`.
- Produces: `parse_agent_list_snapshot(snapshot: AgentPageSnapshot) -> list[dict]`.
- Produces: `parse_agent_detail_snapshot(snapshot: AgentPageSnapshot) -> dict`.

- [ ] **Step 1: Write failing parser bridge tests**

Create `backend/tests/test_crawler_agent_parser_bridge.py`:

```python
from backend.app.modules.crawler.agent.parser_bridge import AgentPageSnapshot, parse_agent_detail_snapshot, parse_agent_list_snapshot


def test_parse_agent_list_snapshot_uses_existing_javdb_selectors():
    snapshot = AgentPageSnapshot(
        page_kind="list",
        url="https://javdb.com/?page=1",
        source_page=1,
        fragments={
            "items": """
            <div class="item">
              <a class="box" href="/v/abc" title="ABC title">
                <img src="https://img.example/abc.jpg" />
                <div class="video-title"><strong>ABC-001</strong></div>
              </a>
            </div>
            """,
        },
    )

    tasks = parse_agent_list_snapshot(snapshot)

    assert tasks[0]["code"] == "ABC-001"
    assert tasks[0]["url"] == "https://javdb.com/v/abc"
    assert tasks[0]["source_page"] == 1


def test_parse_agent_detail_snapshot_uses_existing_javdb_selectors():
    snapshot = AgentPageSnapshot(
        page_kind="detail",
        url="https://javdb.com/v/abc",
        fragments={
            "title": '<h2 class="title is-4"><strong>ABC-001</strong><strong class="current-title">Movie Title</strong></h2>',
            "cover": '<div class="video-cover"><img src="https://img.example/cover.jpg" /></div>',
            "movie_panel": '<nav class="movie-panel-info"><div class="panel-block"><strong>日期:</strong><span class="value">2026-08-10</span></div></nav>',
            "magnets": '<div id="magnets-content"></div>',
        },
    )

    detail = parse_agent_detail_snapshot(snapshot)

    assert detail["code"] == "ABC-001"
    assert detail["source_name"] == "Movie Title"
    assert detail["release_date"] == "2026-08-10"
```

- [ ] **Step 2: Run parser bridge tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_parser_bridge.py -v
```

Expected: import fails because parser bridge does not exist.

- [ ] **Step 3: Implement parser bridge**

Create `backend/app/modules/crawler/agent/parser_bridge.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field
from scrapling.parser import Adaptor

from scraper.spiders.javdb.javdb_parser import parse_detail_page, parse_search_page


class AgentPageSnapshot(BaseModel):
    page_kind: str
    url: str
    fragments: dict[str, str] = Field(default_factory=dict)
    source_page: int = 1


class AgentSnapshotParseError(ValueError):
    pass


def _html_from_fragments(snapshot: AgentPageSnapshot, required: tuple[str, ...]) -> str:
    missing = [key for key in required if not snapshot.fragments.get(key)]
    if missing:
        raise AgentSnapshotParseError(f"missing_required_fragments:{','.join(missing)}")
    body = "\n".join(snapshot.fragments.values())
    return f"<!doctype html><html><head><title></title></head><body>{body}</body></html>"


def _page(snapshot: AgentPageSnapshot, required: tuple[str, ...]) -> Adaptor:
    return Adaptor(_html_from_fragments(snapshot, required), url=snapshot.url)


def parse_agent_list_snapshot(snapshot: AgentPageSnapshot) -> list[dict]:
    if snapshot.page_kind != "list":
        raise AgentSnapshotParseError("invalid_page_kind:list_required")
    page = _page(snapshot, ("items",))
    return parse_search_page(page, source_page=snapshot.source_page)


def parse_agent_detail_snapshot(snapshot: AgentPageSnapshot) -> dict:
    if snapshot.page_kind != "detail":
        raise AgentSnapshotParseError("invalid_page_kind:detail_required")
    page = _page(snapshot, ("title", "movie_panel"))
    detail = parse_detail_page(page)
    if not detail.get("source_name") and not detail.get("code"):
        raise AgentSnapshotParseError("parser_empty_detail")
    return detail
```

- [ ] **Step 4: Run parser bridge tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_parser_bridge.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit parser bridge**

Run:

```bash
git add backend/app/modules/crawler/agent/parser_bridge.py backend/tests/test_crawler_agent_parser_bridge.py
git commit -m "feat: parse javdb agent snapshots"
```

---

### Task 7: Add Agent Work Item Lifecycle and Backend Parse Runtime

**Files:**
- Create: `backend/app/modules/crawler/agent/work_items.py`
- Create: `backend/app/modules/crawler/agent/runtime.py`
- Modify: `backend/app/modules/crawler/agent/router.py`
- Modify: `backend/app/modules/crawler/runtime/threaded.py`
- Create: `backend/tests/test_crawler_agent_work_items.py`

**Interfaces:**
- Consumes: `CrawlerAgentWorkItem` model from Task 4.
- Consumes: parser bridge from Task 6.
- Produces: `create_list_work_items(db, run, task, url_entries) -> list[CrawlerAgentWorkItem]`.
- Produces: `claim_next_work_item(db, owner_id, agent_id, lease_seconds=120) -> CrawlerAgentWorkItem | None`.
- Produces: `complete_work_item_from_snapshot(db, work_item, snapshot) -> None`.
- Produces: Agent WebSocket `agent.task_request` and `agent.page_snapshot` handling.

- [ ] **Step 1: Write failing work item tests**

Create `backend/tests/test_crawler_agent_work_items.py`:

```python
from datetime import UTC, datetime, timedelta

from backend.app.models.crawler_agent import CrawlerAgentWorkItem
from backend.app.modules.crawler.agent.work_items import claim_next_work_item, expire_stale_work_items


def test_claim_next_work_item_marks_item_assigned(db_session, user, crawl_run):
    item = CrawlerAgentWorkItem(
        owner_id=user.id,
        run_id=crawl_run.id,
        task_id=crawl_run.task_id,
        page_kind="detail",
        url="https://javdb.com/v/abc",
        status="pending",
    )
    db_session.add(item)
    db_session.commit()

    claimed = claim_next_work_item(db_session, owner_id=str(user.id), agent_id="00000000-0000-0000-0000-000000000001")

    assert claimed is not None
    assert claimed.status == "assigned"
    assert claimed.attempt == 1
    assert claimed.claimed_until is not None


def test_expire_stale_work_items_returns_assigned_items_to_pending(db_session, user, crawl_run):
    item = CrawlerAgentWorkItem(
        owner_id=user.id,
        run_id=crawl_run.id,
        task_id=crawl_run.task_id,
        page_kind="detail",
        url="https://javdb.com/v/abc",
        status="assigned",
        claimed_until=datetime.now(UTC) - timedelta(seconds=1),
    )
    db_session.add(item)
    db_session.commit()

    expired = expire_stale_work_items(db_session, now=datetime.now(UTC))

    assert expired == 1
    assert item.status == "pending"
    assert item.claimed_until is None
```

Use existing backend fixtures from `backend/tests/conftest.py`. If fixture names differ, use the closest existing user/run fixtures in that file.

- [ ] **Step 2: Run work item tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_work_items.py -v
```

Expected: import fails because work item service does not exist.

- [ ] **Step 3: Implement work item lifecycle**

Create `backend/app/modules/crawler/agent/work_items.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.models.crawler_agent import CrawlerAgentWorkItem


def claim_next_work_item(
    db: Session,
    *,
    owner_id: str,
    agent_id: str,
    lease_seconds: int = 120,
) -> CrawlerAgentWorkItem | None:
    item = (
        db.query(CrawlerAgentWorkItem)
        .filter(CrawlerAgentWorkItem.owner_id == uuid.UUID(owner_id))
        .filter(CrawlerAgentWorkItem.status == "pending")
        .order_by(CrawlerAgentWorkItem.created_at.asc())
        .first()
    )
    if item is None:
        return None
    item.status = "assigned"
    item.assigned_agent_id = uuid.UUID(agent_id)
    item.attempt += 1
    item.claimed_until = datetime.now(UTC) + timedelta(seconds=lease_seconds)
    db.commit()
    db.refresh(item)
    return item


def expire_stale_work_items(db: Session, *, now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    items = (
        db.query(CrawlerAgentWorkItem)
        .filter(CrawlerAgentWorkItem.status.in_(["assigned", "running"]))
        .filter(CrawlerAgentWorkItem.claimed_until.isnot(None))
        .filter(CrawlerAgentWorkItem.claimed_until < current)
        .all()
    )
    for item in items:
        item.status = "pending"
        item.claimed_until = None
        item.assigned_agent_id = None
    db.commit()
    return len(items)
```

- [ ] **Step 4: Handle Agent task request in WebSocket**

Modify `backend/app/modules/crawler/agent/router.py` inside the WebSocket loop:

```python
from backend.app.modules.crawler.agent.work_items import claim_next_work_item
```

Add:

```python
if message.get("type") == "agent.task_request":
    item = claim_next_work_item(db, owner_id=str(agent.owner_id), agent_id=str(agent.id))
    if item is None:
        await websocket.send_json({"id": f"none_{message.get('id')}", "type": "task.none", "payload": {}})
    else:
        await websocket.send_json({
            "id": f"task_{item.id}",
            "type": "task.assigned",
            "payload": {
                "agent_task_id": str(item.id),
                "run_id": str(item.run_id),
                "detail_task_id": str(item.detail_task_id) if item.detail_task_id else None,
                "url_entry_id": str(item.url_entry_id) if item.url_entry_id else None,
                "page_kind": item.page_kind,
                "url": item.url,
                "attempt": item.attempt,
            },
        })
    continue
```

- [ ] **Step 5: Add snapshot completion path**

Create `backend/app/modules/crawler/agent/runtime.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.app.models.crawler_agent import CrawlerAgentWorkItem
from backend.app.modules.crawler.agent.parser_bridge import AgentPageSnapshot, parse_agent_detail_snapshot, parse_agent_list_snapshot


def complete_work_item_from_snapshot(
    db: Session,
    *,
    work_item_id: str,
    snapshot: AgentPageSnapshot,
) -> CrawlerAgentWorkItem:
    item = db.get(CrawlerAgentWorkItem, uuid.UUID(work_item_id))
    if item is None:
        raise ValueError("agent_work_item_not_found")
    if item.page_kind == "list":
        item.result_json = {"tasks": parse_agent_list_snapshot(snapshot)}
    elif item.page_kind == "detail":
        item.result_json = {"detail": parse_agent_detail_snapshot(snapshot)}
    else:
        raise ValueError(f"unsupported_page_kind:{item.page_kind}")
    item.status = "completed"
    item.error_reason = None
    item.claimed_until = None
    db.commit()
    db.refresh(item)
    return item
```

Wire `agent.page_snapshot` in router:

```python
from backend.app.modules.crawler.agent.parser_bridge import AgentPageSnapshot
from backend.app.modules.crawler.agent.runtime import complete_work_item_from_snapshot
```

```python
if message.get("type") == "agent.page_snapshot":
    payload = message.get("payload") or {}
    snapshot = AgentPageSnapshot.model_validate(payload["snapshot"])
    item = complete_work_item_from_snapshot(db, work_item_id=str(payload["agent_task_id"]), snapshot=snapshot)
    await websocket.send_json({"id": f"ack_{message.get('id')}", "type": "server.ack", "payload": {"agent_task_id": str(item.id)}})
    continue
```

- [ ] **Step 6: Route Agent mode from threaded runtime**

Modify `backend/app/modules/crawler/runtime/threaded.py` in `execute_threaded_crawl()`:

```python
if config.JAVDB_FETCH_MODE == "agent" and determine_source(task) == "javdb":
    from backend.app.modules.crawler.agent.runtime import execute_agent_crawl

    return execute_agent_crawl(
        db,
        run,
        task,
        runtime,
        detail_only=detail_only,
        selected_task_url_ids=selected_task_url_ids,
    )
```

Add `execute_agent_crawl()` to `backend/app/modules/crawler/agent/runtime.py` with first behavior:

```python
def execute_agent_crawl(db, run, task, runtime, *, detail_only=False, selected_task_url_ids=None):
    raise RuntimeError("JavDB Agent runtime is configured but Agent work execution is not available in this task")
```

This explicit error is temporary within this task and is removed in the same task before commit by adding queue creation and waiting behavior. Do not commit the explicit error.

Replace it before commit with a minimal implementation that creates detail work for existing pending detail tasks in `detail_only` runs and returns a result when all Agent work is completed. For full list+detail orchestration, use Task 8.

- [ ] **Step 7: Run work item tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_work_items.py backend/tests/test_crawler_agent_ws.py -v
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit work item lifecycle**

Run:

```bash
git add backend/app/modules/crawler/agent backend/app/modules/crawler/runtime/threaded.py backend/tests/test_crawler_agent_work_items.py backend/tests/test_crawler_agent_ws.py
git commit -m "feat: add crawler agent work lifecycle"
```

---

### Task 8: Add Agent Configuration UI and API Wrappers

**Files:**
- Modify: `frontend/src/api/crawler/crawlerConfig/types.ts`
- Modify: `frontend/src/api/crawler/crawlerConfig/index.ts`
- Modify: `frontend/src/pages/crawler/config/ConfigPage.tsx`
- Modify: `frontend/src/pages/crawler/config/ConfigPage.module.less`
- Modify: `frontend/src/pages/crawler/config/__tests__/config-page.test.tsx` if this test exists.
- Modify: `backend/app/modules/crawler/config/router.py`
- Modify: `backend/app/modules/crawler/agent/router.py`

**Interfaces:**
- Consumes: Agent status/token endpoints from Task 5.
- Produces: config page with Agent status and token rotation.
- Produces: no manual cookie JSON editor.

- [ ] **Step 1: Write failing frontend config test**

If there is no config page test file, create `frontend/src/pages/crawler/config/__tests__/config-page.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ConfigPage from '../ConfigPage'

vi.mock('@/api/crawler/crawlerConfig', () => ({
  fetchConfig: vi.fn().mockResolvedValue({ JAVDB_FETCH_MODE: 'agent', JAVDB_AGENT_PARSE_MODE: 'backend' }),
  updateConfig: vi.fn().mockResolvedValue({}),
  fetchAgentStatus: vi.fn().mockResolvedValue({ status: 'offline', last_cookie_sync_at: null, last_seen_at: null }),
  rotateAgentToken: vi.fn().mockResolvedValue({ token: 'agt_secret', status: { status: 'offline' } }),
}))

describe('ConfigPage Agent mode', () => {
  it('shows Agent status and removes raw cookie editor', async () => {
    render(<ConfigPage />)

    expect(await screen.findByText('Chrome Agent')).toBeInTheDocument()
    expect(screen.queryByText('Cookie JSON')).not.toBeInTheDocument()
  })
})
```

Use the project's existing test wrapper if the config page needs Ant Design app context.

- [ ] **Step 2: Run config UI test to verify it fails**

Run:

```bash
cd frontend
npm test -- src/pages/crawler/config
```

Expected: test fails because Agent UI does not exist and cookie editor remains.

- [ ] **Step 3: Update crawler config API types**

Modify `frontend/src/api/crawler/crawlerConfig/types.ts`:

```typescript
export type JavdbFetchMode = 'static' | 'agent'
export type JavdbAgentParseMode = 'backend' | 'extension'

export interface AppConfig {
  MAX_LIST_PAGES?: number
  LIST_MAX_WORKERS?: number
  DETAIL_MAX_WORKERS?: number
  LIST_PAGE_DELAY_MIN?: number
  LIST_PAGE_DELAY_MAX?: number
  DETAIL_PAGE_DELAY_MIN?: number
  DETAIL_PAGE_DELAY_MAX?: number
  SECURITY_WAIT_SECONDS?: number
  REQUEST_TIMEOUT?: number
  INCREMENTAL_EXIST_THRESHOLD?: number
  JAVDB_FETCH_MODE?: JavdbFetchMode
  JAVDB_AGENT_PARSE_MODE?: JavdbAgentParseMode
  [key: string]: unknown
}

export interface JavdbAgentStatus {
  status: 'not_configured' | 'offline' | 'online' | 'busy' | 'error'
  agent_id?: string | null
  name?: string | null
  last_seen_at?: string | null
  last_cookie_sync_at?: string | null
  version?: string | null
}

export interface JavdbAgentTokenRotateResponse {
  token: string
  status: JavdbAgentStatus
}
```

- [ ] **Step 4: Update crawler config API wrappers**

Modify `frontend/src/api/crawler/crawlerConfig/index.ts`:

```typescript
import type { JavdbAgentStatus, JavdbAgentTokenRotateResponse } from './types.ts'

export function fetchAgentStatus(): Promise<JavdbAgentStatus> {
  return request.get<JavdbAgentStatus>('/api/crawler/agent/status')
}

export function rotateAgentToken(): Promise<JavdbAgentTokenRotateResponse> {
  return request.post<JavdbAgentTokenRotateResponse>('/api/crawler/agent/token/rotate', {})
}
```

Remove `fetchCookiesConfig`, `updateCookiesConfig`, and all `javdb-session` wrappers from the public config page usage. Keep cookie test wrapper only if it remains useful for static mode diagnostics.

- [ ] **Step 5: Replace config page cookie/session UI with Agent UI**

Modify `frontend/src/pages/crawler/config/ConfigPage.tsx`:

- remove Monaco editor imports and cookie JSON state
- remove `fetchCookiesConfig`, `updateCookiesConfig`, and all `JavDBSession*` imports
- add `fetchAgentStatus` and `rotateAgentToken`
- add local state:

```typescript
const [agentStatus, setAgentStatus] = useState<JavdbAgentStatus | null>(null)
const [agentToken, setAgentToken] = useState<string | null>(null)
const [agentLoading, setAgentLoading] = useState(false)
```

Add a status refresh:

```typescript
const refreshAgentStatus = useCallback(async () => {
  const status = await fetchAgentStatus()
  setAgentStatus(status)
  return status
}, [])
```

Add token rotation:

```typescript
const handleRotateAgentToken = async () => {
  setAgentLoading(true)
  try {
    const result = await rotateAgentToken()
    setAgentToken(result.token)
    setAgentStatus(result.status)
    message.success('Agent Token 已生成，请保存到 Chrome 插件')
  } catch (error: unknown) {
    message.error(getErrorMessage(error))
  } finally {
    setAgentLoading(false)
  }
}
```

Render a compact Agent card:

```tsx
<Card title="Chrome Agent">
  <Descriptions column={1} size="small">
    <Descriptions.Item label="状态">{agentStatus?.status ?? 'not_configured'}</Descriptions.Item>
    <Descriptions.Item label="最后心跳">{agentStatus?.last_seen_at ?? '-'}</Descriptions.Item>
    <Descriptions.Item label="最后 Cookie 同步">{agentStatus?.last_cookie_sync_at ?? '-'}</Descriptions.Item>
  </Descriptions>
  {agentToken && (
    <Alert
      type="warning"
      showIcon
      message="Agent Token 仅显示一次"
      description={<Typography.Text copyable>{agentToken}</Typography.Text>}
    />
  )}
  <Space>
    <Button onClick={refreshAgentStatus} loading={agentLoading}>刷新状态</Button>
    <Popconfirm title="重新生成后旧 Token 将失效" onConfirm={handleRotateAgentToken}>
      <Button danger loading={agentLoading}>重新生成 Agent Token</Button>
    </Popconfirm>
  </Space>
</Card>
```

Update fetch mode segmented options:

```tsx
<Segmented
  options={[
    { label: '静态请求', value: 'static' },
    { label: 'Chrome Agent', value: 'agent' },
  ]}
/>
```

Add parse mode segmented options:

```tsx
<Segmented
  options={[
    { label: '后端解析', value: 'backend' },
    { label: '插件解析', value: 'extension', disabled: true },
  ]}
/>
```

- [ ] **Step 6: Run config frontend tests**

Run:

```bash
cd frontend
npm test -- src/pages/crawler/config
npm run build
```

Expected: tests and build pass.

- [ ] **Step 7: Commit Agent config UI**

Run:

```bash
git add frontend/src/api/crawler/crawlerConfig frontend/src/pages/crawler/config backend/app/modules/crawler/config/router.py backend/app/modules/crawler/agent/router.py
git commit -m "feat: add javdb agent config ui"
```

---

### Task 9: Add Chrome Extension Package and Documentation

**Files:**
- Create: `chrome-extension/package.json`
- Create: `chrome-extension/tsconfig.json`
- Create: `chrome-extension/vite.config.ts`
- Create: `chrome-extension/manifest.json`
- Create: `chrome-extension/src/background.ts`
- Create: `chrome-extension/src/content.ts`
- Create: `chrome-extension/src/options.html`
- Create: `chrome-extension/src/options.ts`
- Create: `chrome-extension/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Agent session endpoint `POST /api/crawler/agent/sessions`.
- Consumes: Agent WebSocket endpoint `WS /api/crawler/agent/ws?session=...`.
- Produces: MV3 extension that can connect, heartbeat, sync cookies, request work, and send page snapshots.

- [ ] **Step 1: Create extension package files**

Create `chrome-extension/package.json`:

```json
{
  "name": "media-forge-javdb-agent",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "build": "vite build",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {},
  "devDependencies": {
    "@types/chrome": "^0.0.287",
    "typescript": "^6.0.0",
    "vite": "^8.0.0"
  }
}
```

Create `chrome-extension/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "types": ["chrome"],
    "skipLibCheck": true
  },
  "include": ["src/**/*.ts"]
}
```

Create `chrome-extension/vite.config.ts`:

```typescript
import { defineConfig } from 'vite'

export default defineConfig({
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        background: 'src/background.ts',
        content: 'src/content.ts',
        options: 'src/options.html',
      },
      output: {
        entryFileNames: '[name].js',
      },
    },
  },
})
```

- [ ] **Step 2: Create MV3 manifest**

Create `chrome-extension/manifest.json`:

```json
{
  "manifest_version": 3,
  "name": "Media Forge JavDB Agent",
  "version": "0.1.0",
  "permissions": ["storage", "cookies", "tabs", "scripting"],
  "host_permissions": ["https://javdb.com/*", "https://*.javdb.com/*", "http://localhost/*", "http://127.0.0.1/*"],
  "background": {
    "service_worker": "background.js",
    "type": "module"
  },
  "content_scripts": [
    {
      "matches": ["https://javdb.com/*", "https://*.javdb.com/*"],
      "js": ["content.js"],
      "run_at": "document_idle"
    }
  ],
  "options_page": "options.html"
}
```

- [ ] **Step 3: Implement content script fragment extraction**

Create `chrome-extension/src/content.ts`:

```typescript
type PageSnapshot = {
  page_kind: 'list' | 'detail'
  url: string
  source_page?: number
  fragments: Record<string, string>
}

function outer(selector: string): string {
  return document.querySelector(selector)?.outerHTML ?? ''
}

function detectPageKind(): 'list' | 'detail' {
  return location.pathname.startsWith('/v/') ? 'detail' : 'list'
}

function sourcePage(): number {
  const value = new URL(location.href).searchParams.get('page')
  const parsed = Number(value || '1')
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1
}

function snapshot(): PageSnapshot {
  const pageKind = detectPageKind()
  if (pageKind === 'detail') {
    return {
      page_kind: 'detail',
      url: location.href,
      fragments: {
        title: outer('.video-detail h2.title.is-4, h2.title.is-4'),
        cover: outer('.video-cover'),
        movie_panel: outer('nav.movie-panel-info, .movie-panel-info'),
        tags: outer('#tags'),
        magnets: outer('#magnets-content'),
      },
    }
  }
  return {
    page_kind: 'list',
    url: location.href,
    source_page: sourcePage(),
    fragments: {
      section_title: outer('.section-title'),
      items: Array.from(document.querySelectorAll('div.item')).map((node) => node.outerHTML).join('\n'),
    },
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== 'collect_snapshot') return false
  sendResponse({ snapshot: snapshot() })
  return true
})
```

- [ ] **Step 4: Implement background WebSocket client**

Create `chrome-extension/src/background.ts`:

```typescript
type AgentSettings = {
  backendUrl: string
  token: string
}

let socket: WebSocket | null = null

async function settings(): Promise<AgentSettings | null> {
  const data = await chrome.storage.sync.get(['backendUrl', 'token'])
  if (!data.backendUrl || !data.token) return null
  return { backendUrl: String(data.backendUrl).replace(/\/$/, ''), token: String(data.token) }
}

async function createSession(config: AgentSettings): Promise<string> {
  const response = await fetch(`${config.backendUrl}/api/crawler/agent/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: config.token, version: chrome.runtime.getManifest().version, name: 'Chrome Agent' }),
  })
  if (!response.ok) throw new Error(`session_failed:${response.status}`)
  const payload = await response.json()
  return payload.data.session
}

async function javdbCookies() {
  const cookies = await chrome.cookies.getAll({ domain: 'javdb.com' })
  return cookies.map((cookie) => ({
    name: cookie.name,
    value: cookie.value,
    domain: cookie.domain,
    path: cookie.path,
    expirationDate: cookie.expirationDate ?? null,
    hostOnly: cookie.hostOnly,
    httpOnly: cookie.httpOnly,
    sameSite: cookie.sameSite ?? null,
    secure: cookie.secure,
    session: cookie.session,
    storeId: cookie.storeId ?? null,
  }))
}

function wsUrl(backendUrl: string, session: string): string {
  const url = new URL(backendUrl)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = '/api/crawler/agent/ws'
  url.search = `?session=${encodeURIComponent(session)}`
  return url.toString()
}

async function connect() {
  const config = await settings()
  if (!config) return
  const session = await createSession(config)
  socket = new WebSocket(wsUrl(config.backendUrl, session))
  socket.addEventListener('open', async () => {
    send('agent.hello', { version: chrome.runtime.getManifest().version })
    send('agent.cookie_sync', { cookies: await javdbCookies() })
    setInterval(() => send('agent.heartbeat', {}), 20_000)
  })
  socket.addEventListener('message', (event) => {
    void handleServerMessage(JSON.parse(String(event.data)))
  })
}

function send(type: string, payload: Record<string, unknown>) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return
  socket.send(JSON.stringify({ id: `msg_${crypto.randomUUID()}`, type, sent_at: new Date().toISOString(), payload }))
}

async function handleServerMessage(message: { type: string; payload?: Record<string, unknown> }) {
  if (message.type !== 'task.assigned') return
  const payload = message.payload ?? {}
  const url = String(payload.url)
  const tab = await chrome.tabs.create({ url, active: false })
  if (!tab.id) return
  await waitForTabComplete(tab.id)
  const responses = await chrome.tabs.sendMessage(tab.id, { type: 'collect_snapshot' })
  send('agent.page_snapshot', {
    agent_task_id: payload.agent_task_id,
    snapshot: responses.snapshot,
    cookies: await javdbCookies(),
  })
}

function waitForTabComplete(tabId: number): Promise<void> {
  return new Promise((resolve) => {
    const listener = (updatedTabId: number, changeInfo: chrome.tabs.TabChangeInfo) => {
      if (updatedTabId === tabId && changeInfo.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(listener)
        resolve()
      }
    }
    chrome.tabs.onUpdated.addListener(listener)
  })
}

void connect()
```

- [ ] **Step 5: Implement options page**

Create `chrome-extension/src/options.html`:

```html
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Media Forge JavDB Agent</title>
  </head>
  <body>
    <label>
      Backend URL
      <input id="backendUrl" placeholder="http://127.0.0.1:8000" />
    </label>
    <label>
      Agent Token
      <input id="token" type="password" />
    </label>
    <button id="save">Save</button>
    <script type="module" src="./options.ts"></script>
  </body>
</html>
```

Create `chrome-extension/src/options.ts`:

```typescript
const backendUrl = document.querySelector<HTMLInputElement>('#backendUrl')
const token = document.querySelector<HTMLInputElement>('#token')
const save = document.querySelector<HTMLButtonElement>('#save')

chrome.storage.sync.get(['backendUrl', 'token']).then((data) => {
  if (backendUrl) backendUrl.value = String(data.backendUrl ?? '')
  if (token) token.value = String(data.token ?? '')
})

save?.addEventListener('click', () => {
  void chrome.storage.sync.set({
    backendUrl: backendUrl?.value ?? '',
    token: token?.value ?? '',
  })
})
```

- [ ] **Step 6: Build extension**

Run:

```bash
cd chrome-extension
npm install
npm run typecheck
npm run build
```

Expected: typecheck and build pass, `chrome-extension/dist` contains `background.js`, `content.js`, and options output.

- [ ] **Step 7: Document extension installation and Agent flow**

Create `chrome-extension/README.md`:

```markdown
# Media Forge JavDB Agent

This Chrome extension lets a verified real Chrome session collect JavDB page
fragments for Media Forge backend parsing.

## Build

```bash
npm install
npm run build
```

## Install

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Load unpacked extension from `chrome-extension/dist`.
4. Open extension options.
5. Enter the Media Forge backend URL.
6. Enter the Agent Token generated in Media Forge crawler config.

The extension syncs only JavDB cookies and sends only DOM fragments required by
the backend parser.
```

Update root `README.md` with a short JavDB Agent section:

```markdown
### JavDB Chrome Agent

When JavDB rejects backend HTTP or Playwright browser access, set
`JAVDB_FETCH_MODE=agent` and use the Chrome extension in `chrome-extension/`.
The frontend still receives run status through EventSource. The extension uses
WebSocket only for Agent task assignment, Cookie sync, and page snapshot upload.
```

- [ ] **Step 8: Run broad verification**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_auth.py backend/tests/test_crawler_agent_cookie_sync.py backend/tests/test_crawler_agent_ws.py backend/tests/test_crawler_agent_parser_bridge.py backend/tests/test_crawler_agent_work_items.py backend/tests/test_crawler_config_api.py -v
cd frontend
npm run build
cd ../chrome-extension
npm run typecheck
npm run build
```

Expected: all selected backend tests pass, frontend build passes, extension typecheck/build passes.

- [ ] **Step 9: Commit extension and docs**

Run:

```bash
git add chrome-extension README.md frontend/README.md
git commit -m "feat: add javdb chrome agent extension"
```

---

## Self-Review

### Spec Coverage

- Playwright rollback is covered by Task 1.
- EventSource is preserved by Tasks 2 and 3.
- Runtime store management is covered by Tasks 2 and 3.
- Agent WebSocket is covered by Task 5.
- Agent token/session auth is covered by Tasks 4 and 5.
- Cookie auto-sync is covered by Tasks 4, 5, 8, and 9.
- Backend parse mode is covered by Tasks 6 and 7.
- Config UI changes are covered by Task 8.
- Chrome extension implementation is covered by Task 9.
- JavBus regression is covered by Task 1 test selection and Task 9 broad verification.

### Placeholder Scan

The plan contains no placeholder markers and no bare "write tests" instruction without concrete test examples.

### Type Consistency

- `JAVDB_FETCH_MODE` uses `static|agent` in backend and frontend.
- `JAVDB_AGENT_PARSE_MODE` uses `backend|extension` in backend and frontend.
- Agent WebSocket uses `/api/crawler/agent/ws?session=...`.
- Agent session creation uses `POST /api/crawler/agent/sessions`.
- Runtime state helpers use the same names across store, event application, and page migration tasks.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-10-javdb-chrome-agent-backend-parse.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
