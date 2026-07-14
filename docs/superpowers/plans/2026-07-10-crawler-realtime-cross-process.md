# Crawler Realtime Cross-Process Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the crawler detail page on EventSource while making backend realtime event delivery work across API and crawler worker processes.

**Architecture:** Keep `RealtimeEventBus` as the API process local SSE fan-out. Add a Redis-backed cross-process transport behind that bus: publishers send JSON envelopes to owner-scoped Redis Pub/Sub channels, and the API process subscribes to those channels for connected owners and forwards events into local queues. Frontend code remains EventSource-based and uses REST snapshots as the authority when detail summaries, terminal states, or resync signals require it.

**Tech Stack:** Python 3.12+, FastAPI 0.115, Redis 5 Python client, SQLAlchemy 2.0, pytest, React 19, TypeScript 6, Vitest 3, React Testing Library.

## Global Constraints

- Project scope remains the Media Forge refactor and optimization of `/Users/eastwood/Code/PycharmProjects/jav-scrapling`.
- Do not replace EventSource with WebSocket.
- Do not change crawler scheduling, scraping behavior, database schema, or frontend routes.
- Existing event names stay unchanged: `crawler.run.updated`, `crawler.run.detail.updated`, `crawler.run.log.appended`, and `system.resync_required`.
- Database snapshots remain authoritative for run header, task rows, task summary counts, and logs.
- Redis dependency stays `redis>=5.0.0,<6.0.0` from `backend/requirements.txt`; add no new backend dependency.

---

## File Structure

- Modify `backend/app/modules/realtime/bus.py`
  - Keep local per-owner queue fan-out.
  - Add Redis publisher/listener integration through an injectable Redis client factory.
  - Keep existing `event_bus.publish(event)`, `subscribe(owner_id)`, and `unsubscribe(owner_id, queue)` call sites compatible.
- Modify `backend/app/modules/realtime/router.py`
  - Enable Redis transport for the API SSE process before subscribing a user stream.
  - Ensure unsubscribe decreases owner listener references.
- Modify `backend/app/main.py`
  - Enable Redis-backed realtime publishing during backend startup after runtime config is loaded.
  - Close realtime Redis resources on shutdown.
- Modify `backend/app/modules/realtime/schemas.py`
  - Add helpers for serializing/deserializing realtime events if needed by the Redis transport.
- Modify `backend/tests/test_realtime_events.py`
  - Keep local bus tests.
  - Add cross-bus Redis pub/sub tests using an in-memory fake Redis broker.
- Modify `backend/tests/test_crawler_realtime_events.py`
  - Add coverage that crawler event helpers still publish existing event shapes through the bus.
- Modify `frontend/tests/run-detail-realtime.ui.test.tsx`
  - Add coverage that terminal run updates refresh the run header, tasks, and logs snapshots.
- No frontend production file changes are expected unless a test exposes missing snapshot refresh behavior.

### Task 1: Add Redis-Capable Realtime Bus Without Changing Local Semantics

**Files:**
- Modify: `backend/app/modules/realtime/bus.py`
- Modify: `backend/app/modules/realtime/schemas.py`
- Modify: `backend/tests/test_realtime_events.py`

**Interfaces:**
- Consumes: `RealtimeEvent` from `backend.app.modules.realtime.schemas`.
- Produces:
  - `RealtimeEventBus(queue_size: int = 500, redis_client_factory: Callable[[], Any] | None = None)`
  - `RealtimeEventBus.configure_redis(redis_client_factory: Callable[[], Any]) -> None`
  - `RealtimeEventBus.close() -> None`
  - Existing `subscribe`, `unsubscribe`, and `publish` signatures remain compatible.

- [ ] **Step 1: Write failing Redis bus tests**

Append this fake Redis broker and tests to `backend/tests/test_realtime_events.py`:

```python
import json
import queue
import threading
import time
from collections import defaultdict
```

```python
class FakeRedisBroker:
    def __init__(self) -> None:
        self.channels: dict[str, list[queue.Queue[dict]]] = defaultdict(list)
        self.lock = threading.Lock()

    def publish(self, channel: str, message: str) -> int:
        with self.lock:
            queues = list(self.channels.get(channel, []))
        for subscriber_queue in queues:
            subscriber_queue.put({"type": "message", "channel": channel, "data": message})
        return len(queues)

    def pubsub(self):
        return FakePubSub(self)


class FakePubSub:
    def __init__(self, broker: FakeRedisBroker) -> None:
        self.broker = broker
        self.messages: queue.Queue[dict] = queue.Queue()
        self.subscribed_channels: list[str] = []
        self.closed = False

    def subscribe(self, channel: str) -> None:
        self.subscribed_channels.append(channel)
        with self.broker.lock:
            self.broker.channels[channel].append(self.messages)

    def listen(self):
        while not self.closed:
            try:
                yield self.messages.get(timeout=0.05)
            except queue.Empty:
                continue

    def close(self) -> None:
        self.closed = True
        with self.broker.lock:
            for channel in self.subscribed_channels:
                self.broker.channels[channel] = [
                    item for item in self.broker.channels[channel] if item is not self.messages
                ]
```

```python
def wait_for_queue_item(target_queue, timeout: float = 1.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return target_queue.get_nowait()
        except queue.Empty:
            time.sleep(0.01)
    raise AssertionError("queue did not receive an event")
```

```python
def test_realtime_bus_delivers_events_between_process_local_bus_instances() -> None:
    broker = FakeRedisBroker()
    api_bus = RealtimeEventBus(queue_size=10, redis_client_factory=lambda: broker)
    worker_bus = RealtimeEventBus(queue_size=10, redis_client_factory=lambda: broker)
    api_queue = api_bus.subscribe("user-a")

    event = make_realtime_event(
        event="crawler.run.updated",
        scope="crawler.run",
        owner_id="user-a",
        resource_id="run-1",
        payload={"status": "running"},
    )
    worker_bus.publish(event)

    received = wait_for_queue_item(api_queue)
    assert received.id == event.id
    assert received.event == "crawler.run.updated"
    assert received.payload == {"status": "running"}

    api_bus.unsubscribe("user-a", api_queue)
    api_bus.close()
    worker_bus.close()
```

```python
def test_realtime_bus_redis_transport_keeps_owner_scope() -> None:
    broker = FakeRedisBroker()
    api_bus = RealtimeEventBus(queue_size=10, redis_client_factory=lambda: broker)
    worker_bus = RealtimeEventBus(queue_size=10, redis_client_factory=lambda: broker)
    user_a_queue = api_bus.subscribe("user-a")
    user_b_queue = api_bus.subscribe("user-b")

    worker_bus.publish(make_realtime_event(
        event="crawler.run.updated",
        scope="crawler.run",
        owner_id="user-a",
        resource_id="run-1",
        payload={"status": "running"},
    ))

    assert wait_for_queue_item(user_a_queue).owner_id == "user-a"
    assert user_b_queue.empty()

    api_bus.unsubscribe("user-a", user_a_queue)
    api_bus.unsubscribe("user-b", user_b_queue)
    api_bus.close()
    worker_bus.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_realtime_events.py -v
```

Expected: FAIL because `RealtimeEventBus` does not accept `redis_client_factory`.

- [ ] **Step 3: Add event serialization helpers**

In `backend/app/modules/realtime/schemas.py`, add:

```python
def realtime_event_to_json(event: RealtimeEvent) -> str:
    return event.model_dump_json()


def realtime_event_from_json(data: str | bytes) -> RealtimeEvent:
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return RealtimeEvent.model_validate_json(data)
```

- [ ] **Step 4: Implement Redis-capable bus**

Replace `backend/app/modules/realtime/bus.py` with this implementation:

```python
from __future__ import annotations

import json
import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Full, Queue
from typing import Any

from backend.app.modules.realtime.schemas import (
    RealtimeEvent,
    make_realtime_event,
    realtime_event_from_json,
    realtime_event_to_json,
)

logger = logging.getLogger(__name__)


@dataclass
class _OwnerListener:
    thread: threading.Thread
    stop_event: threading.Event
    ref_count: int = 0


class RealtimeEventBus:
    CHANNEL_PREFIX = "media-forge:realtime:owner:"

    def __init__(
        self,
        queue_size: int = 500,
        redis_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.queue_size = queue_size
        self._origin_id = uuid.uuid4().hex
        self._redis_client_factory = redis_client_factory
        self._lock = threading.RLock()
        self._subscribers: dict[str, set[Queue[RealtimeEvent]]] = {}
        self._listeners: dict[str, _OwnerListener] = {}

    def configure_redis(self, redis_client_factory: Callable[[], Any]) -> None:
        with self._lock:
            self._redis_client_factory = redis_client_factory

    def subscribe(self, owner_id: str) -> Queue[RealtimeEvent]:
        queue: Queue[RealtimeEvent] = Queue(maxsize=self.queue_size)
        with self._lock:
            self._subscribers.setdefault(owner_id, set()).add(queue)
            self._ensure_owner_listener_locked(owner_id)
        return queue

    def unsubscribe(self, owner_id: str, queue: Queue[RealtimeEvent]) -> None:
        with self._lock:
            queues = self._subscribers.get(owner_id)
            if queues:
                queues.discard(queue)
                if not queues:
                    self._subscribers.pop(owner_id, None)
            self._release_owner_listener_locked(owner_id)

    def publish(self, event: RealtimeEvent) -> int:
        delivered = self._publish_local(event)
        self._publish_redis(event)
        return delivered

    def close(self) -> None:
        with self._lock:
            listeners = list(self._listeners.values())
            self._listeners.clear()
            self._subscribers.clear()
        for listener in listeners:
            listener.stop_event.set()

    def _publish_local(self, event: RealtimeEvent) -> int:
        with self._lock:
            queues = list(self._subscribers.get(event.owner_id, set()))

        delivered = 0
        for queue in queues:
            if self._put_or_resync(queue, event):
                delivered += 1
        return delivered

    def _publish_redis(self, event: RealtimeEvent) -> None:
        redis_client = self._redis_client()
        if redis_client is None:
            return
        envelope = {"origin_id": self._origin_id, "event": realtime_event_to_json(event)}
        try:
            redis_client.publish(self._channel(event.owner_id), json.dumps(envelope, ensure_ascii=False))
        except Exception:
            logger.warning(
                "Failed to publish realtime event to Redis: event=%s owner_id=%s resource_id=%s",
                event.event,
                event.owner_id,
                event.resource_id,
                exc_info=True,
            )

    def _ensure_owner_listener_locked(self, owner_id: str) -> None:
        if self._redis_client_factory is None:
            return
        listener = self._listeners.get(owner_id)
        if listener is not None:
            listener.ref_count += 1
            return
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._listen_owner,
            args=(owner_id, stop_event),
            daemon=True,
        )
        self._listeners[owner_id] = _OwnerListener(thread=thread, stop_event=stop_event, ref_count=1)
        thread.start()

    def _release_owner_listener_locked(self, owner_id: str) -> None:
        listener = self._listeners.get(owner_id)
        if listener is None:
            return
        listener.ref_count -= 1
        if listener.ref_count > 0:
            return
        listener.stop_event.set()
        self._listeners.pop(owner_id, None)

    def _listen_owner(self, owner_id: str, stop_event: threading.Event) -> None:
        redis_client = self._redis_client()
        if redis_client is None:
            return
        pubsub = redis_client.pubsub()
        try:
            pubsub.subscribe(self._channel(owner_id))
            for message in pubsub.listen():
                if stop_event.is_set():
                    return
                if message.get("type") != "message":
                    continue
                self._handle_redis_message(owner_id, message.get("data"))
        except Exception:
            logger.warning("Realtime Redis listener stopped for owner_id=%s", owner_id, exc_info=True)
            self._publish_local(make_realtime_event(
                event="system.resync_required",
                scope="system",
                owner_id=owner_id,
                payload={"reason": "redis_listener_error"},
            ))
        finally:
            try:
                pubsub.close()
            except Exception:
                logger.debug("Failed to close Redis pubsub", exc_info=True)

    def _handle_redis_message(self, owner_id: str, data: str | bytes) -> None:
        try:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            envelope = json.loads(data)
            if envelope.get("origin_id") == self._origin_id:
                return
            event = realtime_event_from_json(envelope["event"])
        except Exception:
            logger.warning("Malformed realtime Redis event for owner_id=%s", owner_id, exc_info=True)
            self._publish_local(make_realtime_event(
                event="system.resync_required",
                scope="system",
                owner_id=owner_id,
                payload={"reason": "malformed_event"},
            ))
            return
        self._publish_local(event)

    def _redis_client(self):
        if self._redis_client_factory is None:
            return None
        try:
            return self._redis_client_factory()
        except Exception:
            logger.warning("Realtime Redis client unavailable", exc_info=True)
            return None

    @classmethod
    def _channel(cls, owner_id: str) -> str:
        return f"{cls.CHANNEL_PREFIX}{owner_id}"

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

- [ ] **Step 5: Run local and Redis bus tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/realtime/bus.py backend/app/modules/realtime/schemas.py backend/tests/test_realtime_events.py
git commit -m "feat: add redis-capable realtime bus"
```

### Task 2: Enable Redis Realtime Transport In Backend Runtime

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/modules/realtime/router.py`
- Modify: `backend/tests/test_realtime_events.py`

**Interfaces:**
- Consumes:
  - `backend.app.core.dependencies.get_redis() -> redis.Redis`
  - `backend.app.modules.realtime.bus.event_bus`
- Produces:
  - API startup configures `event_bus` with `get_redis`.
  - API shutdown closes realtime bus listener state.
  - SSE stream still authenticates and subscribes by `owner_id`.

- [ ] **Step 1: Write failing backend runtime configuration test**

Append this to `backend/tests/test_realtime_events.py`:

```python
def test_event_bus_can_be_configured_with_redis_factory() -> None:
    bus = RealtimeEventBus(queue_size=10)
    broker = FakeRedisBroker()

    bus.configure_redis(lambda: broker)
    queue_for_owner = bus.subscribe("user-configured")

    worker_bus = RealtimeEventBus(queue_size=10, redis_client_factory=lambda: broker)
    worker_bus.publish(make_realtime_event(
        event="crawler.run.updated",
        scope="crawler.run",
        owner_id="user-configured",
        resource_id="run-1",
        payload={"status": "running"},
    ))

    assert wait_for_queue_item(queue_for_owner).payload == {"status": "running"}

    bus.unsubscribe("user-configured", queue_for_owner)
    bus.close()
    worker_bus.close()
```

- [ ] **Step 2: Run test to verify it passes after Task 1**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_realtime_events.py -t "configured_with_redis_factory" -v
```

Expected: PASS if Task 1 exposed `configure_redis()` correctly. If it fails, fix `configure_redis()` before wiring runtime startup.

- [ ] **Step 3: Configure event bus during backend startup and shutdown**

In `backend/app/main.py`, update imports:

```python
from backend.app.core.dependencies import close_redis, get_redis
from backend.app.modules.realtime.bus import event_bus
```

Inside `lifespan`, after `load_runtime_config()` add:

```python
    event_bus.configure_redis(get_redis)
```

In shutdown, before `close_redis()` add:

```python
    event_bus.close()
```

Remove the local import of `get_redis` inside the storage cleanup block because it is now imported at module level:

```python
            from backend.app.modules.storage.runtime.redis_state import StorageRuntimeState
            storage_stopped = cleanup_interrupted_storage_tasks(session, StorageRuntimeState(get_redis()))
```

- [ ] **Step 4: Ensure SSE route enables Redis when called in tests or partial startup**

In `backend/app/modules/realtime/router.py`, update imports:

```python
from backend.app.core.dependencies import get_db, get_redis
```

In `event_stream`, immediately after `owner_id = str(user.id)` add:

```python
    event_bus.configure_redis(get_redis)
```

This keeps the stream route resilient in tests and in any process where lifespan setup was bypassed.

- [ ] **Step 5: Run backend realtime tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_realtime_events.py backend/tests/test_crawler_realtime_events.py backend/tests/test_storage_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/app/modules/realtime/router.py backend/tests/test_realtime_events.py
git commit -m "feat: enable redis realtime transport"
```

### Task 3: Keep Crawler Event Shapes Stable Through Cross-Process Bus

**Files:**
- Modify: `backend/tests/test_crawler_realtime_events.py`
- Modify: `backend/app/modules/crawler/runtime/events.py`
- Modify: `backend/app/modules/crawler/runtime/threaded.py`

**Interfaces:**
- Consumes existing crawler publisher helpers:
  - `publish_run_updated(db: Session, run: CrawlRun) -> None`
  - `publish_run_detail_updated(db: Session, run: CrawlRun, details: list[CrawlRunDetailTask], *, refresh_tasks: bool = False, reason: str | None = None) -> None`
  - `append_run_log_for_run(db: Session, run: CrawlRun, message: str, level: str = "INFO", **context: Any) -> None`
- Produces unchanged event names and payload shapes.

- [ ] **Step 1: Add crawler event shape regression test**

Append this to `backend/tests/test_crawler_realtime_events.py`:

```python
def test_crawler_realtime_events_keep_frontend_contract(admin_user) -> None:
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
        source_url_name="入口A",
        task_url="https://example.test/list",
        task_final_url="https://example.test/list?page=1",
        task_url_type="list",
        status="saved",
        created_at=datetime.now(),
    )
    session.add(detail)
    session.commit()
    session.refresh(run)
    session.refresh(detail)
    queue = event_bus.subscribe(str(admin_user.id))

    service.publish_run_updated(session, run)
    service.publish_run_detail_updated(session, run, [detail], refresh_tasks=True, reason="detail_saved")
    service.append_run_log_for_run(session, run, "入库成功: AAA-001", "INFO", code="AAA-001")

    events = drain(queue)
    event_bus.unsubscribe(str(admin_user.id), queue)
    session.close()

    run_event = next(event for event in events if event.event == "crawler.run.updated")
    detail_event = next(event for event in events if event.event == "crawler.run.detail.updated")
    log_event = next(event for event in events if event.event == "crawler.run.log.appended")

    assert run_event.payload["id"] == str(run.id)
    assert run_event.payload["task_id"] == str(task.id)
    assert run_event.payload["status"] == "running"
    assert run_event.payload["logs"] == []

    assert detail_event.payload["run_id"] == str(run.id)
    assert detail_event.payload["refresh_tasks"] is True
    assert detail_event.payload["reason"] == "detail_saved"
    assert detail_event.payload["tasks"][0] == {
        "id": str(detail.id),
        "run_id": str(run.id),
        "task_name": "任务A",
        "code": "AAA-001",
        "source_url": "https://example.test/aaa",
        "source_name": "AAA-001",
        "source_url_name": "入口A",
        "task_url": "https://example.test/list",
        "task_final_url": "https://example.test/list?page=1",
        "task_url_type": "list",
        "status": "saved",
        "error": None,
        "created_at": detail.created_at.isoformat(),
    }

    assert log_event.payload["run_id"] == str(run.id)
    assert log_event.payload["log"]["message"] == "入库成功: AAA-001"
    assert log_event.payload["log"]["context"]["code"] == "AAA-001"
```

- [ ] **Step 2: Run crawler realtime tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_realtime_events.py -v
```

Expected: PASS. If this fails, fix only payload shape regressions introduced by Task 1 or Task 2.

- [ ] **Step 3: Ensure threaded crawler publishes refresh signals after commits**

Review `backend/app/modules/crawler/runtime/threaded.py` and make these targeted edits only if missing:

In `_run_list_phase`, after each `db.commit()` that persists a batch of detail rows, publish a refresh event:

```python
                db.commit()
                append_run_log_for_run(db, run, "列表批次已持久化，刷新详情子任务", "INFO")
```

Do not add per-row events in list phase. The frontend should use the existing log event plus current `refresh_tasks` events to reload task rows and summary.

In `_run_detail_phase`, after each `db.commit()` that changes one detail status, publish that detail row:

```python
            db.commit()
            publish_run_detail_updated(db, run, [detail])
```

For the exception branch, after committing `crawl_failed`, publish the failed detail:

```python
            db.commit()
            publish_run_detail_updated(db, run, [detail])
```

Add the import at the top if needed:

```python
from backend.app.modules.crawler.runtime.events import append_run_log_for_run, publish_run_detail_updated
```

- [ ] **Step 4: Run crawler runtime focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_realtime_events.py backend/tests/test_crawler_runtime_redis.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_crawler_realtime_events.py backend/app/modules/crawler/runtime/events.py backend/app/modules/crawler/runtime/threaded.py
git commit -m "test: preserve crawler realtime contracts"
```

If Step 3 required no production edits, omit unchanged files from `git add`.

### Task 4: Verify Frontend Snapshot Resync Semantics

**Files:**
- Modify: `frontend/tests/run-detail-realtime.ui.test.tsx`
- Modify if needed: `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`

**Interfaces:**
- Consumes:
  - `useRunDetailRealtime(args)` current arguments.
  - Existing mocked `getCrawlerRun`, `getCrawlerRunLogs`, and `getCrawlerRunTasks`.
- Produces:
  - Terminal `crawler.run.updated` refreshes run, tasks, and logs snapshots.
  - `refresh_tasks: true` refreshes tasks and summary.
  - `system.resync_required` refreshes run, tasks, and logs.

- [ ] **Step 1: Add failing terminal snapshot test**

In `frontend/tests/run-detail-realtime.ui.test.tsx`, add this test after `reloads final logs from the logs endpoint when a run completes`:

```tsx
  it('reloads the run snapshot when a terminal run event arrives', async () => {
    vi.mocked(getCrawlerRun)
      .mockResolvedValueOnce({
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
      .mockResolvedValueOnce({
        id: 'run-1',
        task_id: 'task-1',
        task_name: '任务A',
        status: 'completed',
        crawl_mode: 'incremental',
        queued_at: null,
        started_at: '2026-07-03T00:01:00Z',
        finished_at: '2026-07-03T00:10:00Z',
        result: { total_tasks: 1, saved: 1 },
        error: null,
        resumed_from: null,
        created_at: '2026-07-03T00:00:00Z',
        updated_at: null,
        logs: [],
      })

    renderPage()
    await screen.findByText('运行详情 - 任务A')

    const initialRunCalls = vi.mocked(getCrawlerRun).mock.calls.length

    emit('crawler.run.updated', {
      id: 'run-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'completed',
      crawl_mode: 'incremental',
      queued_at: null,
      started_at: null,
      finished_at: '2026-07-03T00:10:00Z',
      result: {},
      error: null,
      resumed_from: null,
      created_at: '2026-07-03T00:00:00Z',
      updated_at: null,
      logs: [],
    })

    await waitFor(() => {
      expect(vi.mocked(getCrawlerRun).mock.calls.length).toBeGreaterThan(initialRunCalls)
    })
    expect(await screen.findByText('已完成')).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run test to verify it fails if behavior is missing**

Run:

```bash
cd frontend && npm test -- tests/run-detail-realtime.ui.test.tsx -t "reloads the run snapshot"
```

Expected: FAIL if terminal events currently fetch logs/tasks but not the run snapshot.

- [ ] **Step 3: Update terminal event handling if needed**

In `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`, add `fetchRun` to the hook args:

```ts
  fetchRun: () => Promise<void>
```

Destructure it:

```ts
  const { id, fetchLogs, fetchRun, fetchTasks, keyword, resyncSnapshot, setLogs, setRun, setTasks, statusFilter } = args
```

In the terminal status block, call `fetchRun()`:

```ts
        if (['completed', 'failed', 'stopped'].includes(event.payload.status)) {
          void fetchRun()
          void fetchLogs()
          void fetchTasks()
        }
```

Update the effect dependency list:

```ts
  }, [id, fetchLogs, fetchRun, fetchTasks, keyword, resyncSnapshot, setLogs, setRun, setTasks, statusFilter])
```

In `frontend/src/pages/crawler/runs/RunDetailPage.tsx`, pass `fetchRun`:

```tsx
    fetchRun: detail.fetchRun,
```

- [ ] **Step 4: Run frontend realtime tests**

Run:

```bash
cd frontend && npm test -- tests/run-detail-realtime.ui.test.tsx frontend/tests/realtime-event-source-client.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/tests/run-detail-realtime.ui.test.tsx frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts frontend/src/pages/crawler/runs/RunDetailPage.tsx
git commit -m "fix: resync crawler run snapshot on terminal events"
```

If Step 3 required no production edits, omit unchanged files from `git add`.

### Task 5: Full Verification

**Files:**
- Verify all files changed by Tasks 1-4.

**Interfaces:**
- Consumes completed backend and frontend tasks.
- Produces verified cross-process realtime implementation.

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_realtime_events.py \
  backend/tests/test_crawler_realtime_events.py \
  backend/tests/test_storage_realtime_events.py \
  backend/tests/test_crawler_runtime_redis.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend targeted tests**

Run:

```bash
cd frontend && npm test -- tests/run-detail-realtime.ui.test.tsx frontend/tests/realtime-event-source-client.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: Run backend import smoke test**

Run:

```bash
source .venv/bin/activate
python - <<'PY'
from backend.app.modules.realtime.bus import RealtimeEventBus, event_bus
from backend.app.modules.realtime.schemas import make_realtime_event

bus = RealtimeEventBus(queue_size=2)
queue = bus.subscribe("owner-smoke")
event = make_realtime_event(event="crawler.run.updated", scope="crawler.run", owner_id="owner-smoke", payload={"status": "running"})
assert bus.publish(event) == 1
assert queue.get_nowait().payload == {"status": "running"}
bus.unsubscribe("owner-smoke", queue)
event_bus.close()
print("ok")
PY
```

Expected: prints `ok`.

- [ ] **Step 5: Commit verification fixes if needed**

If verification required additional fixes:

```bash
git add backend/app/modules/realtime backend/app/modules/crawler frontend/src/pages/crawler frontend/tests/run-detail-realtime.ui.test.tsx backend/tests/test_realtime_events.py backend/tests/test_crawler_realtime_events.py
git commit -m "fix: stabilize realtime verification"
```

If no files changed during verification, do not create an empty commit.

## Self-Review

- Spec coverage: Task 1 and Task 2 implement Redis-backed cross-process realtime delivery; Task 3 preserves crawler event contracts; Task 4 enforces frontend snapshot fallback; Task 5 verifies the flow.
- Placeholder scan: no forbidden placeholder wording remains.
- Type consistency: `RealtimeEventBus` keeps existing publish/subscribe interfaces and adds optional Redis configuration without changing crawler publisher helper signatures.
