# Crawler Realtime State Data Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate crawler static REST data from dynamic EventSource state, centralize task/run runtime updates in an in-memory Zustand store, simplify page-local realtime handling, and remove redundant crawler endpoints and payload fields.

**Architecture:** The authenticated application shell owns one EventSource connection. REST endpoints provide static list/detail data plus the initial run and subtask status baselines; EventSource provides a complete task-runtime snapshot and all later task/run/subtask/log changes. TanStack Query owns static server data, Zustand owns task/run runtime overlays, and the run-detail page owns subtask rows, summary, and logs.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, Pydantic, Pytest, React 19, TypeScript 6, Zustand 5, TanStack Query 5, Vitest, React Testing Library.

## Global Constraints

- Preserve crawler scheduling, crawling, retry, and persistence behavior.
- Preserve storage-task, movie-list, and dashboard behavior.
- Keep runtime state in memory only; do not add `localStorage` persistence.
- Keep the single `/api/events/stream` EventSource transport; do not add WebSocket or a second subtask stream.
- Task-list runtime status and top metrics come only from EventSource snapshot/incremental events.
- Run-list and run-detail REST responses may provide initial status baselines; later changes come only from EventSource.
- Normal status events must not refetch task/run lists. Structural changes, filter membership changes, route activation, and resync recovery may refetch narrowly.
- Delete obsolete crawler routes without a compatibility period.
- Preserve unrelated user changes in the working tree, especially theme-transition files and `.playwright-cli/`.
- Follow TDD: add a focused failing test, confirm the expected failure, implement the minimum change, and rerun the focused test before each commit.

## File Responsibility Map

- `backend/app/schemas/crawl_task.py`: full task-detail models plus new task-list/runtime-event models.
- `backend/app/modules/crawler/tasks/serializers.py`: separate full-detail and list-item serialization.
- `backend/app/modules/crawler/tasks/service.py`: task-list aggregation, minimal run-action responses, and task snapshot publication after structural mutations.
- `backend/app/modules/crawler/tasks/router.py`: canonical task routes with UUID path converters; no count/stats/status routes.
- `backend/app/modules/crawler/tasks/runtime_status.py`: task runtime derivation, snapshot construction, ordering timestamp, and snapshot/status publication.
- `backend/app/modules/crawler/runs/schemas.py`: distinct run-list, run-detail, subtask-list, realtime-patch, and accepted-action DTOs.
- `backend/app/modules/crawler/runs/router.py`: single run-list request with total, subtask list with summary, minimal action responses, and removed obsolete routes.
- `backend/app/modules/crawler/runtime/events.py`: minimal run/subtask/log event payloads.
- `backend/app/modules/realtime/router.py`: initial task snapshot after subscriber registration.
- `frontend/src/stores/useCrawlerRuntimeStore.ts`: connection metadata plus task/run runtime overlays only.
- `frontend/src/realtime/types.ts`: exact realtime event contracts.
- `frontend/src/realtime/applyRealtimeEvent.ts`: global event-to-store reducer.
- `frontend/src/realtime/eventSourceClient.ts`: singleton connection, dispatch ordering, controlled reconnect, and subscription registry.
- `frontend/src/realtime/useRealtimeLifecycle.ts`: authenticated-shell connection lifecycle.
- `frontend/src/pages/crawler/tasks/`: static Query data combined with task runtime Store state.
- `frontend/src/pages/crawler/runs/`: run-list Store overlays and run-detail local subtask/log state.
- `frontend/src/api/crawler/`: simplified API calls and DTO types.
- `frontend/README.md`: documented ownership boundaries and global realtime lifecycle.

---

### Task 1: Replace The Crawler Task List Contract

**Files:**
- Modify: `backend/tests/test_crawler_tasks_api.py:68-113`
- Modify: `backend/tests/test_crawl_tasks_api.py:57-86,215-301`
- Modify: `backend/app/schemas/crawl_task.py:8-87`
- Modify: `backend/app/modules/crawler/tasks/serializers.py:1-12`
- Modify: `backend/app/modules/crawler/tasks/service.py:10-82`
- Modify: `backend/app/modules/crawler/tasks/router.py:1-136`
- Modify: `backend/app/repositories/crawl_task.py:16-55,150-184`

**Interfaces:**
- Produces: `serialize_task_list_item(task) -> CrawlTaskListItem`.
- Produces: `CrawlerTaskService.list_tasks(owner_id, page, size, keyword) -> {rows, total, page, size}`.
- Preserves: `serialize_task(task) -> CrawlTaskRead` for create/edit/detail consumers.
- Removes: task `/count`, `/stats`, and `/statuses` routes and their service methods.

- [ ] **Step 1: Replace task-list and removed-route tests**

Replace the pagination/count assertions in `backend/tests/test_crawler_tasks_api.py` with:

```python
def test_crawler_task_list_returns_total_and_static_list_fields(client, auth_headers):
    for index in range(3):
        response = client.post(
            "/api/crawler/tasks",
            json={
                "name": f"paged-task-{index}",
                "storage_location": "A",
                "is_skip": False,
                "urls": [{"url": f"https://javdb.com/actors/{index}", "url_type": "actors"}],
            },
            headers=auth_headers,
        )
        assert response.status_code == 201

    response = client.get("/api/crawler/tasks?page=1&size=2", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["page"] == 1
    assert data["size"] == 2
    assert data["total"] == 3
    assert len(data["rows"]) == 2
    assert set(data["rows"][0]) == {"id", "name", "storage_location", "is_skip", "urls"}
    assert set(data["rows"][0]["urls"][0]) == {
        "id",
        "position",
        "url",
        "url_type",
        "has_magnet",
        "has_chinese_sub",
        "url_name",
    }


def test_removed_task_aggregate_routes_return_404(client, auth_headers):
    for path in ("count", "stats", "statuses"):
        response = client.get(f"/api/crawler/tasks/{path}", headers=auth_headers)
        assert response.status_code == 404
```

In `backend/tests/test_crawl_tasks_api.py`, update the canonical list test to read `response.json()["data"]`, delete the stats and latest-run-metadata tests, and add:

```python
def test_task_detail_keeps_full_edit_fields(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    created = client.post("/api/crawler/tasks", json=task_payload(), headers=headers).json()["data"]

    detail = client.get(f"/api/crawler/tasks/{created['id']}", headers=headers).json()["data"]

    assert detail["owner_id"] == str(admin_user.id)
    assert detail["urls"][0]["source"] == "javdb"
    assert "final_url" in detail["urls"][0]
```

- [ ] **Step 2: Run the task API tests and verify the contract fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_tasks_api.py backend/tests/test_crawl_tasks_api.py -q
```

Expected: FAIL because the list still returns `has_more` and `runtime`, the removed routes still exist, and invalid static UUID paths return 422 rather than 404.

- [ ] **Step 3: Add dedicated task-list schemas and serializer**

Add these models to `backend/app/schemas/crawl_task.py`:

```python
class TaskUrlListItem(BaseModel):
    id: uuid.UUID
    position: int
    url: str
    url_type: str
    has_magnet: bool
    has_chinese_sub: bool
    url_name: str | None = None

    model_config = {"from_attributes": True}


class CrawlTaskListItem(BaseModel):
    id: uuid.UUID
    name: str
    storage_location: str
    is_skip: bool
    urls: list[TaskUrlListItem]

    model_config = {"from_attributes": True}
```

Add the list serializer to `backend/app/modules/crawler/tasks/serializers.py`:

```python
from backend.app.schemas.crawl_task import CrawlTaskListItem, CrawlTaskRead


def serialize_task_list_item(task) -> CrawlTaskListItem:
    return CrawlTaskListItem.model_validate(task)
```

Keep the existing `serialize_task` implementation unchanged for task detail/create/update responses.

- [ ] **Step 4: Make the list service return total and remove runtime queries**

Replace `CrawlerTaskService.list_tasks` with:

```python
def list_tasks(
    self,
    owner_id: uuid.UUID,
    *,
    page: int,
    size: int,
    keyword: str | None = None,
) -> dict:
    rows, _has_more = self.repo.get_by_owner(owner_id, page=page, size=size, keyword=keyword)
    return {
        "rows": [serialize_task_list_item(row).model_dump(mode="json") for row in rows],
        "total": self.repo.count_by_owner(owner_id, keyword=keyword),
        "page": page,
        "size": size,
    }
```

Remove imports and methods used only by list runtime/count/stats responses:

```python
from backend.app.modules.crawler.tasks.serializers import serialize_task, serialize_task_list_item
```

Delete `CrawlerTaskService.count_tasks`, `CrawlerTaskService.get_stats`, the list-time latest-run lookup, and `CrawlTaskStats` if no remaining backend import references it.

- [ ] **Step 5: Remove obsolete routes and make invalid static paths return 404**

Delete `/count`, `/stats`, and `/statuses` handlers from `backend/app/modules/crawler/tasks/router.py`. Remove unused imports. Change every UUID task route to Starlette's UUID converter, including:

```python
@router.get("/{task_id:uuid}")
@router.post("/{task_id:uuid}/run", status_code=status.HTTP_201_CREATED)
@router.post("/{task_id:uuid}/url-run", status_code=status.HTTP_201_CREATED)
@router.put("/{task_id:uuid}")
@router.delete("/{task_id:uuid}")
```

This prevents removed names such as `count` from falling through to UUID validation and returning 422.

- [ ] **Step 6: Run focused backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_tasks_api.py backend/tests/test_crawl_tasks_api.py backend/tests/test_task_delete_cascade.py -q
```

Expected: PASS; the task list contains only static fields and all three removed routes return 404.

- [ ] **Step 7: Commit the task-list backend contract**

```bash
git add backend/app/schemas/crawl_task.py backend/app/modules/crawler/tasks/serializers.py backend/app/modules/crawler/tasks/service.py backend/app/modules/crawler/tasks/router.py backend/app/repositories/crawl_task.py backend/tests/test_crawler_tasks_api.py backend/tests/test_crawl_tasks_api.py
git commit -m "refactor: simplify crawler task list api"
```

---

### Task 2: Simplify Run APIs And Action Responses

**Files:**
- Modify: `backend/tests/test_crawler_runs_api.py:72-165,869-950`
- Modify: `backend/app/modules/crawler/runs/schemas.py:1-108`
- Modify: `backend/app/modules/crawler/runs/router.py:1-242`
- Modify: `backend/app/modules/crawler/tasks/service.py:84-157`

**Interfaces:**
- Produces: `CrawlRunListItem`, `CrawlRunDetailRead`, `CrawlRunDetailTaskListItem`, `RunTaskPage`, and `RunActionAccepted`.
- Produces: `accepted_run_action(run) -> {run_id: str, accepted: bool}`.
- Removes: run `/count`, `/queue-status`, and `/{run_id}/tasks/summary` routes.
- Preserves: internal `CrawlerRuntimeState.queue_status()` for the dashboard.

- [ ] **Step 1: Write failing run API contract tests**

Update `backend/tests/test_crawler_runs_api.py` with:

```python
def test_run_list_returns_total_and_only_list_fields(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    task = CrawlTask(name="list-contract", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    session.add(CrawlRun(task_id=task.id, task_name=task.name, status="running", crawl_mode="full"))
    session.commit()
    session.close()

    response = client.get("/api/crawler/runs?page=1&size=20", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["size"] == 20
    assert set(data["rows"][0]) == {"id", "task_name", "status", "crawl_mode", "created_at"}


def test_run_tasks_include_summary_and_trim_rows(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="detail-contract", status="running", crawl_mode="full")
    session.add(run)
    session.flush()
    session.add(CrawlRunDetailTask(
        run_id=run.id,
        task_name=run.task_name,
        code="AAA-001",
        source_url="https://example.test/aaa",
        source_name="AAA",
        source_url_name="入口 A",
        task_url_type="list",
        status="saved",
    ))
    session.commit()
    run_id = str(run.id)
    session.close()

    response = client.get(f"/api/crawler/runs/{run_id}/tasks", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["summary"]["saved"] == 1
    assert set(body["rows"][0]) == {
        "id",
        "code",
        "source_name",
        "source_url_name",
        "task_url_type",
        "status",
        "error",
        "display_code",
        "display_source_name",
    }


def test_removed_run_routes_return_404(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    for path in ("count", "queue-status"):
        assert client.get(f"/api/crawler/runs/{path}", headers=headers).status_code == 404
    missing = "00000000-0000-0000-0000-000000000001"
    assert client.get(f"/api/crawler/runs/{missing}/tasks/summary", headers=headers).status_code == 404
```

Change task-run creation assertions to require exactly:

```python
body = response.json()["data"]
assert body == {"run_id": runtime.enqueued[0], "accepted": True}
```

For stop, restart, and retry tests, the service reuses the same run row, so assert:

```python
assert response.json()["data"] == {"run_id": run_id, "accepted": True}
```

- [ ] **Step 2: Run focused run API tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py backend/tests/test_crawl_tasks_api.py -q
```

Expected: FAIL because list rows still contain full run fields, totals use a second endpoint, summary uses a second endpoint, and actions return full run objects.

- [ ] **Step 3: Add dedicated run schemas and serializers**

Add to `backend/app/modules/crawler/runs/schemas.py`:

```python
class CrawlRunListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_name: str
    status: str
    crawl_mode: str
    created_at: datetime


class CrawlRunDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_name: str
    status: str
    crawl_mode: str
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    created_at: datetime


class CrawlRunDetailTaskListItem(BaseModel):
    id: uuid.UUID
    code: str | None
    source_name: str
    source_url_name: str | None
    task_url_type: str | None
    status: str
    error: str | None
    display_code: str | None
    display_source_name: str | None


class RunActionAccepted(BaseModel):
    run_id: uuid.UUID
    accepted: bool = True


def accepted_run_action(run: Any) -> dict:
    return RunActionAccepted(run_id=run.id).model_dump(mode="json")
```

Replace `_serialize_run_detail_task` with a list serializer that derives display fields and validates through `CrawlRunDetailTaskListItem`. Keep any full serializer still required by non-list code under an explicit full-detail name.

- [ ] **Step 4: Return total in the run list and summary in the subtask page**

In `backend/app/modules/crawler/runs/router.py`, make `list_runs` count the filtered query before pagination and serialize with `CrawlRunListItem`:

```python
query = _owned_run_query(db, current_user.id, task_id=task_id, status_filter=status_filter)
total = query.count()
rows = (
    query.order_by(CrawlRun.created_at.desc(), CrawlRun.id.desc())
    .offset((page - 1) * size)
    .limit(size)
    .all()
)
return success(data={
    "rows": [CrawlRunListItem.model_validate(row).model_dump(mode="json") for row in rows],
    "total": total,
    "page": page,
    "size": size,
})
```

Make `list_run_tasks` return:

```python
return {
    "code": 200,
    "msg": "success",
    "rows": [_serialize_run_detail_task_list_item(row) for row in rows],
    "total": total,
    "summary": _run_task_summary(db, run),
}
```

Delete `/count`, `/queue-status`, and `/{run_id}/tasks/summary`. Change every run UUID route to `/{run_id:uuid}` so removed static paths return 404. Keep `_run_task_summary` because both the subtask list and realtime detail events use it.

- [ ] **Step 5: Return minimal accepted-action payloads**

Use `accepted_run_action(run)` in task run creation, URL subset run, temporary run, stop, restart, and retry handlers. The service can return the accepted payload directly:

```python
run = CrawlerRunService(self.db, get_runtime_state()).create_run(task, data.crawl_mode)
return accepted_run_action(run)
```

Do not change task create/update/delete response payloads. Do not remove the internal runtime `queue_status()` method or dashboard use.

- [ ] **Step 6: Run focused backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py backend/tests/test_crawl_tasks_api.py backend/tests/test_dashboard_overview.py -q
```

Expected: PASS; list/detail payloads are trimmed, action responses are minimal, removed routes return 404, and dashboard queue data remains available.

- [ ] **Step 7: Commit run API changes**

```bash
git add backend/app/modules/crawler/runs/schemas.py backend/app/modules/crawler/runs/router.py backend/app/modules/crawler/tasks/service.py backend/tests/test_crawler_runs_api.py backend/tests/test_crawl_tasks_api.py
git commit -m "refactor: simplify crawler run api contracts"
```

---

### Task 3: Publish Initial Task Snapshots And Minimal Realtime Events

**Files:**
- Modify: `backend/tests/test_realtime_events.py:1-220`
- Modify: `backend/tests/test_crawler_realtime_events.py:1-420`
- Modify: `backend/app/schemas/crawl_task.py:150-185`
- Modify: `backend/app/modules/crawler/tasks/runtime_status.py:1-220`
- Modify: `backend/app/modules/crawler/tasks/service.py:159-249`
- Modify: `backend/app/modules/crawler/runtime/events.py:1-145`
- Modify: `backend/app/modules/realtime/router.py:1-92`

**Interfaces:**
- Produces: `build_task_runtime_snapshot_event(db, owner_id, reason) -> RealtimeEvent`.
- Produces: `publish_task_runtime_snapshot(db, owner_id, reason) -> None`.
- Produces events: `crawler.task.runtime.snapshot`, `crawler.task.status.updated`, `crawler.run.status.updated`, `crawler.run.detail.updated`, and `crawler.run.log.appended`.
- Removes event: `crawler.queue.updated` and `publish_queue_updated`.

- [ ] **Step 1: Write failing task snapshot and minimal-event tests**

Add to `backend/tests/test_crawler_realtime_events.py`:

```python
def test_build_task_runtime_snapshot_event_contains_all_owner_tasks(admin_user) -> None:
    from backend.app.modules.crawler.tasks.runtime_status import build_task_runtime_snapshot_event

    session = TestingSessionLocal()
    own_task = CrawlTask(name="own", storage_location="A", owner_id=admin_user.id)
    session.add(own_task)
    session.commit()

    event = build_task_runtime_snapshot_event(session, admin_user.id, "connected")

    assert event.event == "crawler.task.runtime.snapshot"
    assert event.owner_id == str(admin_user.id)
    assert event.payload["reason"] == "connected"
    assert event.payload["stats"] == {"total": 1, "idle": 1, "running": 0, "queued": 0, "stopped": 0}
    assert event.payload["tasks"][0]["task_id"] == str(own_task.id)
    assert set(event.payload["tasks"][0]) == {
        "task_id", "runtime_status", "latest_run_id", "last_run_at", "state_updated_at"
    }
    session.close()


def test_run_status_event_contains_only_dynamic_fields(admin_user) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(name="event-task", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="running", crawl_mode="full")
    session.add(run)
    session.commit()
    queue = event_bus.subscribe(str(admin_user.id))

    service.publish_run_updated(session, run)

    run_event = drain(queue)[0]
    assert run_event.event == "crawler.run.status.updated"
    assert set(run_event.payload) == {
        "run_id", "status", "error", "started_at", "finished_at", "state_updated_at"
    }
    event_bus.unsubscribe(str(admin_user.id), queue)
    session.close()
```

Update the detail-event assertion so each task patch contains only:

```python
assert set(detail_event.payload["tasks"][0]) == {
    "id",
    "status",
    "error",
    "code",
    "source_name",
    "source_url_name",
    "task_url_type",
    "display_code",
    "display_source_name",
}
```

Add a unit test in `backend/tests/test_realtime_events.py` that uses a fake bus and fake builder to assert `subscribe` happens before snapshot construction:

```python
def test_initial_stream_subscribes_before_building_snapshot(monkeypatch) -> None:
    order: list[str] = []

    class Bus:
        def subscribe(self, owner_id):
            order.append("subscribe")
            return queue.Queue()

        def unsubscribe(self, owner_id, target_queue):
            order.append("unsubscribe")

    monkeypatch.setattr("backend.app.modules.realtime.router.event_bus", Bus())
    monkeypatch.setattr(
        "backend.app.modules.realtime.router.build_task_runtime_snapshot_event",
        lambda db, owner_id, reason: order.append("snapshot") or make_realtime_event(
            event="crawler.task.runtime.snapshot",
            scope="crawler.task",
            owner_id=owner_id,
            payload={"reason": reason, "tasks": [], "stats": {}},
        ),
    )

    async def consume_initial_frames():
        stream = build_owner_event_stream(object(), "owner-1")
        try:
            return await anext(stream), await anext(stream)
        finally:
            await stream.aclose()

    first, second = asyncio.run(consume_initial_frames())
    assert "system.connected" in first
    assert "crawler.task.runtime.snapshot" in second
    assert order[:2] == ["subscribe", "snapshot"]
```

- [ ] **Step 2: Run realtime tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_realtime_events.py backend/tests/test_realtime_events.py -q
```

Expected: FAIL because the snapshot event/helper does not exist and run/detail events still use full payload contracts.

- [ ] **Step 3: Add ordered runtime timestamps and snapshot construction**

Change `CrawlTaskRuntimeSnapshot` to remove `latest_run_status` and add `state_updated_at: datetime`. Derive it with:

```python
state_updated_at = (
    latest_run.updated_at or latest_run.created_at
    if latest_run is not None
    else task.updated_at or task.created_at
)
```

Add to `backend/app/modules/crawler/tasks/runtime_status.py`:

```python
SnapshotReason = Literal["connected", "task_created", "task_deleted"]


def build_task_runtime_snapshot_event(
    db: Session,
    owner_id: uuid.UUID,
    reason: SnapshotReason,
):
    from backend.app.modules.realtime.schemas import make_realtime_event

    snapshot = build_task_runtime_status_response(db, owner_id)
    return make_realtime_event(
        event="crawler.task.runtime.snapshot",
        scope="crawler.task",
        owner_id=str(owner_id),
        payload={
            "reason": reason,
            "tasks": [item.model_dump(mode="json") for item in snapshot.tasks],
            "stats": snapshot.stats.model_dump(),
            "generated_at": datetime.now(UTC).isoformat(),
        },
    )


def publish_task_runtime_snapshot(
    db: Session,
    owner_id: uuid.UUID,
    reason: SnapshotReason,
) -> None:
    from backend.app.modules.realtime.bus import event_bus

    event_bus.publish(build_task_runtime_snapshot_event(db, owner_id, reason))
```

Publish `task_created` after a successful task create and `task_deleted` after deletion and runtime-key purge.

- [ ] **Step 4: Extract and use an owner-stream generator**

In `backend/app/modules/realtime/router.py`, extract:

```python
async def build_owner_event_stream(db: Session, owner_id: str):
    queue = event_bus.subscribe(owner_id)
    last_keepalive = asyncio.get_running_loop().time()
    try:
        yield format_sse_event(make_realtime_event(
            event="system.connected",
            scope="system",
            owner_id=owner_id,
            payload={"message": "connected"},
        ))
        yield format_sse_event(build_task_runtime_snapshot_event(db, uuid.UUID(owner_id), "connected"))
        while True:
            try:
                event = queue.get_nowait()
                yield format_sse_event(event)
                continue
            except Empty:
                pass
            now = asyncio.get_running_loop().time()
            if now - last_keepalive >= KEEPALIVE_SECONDS:
                last_keepalive = now
                yield format_sse_comment("keepalive")
            await asyncio.sleep(QUEUE_POLL_SECONDS)
    finally:
        event_bus.unsubscribe(owner_id, queue)
```

Have `event_stream` return `StreamingResponse(build_owner_event_stream(db, owner_id), ...)` with the existing headers.

- [ ] **Step 5: Minimize run and detail events**

Change `publish_run_updated` to publish `crawler.run.status.updated`:

```python
payload = {
    "run_id": str(run.id),
    "status": run.status,
    "error": run.error,
    "started_at": run.started_at.isoformat() if run.started_at else None,
    "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    "state_updated_at": (run.updated_at or run.created_at).isoformat(),
}
```

Serialize detail patches with the dedicated list/patch serializer from Task 2 and keep the full summary in `crawler.run.detail.updated`. Delete `publish_queue_updated`; do not delete `CrawlerRuntimeState.queue_status()`.

- [ ] **Step 6: Run realtime and mutation tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_realtime_events.py backend/tests/test_realtime_events.py backend/tests/test_crawler_runs_api.py backend/tests/test_crawl_tasks_api.py -q
```

Expected: PASS; owner streams start with connected plus snapshot, mutation snapshots are published, and incremental payloads are minimal.

- [ ] **Step 7: Commit backend realtime changes**

```bash
git add backend/app/schemas/crawl_task.py backend/app/modules/crawler/tasks/runtime_status.py backend/app/modules/crawler/tasks/service.py backend/app/modules/crawler/runtime/events.py backend/app/modules/realtime/router.py backend/tests/test_crawler_realtime_events.py backend/tests/test_realtime_events.py
git commit -m "refactor: publish crawler runtime snapshots"
```

---

### Task 4: Replace The Frontend Runtime Store And Event Reducer

**Files:**
- Create: `frontend/src/stores/__tests__/crawler-runtime-store.test.ts`
- Create: `frontend/src/realtime/__tests__/applyRealtimeEvent.test.ts`
- Modify: `frontend/src/stores/useCrawlerRuntimeStore.ts:1-89`
- Modify: `frontend/src/realtime/types.ts:1-75`
- Modify: `frontend/src/realtime/applyRealtimeEvent.ts:1-58`
- Modify: `frontend/src/api/crawler/crawlTask/types.ts:92-113`
- Modify: `frontend/src/api/crawler/crawlerRun/types.ts:1-75`

**Interfaces:**
- Produces: `replaceTaskRuntimeSnapshot(payload)`, `upsertTaskRuntime(snapshot)`, `hydrateRunRuntime(baselines)`, `upsertRunRuntime(runtime)`, `removeRunRuntime(runId)`, and `reset()`.
- Produces Store state: `taskRuntimeById`, `taskStats`, `taskSnapshotReady`, and `runRuntimeById`.
- Preserves connection actions: `setConnectionStatus`, `markConnected`, and `markResyncRequired`.
- Removes Store state: complete runs, detail tasks, logs, and summaries.

- [ ] **Step 1: Write failing Store and reducer tests**

Create `frontend/src/stores/__tests__/crawler-runtime-store.test.ts`:

```typescript
import { beforeEach, describe, expect, it } from 'vitest'
import { useCrawlerRuntimeStore } from '../useCrawlerRuntimeStore'

beforeEach(() => useCrawlerRuntimeStore.getState().reset())

describe('crawler runtime store', () => {
  it('atomically replaces task runtime and stats from a snapshot', () => {
    useCrawlerRuntimeStore.getState().replaceTaskRuntimeSnapshot({
      reason: 'connected',
      generated_at: '2026-08-13T09:00:00Z',
      tasks: [{
        task_id: 'task-1',
        runtime_status: 'running',
        latest_run_id: 'run-1',
        last_run_at: '2026-08-13T08:59:00Z',
        state_updated_at: '2026-08-13T08:59:30Z',
      }],
      stats: { total: 1, idle: 0, running: 1, queued: 0, stopped: 0 },
    })

    const state = useCrawlerRuntimeStore.getState()
    expect(state.taskSnapshotReady).toBe(true)
    expect(state.taskStats.running).toBe(1)
    expect(state.taskRuntimeById['task-1'].latest_run_id).toBe('run-1')
  })

  it('rejects an older run event', () => {
    const store = useCrawlerRuntimeStore.getState()
    store.upsertRunRuntime({ run_id: 'run-1', status: 'completed', error: null, started_at: null, finished_at: null, state_updated_at: '2026-08-13T09:01:00Z' })
    store.upsertRunRuntime({ run_id: 'run-1', status: 'running', error: null, started_at: null, finished_at: null, state_updated_at: '2026-08-13T09:00:00Z' })

    expect(useCrawlerRuntimeStore.getState().runRuntimeById['run-1'].status).toBe('completed')
  })
})
```

Create `frontend/src/realtime/__tests__/applyRealtimeEvent.test.ts` with snapshot, task-update, run-update, connected, and resync assertions. The run assertion must use `crawler.run.status.updated` and verify no complete run object is stored.

- [ ] **Step 2: Run the Store/reducer tests and verify failure**

Run:

```bash
cd frontend
npm test -- src/stores/__tests__/crawler-runtime-store.test.ts src/realtime/__tests__/applyRealtimeEvent.test.ts
```

Expected: FAIL because the new state/action names and event contracts do not exist.

- [ ] **Step 3: Define exact frontend runtime DTOs**

In the crawler API/realtime types, define:

```typescript
export type TaskRuntimeStatus = 'idle' | 'queued' | 'running' | 'stopped'

export interface CrawlTaskRuntimeSnapshot {
  task_id: string
  runtime_status: TaskRuntimeStatus
  latest_run_id: string | null
  last_run_at: string | null
  state_updated_at: string
}

export interface CrawlTaskRuntimeStats {
  total: number
  idle: number
  running: number
  queued: number
  stopped: number
}

export interface CrawlerTaskRuntimeSnapshotPayload {
  reason: 'connected' | 'task_created' | 'task_deleted'
  generated_at: string
  tasks: CrawlTaskRuntimeSnapshot[]
  stats: CrawlTaskRuntimeStats
}

export interface CrawlRunRuntime {
  run_id: string
  status: CrawlRunStatus
  error: string | null
  started_at: string | null
  finished_at: string | null
  state_updated_at: string
}

export interface CrawlRunDetailTaskPatch {
  id: string
  status: DetailTaskStatus
  error: string | null
  code: string | null
  source_name: string
  source_url_name: string | null
  task_url_type: string | null
  display_code: string | null
  display_source_name: string | null
}
```

Change `CrawlerRunDetailUpdatedPayload.tasks` to `CrawlRunDetailTaskPatch[]`, where each patch contains the exact backend fields from Task 3. Remove `QueueStatus`, `CrawlerRunUpdatedPayload`, and `crawler.queue.updated`.

- [ ] **Step 4: Implement the focused Store**

Replace `useCrawlerRuntimeStore.ts` with connection fields plus the four state collections from the interface block. Use this ordering guard in both upserts:

```typescript
function isNewer(current: { state_updated_at: string } | undefined, incoming: string): boolean {
  return !current || Date.parse(incoming) >= Date.parse(current.state_updated_at)
}
```

`replaceTaskRuntimeSnapshot` must replace the whole task map and stats atomically. `upsertTaskRuntime` must decrement the prior status count and increment the new status count only when the status changes. `hydrateRunRuntime` must fill missing run IDs without overwriting an existing event-derived entry. `reset()` must restore a fresh object rather than reusing mutable references.

`markResyncRequired(reason)` must set `taskSnapshotReady` to `false`, record the
reason, and clear `runRuntimeById`. Clearing run overlays ensures the next visible
run-list/detail REST baseline cannot be masked by a status missed during the
disconnection.

- [ ] **Step 5: Route global events through the focused reducer**

Implement these branches in `applyRealtimeEvent`:

```typescript
if (event.event === 'crawler.task.runtime.snapshot') {
  store.replaceTaskRuntimeSnapshot(event.payload as CrawlerTaskRuntimeSnapshotPayload)
  return
}
if (event.event === 'crawler.task.status.updated') {
  store.upsertTaskRuntime(event.payload as CrawlTaskRuntimeSnapshot)
  return
}
if (event.event === 'crawler.run.status.updated') {
  store.upsertRunRuntime(event.payload as CrawlRunRuntime)
  return
}
```

Keep connected/resync connection metadata branches. Remove detail-task/log/summary writes from the global reducer; page subscribers handle those events locally.

- [ ] **Step 6: Run focused frontend tests**

Run:

```bash
cd frontend
npm test -- src/stores/__tests__/crawler-runtime-store.test.ts src/realtime/__tests__/applyRealtimeEvent.test.ts
```

Expected: PASS; task snapshots replace atomically, incremental stats remain correct, and old run events are ignored.

- [ ] **Step 7: Commit the Store and reducer**

```bash
git add frontend/src/stores/useCrawlerRuntimeStore.ts frontend/src/stores/__tests__/crawler-runtime-store.test.ts frontend/src/realtime/types.ts frontend/src/realtime/applyRealtimeEvent.ts frontend/src/realtime/__tests__/applyRealtimeEvent.test.ts frontend/src/api/crawler/crawlTask/types.ts frontend/src/api/crawler/crawlerRun/types.ts
git commit -m "refactor: focus crawler runtime store"
```

---

### Task 5: Move EventSource Lifecycle To The Authenticated Shell

**Files:**
- Create: `frontend/src/realtime/useRealtimeLifecycle.ts`
- Create: `frontend/src/realtime/__tests__/useRealtimeLifecycle.test.tsx`
- Modify: `frontend/src/realtime/eventSourceClient.ts:1-92`
- Modify: `frontend/src/layout/index.tsx:1-38`
- Modify: crawler/storage/movie realtime hooks that call `connectRealtime`

**Interfaces:**
- Produces: `useRealtimeLifecycle(): void`.
- Produces: `restartRealtime(reason: string): EventSource | null` without clearing page handlers.
- Preserves: `subscribeRealtime(eventName, handler) -> unsubscribe`.

- [ ] **Step 1: Write a failing lifecycle test**

Create `frontend/src/realtime/__tests__/useRealtimeLifecycle.test.tsx`:

```typescript
import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import { useRealtimeLifecycle } from '../useRealtimeLifecycle'
import { connectRealtime, disconnectRealtime } from '../eventSourceClient'

vi.mock('../eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  disconnectRealtime: vi.fn(),
}))

describe('useRealtimeLifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useCrawlerRuntimeStore.getState().reset()
  })

  it('connects once and disconnects plus resets on unmount', () => {
    const { rerender, unmount } = renderHook(() => useRealtimeLifecycle())
    rerender()
    expect(connectRealtime).toHaveBeenCalledTimes(1)

    useCrawlerRuntimeStore.getState().setConnectionStatus('connected')
    unmount()

    expect(disconnectRealtime).toHaveBeenCalledTimes(1)
    expect(useCrawlerRuntimeStore.getState().connectionStatus).toBe('idle')
  })
})
```

- [ ] **Step 2: Run the lifecycle test and verify failure**

Run:

```bash
cd frontend
npm test -- src/realtime/__tests__/useRealtimeLifecycle.test.tsx
```

Expected: FAIL because `useRealtimeLifecycle` does not exist.

- [ ] **Step 3: Implement the shell lifecycle hook**

Create `frontend/src/realtime/useRealtimeLifecycle.ts`:

```typescript
import { useEffect } from 'react'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import { connectRealtime, disconnectRealtime } from './eventSourceClient'

export function useRealtimeLifecycle(): void {
  useEffect(() => {
    connectRealtime()
    return () => {
      disconnectRealtime()
      useCrawlerRuntimeStore.getState().reset()
    }
  }, [])
}
```

Call `useRealtimeLifecycle()` once at the top of `AppLayout`.

- [ ] **Step 4: Make connection dispatch and resync behavior global**

Add `crawler.task.runtime.snapshot` and `crawler.run.status.updated` to `EVENT_NAMES`; remove old run/queue names. Ensure `emitLocalResync` calls `applyRealtimeEvent(event)` before notifying handlers.

Implement restart without clearing handlers:

```typescript
export function restartRealtime(reason: string): EventSource | null {
  source?.close()
  source = null
  useCrawlerRuntimeStore.getState().markResyncRequired(reason)
  return connectRealtime()
}
```

For a server `system.resync_required` event or malformed event, notify current subscribers and then call `restartRealtime(reason)`. Keep native EventSource retry for ordinary `onerror`. Track whether this client has connected before; when a later server `system.connected` arrives after an error, first emit a local `system.resync_required` with reason `reconnected`, then dispatch `system.connected`. This delays visible-page recovery requests until transport is available again. The following server snapshot restores task runtime. `disconnectRealtime()` remains the logout/unmount operation and resets the connection-history flag and clears handlers.

- [ ] **Step 5: Remove page-owned connection calls**

Remove `connectRealtime()` imports/calls from crawler, storage, and movie page hooks. Keep their `subscribeRealtime` calls. This ensures feature hooks register handlers but never own transport lifetime.

- [ ] **Step 6: Run realtime and affected page tests**

Run:

```bash
cd frontend
npm test -- src/realtime src/pages/crawler src/pages/storage/tasks src/pages/content/movies
```

Expected: PASS; one shell lifecycle owns the connection while feature subscriptions continue working.

- [ ] **Step 7: Commit the global lifecycle**

```bash
git add frontend/src/realtime frontend/src/layout/index.tsx frontend/src/pages/crawler frontend/src/pages/storage/tasks/hooks frontend/src/pages/content/movies/hooks
git commit -m "refactor: centralize realtime connection lifecycle"
```

---

### Task 6: Make The Task List Consume Static REST Data And Store Runtime

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/__tests__/task-list-query.test.tsx`
- Modify: `frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx`
- Modify: `frontend/src/api/crawler/crawlTask/index.ts:1-78`
- Modify: `frontend/src/api/crawler/crawlTask/types.ts:1-125`
- Modify: `frontend/src/api/queryKeys.ts:12-19`
- Modify: `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx:1-215`
- Modify: `frontend/src/pages/crawler/tasks/hooks/useTaskListRealtime.ts:1-40`
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx:1-145`
- Modify: `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx:1-290`
- Delete: `frontend/src/pages/crawler/tasks/utils/runtimeStats.ts`

**Interfaces:**
- Consumes: `taskRuntimeById`, `taskStats`, `taskSnapshotReady`, and `connectionStatus` from Task 4.
- Produces: one `getCrawlTasks({page, size})` call returning `{rows, total, page, size}`.
- Removes: frontend `getCrawlTaskCount`, `getCrawlTaskStats`, and `getCrawlTaskRuntimeStatuses`.

- [ ] **Step 1: Write failing single-request and snapshot-readiness tests**

Update `task-list-query.test.tsx` so the mock only exports task-list CRUD functions and add:

```typescript
it('loads static task rows with one list request and reads runtime from the store', async () => {
  vi.mocked(getCrawlTasks).mockResolvedValue({ rows: [taskRow], total: 1, page: 1, size: 20 })
  useCrawlerRuntimeStore.getState().replaceTaskRuntimeSnapshot({
    reason: 'connected',
    generated_at: '2026-08-13T09:00:00Z',
    tasks: [{ task_id: taskRow.id, runtime_status: 'running', latest_run_id: 'run-1', last_run_at: null, state_updated_at: '2026-08-13T09:00:00Z' }],
    stats: { total: 1, idle: 0, running: 1, queued: 0, stopped: 0 },
  })

  const { result } = renderHook(() => useTaskListData(), { wrapper })

  await waitFor(() => expect(result.current.loading).toBe(false))
  expect(result.current.total).toBe(1)
  expect(result.current.runtimeByTaskId[taskRow.id].runtime_status).toBe('running')
  expect(getCrawlTasks).toHaveBeenCalledTimes(1)
})
```

Add a card test that resets the Store without a snapshot and asserts the card shows `同步中` and that run/edit/delete buttons are disabled or absent.

- [ ] **Step 2: Run task-list tests and verify failure**

Run:

```bash
cd frontend
npm test -- src/pages/crawler/tasks/__tests__/task-list-query.test.tsx src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
```

Expected: FAIL because the hook still calls the count query and owns local runtime/stats state.

- [ ] **Step 3: Simplify task API types and query keys**

Define a distinct `CrawlTaskListItem` and `PagedListResponse<T>`:

```typescript
export interface TaskUrlListItem {
  id: string
  position: number
  url: string
  url_type: string
  has_magnet: boolean
  has_chinese_sub: boolean
  url_name: string | null
}

export interface CrawlTaskListItem {
  id: string
  name: string
  storage_location: string
  is_skip: boolean
  urls: TaskUrlListItem[]
}

export interface PagedListResponse<T> {
  rows: T[]
  total: number
  page: number
  size: number
}
```

Make `getCrawlTasks` return `Promise<PagedListResponse<CrawlTaskListItem>>`. Delete the three obsolete API methods and crawler task count/runtime query keys. Move `CountResponse` to the storage API type module if storage still imports it.

- [ ] **Step 4: Rewrite `useTaskListData` around Query plus Store selectors**

Use memoized list params and remove the count query, local runtime state, render-time state writes, and runtime refresh function:

```typescript
const listParams = useMemo(() => ({ page: current, size: pageSize }), [current, pageSize])
const listQuery = useQuery({
  queryKey: queryKeys.crawlerTasks.list(listParams),
  queryFn: () => getCrawlTasks(listParams),
  placeholderData: (previousData) => previousData,
})
const runtimeByTaskId = useCrawlerRuntimeStore((state) => state.taskRuntimeById)
const stats = useCrawlerRuntimeStore((state) => state.taskStats)
const runtimeReady = useCrawlerRuntimeStore(
  (state) => state.taskSnapshotReady && state.connectionStatus === 'connected',
)
```

Set `total = listQuery.data?.total ?? 0`, `loading = listQuery.isFetching`, and have `refreshList` invalidate only the current task-list key. Start/stop/restart success handlers must not refresh task runtime; they only show accepted messages. Keep run-list invalidation after creating a new run because a new static run row exists.

- [ ] **Step 5: Reduce the task realtime hook to structural refreshes**

Subscribe to `crawler.task.runtime.snapshot` and `system.resync_required`. When a snapshot reason is `task_created` or `task_deleted`, debounce a single `refreshList()` call. Ignore `connected` so the initial snapshot does not duplicate the initial list request. On resync, refresh the static list once because task creation/deletion may have occurred while disconnected. The global reducer already applies snapshot/status data before these handlers run.

- [ ] **Step 6: Render unknown runtime explicitly**

Pass `runtimeReady` through `TaskListPage` to `TaskListCards`. In `TaskCard`, use:

```typescript
const runtimeStatus = runtimeReady ? runtime?.runtime_status : undefined
const isIdle = runtimeStatus === 'idle'
```

Render a neutral `同步中` tag when `runtimeStatus` is undefined. All actions whose permission depends on runtime state must be disabled or hidden until `runtimeReady` is true. Remove `countLoading`, `hasMore`, and `runtimeStats.ts`; Ant Design pagination uses the list response `total` directly.

- [ ] **Step 7: Run all task-list tests**

Run:

```bash
cd frontend
npm test -- src/pages/crawler/tasks
```

Expected: PASS; one REST query provides static rows/total and Store runtime controls metrics and actions.

- [ ] **Step 8: Commit task-list frontend changes**

```bash
git add frontend/src/api/crawler/crawlTask frontend/src/api/queryKeys.ts frontend/src/pages/crawler/tasks
git commit -m "refactor: source task runtime from event store"
```

---

### Task 7: Overlay Run-List Status From The Store

**Files:**
- Modify: `frontend/src/pages/crawler/runs/__tests__/run-list-query.test.tsx`
- Modify: `frontend/src/api/crawler/crawlerRun/index.ts:1-82`
- Modify: `frontend/src/api/crawler/crawlerRun/types.ts:1-90`
- Modify: `frontend/src/api/queryKeys.ts:5-11`
- Modify: `frontend/src/pages/crawler/runs/RunListPage.tsx:1-250`

**Interfaces:**
- Consumes: `hydrateRunRuntime`, `runRuntimeById`, and `removeRunRuntime` from Task 4.
- Produces: one run-list query returning `PagedListResponse<CrawlRunListItem>`.
- Removes: frontend `getCrawlerRunCount` and `getCrawlerQueueStatus`.

- [ ] **Step 1: Write failing run-list overlay tests**

Update `run-list-query.test.tsx` to remove the count mock and assert:

```typescript
it('uses one list request and renders a store status overlay', async () => {
  vi.mocked(getCrawlerRuns).mockResolvedValue({ rows: [buildRun('running')], total: 1, page: 1, size: 20 })
  const { findByText } = render(<RunListPage />, { wrapper })
  await findByText('Run Task')

  useCrawlerRuntimeStore.getState().upsertRunRuntime({
    run_id: 'run-1',
    status: 'failed',
    error: 'network error',
    started_at: null,
    finished_at: '2026-08-13T09:00:00Z',
    state_updated_at: '2026-08-13T09:00:00Z',
  })

  await findByText('失败')
  expect(getCrawlerRuns).toHaveBeenCalledTimes(1)
})
```

Add another test that sends two `crawler.run.status.updated` events for an unknown ID in the same tick and asserts the list is invalidated/refetched once.
Add a connection-error case that sets Store `connectionStatus` to `error` and
asserts stop, restart, and delete controls are disabled until reconnection.

- [ ] **Step 2: Run run-list tests and verify failure**

Run:

```bash
cd frontend
npm test -- src/pages/crawler/runs/__tests__/run-list-query.test.tsx
```

Expected: FAIL because the page still calls the count API and writes realtime status directly into Query data.

- [ ] **Step 3: Simplify the run API module and types**

Define:

```typescript
export interface CrawlRunListItem {
  id: string
  task_name: string
  status: CrawlRunStatus
  crawl_mode: CrawlMode
  created_at: string
}

export interface RunActionAccepted {
  run_id: string
  accepted: true
}
```

Make list and action API functions use these types. Delete `getCrawlerRunCount`, `getCrawlerQueueStatus`, and their query keys/types.

- [ ] **Step 4: Hydrate baselines and render overlays**

After list data changes, hydrate only missing Store entries:

```typescript
useEffect(() => {
  hydrateRunRuntime((listQuery.data?.rows ?? []).map((run) => ({
    run_id: run.id,
    status: run.status,
    error: null,
    started_at: null,
    finished_at: null,
    state_updated_at: run.created_at,
  })))
}, [hydrateRunRuntime, listQuery.data?.rows])

const runs = (listQuery.data?.rows ?? []).map((run) => ({
  ...run,
  status: runRuntimeById[run.id]?.status ?? run.status,
}))
```

Remove the count query. Use `listQuery.data?.total ?? 0` for pagination. Stop/restart success waits for EventSource and does not refresh the list. Delete removes the Store runtime and refreshes the static list.

Select `connectionStatus` from the Store and pass
`realtimeReady={connectionStatus === 'connected'}` into the action renderer.
Disable stop, restart, and delete when `realtimeReady` is false; viewing details
and pagination remain available.

- [ ] **Step 5: Refresh once for unknown structural rows**

Keep page-local subscriptions to `crawler.run.status.updated` and `system.resync_required`. Because the global reducer runs first, the run handler only checks whether the event run ID exists in the current REST row IDs. Use a single pending timer/ref to coalesce unknown IDs into one `refreshRuns()` call; known IDs never refresh. The resync handler refreshes the current list once so the cleared Store overlay is rehydrated from a current REST baseline.

- [ ] **Step 6: Run run-list tests**

Run:

```bash
cd frontend
npm test -- src/pages/crawler/runs/__tests__/run-list-query.test.tsx
```

Expected: PASS; the current row changes through Store state without a list request, and unknown structural events refetch once.

- [ ] **Step 7: Commit run-list frontend changes**

```bash
git add frontend/src/api/crawler/crawlerRun frontend/src/api/queryKeys.ts frontend/src/pages/crawler/runs/RunListPage.tsx frontend/src/pages/crawler/runs/__tests__/run-list-query.test.tsx
git commit -m "refactor: overlay run list runtime state"
```

---

### Task 8: Keep Run-Detail Subtasks And Logs Local

**Files:**
- Modify: `frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx`
- Create: `frontend/src/pages/crawler/runs/__tests__/run-detail-realtime.test.tsx`
- Modify: `frontend/src/api/crawler/crawlerRun/index.ts:30-65`
- Modify: `frontend/src/api/crawler/crawlerRun/types.ts:14-90`
- Modify: `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts:1-229`
- Modify: `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts:1-129`
- Modify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx:1-78`
- Modify: `frontend/src/pages/crawler/runs/components/RunSummaryCard.tsx:1-115`
- Modify: `frontend/src/pages/crawler/runs/components/runTaskColumns.tsx:1-75`

**Interfaces:**
- Consumes: run runtime overlay from Task 4.
- Produces: `RunTaskPage = {rows, total, summary}`.
- Keeps local: `tasks`, `taskSummary`, and `logs`.
- Removes: `getCrawlerRunTaskSummary` and all run-detail Store hydration.

- [ ] **Step 1: Write failing run-detail ownership tests**

Update `run-detail-retry.test.tsx` so the tasks API resolves:

```typescript
vi.mocked(getCrawlerRunTasks).mockResolvedValue({
  rows: detailRows,
  total: detailRows.length,
  summary: { total: 2, pending_crawl: 0, crawling: 0, saved: 1, skipped: 0, crawl_failed: 1, save_failed: 0, completed: 1, waiting: 0, failed: 1 },
})
```

Remove the summary API mock and assert it is absent from the mocked module. Add `run-detail-realtime.test.tsx` to verify a detail event updates the rendered row/summary while `useCrawlerRuntimeStore.getState()` still has no detail/log/summary collections. Add a duplicate log event twice and assert the message appears once.
Add a connection-error assertion that stop/restart/retry controls are disabled
while static run details, subtasks, and logs remain readable.

- [ ] **Step 2: Run detail tests and verify failure**

Run:

```bash
cd frontend
npm test -- src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx src/pages/crawler/runs/__tests__/run-detail-realtime.test.tsx
```

Expected: FAIL because summary is still fetched separately, full details/logs are hydrated into Store, and duplicate logs are appended.

- [ ] **Step 3: Define the run-detail REST types**

Use exact frontend models matching Task 2:

```typescript
export interface CrawlRunDetail {
  id: string
  task_name: string
  status: CrawlRunStatus
  crawl_mode: CrawlMode
  queued_at: string | null
  started_at: string | null
  finished_at: string | null
  error: string | null
  created_at: string
}

export interface CrawlRunDetailTask {
  id: string
  code: string | null
  source_name: string
  source_url_name: string | null
  task_url_type: string | null
  status: DetailTaskStatus
  error: string | null
  display_code: string | null
  display_source_name: string | null
}

export interface RunTaskPage {
  rows: CrawlRunDetailTask[]
  total: number
  summary: RunTaskSummary
}
```

Delete `getCrawlerRunTaskSummary`; make `getCrawlerRunTasks` return `Promise<RunTaskPage>`.

- [ ] **Step 4: Simplify `useRunDetail` fetch and action flows**

Remove `hydrateRun`, `hydrateRunLogs`, `hydrateRunDetails`, and `fetchTaskSummary`. `fetchTasks` sets all three local values from one response:

```typescript
const data = await getCrawlerRunTasks(id, params)
setTasks(data.rows)
setTaskTotal(data.total)
setTaskSummary(data.summary)
```

`resyncSnapshot` calls only `fetchRun`, `fetchLogs`, and `fetchTasks`. Stop/restart/retry success handlers display an accepted message and wait for realtime changes; they do not set a returned full run and do not perform a normal-path resync.

Select `runRuntimeById[id]` in the hook or page and build:

```typescript
const displayedRun = run ? {
  ...run,
  ...(runtime ? {
    status: runtime.status,
    error: runtime.error,
    started_at: runtime.started_at,
    finished_at: runtime.finished_at,
  } : {}),
} : null
```

Also select `connectionStatus`; expose `realtimeReady` to `RunSummaryCard` and
`RunTaskTable`. Disable stop, restart, and retry controls unless it equals
`connected`. Reading detail data and changing filters remain enabled.

- [ ] **Step 5: Merge subtask patches and deduplicate logs locally**

Remove run-status local mutation from `useRunDetailRealtime`; the global reducer owns it. For each detail patch, merge into an existing row with `{...current, ...patch}`. Preserve current server row order instead of sorting by a removed `created_at` field. Apply the event summary directly. If `refresh_tasks` is true, or a patch may enter the current filtered page without an existing row, call `fetchTasks()` once.

Use this log key:

```typescript
function runLogKey(log: RunLogEntry): string {
  return [log.timestamp, log.component ?? '', log.event ?? '', log.message].join('|')
}
```

Append only when no existing local log has the same key. `system.resync_required` calls `resyncSnapshot()`.

- [ ] **Step 6: Run all run-detail tests**

Run:

```bash
cd frontend
npm test -- src/pages/crawler/runs
```

Expected: PASS; summary loads with the task page, Store contains only run runtime, local patches update rows, and duplicate logs are suppressed.

- [ ] **Step 7: Commit run-detail frontend changes**

```bash
git add frontend/src/api/crawler/crawlerRun frontend/src/pages/crawler/runs
git commit -m "refactor: keep run detail realtime state local"
```

---

### Task 9: Remove Dead Contracts, Document Ownership, And Verify End To End

**Files:**
- Modify: `frontend/README.md:110-145`
- Modify: remaining tests/imports found by the exact searches below
- Verify: all files changed by Tasks 1-8

**Interfaces:**
- Removes all obsolete API functions, query keys, response fields, Store actions, event names, and backend routes listed in the approved design.
- Documents the final REST/EventSource/Store/page-local ownership model.

- [ ] **Step 1: Search for obsolete contract references**

Run:

```bash
rg -n "getCrawlTaskCount|getCrawlTaskStats|getCrawlTaskRuntimeStatuses|getCrawlerRunCount|getCrawlerQueueStatus|getCrawlerRunTaskSummary|crawler\.run\.updated|crawler\.queue\.updated|detailsByRunId|logsByRunId|summaryByRunId|runsById|/tasks/count|/tasks/stats|/tasks/statuses|/runs/count|/runs/queue-status|tasks/summary" frontend/src backend/app backend/tests
```

Expected: only intentional removed-route assertions in backend tests remain. Any production-code or stale fixture match must be deleted or renamed to the new contracts before proceeding.

- [ ] **Step 2: Update frontend documentation**

Replace the API/realtime paragraphs in `frontend/README.md` with explicit ownership text:

```markdown
- `crawler/crawlTask/`: task CRUD, one paginated static task-list API, and run submission actions.
- `crawler/crawlerRun/`: one paginated run-list API, run detail/log/subtask APIs, and stop/restart/retry actions.

The authenticated application layout owns one EventSource connection for the
whole login session. Every realtime event first passes through the global
event reducer. `useCrawlerRuntimeStore` stores only connection metadata, task
runtime snapshots/statistics, and run runtime overlays. TanStack Query owns
static task/run data; run-detail subtask rows, summaries, and logs remain local
to the run-detail page.
```

- [ ] **Step 3: Run backend focused suites**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_crawler_tasks_api.py \
  backend/tests/test_crawl_tasks_api.py \
  backend/tests/test_crawler_runs_api.py \
  backend/tests/test_crawler_realtime_events.py \
  backend/tests/test_realtime_events.py \
  backend/tests/test_crawler_runtime_redis.py \
  backend/tests/test_dashboard_overview.py -q
```

Expected: PASS with no failed tests.

- [ ] **Step 4: Run the complete backend suite**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests -q
```

Expected: PASS. If an unrelated environment integration is unavailable, record the exact failing test and error; do not weaken assertions related to this feature.

- [ ] **Step 5: Run frontend focused suites**

Run:

```bash
cd frontend
npm test -- src/realtime src/stores src/pages/crawler src/pages/storage/tasks src/pages/content/movies
```

Expected: PASS with one global connection lifecycle and no removed API mocks.

- [ ] **Step 6: Run the complete frontend suite and build**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected: all Vitest tests pass and Vite/TypeScript production build completes successfully.

- [ ] **Step 7: Inspect the final diff and verify no unrelated files are staged**

Run:

```bash
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors. Existing user-owned theme-transition changes and `.playwright-cli/` remain untouched and unstaged unless the user independently changed their status.

- [ ] **Step 8: Commit cleanup and documentation**

```bash
git add frontend/README.md
git diff --cached --name-only
git commit -m "docs: document crawler realtime ownership"
```

Before committing, inspect `git diff --cached --name-only`; it must contain only
`frontend/README.md`. If the obsolete-reference search required a source cleanup,
stage that exact file path explicitly after reviewing its diff. Never use a broad
`git add frontend/src` while unrelated theme-transition changes are present.

---

## Completion Check

Before declaring the implementation complete, verify all of the following from browser network logs or page tests:

- Opening `/crawler/tasks` issues one task-list request and no task count/stats/status request.
- Opening `/crawler/runs` issues one run-list request and no run count/queue request.
- Opening `/crawler/runs/{id}` does not request `/tasks/summary`.
- Navigating away from crawler pages does not close the global EventSource.
- A task/run status event received on another authenticated page updates Store state.
- Known task/run status changes do not refetch static lists.
- Subtask changes update the open run detail without entering Zustand.
- Reconnect and `system.resync_required` restore task snapshots and refresh only the visible detail/list data needed for correctness.
