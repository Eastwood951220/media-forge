# EventSource Realtime Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable EventSource/SSE realtime event channel and use it to replace crawler run detail polling.

**Architecture:** Backend adds a `realtime` module with a process-local user-scoped event bus, canonical event schema, SSE formatting, and `/api/events/stream?token=<jwt>`. Crawler runtime publishes run/detail/log/queue events through the bus. Frontend adds a reusable EventSource client and local subscription API, then `RunDetailPage` keeps REST snapshot loading but consumes realtime events instead of timer polling.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pytest, React 19, TypeScript 6, Ant Design 6, Vitest 3, React Testing Library, browser EventSource.

---

## File Structure

- Create `backend/app/modules/realtime/__init__.py`: realtime package marker.
- Create `backend/app/modules/realtime/schemas.py`: canonical `RealtimeEvent` Pydantic model and event factory.
- Create `backend/app/modules/realtime/bus.py`: process-local user-scoped queue bus with bounded queues and resync handling.
- Create `backend/app/modules/realtime/sse.py`: SSE wire-format serialization helpers.
- Create `backend/app/modules/realtime/router.py`: `/api/events/stream?token=...` endpoint and token auth for EventSource.
- Modify `backend/app/main.py`: register realtime router.
- Create `backend/tests/test_realtime_events.py`: backend event bus, SSE formatting, and stream auth tests.
- Modify `backend/app/modules/crawler/runtime/service.py`: publish crawler run, detail task, log, and queue events.
- Modify `backend/app/modules/crawler/tasks/router.py`: publish queue/run event when a run is created.
- Modify `backend/app/modules/crawler/runs/router.py`: publish queue/run event when stopping or restarting.
- Create `backend/tests/test_crawler_realtime_events.py`: crawler event publishing tests.
- Create `frontend/src/realtime/types.ts`: shared realtime event and crawler payload types.
- Create `frontend/src/realtime/eventSourceClient.ts`: singleton EventSource wrapper and local subscription API.
- Create `frontend/tests/realtime-event-source-client.test.ts`: EventSource client tests.
- Modify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`: remove polling loops and subscribe to realtime events.
- Create or modify `frontend/tests/run-detail-realtime.ui.test.tsx`: verify run detail applies realtime events and does not use intervals.

---

### Task 1: Backend Realtime Event Foundation

**Files:**
- Create: `backend/app/modules/realtime/__init__.py`
- Create: `backend/app/modules/realtime/schemas.py`
- Create: `backend/app/modules/realtime/bus.py`
- Create: `backend/app/modules/realtime/sse.py`
- Create: `backend/tests/test_realtime_events.py`

- [ ] **Step 1: Write failing backend foundation tests**

Create `backend/tests/test_realtime_events.py`:

```python
import json
from datetime import UTC

from backend.app.modules.realtime.bus import RealtimeEventBus
from backend.app.modules.realtime.schemas import make_realtime_event
from backend.app.modules.realtime.sse import format_sse_event


def test_make_realtime_event_fills_required_metadata() -> None:
    event = make_realtime_event(
        event="crawler.run.updated",
        scope="crawler.run",
        owner_id="user-1",
        resource_id="run-1",
        payload={"status": "running"},
    )

    assert event.event == "crawler.run.updated"
    assert event.scope == "crawler.run"
    assert event.owner_id == "user-1"
    assert event.resource_id == "run-1"
    assert event.payload == {"status": "running"}
    assert event.id
    assert event.created_at.tzinfo is not None
    assert event.created_at.utcoffset() == UTC.utcoffset(event.created_at)


def test_format_sse_event_outputs_standard_event_frame() -> None:
    event = make_realtime_event(
        event="crawler.run.updated",
        scope="crawler.run",
        owner_id="user-1",
        resource_id="run-1",
        payload={"status": "running"},
    )

    frame = format_sse_event(event)

    assert frame.startswith(f"id: {event.id}\n")
    assert "\nevent: crawler.run.updated\n" in frame
    assert frame.endswith("\n\n")
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    data = json.loads(data_line.removeprefix("data: "))
    assert data["event"] == "crawler.run.updated"
    assert data["payload"] == {"status": "running"}


def test_realtime_bus_routes_events_by_owner() -> None:
    bus = RealtimeEventBus(queue_size=10)
    user_a_queue = bus.subscribe("user-a")
    user_b_queue = bus.subscribe("user-b")

    event = make_realtime_event(
        event="crawler.run.updated",
        scope="crawler.run",
        owner_id="user-a",
        resource_id="run-1",
        payload={"status": "running"},
    )
    delivered = bus.publish(event)

    assert delivered == 1
    assert user_a_queue.get_nowait().id == event.id
    assert user_b_queue.empty()

    bus.unsubscribe("user-a", user_a_queue)
    bus.unsubscribe("user-b", user_b_queue)


def test_realtime_bus_emits_resync_when_queue_is_full() -> None:
    bus = RealtimeEventBus(queue_size=1)
    queue = bus.subscribe("user-a")

    bus.publish(make_realtime_event(event="one", scope="test", owner_id="user-a", payload={}))
    bus.publish(make_realtime_event(event="two", scope="test", owner_id="user-a", payload={}))

    event = queue.get_nowait()
    assert event.event == "system.resync_required"
    assert event.scope == "system"
    assert event.owner_id == "user-a"

    bus.unsubscribe("user-a", queue)
```

- [ ] **Step 2: Run backend foundation tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_realtime_events.py -v
```

Expected: FAIL because `backend.app.modules.realtime` does not exist.

- [ ] **Step 3: Create realtime package and event schema**

Create `backend/app/modules/realtime/__init__.py`:

```python
"""Realtime event streaming infrastructure."""
```

Create `backend/app/modules/realtime/schemas.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class RealtimeEvent(BaseModel):
    id: str
    event: str
    scope: str
    resource_id: str | None = None
    owner_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


def make_realtime_event(
    *,
    event: str,
    scope: str,
    owner_id: str,
    resource_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> RealtimeEvent:
    created_at = datetime.now(UTC)
    return RealtimeEvent(
        id=f"{created_at.strftime('%Y%m%d%H%M%S%f')}-{uuid.uuid4().hex[:8]}",
        event=event,
        scope=scope,
        resource_id=resource_id,
        owner_id=owner_id,
        payload=payload or {},
        created_at=created_at,
    )
```

- [ ] **Step 4: Create process-local event bus**

Create `backend/app/modules/realtime/bus.py`:

```python
from __future__ import annotations

from queue import Empty, Full, Queue
from threading import Lock

from backend.app.modules.realtime.schemas import RealtimeEvent, make_realtime_event


class RealtimeEventBus:
    def __init__(self, queue_size: int = 500) -> None:
        self.queue_size = queue_size
        self._lock = Lock()
        self._subscribers: dict[str, set[Queue[RealtimeEvent]]] = {}

    def subscribe(self, owner_id: str) -> Queue[RealtimeEvent]:
        queue: Queue[RealtimeEvent] = Queue(maxsize=self.queue_size)
        with self._lock:
            self._subscribers.setdefault(owner_id, set()).add(queue)
        return queue

    def unsubscribe(self, owner_id: str, queue: Queue[RealtimeEvent]) -> None:
        with self._lock:
            queues = self._subscribers.get(owner_id)
            if not queues:
                return
            queues.discard(queue)
            if not queues:
                self._subscribers.pop(owner_id, None)

    def publish(self, event: RealtimeEvent) -> int:
        with self._lock:
            queues = list(self._subscribers.get(event.owner_id, set()))

        delivered = 0
        for queue in queues:
            if self._put_or_resync(queue, event):
                delivered += 1
        return delivered

    def _put_or_resync(self, queue: Queue[RealtimeEvent], event: RealtimeEvent) -> bool:
        try:
            queue.put_nowait(event)
            return True
        except Full:
            self._clear_queue(queue)
            queue.put_nowait(
                make_realtime_event(
                    event="system.resync_required",
                    scope="system",
                    owner_id=event.owner_id,
                    resource_id=event.resource_id,
                    payload={"reason": "queue_overflow"},
                )
            )
            return True

    @staticmethod
    def _clear_queue(queue: Queue[RealtimeEvent]) -> None:
        while True:
            try:
                queue.get_nowait()
            except Empty:
                return


event_bus = RealtimeEventBus()
```

- [ ] **Step 5: Create SSE formatter**

Create `backend/app/modules/realtime/sse.py`:

```python
from __future__ import annotations

import json

from backend.app.modules.realtime.schemas import RealtimeEvent


def format_sse_event(event: RealtimeEvent) -> str:
    data = event.model_dump(mode="json")
    return (
        f"id: {event.id}\n"
        f"event: {event.event}\n"
        f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def format_sse_comment(comment: str) -> str:
    return f": {comment}\n\n"
```

- [ ] **Step 6: Run backend foundation tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/realtime backend/tests/test_realtime_events.py
git commit -m "feat: add realtime event bus foundation"
```

---

### Task 2: SSE Endpoint And Token Authentication

**Files:**
- Create: `backend/app/modules/realtime/router.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_realtime_events.py`

- [ ] **Step 1: Add failing SSE endpoint tests**

Append these imports to `backend/tests/test_realtime_events.py`:

```python
from fastapi.testclient import TestClient

from backend.app.core.security import create_access_token
```

Append these tests:

```python
def test_event_stream_rejects_missing_token(client: TestClient) -> None:
    response = client.get("/api/events/stream")

    assert response.status_code == 401


def test_event_stream_rejects_invalid_token(client: TestClient) -> None:
    response = client.get("/api/events/stream?token=bad-token")

    assert response.status_code == 401


def test_event_stream_accepts_valid_token_and_emits_connected_event(
    client: TestClient,
    admin_user,
) -> None:
    token = create_access_token(data={"sub": admin_user.username})

    with client.stream("GET", f"/api/events/stream?token={token}") as response:
        assert response.status_code == 200
        chunk = next(response.iter_text())

    assert "event: system.connected" in chunk
    assert f'"owner_id":"{admin_user.id}"' in chunk
```

- [ ] **Step 2: Run SSE endpoint tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_realtime_events.py::test_event_stream_rejects_missing_token backend/tests/test_realtime_events.py::test_event_stream_rejects_invalid_token backend/tests/test_realtime_events.py::test_event_stream_accepts_valid_token_and_emits_connected_event -v
```

Expected: FAIL because `/api/events/stream` does not exist.

- [ ] **Step 3: Create SSE router**

Create `backend/app/modules/realtime/router.py`:

```python
from __future__ import annotations

import asyncio
from queue import Empty

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_db
from backend.app.core.security import decode_access_token
from backend.app.modules.realtime.bus import event_bus
from backend.app.modules.realtime.schemas import make_realtime_event
from backend.app.modules.realtime.sse import format_sse_comment, format_sse_event
from backend.app.repositories.user import UserRepository

router = APIRouter(prefix="/api/events", tags=["realtime-events"])

KEEPALIVE_SECONDS = 20
QUEUE_POLL_SECONDS = 0.5


def authenticate_stream_user(token: str | None, db: Session):
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = UserRepository(db).get_by_username(str(username))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


@router.get("/stream")
def event_stream(
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    user = authenticate_stream_user(token, db)
    owner_id = str(user.id)

    async def stream():
        queue = event_bus.subscribe(owner_id)
        last_keepalive = asyncio.get_running_loop().time()
        try:
            yield format_sse_event(
                make_realtime_event(
                    event="system.connected",
                    scope="system",
                    owner_id=owner_id,
                    payload={"message": "connected"},
                )
            )
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

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 4: Register realtime router**

Modify `backend/app/main.py`.

Add the import near other routers:

```python
from backend.app.modules.realtime.router import router as realtime_router
```

Add router registration before `crawler_tasks_router`:

```python
app.include_router(realtime_router)
```

- [ ] **Step 5: Run SSE endpoint tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/realtime/router.py backend/app/main.py backend/tests/test_realtime_events.py
git commit -m "feat: expose realtime event stream"
```

---

### Task 3: Crawler Realtime Event Publishing

**Files:**
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Modify: `backend/app/modules/crawler/runs/router.py`
- Create: `backend/tests/test_crawler_realtime_events.py`

- [ ] **Step 1: Write failing crawler event tests**

Create `backend/tests/test_crawler_realtime_events.py`:

```python
import uuid
from datetime import datetime

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.runtime import service
from backend.app.modules.realtime.bus import event_bus
from backend.tests.conftest import TestingSessionLocal


def drain(queue):
    rows = []
    while not queue.empty():
        rows.append(queue.get_nowait())
    return rows


def test_publish_run_updated_event_for_owner(admin_user) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(name="任务A", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        created_at=datetime.now(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    queue = event_bus.subscribe(str(admin_user.id))

    service.publish_run_updated(session, run)

    events = drain(queue)
    event_bus.unsubscribe(str(admin_user.id), queue)
    session.close()

    assert [event.event for event in events] == ["crawler.run.updated"]
    assert events[0].resource_id == str(run.id)
    assert events[0].payload["status"] == "running"


def test_publish_detail_updated_event_for_owner(admin_user) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(name="任务A", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        created_at=datetime.now(),
    )
    session.add(run)
    session.flush()
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code="AAA-001",
        source_url="https://example.test/aaa",
        source_name="AAA-001",
        status="saved",
        created_at=datetime.now(),
    )
    session.add(detail)
    session.commit()
    session.refresh(run)
    session.refresh(detail)
    queue = event_bus.subscribe(str(admin_user.id))

    service.publish_run_detail_updated(session, run, [detail])

    events = drain(queue)
    event_bus.unsubscribe(str(admin_user.id), queue)
    session.close()

    assert [event.event for event in events] == ["crawler.run.detail.updated"]
    assert events[0].resource_id == str(run.id)
    assert events[0].payload["run_id"] == str(run.id)
    assert events[0].payload["tasks"][0]["status"] == "saved"


def test_publish_run_log_event_for_owner(admin_user) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(name="任务A", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        created_at=datetime.now(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    queue = event_bus.subscribe(str(admin_user.id))

    service.append_run_log_for_run(session, run, "入库成功: AAA-001", "INFO", code="AAA-001")

    events = drain(queue)
    event_bus.unsubscribe(str(admin_user.id), queue)
    session.close()

    assert [event.event for event in events] == ["crawler.run.log.appended"]
    assert events[0].resource_id == str(run.id)
    assert events[0].payload["run_id"] == str(run.id)
    assert events[0].payload["log"]["message"] == "入库成功: AAA-001"
    assert events[0].payload["log"]["context"]["code"] == "AAA-001"
```

- [ ] **Step 2: Run crawler event tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_realtime_events.py -v
```

Expected: FAIL because publishing helpers do not exist.

- [ ] **Step 3: Add publishing helpers to runtime service**

Modify `backend/app/modules/crawler/runtime/service.py`.

Add imports near the top:

```python
from backend.app.modules.crawler.runs.schemas import CrawlRunDetailTaskRead, CrawlRunRead
from backend.app.modules.realtime.bus import event_bus
from backend.app.modules.realtime.schemas import make_realtime_event
```

Add helper functions after `_append_run_log`:

```python
def _run_owner_id(db: Session, run: CrawlRun) -> str | None:
    if run.task_id is None:
        return None
    task = db.get(CrawlTask, run.task_id)
    return str(task.owner_id) if task is not None else None


def publish_run_updated(db: Session, run: CrawlRun) -> None:
    owner_id = _run_owner_id(db, run)
    if owner_id is None:
        return
    payload = CrawlRunRead.model_validate(run).model_dump(mode="json")
    payload["logs"] = []
    event_bus.publish(
        make_realtime_event(
            event="crawler.run.updated",
            scope="crawler.run",
            owner_id=owner_id,
            resource_id=str(run.id),
            payload=payload,
        )
    )


def publish_run_detail_updated(
    db: Session,
    run: CrawlRun,
    details: list[CrawlRunDetailTask],
) -> None:
    owner_id = _run_owner_id(db, run)
    if owner_id is None:
        return
    event_bus.publish(
        make_realtime_event(
            event="crawler.run.detail.updated",
            scope="crawler.run",
            owner_id=owner_id,
            resource_id=str(run.id),
            payload={
                "run_id": str(run.id),
                "tasks": [
                    CrawlRunDetailTaskRead.model_validate(detail).model_dump(mode="json")
                    for detail in details
                ],
            },
        )
    )


def publish_queue_updated(db: Session, runtime: CrawlerRuntimeState, owner_id: str | None = None) -> None:
    if owner_id is None:
        return
    event_bus.publish(
        make_realtime_event(
            event="crawler.queue.updated",
            scope="crawler.queue",
            owner_id=owner_id,
            payload=runtime.queue_status(),
        )
    )


def append_run_log_for_run(
    db: Session,
    run: CrawlRun,
    message: str,
    level: str = "INFO",
    **context: Any,
) -> None:
    from backend.app.modules.crawler.runs.logs import append_run_log, build_run_log

    entry = build_run_log(level, message, **context)
    append_run_log(str(run.id), entry)
    owner_id = _run_owner_id(db, run)
    if owner_id is None:
        return
    event_bus.publish(
        make_realtime_event(
            event="crawler.run.log.appended",
            scope="crawler.run",
            owner_id=owner_id,
            resource_id=str(run.id),
            payload={"run_id": str(run.id), "log": entry},
        )
    )
```

- [ ] **Step 4: Replace runtime log calls with event-aware helper**

In `backend/app/modules/crawler/runtime/service.py`, replace calls like:

```python
_append_run_log(str(run.id), "message", "INFO")
```

with:

```python
append_run_log_for_run(db, run, "message", "INFO")
```

When the call passes context, preserve it:

```python
append_run_log_for_run(db, run, f"入库成功: {code}", "INFO", code=code, movie_id=str(movie_id))
```

Update these concrete call patterns:

```python
append_run_log_for_run(db, run, f"已存在影片追加任务ID: {item.get('code')} -> {task.id}", "INFO", code=item.get("code"))
append_run_log_for_run(db, run, f"创建子任务 {len(items)} 条，跳过 {skipped_count} 条")
append_run_log_for_run(db, run, f"入库成功: {code}", "INFO", code=code, movie_id=str(movie_id))
append_run_log_for_run(db, run, f"入库失败: {code}: {exc}", "ERROR", code=code)
append_run_log_for_run(db, run, f"爬取失败: {task_info.get('code') or task_info.get('url')}: {error}", "ERROR")
append_run_log_for_run(db, run, f"跳过已存在影片并追加任务ID: {code}", "INFO", code=code)
append_run_log_for_run(db, run, message, level)
append_run_log_for_run(db, run, f"列表阶段发现已存在影片 {len(existing_codes)} 条", "INFO")
append_run_log_for_run(db, run, f"详情阶段跳过已存在影片: {code}", "INFO", code=code)
append_run_log_for_run(db, run, f"任务完成: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}, 跳过={skipped_count}", "INFO")
append_run_log_for_run(db, run, "MovieService 不可用，使用空结果完成运行", "WARNING")
```

Leave the old `_append_run_log` function in place only if other modules still import it. If no references remain, delete `_append_run_log`.

- [ ] **Step 5: Publish run and detail state changes**

In `process_run`, after committing `run.status = "running"`:

```python
        publish_run_updated(db, run)
```

In the exception handler after committing failed status:

```python
            publish_run_updated(db, run)
```

At the end of `_execute_run`, after the final `db.commit()`:

```python
    publish_run_updated(db, run)
```

Inside callbacks where detail status is changed and committed, publish affected details:

```python
        publish_run_detail_updated(db, run, details)
```

Use the exact detail variable available at each point:

```python
        publish_run_detail_updated(db, run, [detail])
```

for saved/save_failed/crawl_failed/skipped paths.

- [ ] **Step 6: Publish run and queue events from REST actions**

Modify `backend/app/modules/crawler/tasks/router.py`.

After `run = CrawlerRunService(...).create_run(...)` and before return:

```python
    from backend.app.modules.crawler.runtime.service import publish_queue_updated, publish_run_updated

    publish_run_updated(db, run)
    publish_queue_updated(db, get_runtime_state(), owner_id=str(current_user.id))
```

Modify `backend/app/modules/crawler/runs/router.py`.

After stop succeeds:

```python
    from backend.app.modules.crawler.runtime.service import publish_queue_updated, publish_run_updated

    publish_run_updated(db, run)
    publish_queue_updated(db, get_runtime_state(), owner_id=str(_current_user.id))
```

After restart succeeds:

```python
    from backend.app.modules.crawler.runtime.service import publish_queue_updated, publish_run_updated

    publish_run_updated(db, run)
    publish_queue_updated(db, get_runtime_state(), owner_id=str(_current_user.id))
```

- [ ] **Step 7: Run crawler realtime tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_realtime_events.py backend/tests/test_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 8: Run existing crawler worker tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py backend/tests/test_crawler_runs_api.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/crawler/runtime/service.py backend/app/modules/crawler/tasks/router.py backend/app/modules/crawler/runs/router.py backend/tests/test_crawler_realtime_events.py
git commit -m "feat: publish crawler realtime events"
```

---

### Task 4: Frontend EventSource Client

**Files:**
- Create: `frontend/src/realtime/types.ts`
- Create: `frontend/src/realtime/eventSourceClient.ts`
- Create: `frontend/tests/realtime-event-source-client.test.ts`

- [ ] **Step 1: Write failing EventSource client tests**

Create `frontend/tests/realtime-event-source-client.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { connectRealtime, disconnectRealtime, subscribeRealtime } from '../src/realtime/eventSourceClient'
import { setToken, removeToken } from '../src/utils/auth'

type ListenerMap = Record<string, Array<(event: MessageEvent) => void>>

class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  listeners: ListenerMap = {}
  close = vi.fn()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(eventName: string, handler: (event: MessageEvent) => void) {
    this.listeners[eventName] = [...(this.listeners[eventName] ?? []), handler]
  }

  removeEventListener(eventName: string, handler: (event: MessageEvent) => void) {
    this.listeners[eventName] = (this.listeners[eventName] ?? []).filter((item) => item !== handler)
  }

  emit(eventName: string, data: unknown) {
    for (const handler of this.listeners[eventName] ?? []) {
      handler(new MessageEvent(eventName, { data: JSON.stringify(data) }))
    }
  }
}

describe('eventSourceClient', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
    setToken('token with space')
  })

  afterEach(() => {
    disconnectRealtime()
    removeToken()
    vi.unstubAllGlobals()
  })

  it('connects with encoded query token', () => {
    connectRealtime()

    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.instances[0].url).toBe('/api/events/stream?token=token%20with%20space')
  })

  it('does not connect without a token', () => {
    removeToken()

    connectRealtime()

    expect(FakeEventSource.instances).toHaveLength(0)
  })

  it('delivers parsed realtime events to subscribers', () => {
    const handler = vi.fn()
    subscribeRealtime('crawler.run.updated', handler)
    connectRealtime()

    FakeEventSource.instances[0].emit('crawler.run.updated', {
      id: 'event-1',
      event: 'crawler.run.updated',
      scope: 'crawler.run',
      resource_id: 'run-1',
      owner_id: 'user-1',
      payload: { status: 'running' },
      created_at: '2026-07-03T00:00:00Z',
    })

    expect(handler).toHaveBeenCalledWith(expect.objectContaining({
      event: 'crawler.run.updated',
      payload: { status: 'running' },
    }))
  })

  it('unsubscribes handlers', () => {
    const handler = vi.fn()
    const unsubscribe = subscribeRealtime('crawler.run.updated', handler)
    connectRealtime()

    unsubscribe()
    FakeEventSource.instances[0].emit('crawler.run.updated', {
      id: 'event-1',
      event: 'crawler.run.updated',
      scope: 'crawler.run',
      resource_id: 'run-1',
      owner_id: 'user-1',
      payload: { status: 'running' },
      created_at: '2026-07-03T00:00:00Z',
    })

    expect(handler).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run EventSource client tests and verify they fail**

Run:

```bash
cd frontend
npm test -- realtime-event-source-client.test.ts
```

Expected: FAIL because `frontend/src/realtime/eventSourceClient.ts` does not exist.

- [ ] **Step 3: Create realtime types**

Create `frontend/src/realtime/types.ts`:

```ts
import type { CrawlRun, CrawlRunDetailTask, RunLogEntry } from '@/api/crawlerRun/types'

export type RealtimeEvent<TPayload = Record<string, unknown>> = {
  id: string
  event: string
  scope: string
  resource_id: string | null
  owner_id: string
  payload: TPayload
  created_at: string
}

export type CrawlerRunUpdatedPayload = CrawlRun

export type CrawlerRunDetailUpdatedPayload = {
  run_id: string
  tasks: CrawlRunDetailTask[]
}

export type CrawlerRunLogAppendedPayload = {
  run_id: string
  log: RunLogEntry
}

export type RealtimeEventName =
  | 'system.connected'
  | 'system.resync_required'
  | 'crawler.run.updated'
  | 'crawler.run.detail.updated'
  | 'crawler.run.log.appended'
  | 'crawler.queue.updated'

export type RealtimeHandler<TPayload = Record<string, unknown>> = (
  event: RealtimeEvent<TPayload>,
) => void
```

- [ ] **Step 4: Create EventSource client**

Create `frontend/src/realtime/eventSourceClient.ts`:

```ts
import { getToken } from '@/utils/auth'
import type { RealtimeEvent, RealtimeEventName, RealtimeHandler } from './types'

const EVENT_NAMES: RealtimeEventName[] = [
  'system.connected',
  'system.resync_required',
  'crawler.run.updated',
  'crawler.run.detail.updated',
  'crawler.run.log.appended',
  'crawler.queue.updated',
]

type AnyHandler = RealtimeHandler<Record<string, unknown>>

let source: EventSource | null = null
const handlers = new Map<string, Set<AnyHandler>>()

function eventStreamUrl(token: string) {
  return `/api/events/stream?token=${encodeURIComponent(token)}`
}

function dispatch(eventName: string, message: MessageEvent) {
  let parsed: RealtimeEvent<Record<string, unknown>>
  try {
    parsed = JSON.parse(String(message.data)) as RealtimeEvent<Record<string, unknown>>
  } catch {
    emitLocalResync('malformed_event')
    return
  }

  for (const handler of handlers.get(eventName) ?? []) {
    handler(parsed)
  }
}

function emitLocalResync(reason: string) {
  const event: RealtimeEvent = {
    id: `local-${Date.now()}`,
    event: 'system.resync_required',
    scope: 'system',
    resource_id: null,
    owner_id: '',
    payload: { reason },
    created_at: new Date().toISOString(),
  }
  for (const handler of handlers.get('system.resync_required') ?? []) {
    handler(event)
  }
}

export function connectRealtime() {
  if (source) return source
  const token = getToken()
  if (!token) return null

  source = new EventSource(eventStreamUrl(token))
  for (const eventName of EVENT_NAMES) {
    source.addEventListener(eventName, (message) => dispatch(eventName, message))
  }
  source.onerror = () => {
    emitLocalResync('connection_error')
  }
  return source
}

export function disconnectRealtime() {
  source?.close()
  source = null
  handlers.clear()
}

export function subscribeRealtime<TPayload = Record<string, unknown>>(
  eventName: RealtimeEventName,
  handler: RealtimeHandler<TPayload>,
) {
  const typedHandler = handler as AnyHandler
  const nextHandlers = handlers.get(eventName) ?? new Set<AnyHandler>()
  nextHandlers.add(typedHandler)
  handlers.set(eventName, nextHandlers)

  return () => {
    const currentHandlers = handlers.get(eventName)
    if (!currentHandlers) return
    currentHandlers.delete(typedHandler)
    if (currentHandlers.size === 0) {
      handlers.delete(eventName)
    }
  }
}
```

- [ ] **Step 5: Run EventSource client tests and verify they pass**

Run:

```bash
cd frontend
npm test -- realtime-event-source-client.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/realtime frontend/tests/realtime-event-source-client.test.ts
git commit -m "feat: add frontend realtime eventsource client"
```

---

### Task 5: Run Detail Page Realtime Integration

**Files:**
- Modify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- Create: `frontend/tests/run-detail-realtime.ui.test.tsx`

- [ ] **Step 1: Write failing run detail realtime tests**

Create `frontend/tests/run-detail-realtime.ui.test.tsx`:

```tsx
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RunDetailPage from '../src/pages/crawler/runs/RunDetailPage'
import { getCrawlerRun, getCrawlerRunTasks } from '../src/api/crawlerRun'
import type { RealtimeEventName, RealtimeHandler } from '../src/realtime/types'

const realtimeHandlers = new Map<string, Set<RealtimeHandler>>()

vi.mock('../src/api/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunTasks: vi.fn(),
}))

vi.mock('../src/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(() => null),
  subscribeRealtime: vi.fn((eventName: RealtimeEventName, handler: RealtimeHandler) => {
    const handlers = realtimeHandlers.get(eventName) ?? new Set()
    handlers.add(handler)
    realtimeHandlers.set(eventName, handlers)
    return () => handlers.delete(handler)
  }),
}))

function emit(eventName: RealtimeEventName, payload: Record<string, unknown>, resourceId = 'run-1') {
  for (const handler of realtimeHandlers.get(eventName) ?? []) {
    handler({
      id: `event-${Date.now()}`,
      event: eventName,
      scope: eventName.startsWith('crawler') ? 'crawler.run' : 'system',
      resource_id: resourceId,
      owner_id: 'user-1',
      payload,
      created_at: '2026-07-03T00:00:00Z',
    })
  }
}

function renderPage(initialPath = '/crawler/runs/run-1') {
  const rootRoute = createRootRoute({ component: () => <RunDetailPage /> })
  const detailRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/runs/$id',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([detailRoute]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })

  return render(<RouterProvider router={router} />)
}

describe('RunDetailPage realtime events', () => {
  beforeEach(() => {
    realtimeHandlers.clear()
    vi.useFakeTimers()
    vi.spyOn(window, 'setInterval')
    vi.mocked(getCrawlerRun).mockResolvedValue({
      id: 'run-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'running',
      crawl_mode: 'incremental',
      queued_at: null,
      started_at: null,
      finished_at: null,
      result: null,
      error: null,
      resumed_from: null,
      created_at: '2026-07-03T00:00:00Z',
      updated_at: null,
      logs: [],
    })
    vi.mocked(getCrawlerRunTasks).mockResolvedValue({
      rows: [],
      total: 0,
    })
  })

  it('does not create polling intervals', async () => {
    renderPage()

    expect(await screen.findByText('运行详情 - 任务A')).toBeInTheDocument()
    expect(window.setInterval).not.toHaveBeenCalled()
  })

  it('updates run status from crawler.run.updated events', async () => {
    renderPage()

    expect(await screen.findByText('运行中')).toBeInTheDocument()
    emit('crawler.run.updated', {
      id: 'run-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'completed',
      crawl_mode: 'incremental',
      queued_at: null,
      started_at: null,
      finished_at: '2026-07-03T00:10:00Z',
      result: null,
      error: null,
      resumed_from: null,
      created_at: '2026-07-03T00:00:00Z',
      updated_at: null,
      logs: [],
    })

    expect(await screen.findByText('已完成')).toBeInTheDocument()
  })

  it('upserts detail rows from crawler.run.detail.updated events', async () => {
    renderPage()

    emit('crawler.run.detail.updated', {
      run_id: 'run-1',
      tasks: [{
        id: 'detail-1',
        run_id: 'run-1',
        task_name: '任务A',
        code: 'AAA-001',
        source_url: 'https://example.test/aaa',
        source_name: 'AAA-001',
        status: 'saved',
        error: null,
        item_data: null,
        created_at: '2026-07-03T00:00:00Z',
        crawled_at: '2026-07-03T00:01:00Z',
        saved_at: '2026-07-03T00:02:00Z',
      }],
    })

    expect(await screen.findByText('AAA-001')).toBeInTheDocument()
    expect(await screen.findByText('已保存')).toBeInTheDocument()
  })

  it('appends logs from crawler.run.log.appended events', async () => {
    renderPage()

    emit('crawler.run.log.appended', {
      run_id: 'run-1',
      log: {
        timestamp: '2026-07-03T00:03:00Z',
        level: 'INFO',
        component: 'crawler.run',
        event: 'run_log',
        message: '入库成功: AAA-001',
        context: { code: 'AAA-001' },
      },
    })

    expect(await screen.findByText('入库成功: AAA-001')).toBeInTheDocument()
  })

  it('resyncs snapshots when system resync is required', async () => {
    renderPage()
    await screen.findByText('运行详情 - 任务A')

    emit('system.resync_required', { reason: 'connection_error' }, null)

    await waitFor(() => {
      expect(getCrawlerRun).toHaveBeenCalledTimes(2)
      expect(getCrawlerRunTasks).toHaveBeenCalledTimes(2)
    })
  })
})
```

- [ ] **Step 2: Run run detail realtime tests and verify they fail**

Run:

```bash
cd frontend
npm test -- run-detail-realtime.ui.test.tsx
```

Expected: FAIL because `RunDetailPage` still uses polling intervals and does not subscribe to realtime events.

- [ ] **Step 3: Refactor RunDetailPage fetch helpers**

Modify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`.

Add imports:

```ts
import { useCallback, useEffect, useState } from 'react'
import { connectRealtime, subscribeRealtime } from '@/realtime/eventSourceClient'
import type {
  CrawlerRunDetailUpdatedPayload,
  CrawlerRunLogAppendedPayload,
  CrawlerRunUpdatedPayload,
} from '@/realtime/types'
```

Replace the existing `import { useEffect, useState } from 'react'`.

Add helper inside `RunDetailPage` after state declarations:

```ts
  const fetchRun = useCallback(async () => {
    if (!id) return
    const data = await getCrawlerRun(id)
    setRun(data)
  }, [id])

  const fetchTasks = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const data = await getCrawlerRunTasks(id, {
        limit: 200,
        status: statusFilter,
        keyword: keyword || undefined,
      })
      setTasks(data.rows)
    } finally {
      setLoading(false)
    }
  }, [id, keyword, statusFilter])

  const resyncSnapshot = useCallback(() => {
    void fetchRun()
    void fetchTasks()
  }, [fetchRun, fetchTasks])
```

- [ ] **Step 4: Replace initial fetch effects**

Replace the current run-fetch effect with:

```ts
  useEffect(() => {
    void fetchRun()
  }, [fetchRun])
```

Replace the current task-fetch effect with:

```ts
  useEffect(() => {
    void fetchTasks()
  }, [fetchTasks])
```

Delete both effects that create `window.setInterval`.

- [ ] **Step 5: Add realtime subscription effects**

Add this effect after snapshot fetch effects:

```ts
  useEffect(() => {
    if (!id) return
    connectRealtime()

    const unsubscribeRun = subscribeRealtime<CrawlerRunUpdatedPayload>(
      'crawler.run.updated',
      (event) => {
        if (event.resource_id !== id) return
        setRun(event.payload)
      },
    )

    const unsubscribeDetails = subscribeRealtime<CrawlerRunDetailUpdatedPayload>(
      'crawler.run.detail.updated',
      (event) => {
        if (event.resource_id !== id || event.payload.run_id !== id) return
        setTasks((currentTasks) => {
          const byId = new Map(currentTasks.map((task) => [task.id, task]))
          for (const task of event.payload.tasks) {
            const matchesStatus = !statusFilter || task.status === statusFilter
            const normalizedKeyword = keyword.trim().toLowerCase()
            const matchesKeyword = !normalizedKeyword
              || (task.code ?? '').toLowerCase().includes(normalizedKeyword)
              || task.source_name.toLowerCase().includes(normalizedKeyword)
            if (matchesStatus && matchesKeyword) {
              byId.set(task.id, task)
            } else {
              byId.delete(task.id)
            }
          }
          return Array.from(byId.values()).sort((a, b) => (
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          ))
        })
      },
    )

    const unsubscribeLogs = subscribeRealtime<CrawlerRunLogAppendedPayload>(
      'crawler.run.log.appended',
      (event) => {
        if (event.resource_id !== id || event.payload.run_id !== id) return
        setRun((currentRun) => {
          if (!currentRun) return currentRun
          return {
            ...currentRun,
            logs: [...(currentRun.logs ?? []), event.payload.log],
          }
        })
      },
    )

    const unsubscribeResync = subscribeRealtime(
      'system.resync_required',
      () => {
        resyncSnapshot()
      },
    )

    return () => {
      unsubscribeRun()
      unsubscribeDetails()
      unsubscribeLogs()
      unsubscribeResync()
    }
  }, [id, keyword, resyncSnapshot, statusFilter])
```

- [ ] **Step 6: Run run detail realtime tests and verify they pass**

Run:

```bash
cd frontend
npm test -- run-detail-realtime.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Run existing run detail related tests**

Run:

```bash
cd frontend
npm test -- detail-singleton-state.ui.test.tsx
```

Expected: PASS if the file exists. If Vitest reports no matching test file, record that in the verification notes and continue.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/crawler/runs/RunDetailPage.tsx frontend/tests/run-detail-realtime.ui.test.tsx
git commit -m "feat: update run detail via realtime events"
```

---

### Task 6: Full Verification

**Files:**
- No source changes.

- [ ] **Step 1: Run backend realtime tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_realtime_events.py backend/tests/test_crawler_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 2: Run backend crawler tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py backend/tests/test_crawler_runs_api.py backend/tests/test_crawl_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 3: Run frontend realtime tests**

Run:

```bash
cd frontend
npm test -- realtime-event-source-client.test.ts run-detail-realtime.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 5: Manual realtime verification**

Run backend:

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

Run frontend:

```bash
cd frontend
npm run dev
```

Manual flow:

1. Log in.
2. Open `/crawler/tasks`.
3. Start a crawler task.
4. Open the run detail page.
5. Confirm browser devtools Network contains one `/api/events/stream?token=...` request.
6. Confirm the run detail page updates status, detail rows, and logs without repeated `/api/crawler/runs/{id}` or `/api/crawler/runs/{id}/tasks` requests every 3 seconds.
7. Stop or complete the run and confirm the page updates from realtime events.

Expected:

- One EventSource connection per browser tab.
- Initial REST snapshot requests still happen.
- No timer polling after the initial snapshot.
- Reconnecting the EventSource triggers a REST resync.

---

## Self-Review

- Spec coverage:
  - Generic SSE endpoint and query-token authentication are covered in Task 2.
  - User-scoped event bus, queue overflow, and `system.resync_required` are covered in Task 1.
  - Crawler run/detail/log/queue publishing is covered in Task 3.
  - Frontend reusable EventSource client is covered in Task 4.
  - `RunDetailPage` polling removal and realtime updates are covered in Task 5.
  - Future cloud storage fit is preserved by generic event schema and reserved event naming, without implementing cloud storage in this phase.
- Red-flag scan:
  - The plan contains concrete file paths, commands, expected results, and source/test snippets.
- Type consistency:
  - Backend `RealtimeEvent.event` names match frontend `RealtimeEventName`.
  - Backend crawler payloads serialize through existing run/detail schemas, matching frontend `CrawlRun` and `CrawlRunDetailTask`.
  - `system.resync_required` is emitted by backend queue overflow and also locally by frontend connection/parse failures.
