# JavDB Chrome Agent Backend Parse Design

Date: 2026-08-10

## Context

Media Forge currently has a JavDB static fetch path and a recently added
Playwright browser-session path. In practice, JavDB rejects the Playwright
browser environment with a repeated human-verification loop, while the user's
ordinary Chrome can pass verification.

This means the reliable browser identity is the user's real Chrome session, not
the backend's Playwright Chromium profile. The next design should move JavDB
page access into a Chrome extension running in the user's normal browser, while
keeping parsing, persistence, run orchestration, and task status management in
Media Forge.

The frontend/backend realtime connection should remain EventSource/SSE. The
new WebSocket requirement applies only to the Chrome extension Agent and the
backend.

## Goals

- Replace JavDB Playwright browser mode with a Chrome extension Agent path.
- Keep frontend/backend realtime transport as the existing EventSource stream.
- Add a frontend runtime store for crawler run/task state so realtime updates
  are managed centrally instead of being scattered across page-local state.
- Use WebSocket only between the Chrome extension Agent and backend.
- Support an initial `backend` parse mode where the extension collects page
  fragments and the backend reuses existing JavDB parser logic.
- Automatically sync JavDB cookies from the extension to the backend; remove
  the manual cookie JSON editor from the configuration UI.
- Keep JavDB `static` mode as a fallback for environments where backend HTTP
  access still works.
- Keep the first implementation scoped to JavDB.

## Non-Goals

- Do not keep or improve the Playwright persistent browser-session mode.
- Do not replace the frontend EventSource stream with WebSocket.
- Do not solve captchas, bypass human verification, or automate security
  checks.
- Do not scrape cookies from arbitrary domains; only JavDB cookies are in
  scope.
- Do not make the extension parse and persist full movie records in the first
  implementation.
- Do not redesign the crawler task model, movie persistence model, or storage
  worker realtime model.

## Recommended Architecture

Use two separate realtime-style channels:

```text
Frontend UI  <---- EventSource ----  Media Forge backend
Chrome Agent <---- WebSocket  -----> Media Forge backend
```

The existing `RealtimeEventBus` remains the backend source for UI updates.
Crawler and storage runtime events continue flowing through:

```text
GET /api/events/stream?token=...
```

Add a separate Chrome Agent WebSocket endpoint, for example:

```text
WS /api/crawler/agent/ws
```

The Agent WebSocket owns task assignment, page snapshot upload, heartbeat,
cookie sync, and Agent error reporting. It should publish normal crawler run
events back into `RealtimeEventBus` so the UI keeps receiving status through
EventSource.

## Configuration

Replace the JavDB fetch mode values with:

```text
JAVDB_FETCH_MODE=static|agent
JAVDB_AGENT_PARSE_MODE=backend|extension
```

Initial supported state:

```text
JAVDB_FETCH_MODE=agent
JAVDB_AGENT_PARSE_MODE=backend
```

`extension` parse mode is reserved for a later implementation where the
extension sends structured movie/list data instead of DOM fragments.

Remove `browser` from valid JavDB fetch modes once the Playwright path is
rolled back.

## Rollback Scope

Remove the Playwright browser-session implementation and UI/API surface:

- remove `scraper/fetchers/javdb_browser_session.py`
- remove browser-mode branches from `ScraplingFetcher`
- remove browser-session construction from `build_site_fetcher`
- remove `/api/crawler/config/javdb-session*` endpoints
- remove JavDB browser-session schemas
- remove config-page session controls such as "打开辅助验证浏览器"
- remove Playwright-specific tests
- remove README/docs that instruct users to use Playwright profile verification
- remove `browser` from `VALID_JAVDB_FETCH_MODES`

Keep:

- `static` mode
- existing cookie file read/write utilities where useful
- existing JavDB parser, spider constants, URL helpers, and persistence pipeline

Manual cookie JSON configuration should no longer be exposed in the UI. Cookie
storage can remain internally because the Agent will write synchronized JavDB
cookies to the backend.

## Frontend Runtime Store

Add a crawler runtime store, for example:

```text
frontend/src/stores/useCrawlerRuntimeStore.ts
```

The store should manage runtime snapshots and event-derived state, not replace
all server data loading.

Recommended state:

```text
connectionStatus: "idle" | "connecting" | "connected" | "error"
lastConnectedAt: string | null
lastResyncReason: string | null
runtimeByTaskId: Record<string, CrawlTaskRuntimeSnapshot>
runsById: Record<string, CrawlRun>
detailsByRunId: Record<string, Record<string, CrawlRunDetailTask>>
logsByRunId: Record<string, RunLogEntry[]>
summaryByRunId: Record<string, RunTaskSummary>
```

Recommended actions:

```text
applyRealtimeEvent(event)
hydrateTaskRuntime(snapshots)
hydrateRun(run)
hydrateRunDetails(runId, tasks, summary)
hydrateRunLogs(runId, logs)
markResyncRequired(reason)
clearRun(runId)
reset()
```

Initial page load still uses HTTP APIs:

- task list loads tasks and runtime snapshots through existing endpoints
- run detail loads run, logs, tasks, and summary through existing endpoints
- EventSource updates then patch the store
- `system.resync_required` triggers the existing HTTP refresh and then hydrates
  the store with fresh snapshots

This avoids conflicts with pagination, filtering, and TanStack Query caches.
The store should hold active runtime state and recently viewed run state; it
should not become a permanent client-side database.

## EventSource Integration

Keep `frontend/src/realtime/eventSourceClient.ts` as the transport client.

Add a small event-application boundary:

```text
frontend/src/realtime/applyRealtimeEvent.ts
```

Its job is to map existing realtime events into store actions:

- `system.connected` updates connection status
- `system.resync_required` records resync reason
- `crawler.task.status.updated` updates `runtimeByTaskId`
- `crawler.run.updated` updates `runsById`
- `crawler.run.detail.updated` merges detail tasks and summary
- `crawler.run.log.appended` appends a run log entry

The existing page hooks can be migrated incrementally:

1. keep `connectRealtime()` / `subscribeRealtime()` calls
2. replace direct local `setState` patches with store actions
3. hydrate store from existing HTTP fetch results
4. read active runtime state from store selectors

Storage and movie realtime hooks can keep their current local behavior unless a
later change intentionally centralizes them.

## Chrome Agent WebSocket

Add a dedicated backend module:

```text
backend/app/modules/crawler/agent/
```

Suggested files:

```text
router.py
schemas.py
auth.py
service.py
registry.py
parser_bridge.py
cookie_sync.py
```

Suggested endpoint:

```text
WS /api/crawler/agent/ws
```

The extension cannot reliably send arbitrary custom headers in a browser
WebSocket. Use one of these authentication options:

1. short-lived session token returned by an authenticated HTTP endpoint
2. Agent token in the WebSocket subprotocol
3. Agent token in query string with strict logging redaction

Recommended first implementation:

```text
POST /api/crawler/agent/sessions
WS   /api/crawler/agent/ws?session=...
```

The user config page generates or rotates an Agent token. The extension stores
only the Agent token and backend URL. The extension first exchanges the token
for a short-lived session id, then opens the WebSocket with that session id.

## Agent Message Protocol

Use an envelope with idempotency and acknowledgements:

```json
{
  "id": "msg_...",
  "type": "agent.page_snapshot",
  "sent_at": "2026-08-10T12:00:00Z",
  "payload": {}
}
```

Core message types from extension to backend:

```text
agent.hello
agent.heartbeat
agent.cookie_sync
agent.task_request
agent.page_snapshot
agent.task_failed
agent.log
```

Core message types from backend to extension:

```text
server.hello
server.ack
server.error
task.assigned
task.cancelled
task.none
```

Every task-related message should include:

```text
agent_task_id
run_id
detail_task_id | url_entry_id
page_kind: "list" | "detail"
url
attempt
```

## Backend Parse Mode

In `JAVDB_AGENT_PARSE_MODE=backend`, the extension does not produce final
business objects. It sends DOM fragments that preserve the selectors needed by
the existing backend parser.

List page snapshot:

```json
{
  "page_kind": "list",
  "url": "https://javdb.com/...",
  "source_page": 1,
  "fragments": {
    "section_title": "<div class=\"section-title\">...</div>",
    "items": "<div class=\"movie-list\">...</div>"
  }
}
```

Detail page snapshot:

```json
{
  "page_kind": "detail",
  "url": "https://javdb.com/v/...",
  "fragments": {
    "title": "<h2 class=\"title is-4\">...</h2>",
    "cover": "<div class=\"video-cover\">...</div>",
    "movie_panel": "<nav class=\"movie-panel-info\">...</nav>",
    "tags": "<div id=\"tags\">...</div>",
    "magnets": "<div id=\"magnets-content\">...</div>"
  }
}
```

The backend `parser_bridge` should wrap fragments in a synthetic HTML document
before passing them to the existing parser. This keeps selector ownership in
Python and reduces WebSocket payload size compared with sending the entire
document.

If a fragment set cannot be parsed, the backend should mark the Agent task as
failed with a parser-specific reason and publish normal run detail updates.

## Cookie Sync

The extension automatically syncs JavDB cookies using Chrome extension cookie
APIs.

Cookie sync behavior:

- sync only cookies whose domain matches `javdb.com` or `.javdb.com`
- sync on Agent connect
- sync after a page finishes loading
- sync after a successful verification state is detected
- include expiration, path, secure, httpOnly, sameSite, and session metadata

Backend behavior:

- validate cookie domain before writing
- store cookies in the existing JavDB cookie storage format or a compatible
  internal format
- record `last_cookie_sync_at`
- expose cookie sync status in the crawler config page
- never show raw cookie values in the UI

The cookie config UI should become a status/control panel instead of a JSON
editor.

## Agent Task Flow

List phase:

1. crawler run enters list collection
2. backend creates Agent list-page work items
3. Chrome Agent requests work over WebSocket
4. Agent opens the URL in real Chrome
5. Agent sends list DOM fragments and cookies
6. backend parses list fragments with `parse_search_page`
7. backend applies existing dedup and incremental rules
8. backend persists detail tasks
9. backend publishes existing crawler realtime events through EventSource

Detail phase:

1. backend creates or claims pending detail work
2. Chrome Agent requests detail work
3. Agent opens detail URL in real Chrome
4. Agent sends detail DOM fragments and cookies
5. backend parses fragments with `parse_detail_page`
6. backend runs existing movie pipeline and persistence
7. backend updates detail task status
8. backend publishes existing crawler realtime events through EventSource

The user should see normal run progress in the existing UI. The UI should not
need to know whether the page came from Scrapling static fetch or Chrome Agent.

## Backend Integration Boundary

Do not force the existing JavDB spider to directly operate a WebSocket. Instead
add an Agent-backed fetch/collection boundary that can be selected by
`JAVDB_FETCH_MODE=agent`.

Two implementation options are acceptable:

1. Add an `AgentFetcher` that returns parser-compatible page objects after the
   Agent submits a snapshot.
2. Add an Agent runtime path in crawler execution that creates Agent work items
   and feeds parsed results into the existing persistence callbacks.

Recommended first implementation is option 2 for clarity. The list/detail work
is asynchronous and claim-based, so representing it as Agent work items is more
explicit than pretending the backend is doing a normal blocking HTTP fetch.

## Data Model

Add persistent or Redis-backed Agent runtime records:

```text
agent_id
owner_id
name
status: offline|online|busy|error
last_seen_at
last_cookie_sync_at
version
```

Add Agent work item state:

```text
agent_task_id
owner_id
run_id
task_id
detail_task_id
url_entry_id
page_kind
url
status: pending|assigned|running|completed|failed|cancelled
attempt
assigned_agent_id
claimed_until
error_reason
created_at
updated_at
```

Redis is acceptable for transient assignment state, but task outcome must be
recoverable enough that interrupted runs can be marked stopped or failed on
backend restart.

## Frontend Configuration UI

Update the crawler config page to show:

- JavDB fetch mode: `static` or `agent`
- Agent parse mode: `backend` first, `extension` disabled or marked reserved
- Agent connection status
- last Agent heartbeat
- last cookie sync time
- last successful JavDB page snapshot
- Agent token rotate button
- Chrome extension installation/download instructions

Remove:

- manual JavDB cookie JSON editor
- Playwright browser session controls
- Playwright profile export/reset controls

## Error Handling

Recommended Agent error reasons:

```text
agent_offline
agent_timeout
agent_cancelled
page_load_timeout
security_challenge_loop
not_verified
cookie_sync_failed
snapshot_missing_required_fragments
parser_error
payload_too_large
task_claim_expired
```

When an Agent error affects a crawl run, map it into the existing run/detail
status model and publish:

- `crawler.run.log.appended`
- `crawler.run.detail.updated`
- `crawler.run.updated` when run-level state changes
- `crawler.task.status.updated`

The UI should use the existing resync path if it receives
`system.resync_required`.

## Payload Limits

Because snapshots travel over WebSocket, enforce limits:

- maximum single message size
- maximum fragment size
- maximum fragments per snapshot
- maximum pending Agent tasks per run

If a detail page exceeds the limit, the Agent should either send only required
fragments or fail the task with `payload_too_large`. The first implementation
should not fall back to whole-document upload.

## Security

- Treat Agent input as untrusted.
- Validate all URLs belong to JavDB before accepting snapshots.
- Validate cookie domains before saving.
- Do not log raw cookies or full HTML fragments.
- Redact Agent token and session ids from logs.
- Scope Agent sessions to an owner id.
- Expire Agent sessions.
- Use message ids for idempotency and duplicate suppression.

## Testing Strategy

Backend tests:

- Agent auth/session exchange rejects invalid tokens.
- Agent WebSocket accepts `hello`, `heartbeat`, `cookie_sync`, and snapshot
  messages.
- Agent work assignment is owner-scoped.
- expired claims are returned to pending or failed deterministically.
- cookie sync accepts JavDB cookies and rejects unrelated domains.
- backend parser bridge parses list fragments with `parse_search_page`.
- backend parser bridge parses detail fragments with `parse_detail_page`.
- Agent errors publish existing crawler realtime events.

Frontend tests:

- crawler runtime store applies `crawler.task.status.updated`.
- crawler runtime store applies `crawler.run.updated`.
- crawler runtime store merges `crawler.run.detail.updated`.
- crawler runtime store appends `crawler.run.log.appended`.
- `system.resync_required` records reason and lets pages trigger HTTP refresh.
- config page no longer renders manual cookie JSON editor.
- config page shows Agent connection and cookie sync status.

Regression tests:

- static JavDB fetcher still merges configured headers and cookies.
- JavBus fetcher remains unaffected.
- existing storage realtime hooks keep working through EventSource.

## Implementation Phases

### Phase 1: Roll Back Playwright Browser Mode

- remove Playwright browser-session code and UI/API surface
- remove `browser` fetch mode
- keep `static` mode
- update docs and tests

### Phase 2: Runtime Store Without Transport Change

- add crawler runtime store
- add realtime event application helper
- migrate crawler task list and run detail state updates to store
- keep EventSource transport unchanged

### Phase 3: Agent Backend Foundation

- add Agent token/session APIs
- add Agent WebSocket endpoint
- add Agent registry and heartbeat handling
- add cookie sync handling
- expose Agent status on config page

### Phase 4: Backend Parse Mode

- add Agent work item lifecycle
- implement list snapshot parsing
- implement detail snapshot parsing
- connect parsed results to existing crawler persistence and events
- mark `JAVDB_AGENT_PARSE_MODE=backend` as supported

### Phase 5: Chrome Extension

- implement MV3 extension manifest
- add background service worker for WebSocket connection
- add content script for JavDB page fragment extraction
- add cookie sync
- add simple extension status/options page

## Open Decisions

- Whether Agent work items are stored in PostgreSQL, Redis, or a hybrid model.
  PostgreSQL is safer for restart recovery; Redis is simpler for transient
  assignment.
- Whether the extension package is built inside `frontend/`, a new
  `chrome-extension/` directory, or a separate package.
- Whether Agent token rotation invalidates all current sessions immediately or
  allows a short grace period.
- Whether `static` mode should continue reading Agent-synced cookies for
  diagnostic fallback.

## Acceptance Criteria

- Frontend/backend EventSource realtime continues to work.
- Crawler runtime state has a central Zustand store.
- Playwright JavDB browser mode is removed.
- Manual JavDB cookie JSON editing is removed from the UI.
- Chrome Agent can connect to backend through WebSocket.
- Chrome Agent can sync JavDB cookies without exposing raw cookie values in UI.
- Backend parse mode can parse Agent-submitted JavDB list and detail fragments.
- Existing crawler run/detail realtime events continue driving UI progress.
- JavBus behavior is unchanged.
