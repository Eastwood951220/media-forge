# JavDB Page Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add secure, contextual Chrome-extension actions that create temporary detail runs, create and fully crawl a task from any non-home JavDB movie-list page, or add that list URL to an enabled task and incrementally crawl only that URL.

**Architecture:** A plain-TypeScript content-script UI classifies JavDB pages and renders a Shadow DOM toolbar, then sends typed messages to the extension background service worker. The background worker is the only extension context that reads the configured Agent token and calls new Agent-authenticated FastAPI page-action endpoints; backend services normalize URLs, enforce owner scope, persist task/run changes, and enqueue existing crawler runs.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy 2.0, pytest, Chrome Manifest V3, TypeScript 6, Vite 8, Vitest 3, happy-dom.

**Spec:** `docs/superpowers/specs/2026-09-24-javdb-page-actions-design.md`

## Global Constraints

- Work in the current checkout with ordinary branches only; do not create or use a Git worktree.
- Do not stage or modify the pre-existing unrelated change in `scraper/spiders/javdb/javdb_spider.py`.
- Inject no page-action UI on JavDB `/`; inject one temporary-run action on `/v/<identifier>`; inject both list actions only when a non-home, non-detail page contains the JavDB movie-list DOM.
- Preserve list search, filter, and sort query parameters, remove fragments, sort query keys, and force exactly `page=1`.
- Keep the Agent token in the extension background context; never include it in content-script messages, rendered DOM, diagnostics, or errors.
- Keep the existing Agent WebSocket protocol and page-snapshot behavior unchanged.
- Use plain TypeScript and DOM APIs in the extension; do not add React, Ant Design, or another UI framework.
- Reuse existing crawl-task and crawl-run tables; do not add a database migration.
- Task-name conflicts return an error and create nothing; never add an automatic numeric suffix.
- Existing normalized task URLs are reused instead of duplicated, then run incrementally as a one-URL subset.
- All task selectors return enabled tasks only and revalidate enabled/owned state at submission time.

## Review Focus

- Equivalent URLs with reordered query keys, repeated `page` values, fragments, mixed-case hosts, or page numbers other than 1 must normalize to one stored URL; Task 1 tests this matrix.
- Two add-to-task requests for the same normalized URL must resolve to one `CrawlTaskUrl`; Task 2 tests the row-lock/unique-constraint path and Task 3 tests repeated API requests.
- A task deleted or disabled after the selector loads must be rejected without creating a run; Task 3 tests both races.
- Runtime enqueue failure after task/run persistence must return the run ID with an explicit partial-failure result; Task 2 pins the activation boundary and Task 3 pins the API response.
- DOM replacement or repeated bootstrap on a list page must not duplicate the toolbar or lose focus restoration; Tasks 5 and 6 test remount and modal focus behavior.

---

### Task 1: Agent HTTP Authentication and JavDB URL Normalization

**Files:**
- Create: `backend/app/modules/crawler/agent/page_actions/__init__.py`
- Create: `backend/app/modules/crawler/agent/page_actions/auth.py`
- Create: `backend/app/modules/crawler/agent/page_actions/schemas.py`
- Create: `backend/app/modules/crawler/agent/page_actions/urls.py`
- Modify: `backend/app/modules/crawler/agent/auth.py`
- Modify: `backend/app/modules/crawler/agent/router.py`
- Test: `backend/tests/test_crawler_agent_page_action_foundation.py`

**Interfaces:**
- Consumes: `CrawlerAgent`, `hash_agent_token`, `verify_agent_token`, `detect_task_url_type`, and FastAPI `HTTPBearer` credentials.
- Produces: `find_agent_by_token(db: Session, token: str) -> CrawlerAgent | None`, `get_page_action_agent(credentials: HTTPAuthorizationCredentials | None, db: Session) -> CrawlerAgent`, `normalize_javdb_list_url(raw_url: str) -> NormalizedJavdbListUrl`, request/response Pydantic models used by Tasks 2-4.

- [ ] **Step 1: Write failing foundation tests**

Create tests covering valid/invalid bearer tokens and the complete normalization matrix:

```python
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://JAVDB.com/actors/A?page=9&t=d#results",
            "https://javdb.com/actors/A?page=1&t=d",
        ),
        (
            "https://javdb.com/search?z=2&page=3&q=abc&a=1&page=8",
            "https://javdb.com/search?a=1&page=1&q=abc&z=2",
        ),
    ],
)
def test_normalize_javdb_list_url_preserves_filters_and_forces_page_one(raw, expected):
    assert normalize_javdb_list_url(raw).url == expected


@pytest.mark.parametrize("raw", [
    "https://javdb.com/",
    "https://javdb.com/v/abc",
    "https://example.com/actors/A",
    "javascript:alert(1)",
])
def test_normalize_javdb_list_url_rejects_non_list_targets(raw):
    with pytest.raises(ValueError):
        normalize_javdb_list_url(raw)
```

Seed two agents and assert `find_agent_by_token` returns only the matching agent. Exercise `get_page_action_agent` through a minimal dependency test and assert missing, malformed, and invalid bearer headers return `401` without leaking the token.

- [ ] **Step 2: Run the foundation tests and verify failure**

Run:

```bash
python -m pytest backend/tests/test_crawler_agent_page_action_foundation.py -q
```

Expected: collection fails because the `page_actions` package and exported functions do not exist.

- [ ] **Step 3: Implement reusable authentication and URL contracts**

Refactor the existing session-token lookup to use:

```python
def find_agent_by_token(db: Session, token: str) -> CrawlerAgent | None:
    if not token:
        return None
    return next(
        (agent for agent in db.query(CrawlerAgent).all()
         if verify_agent_token(token, agent.token_hash)),
        None,
    )
```

Keep `POST /api/crawler/agent/sessions` behavior unchanged and call this helper there.

In `page_actions/auth.py`, define a dedicated `HTTPBearer(auto_error=False)` dependency that validates an `agt_` token and returns its `CrawlerAgent`. Return the standard `401` envelope with a stable `invalid_agent_token` code in `data`.

In `page_actions/urls.py`, define:

```python
@dataclass(frozen=True)
class NormalizedJavdbListUrl:
    url: str
    url_type: str


def normalize_javdb_list_url(raw_url: str) -> NormalizedJavdbListUrl:
    parsed = urlsplit(raw_url.strip())
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("仅支持 HTTP 或 HTTPS URL")
    if hostname != "javdb.com" and not hostname.endswith(".javdb.com"):
        raise ValueError("仅支持 JavDB URL")
    if parsed.username or parsed.password:
        raise ValueError("URL 不能包含认证信息")
    path = parsed.path or "/"
    if path == "/" or re.match(r"^/v/[^/]+/?$", path):
        raise ValueError("当前页面不是 JavDB 列表页")
    default_port = (parsed.scheme == "http" and parsed.port == 80) or (
        parsed.scheme == "https" and parsed.port == 443
    )
    netloc = hostname if parsed.port is None or default_port else f"{hostname}:{parsed.port}"
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != "page"
    ]
    query.append(("page", "1"))
    query.sort(key=lambda pair: (pair[0], pair[1]))
    url = urlunsplit((parsed.scheme, netloc, path, urlencode(query, doseq=True), ""))
    return NormalizedJavdbListUrl(
        url=url,
        url_type=detect_task_url_type(url, "javdb") or "list",
    )
```

Normalize host casing and default ports, reject `/` and `/v/<identifier>`, drop the fragment, remove all existing `page` pairs, append `page=1`, and sort query pairs by key then value. Use `detect_task_url_type`; return `list` when the host/path are valid but no known list type matches.

In `schemas.py`, define exact contracts:

```python
class PageActionTaskChoice(BaseModel):
    id: uuid.UUID
    name: str

class TemporaryPageRunCreate(BaseModel):
    task_id: uuid.UUID
    detail_url: str

class QuickCreatePageRunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    page_name: str = Field(min_length=1, max_length=200)
    list_url: str = Field(min_length=1)

class AddUrlPageRunCreate(BaseModel):
    task_id: uuid.UUID
    page_name: str = Field(min_length=1, max_length=200)
    list_url: str = Field(min_length=1)

class PageActionRunResult(BaseModel):
    task_id: uuid.UUID
    task_name: str
    run_id: uuid.UUID
    crawl_mode: Literal["temporary", "full", "incremental"]
    accepted: bool
    runtime_error: str | None = None
    url_entry_id: uuid.UUID | None = None
    url_added: bool | None = None
```

- [ ] **Step 4: Run foundation and existing Agent auth tests**

Run:

```bash
python -m pytest backend/tests/test_crawler_agent_page_action_foundation.py backend/tests/test_crawler_agent_auth.py backend/tests/test_crawler_agent_ws.py::test_agent_session_rejects_invalid_token -q
```

Expected: all selected tests pass and existing session rejection remains `401`.

- [ ] **Step 5: Commit the foundation**

```bash
git add backend/app/modules/crawler/agent/auth.py backend/app/modules/crawler/agent/router.py backend/app/modules/crawler/agent/page_actions/__init__.py backend/app/modules/crawler/agent/page_actions/auth.py backend/app/modules/crawler/agent/page_actions/schemas.py backend/app/modules/crawler/agent/page_actions/urls.py backend/tests/test_crawler_agent_page_action_foundation.py
git diff --cached --name-only
git commit -m "feat: add Agent page action foundations"
```

### Task 2: Transaction-Safe Task URL and Run Primitives

**Files:**
- Modify: `backend/app/repositories/crawl_task.py`
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Test: `backend/tests/test_crawler_page_action_primitives.py`
- Test: `backend/tests/test_crawler_task_url_subset_run.py`

**Interfaces:**
- Consumes: `TaskUrlEntryCreate`, `CrawlTask`, `CrawlTaskUrl`, `CrawlerRuntimeState`, and existing run-scope builders.
- Produces: `CrawlerTaskRepository.add_with_urls`, `get_owned_for_update`, `append_url`, `get_enabled_dict_by_owner`, `CrawlerRunService.prepare_run`, and `activate_run` for Task 3, with the exact signatures shown below.

- [ ] **Step 1: Write failing primitive and regression tests**

Pin these behaviors:

```python
def test_add_with_urls_flushes_without_committing(db_session, test_user):
    repo = CrawlTaskRepository(db_session)
    task = repo.add_with_urls(
        owner_id=test_user.id,
        name="演员 A",
        storage_location="演员 A",
        is_skip=False,
        urls=[TaskUrlEntryCreate(
            url="https://javdb.com/actors/A?page=1",
            final_url="https://javdb.com/actors/A?page=1",
            url_type="actors",
            url_name="演员 A",
        )],
    )
    assert task.id is not None
    db_session.rollback()
    assert db_session.get(CrawlTask, task.id) is None


def test_prepare_run_and_activate_run_have_separate_boundaries(db_session, task, fake_runtime):
    service = CrawlerRunService(db_session, fake_runtime)
    run = service.prepare_run(task, "full")
    assert fake_runtime.enqueued == []
    db_session.commit()
    service.activate_run(run)
    assert fake_runtime.enqueued == [str(run.id)]
```

Also test that `append_url` uses `max(position) + 1`, `get_owned_for_update` is owner-scoped, enabled choices exclude `is_skip=True`, and existing `create_run` still commits and enqueues exactly once.

- [ ] **Step 2: Run primitive tests and verify failure**

Run:

```bash
python -m pytest backend/tests/test_crawler_page_action_primitives.py backend/tests/test_crawler_task_url_subset_run.py -q
```

Expected: new tests fail on missing repository/runtime methods while existing URL-subset tests remain green.

- [ ] **Step 3: Add non-committing repository primitives**

Implement:

```python
def add_with_urls(self, *, owner_id, name, storage_location, is_skip, urls) -> CrawlTask:
    task = CrawlTask(
        owner_id=owner_id,
        name=name,
        storage_location=storage_location,
        is_skip=is_skip,
    )
    task.urls = self.build_url_rows(urls)
    self.session.add(task)
    self.session.flush()
    return task

def get_owned_for_update(self, task_id, owner_id) -> CrawlTask | None:
    return (
        self._owner_query(owner_id)
        .filter(CrawlTask.id == task_id)
        .with_for_update()
        .first()
    )

def append_url(self, task, entry) -> CrawlTaskUrl:
    next_position = max((row.position for row in task.urls), default=-1) + 1
    row = CrawlTaskUrl(**self.build_url_values(entry, next_position))
    task.urls.append(row)
    self.session.flush()
    return row
```

Make existing `create_with_urls` delegate to `add_with_urls`, then retain its current commit/refresh behavior. Add `get_enabled_dict_by_owner` ordered by name.

- [ ] **Step 4: Separate run persistence from activation without changing callers**

Extract the existing `create_run` construction into:

```python
def prepare_run(
    self,
    task: CrawlTask,
    crawl_mode: str,
    *,
    selected_task_url_ids: list[uuid.UUID] | None = None,
) -> CrawlRun:
    # validate mode, construct scope/result, add, flush, return

def activate_run(self, run: CrawlRun) -> None:
    self.runtime.enqueue_run(str(run.id))
    self._ensure_worker_started()
```

Keep `create_run` backward compatible by calling `prepare_run`, committing,
refreshing, then calling `activate_run`. Do not change temporary-run behavior
in this task.

- [ ] **Step 5: Run primitive and crawler regression tests**

Run:

```bash
python -m pytest backend/tests/test_crawler_page_action_primitives.py backend/tests/test_crawler_task_url_subset_run.py backend/tests/test_crawl_tasks_api.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit transaction primitives**

```bash
git add backend/app/repositories/crawl_task.py backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_page_action_primitives.py backend/tests/test_crawler_task_url_subset_run.py
git diff --cached --name-only
git commit -m "refactor: separate crawler run persistence and activation"
```

### Task 3: Agent Page-Action Service and API

**Files:**
- Create: `backend/app/modules/crawler/agent/page_actions/service.py`
- Create: `backend/app/modules/crawler/agent/page_actions/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_crawler_agent_page_actions_api.py`

**Interfaces:**
- Consumes: Task 1's Agent principal, schemas, and normalized URL result; Task 2's repository and run primitives; existing `create_temporary_detail_run`.
- Produces: the four `/api/crawler/agent/page-actions/*` endpoints consumed by the extension background client in Task 4.

- [ ] **Step 1: Write failing endpoint tests for task choices and temporary runs**

Create an `agent_headers` fixture by rotating an Agent token for `test_user`.
Test:

```python
def test_task_choices_return_only_owned_enabled_tasks(client, agent_headers, seeded_tasks):
    response = client.get("/api/crawler/agent/page-actions/tasks", headers=agent_headers)
    assert response.status_code == 200
    assert [row["name"] for row in response.json()["data"]] == ["启用任务"]


def test_temporary_run_uses_selected_owned_task(client, agent_headers, enabled_task, runtime):
    response = client.post(
        "/api/crawler/agent/page-actions/temporary-runs",
        headers=agent_headers,
        json={"task_id": str(enabled_task.id), "detail_url": "https://javdb.com/v/abc"},
    )
    assert response.status_code == 201
    assert response.json()["data"]["crawl_mode"] == "temporary"
```

Add missing/invalid token, foreign task, disabled task, deleted-task race, and invalid detail URL cases.

- [ ] **Step 2: Write failing quick-create tests**

Test successful task plus full run creation, exact name conflict with no extra
task/run rows, generic list type, and normalized URL persistence:

```python
assert created_url.url == "https://javdb.com/actors/A?page=1&t=d"
assert created_url.final_url == created_url.url
assert run.crawl_mode == "full"
assert run.result["scope"] == "task_full"
```

Mock `activate_run` to raise after commit and assert the response contains
`accepted: false`, the persisted `run_id`, and a non-empty `runtime_error`.

- [ ] **Step 3: Write failing add-to-task tests**

Send one URL with `page=7&t=d` and then the equivalent URL with reordered query
parameters and `page=3`. Assert there is one URL row, the first response has
`url_added: true`, the second has `url_added: false`, and both runs contain only
that URL entry ID in `selected_task_url_ids`.

Add tests for a disabled-task race, owner isolation, the `with_for_update`
lookup path, and a forced unique-constraint collision that recovers by loading
the now-existing normalized URL rather than creating a duplicate.

- [ ] **Step 4: Run API tests and verify failure**

Run:

```bash
python -m pytest backend/tests/test_crawler_agent_page_actions_api.py -q
```

Expected: all requests return `404` because the router is not registered.

- [ ] **Step 5: Implement the composite service**

Define `PageActionService.list_enabled_tasks(owner_id: uuid.UUID) ->
list[dict[str, str]]`,
`create_temporary_run(owner_id: uuid.UUID, data: TemporaryPageRunCreate) ->
PageActionRunResult`,
`quick_create_run(owner_id: uuid.UUID, data: QuickCreatePageRunCreate) ->
PageActionRunResult`, and
`add_url_run(owner_id: uuid.UUID, data: AddUrlPageRunCreate) ->
PageActionRunResult`.

For quick create, normalize before mutation, reject `get_by_name`, create a
`TaskUrlEntryCreate` with `url` and `final_url` both set to the normalized URL,
`url_name=data.page_name`, `is_skip=False`, then call
`prepare_run(task, "full")`.
Commit task and run together, refresh them, and call `activate_run` afterward.

For add-to-task, lock the owned task, reject disabled tasks, compare normalized
stored URLs, append only when absent, call `prepare_run` with
`selected_task_url_ids=[url_entry.id]` and `crawl_mode="incremental"`, and
commit the URL/run together. Recover an `IntegrityError` caused by the existing
`uq_crawl_task_urls_task_url` constraint by rolling back, locking/reloading the
task, resolving the existing normalized row, and preparing one run for that
row.

Use a small activation helper that returns `accepted=True` on successful
enqueue or returns the persisted IDs plus `accepted=False` and a redacted
`runtime_error` if enqueue/worker startup fails.

- [ ] **Step 6: Implement and register the router**

Create an `APIRouter(prefix="/api/crawler/agent/page-actions")` with the four
confirmed endpoints. Each route depends on `get_page_action_agent`, constructs
`PageActionService(db)`, and passes only `agent.owner_id` into service methods.
Register this router in `backend/app/main.py` without altering the existing
Agent WebSocket router.

- [ ] **Step 7: Run focused and adjacent backend tests**

Run:

```bash
python -m pytest backend/tests/test_crawler_agent_page_actions_api.py backend/tests/test_crawler_agent_page_action_foundation.py backend/tests/test_crawl_tasks_api.py backend/tests/test_crawler_task_url_subset_run.py backend/tests/test_crawler_agent_ws.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit the Agent page-action API**

```bash
git add backend/app/main.py backend/app/modules/crawler/agent/page_actions/service.py backend/app/modules/crawler/agent/page_actions/router.py backend/tests/test_crawler_agent_page_actions_api.py
git diff --cached --name-only
git commit -m "feat: add Agent-authenticated crawler page actions"
```

### Task 4: Typed Extension Background Client

**Files:**
- Create: `chrome-extension/src/pageActions/types.ts`
- Create: `chrome-extension/src/pageActions/backgroundApi.ts`
- Create: `chrome-extension/src/pageActions/backgroundApi.test.ts`
- Modify: `chrome-extension/src/background.ts`

**Interfaces:**
- Consumes: the four backend endpoints from Task 3 and existing `backendUrl`/`token` extension settings.
- Produces: `PageActionMessage`, `PageActionResponse<T>`, `handlePageActionMessage(message, deps)`, and the background message bridge consumed by Task 6.

- [ ] **Step 1: Write failing background-client tests**

Define tests around dependency-injected `fetch` and settings:

```typescript
it('adds Agent authorization only in the background request', async () => {
  const fetch = vi.fn().mockResolvedValue(okResponse({ rows: [] }))
  const result = await handlePageActionMessage(
    { type: 'page_action.list_tasks' },
    { fetch, settings: async () => ({ backendUrl: 'http://mf.test', token: 'agt_secret' }) },
  )
  expect(fetch).toHaveBeenCalledWith(
    'http://mf.test/api/crawler/agent/page-actions/tasks',
    expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer agt_secret' }) }),
  )
  expect(JSON.stringify(result)).not.toContain('agt_secret')
})
```

Also test missing settings, transport failure, a `409` name conflict, successful
temporary/full/incremental results, partial activation (`accepted: false` with
run ID), and `page_action.open_run` constructing
`<backendUrl>/crawler/runs/<run_id>` through `chrome.tabs.create`.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd chrome-extension
pnpm test -- src/pageActions/backgroundApi.test.ts
```

Expected: test collection fails because the page-action modules do not exist.

- [ ] **Step 3: Implement typed messages and response mapping**

Define the message union explicitly:

```typescript
export type PageActionMessage =
  | { type: 'page_action.list_tasks' }
  | { type: 'page_action.temporary_run'; taskId: string; detailUrl: string }
  | { type: 'page_action.quick_create_run'; name: string; pageName: string; listUrl: string }
  | { type: 'page_action.add_url_run'; taskId: string; pageName: string; listUrl: string }
  | { type: 'page_action.open_run'; runId: string }

export type PageActionResponse<T> =
  | { ok: true; data: T }
  | { ok: false; error: { code: string; message: string; data?: unknown } }
```

`backgroundApi.ts` must validate settings, construct only the confirmed API
paths, attach JSON and bearer headers, parse the standard backend envelope, and
return redacted typed errors. Never echo request headers or tokens.

- [ ] **Step 4: Integrate the background listener**

Extend the existing `chrome.runtime.onMessage` listener to route messages whose
type starts with `page_action.` to `handlePageActionMessage`, call
`sendResponse`, and return `true`. Preserve the current reconnect/settings
message behavior exactly.

- [ ] **Step 5: Run extension client tests and typecheck**

Run:

```bash
cd chrome-extension
pnpm test -- src/pageActions/backgroundApi.test.ts
pnpm typecheck
```

Expected: both commands pass.

- [ ] **Step 6: Commit the background client**

```bash
git add chrome-extension/src/background.ts chrome-extension/src/pageActions/types.ts chrome-extension/src/pageActions/backgroundApi.ts chrome-extension/src/pageActions/backgroundApi.test.ts
git diff --cached --name-only
git commit -m "feat: add extension page action client"
```

### Task 5: JavDB Page Classification and Metadata Extraction

**Files:**
- Create: `chrome-extension/src/pageActions/pageContext.ts`
- Create: `chrome-extension/src/pageActions/pageContext.test.ts`
- Modify: `chrome-extension/package.json`
- Modify: `chrome-extension/pnpm-lock.yaml`

**Interfaces:**
- Consumes: JavDB `Location`/`Document` state.
- Produces: `classifyPage(location, document) -> PageKind`, `extractPageContext(location, document) -> PageContext`, and `normalizeListUrlPreview(url) -> string` used by Task 6.

- [ ] **Step 1: Install the DOM test runtime**

Run:

```bash
cd chrome-extension
pnpm add -D happy-dom
```

Expected: `package.json` and `pnpm-lock.yaml` add only the `happy-dom`
development dependency and its transitive lock entries.

- [ ] **Step 2: Write failing page-context tests**

Use `// @vitest-environment happy-dom` and cover:

```typescript
it.each([
  ['https://javdb.com/', '<div class="item"></div>', 'home'],
  ['https://javdb.com/v/abc', '<div class="video-detail"></div>', 'detail'],
  ['https://javdb.com/actors/A?page=9', '<div class="item"></div>', 'list'],
  ['https://javdb.com/future-list', '<div class="item"></div>', 'list'],
  ['https://javdb.com/users/sign_in', '<form></form>', 'unsupported'],
])('classifies %s as %s', (url, html, expected) => {
  document.body.innerHTML = html
  expect(classifyPage(new URL(url), document)).toBe(expected)
})
```

Add tests for detail-title selectors, `.actor-section-name`, `.section-name`,
`.section-title`, search-query fallback, cleaned document-title fallback, hash
removal, query preservation, stable order, and forced `page=1` preview.

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
cd chrome-extension
pnpm test -- src/pageActions/pageContext.test.ts
```

Expected: collection fails because `pageContext.ts` does not exist.

- [ ] **Step 4: Implement pure page-context helpers**

Define:

```typescript
export type PageKind = 'home' | 'detail' | 'list' | 'unsupported'

export type PageContext = {
  kind: PageKind
  url: string
  normalizedUrl: string
  pageName: string
}
```

Classify `/` before checking DOM so a home page containing `.item` remains
excluded. Treat `/v/<non-empty>` as detail. Require at least one `div.item` for
all list pages. Build metadata without mutating the host DOM. Client URL
normalization is display-only; the backend remains authoritative.

- [ ] **Step 5: Run page-context tests and extension typecheck**

Run:

```bash
cd chrome-extension
pnpm test -- src/pageActions/pageContext.test.ts
pnpm typecheck
```

Expected: both commands pass.

- [ ] **Step 6: Commit page classification**

```bash
git add chrome-extension/package.json chrome-extension/pnpm-lock.yaml chrome-extension/src/pageActions/pageContext.ts chrome-extension/src/pageActions/pageContext.test.ts
git diff --cached --name-only
git commit -m "feat: classify JavDB pages for extension actions"
```

### Task 6: Shadow DOM Toolbar, Modal Workflows, and Content Integration

**Files:**
- Create: `chrome-extension/src/pageActions/ui.ts`
- Create: `chrome-extension/src/pageActions/controller.ts`
- Create: `chrome-extension/src/pageActions/ui.test.ts`
- Modify: `chrome-extension/src/content.ts`

**Interfaces:**
- Consumes: Task 4's typed runtime messages and Task 5's `PageContext`.
- Produces: `mountPageActions(context, deps) -> PageActionMount | null`, `refreshPageActions()`, and the complete injected user workflow.

- [ ] **Step 1: Write failing toolbar and idempotence tests**

Use happy-dom to assert:

```typescript
expect(mountFor('home')).toBeNull()
expect(detailShadow.querySelectorAll('[data-action="temporary"]')).toHaveLength(1)
expect(listShadow.querySelectorAll('[data-action="quick-create"]')).toHaveLength(1)
expect(listShadow.querySelectorAll('[data-action="add-existing"]')).toHaveLength(1)

mountPageActions(listContext, deps)
mountPageActions(listContext, deps)
expect(document.querySelectorAll('#media-forge-page-actions')).toHaveLength(1)
```

Simulate body replacement followed by `refreshPageActions()` and assert there
is still one host with the correct buttons.

- [ ] **Step 2: Write failing modal workflow tests**

Test all three flows with mocked `sendMessage`:

- Task choices load only after opening temporary/add-existing modals.
- Only returned enabled tasks appear.
- Quick-create name is prefilled and editable, crawl mode is fixed to full,
  and a `409` error stays attached to the name field.
- Add-existing submits task ID, page name, and normalized current URL; both
  `url_added` values render success correctly.
- Temporary submits exactly one detail URL.
- Double submit while pending sends one message.
- `accepted: false` plus run ID renders partial failure and still offers
  `查看运行详情`.
- Escape closes, initial focus enters the modal, Tab stays inside, and closing
  restores focus to the invoking button.
- Clicking `查看运行详情` sends `page_action.open_run` with the returned run ID.
- `JSON.stringify` of all content-script messages and Shadow DOM text never
  contains an `agt_` token.

- [ ] **Step 3: Run UI tests and verify failure**

Run:

```bash
cd chrome-extension
pnpm test -- src/pageActions/ui.test.ts
```

Expected: collection fails because `ui.ts` and `controller.ts` do not exist.

- [ ] **Step 4: Implement the accessible Shadow DOM shell**

Create one host with ID `media-forge-page-actions` and a closed Shadow Root.
Render visible text plus inline SVG icons, 44-pixel minimum controls, a
high-contrast focus ring, modal backdrop, labelled fields, `role="dialog"`,
`aria-modal="true"`, and `role="alert"` for errors. Keep styles in a constant
inside `ui.ts` so no host-page stylesheet or additional manifest asset is
required.

Expose UI methods for opening/closing, setting task choices, setting busy
state, showing field/general errors, and showing success/partial-success
results. Do not put request logic in `ui.ts`.

- [ ] **Step 5: Implement the controller workflows**

`controller.ts` maps button events to typed messages:

```typescript
type PageActionDeps = {
  sendMessage: <T>(message: PageActionMessage) => Promise<PageActionResponse<T>>
}

export function mountPageActions(
  context: PageContext,
  deps: PageActionDeps,
): PageActionMount | null
```

Load task choices on demand, preserve input on recoverable failure, guard each
submit with one in-flight promise, and map success/partial activation/error
responses into the UI methods. Empty task choices show the confirmed message
that the user must enable or create a task in Media Forge.

- [ ] **Step 6: Integrate without changing snapshot collection**

Keep `detectPageKind`, `snapshot`, and the `collect_snapshot` message response
behavior in `content.ts` intact. Add a debounced bootstrap that calls
`extractPageContext`, removes a stale action host when the page becomes
home/unsupported, and mounts the correct action UI. Trigger it on initial
load, `popstate`, `hashchange`, and relevant body mutations. Disconnect or
reuse observers so repeated bootstrap cannot create observer leaks.

- [ ] **Step 7: Run focused and full extension verification**

Run:

```bash
cd chrome-extension
pnpm test -- src/pageActions/ui.test.ts src/pageActions/pageContext.test.ts src/pageActions/backgroundApi.test.ts
pnpm typecheck
pnpm build
node scripts/verify-agent-extension.mjs
```

Expected: all commands pass and `dist/content.js` contains the three Chinese
action labels without containing an Agent token.

- [ ] **Step 8: Commit the injected workflows**

```bash
git add chrome-extension/src/content.ts chrome-extension/src/pageActions/ui.ts chrome-extension/src/pageActions/controller.ts chrome-extension/src/pageActions/ui.test.ts
git diff --cached --name-only
git commit -m "feat: add JavDB page action toolbar"
```

### Task 7: Documentation, Build Assertions, and Final Verification

**Files:**
- Modify: `README.md`
- Modify: `chrome-extension/scripts/verify-agent-extension.mjs`

**Interfaces:**
- Consumes: all shipped backend and extension behavior from Tasks 1-6.
- Produces: operator documentation, stronger packaged-extension assertions, and final verification evidence.

- [ ] **Step 1: Strengthen the extension artifact verifier**

Add source/build assertions that:

- `content.ts` imports the page-action bootstrap.
- `background.ts` handles `page_action.list_tasks` and
  `page_action.open_run`.
- `dist/content.js` contains `加入临时任务`, `快速创建并全量爬取`, and
  `加入已有任务并增量爬取`.
- Neither built script contains a concrete test token such as `agt_secret`.

Run before rebuilding to verify the new assertions fail against stale output:

```bash
cd chrome-extension
node scripts/verify-agent-extension.mjs
```

Expected: FAIL because the stale build lacks page-action labels.

- [ ] **Step 2: Update operator documentation**

Extend the `JavDB Chrome Agent` section in `README.md` with:

- The detail-page temporary-run action.
- Both non-home movie-list actions and their fixed crawl modes.
- The `page=1` plus preserved-filter rule.
- The enabled-task-only selector and duplicate-name error behavior.
- Rebuild/reload instructions after upgrading the unpacked extension.
- A statement that the Agent token remains in the background context.

Do not add a React frontend route or change `frontend/README.md`, because the
feature uses the existing run-detail route and does not change frontend module
structure.

- [ ] **Step 3: Run complete focused verification**

Run:

```bash
python -m pytest backend/tests/test_crawler_agent_page_action_foundation.py backend/tests/test_crawler_page_action_primitives.py backend/tests/test_crawler_agent_page_actions_api.py backend/tests/test_crawl_tasks_api.py backend/tests/test_crawler_task_url_subset_run.py backend/tests/test_crawler_agent_ws.py -q
cd chrome-extension
pnpm test
pnpm typecheck
pnpm build
node scripts/verify-agent-extension.mjs
```

Expected: all tests and checks pass.

- [ ] **Step 4: Inspect the final diff and worktree boundary**

Run:

```bash
git status --short
git diff --check
git diff --stat HEAD~6..HEAD
```

Expected: the unrelated `scraper/spiders/javdb/javdb_spider.py` modification is
still unstaged and absent from every feature commit; no whitespace errors are
reported.

- [ ] **Step 5: Commit documentation and verification updates**

```bash
git add README.md chrome-extension/scripts/verify-agent-extension.mjs
git diff --cached --name-only
git commit -m "docs: document JavDB extension page actions"
```

- [ ] **Step 6: Run post-commit verification and record evidence**

Repeat the commands from Step 3 after the final commit. Record exact passing
test counts and any pre-existing warnings in the completion report. Do not
claim the feature complete if any newly introduced failure remains.
