# Crawler Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make JavDB incremental and full crawler runs execute successfully in `JAVDB_FETCH_MODE=agent` by creating Agent work items, waiting for Chrome Agent snapshots, parsing them on the backend, and continuing the existing crawler persistence flow.

**Architecture:** Keep the existing synchronous `execute_run -> execute_threaded_crawl -> finalize_run` lifecycle. The Agent runtime creates `CrawlerAgentWorkItem` rows, waits for a connected Chrome Agent to complete them, parses DOM fragments through backend JavDB parser bridge functions, and reuses current detail-task/movie persistence plus EventSource helpers. Agent unavailability, timeout, parser failure, and user stop are explicit run/detail outcomes; no static fallback is added.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, Pydantic, Pytest, React 19, TypeScript 6, Zustand 5, TanStack Query 5, Vitest, React Testing Library.

## Global Constraints

- Preserve crawler scheduling, run finalization, retry, detail persistence, movie persistence, and current EventSource status behavior.
- Preserve static JavDB mode unchanged.
- Preserve existing Chrome Agent token/session/WebSocket/cookie-sync protocol.
- Keep backend parsing as the only business parsing path; the Chrome Agent only returns DOM fragments.
- Do not introduce a second crawler scheduler or asynchronous run state machine.
- Do not add WebSocket as a crawler realtime replacement; existing run/task EventSource behavior remains unchanged.
- Do not automatically fall back to static mode when Agent mode is selected.
- Agent unavailable or Agent execution timeout must fail with a clear readable error.
- Agent work timeout must reuse `SECURITY_WAIT_SECONDS`; do not add new config fields in this plan.
- Follow TDD: add a focused failing test, confirm the expected failure, implement the minimum change, and rerun the focused test before each commit.
- Preserve unrelated user changes in the working tree. At plan creation time these files already had uncommitted changes: `backend/app/modules/crawler/runtime/threaded.py`, `backend/app/modules/crawler/tasks/runtime_status.py`, `backend/tests/test_crawler_realtime_events.py`, `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`. Inspect their diffs before editing; when a plan task modifies one of those files, merge the planned edit without deleting the existing user change.

## File Responsibility Map

- `backend/app/modules/crawler/agent/errors.py`: Agent-specific runtime exceptions with user-readable messages.
- `backend/app/modules/crawler/agent/work_items.py`: create, claim, stale-expire, wait, fail, and completion-guard helpers for `CrawlerAgentWorkItem`.
- `backend/app/modules/crawler/agent/runtime.py`: synchronous Agent crawler runtime; list phase, detail phase, result aggregation, backend parse/persistence integration.
- `backend/app/modules/crawler/agent/router.py`: existing Agent WebSocket protocol, with guarded snapshot completion and failed/ignored acknowledgements.
- `backend/tests/test_crawler_agent_work_items.py`: focused unit tests for work item lifecycle and waiting behavior.
- `backend/tests/test_crawler_agent_ws.py`: Agent WebSocket completion/late-snapshot/parse-error tests.
- `backend/tests/test_crawler_agent_runtime.py`: synchronous Agent runtime tests for unavailable Agent, list snapshot, detail snapshot, timeout, and stop.
- `backend/tests/test_crawler_threaded_runtime.py`: integration guard that Agent mode no longer reaches the old placeholder error.
- `frontend/src/pages/crawler/runs/__tests__/run-detail-realtime.test.tsx`: verify existing run-detail log rendering still exposes backend run-log messages.

---

### Task 1: Add Agent Errors And Work Item Lifecycle Helpers

**Files:**
- Create: `backend/app/modules/crawler/agent/errors.py`
- Modify: `backend/app/modules/crawler/agent/work_items.py`
- Modify: `backend/tests/test_crawler_agent_work_items.py`

**Interfaces:**
- Produces: `AgentRuntimeError(RuntimeError)`.
- Produces: `AgentUnavailableError`, `AgentWorkTimeoutError`, `AgentWorkFailedError`, `AgentWorkStopped`.
- Produces: `create_work_item(db, *, owner_id, run_id, task_id, page_kind, url, detail_task_id=None, url_entry_id=None) -> CrawlerAgentWorkItem`.
- Produces: `mark_work_item_failed(db, item, reason) -> CrawlerAgentWorkItem`.
- Produces: `is_work_item_completable(item) -> bool`.
- Produces: `wait_for_work_item_result(db, item, *, runtime, run_id, timeout_seconds, poll_interval_seconds=1.0, now=None, sleep=None) -> CrawlerAgentWorkItem`.
- Consumes: existing `claim_next_work_item()` and `expire_stale_work_items()`.

- [ ] **Step 1: Add failing work item lifecycle tests**

Append these tests to `backend/tests/test_crawler_agent_work_items.py`:

```python
import time
from backend.app.modules.crawler.agent.errors import (
    AgentWorkFailedError,
    AgentWorkStopped,
    AgentWorkTimeoutError,
)
from backend.app.modules.crawler.agent.work_items import (
    create_work_item,
    is_work_item_completable,
    mark_work_item_failed,
    wait_for_work_item_result,
)


class WaitingRuntime:
    def __init__(self, stopped: bool = False) -> None:
        self.stopped = stopped

    def is_stop_requested(self, run_id: str) -> bool:
        return self.stopped


def test_create_work_item_sets_pending_defaults(db_session, test_user) -> None:
    run_id = uuid.uuid4()
    task_id = uuid.uuid4()
    detail_id = uuid.uuid4()
    url_entry_id = uuid.uuid4()

    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=run_id,
        task_id=task_id,
        detail_task_id=detail_id,
        url_entry_id=url_entry_id,
        page_kind="detail",
        url="https://javdb.com/v/abc",
    )

    assert item.status == "pending"
    assert item.owner_id == test_user.id
    assert item.run_id == run_id
    assert item.task_id == task_id
    assert item.detail_task_id == detail_id
    assert item.url_entry_id == url_entry_id
    assert item.page_kind == "detail"
    assert item.url == "https://javdb.com/v/abc"
    assert item.attempt == 0
    assert item.error_reason is None


def test_mark_work_item_failed_records_reason(db_session, test_user) -> None:
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )

    failed = mark_work_item_failed(db_session, item, "parser_empty_detail")

    assert failed.status == "failed"
    assert failed.error_reason == "parser_empty_detail"
    assert failed.claimed_until is None


def test_is_work_item_completable_allows_only_active_states(db_session, test_user) -> None:
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )

    item.status = "pending"
    assert is_work_item_completable(item) is True
    item.status = "assigned"
    assert is_work_item_completable(item) is True
    item.status = "running"
    assert is_work_item_completable(item) is True
    item.status = "completed"
    assert is_work_item_completable(item) is False
    item.status = "failed"
    assert is_work_item_completable(item) is False


def test_wait_for_work_item_result_returns_completed_item(db_session, test_user) -> None:
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )
    item.status = "completed"
    item.result_json = {"tasks": [{"code": "ABC-001"}]}
    db_session.commit()

    result = wait_for_work_item_result(
        db_session,
        item,
        runtime=WaitingRuntime(),
        run_id=str(item.run_id),
        timeout_seconds=1,
        poll_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    assert result.status == "completed"
    assert result.result_json == {"tasks": [{"code": "ABC-001"}]}


def test_wait_for_work_item_result_raises_failed_reason(db_session, test_user) -> None:
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="detail",
        url="https://javdb.com/v/abc",
    )
    mark_work_item_failed(db_session, item, "missing_required_fragments:title")

    with pytest.raises(AgentWorkFailedError, match="missing_required_fragments:title"):
        wait_for_work_item_result(
            db_session,
            item,
            runtime=WaitingRuntime(),
            run_id=str(item.run_id),
            timeout_seconds=1,
            poll_interval_seconds=0,
            sleep=lambda _seconds: None,
        )


def test_wait_for_work_item_result_raises_stopped(db_session, test_user) -> None:
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )

    with pytest.raises(AgentWorkStopped):
        wait_for_work_item_result(
            db_session,
            item,
            runtime=WaitingRuntime(stopped=True),
            run_id=str(item.run_id),
            timeout_seconds=10,
            poll_interval_seconds=0,
            sleep=lambda _seconds: None,
        )


def test_wait_for_work_item_result_raises_timeout(db_session, test_user) -> None:
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )
    ticks = iter([100.0, 100.5, 101.2])

    with pytest.raises(AgentWorkTimeoutError, match="Chrome Agent 执行超时"):
        wait_for_work_item_result(
            db_session,
            item,
            runtime=WaitingRuntime(),
            run_id=str(item.run_id),
            timeout_seconds=1,
            poll_interval_seconds=0,
            now=lambda: next(ticks),
            sleep=lambda _seconds: None,
        )
```

- [ ] **Step 2: Run the work item tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_work_items.py -q
```

Expected: FAIL because `backend.app.modules.crawler.agent.errors`, `create_work_item`, `mark_work_item_failed`, `is_work_item_completable`, and `wait_for_work_item_result` do not exist.

- [ ] **Step 3: Add Agent exception classes**

Create `backend/app/modules/crawler/agent/errors.py`:

```python
from __future__ import annotations


class AgentRuntimeError(RuntimeError):
    """Base class for Chrome Agent crawler runtime failures."""


class AgentUnavailableError(AgentRuntimeError):
    """Raised when Agent mode is selected but no online Agent is available."""

    def __init__(self, message: str = "Chrome Agent 未在线，无法执行 JavDB Agent 爬取") -> None:
        super().__init__(message)


class AgentWorkTimeoutError(AgentRuntimeError):
    """Raised when a work item is not completed before the configured timeout."""

    def __init__(self, message: str = "Chrome Agent 执行超时") -> None:
        super().__init__(message)


class AgentWorkFailedError(AgentRuntimeError):
    """Raised when a work item is marked failed by the Agent/WebSocket layer."""


class AgentWorkStopped(AgentRuntimeError):
    """Raised internally when the crawler run is stopped while waiting for Agent work."""

    def __init__(self, message: str = "用户停止任务") -> None:
        super().__init__(message)
```

- [ ] **Step 4: Add work item lifecycle helpers**

Modify `backend/app/modules/crawler/agent/work_items.py` to include these imports and functions while preserving existing `claim_next_work_item()` and `expire_stale_work_items()`:

```python
from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.models.crawler_agent import CrawlerAgentWorkItem
from backend.app.modules.crawler.agent.errors import (
    AgentWorkFailedError,
    AgentWorkStopped,
    AgentWorkTimeoutError,
)

COMPLETABLE_WORK_ITEM_STATUSES = {"pending", "assigned", "running"}


def create_work_item(
    db: Session,
    *,
    owner_id: uuid.UUID | str,
    run_id: uuid.UUID | str,
    task_id: uuid.UUID | str | None,
    page_kind: str,
    url: str,
    detail_task_id: uuid.UUID | str | None = None,
    url_entry_id: uuid.UUID | str | None = None,
) -> CrawlerAgentWorkItem:
    item = CrawlerAgentWorkItem(
        owner_id=uuid.UUID(str(owner_id)),
        run_id=uuid.UUID(str(run_id)),
        task_id=uuid.UUID(str(task_id)) if task_id is not None else None,
        detail_task_id=uuid.UUID(str(detail_task_id)) if detail_task_id is not None else None,
        url_entry_id=uuid.UUID(str(url_entry_id)) if url_entry_id is not None else None,
        page_kind=page_kind,
        url=url,
        status="pending",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def is_work_item_completable(item: CrawlerAgentWorkItem) -> bool:
    return item.status in COMPLETABLE_WORK_ITEM_STATUSES


def mark_work_item_failed(
    db: Session,
    item: CrawlerAgentWorkItem,
    reason: str,
) -> CrawlerAgentWorkItem:
    item.status = "failed"
    item.error_reason = reason[:100]
    item.claimed_until = None
    db.commit()
    db.refresh(item)
    return item


def wait_for_work_item_result(
    db: Session,
    item: CrawlerAgentWorkItem,
    *,
    runtime,
    run_id: str,
    timeout_seconds: float,
    poll_interval_seconds: float = 1.0,
    now: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> CrawlerAgentWorkItem:
    clock = now or time.monotonic
    sleeper = sleep or time.sleep
    deadline = clock() + max(0.0, float(timeout_seconds))

    while True:
        if runtime.is_stop_requested(str(run_id)):
            raise AgentWorkStopped()
        expire_stale_work_items(db)
        db.refresh(item)
        if item.status == "completed":
            return item
        if item.status == "failed":
            raise AgentWorkFailedError(item.error_reason or "agent_work_failed")
        if clock() >= deadline:
            mark_work_item_failed(db, item, "agent_work_timeout")
            raise AgentWorkTimeoutError()
        sleeper(max(0.0, float(poll_interval_seconds)))
```

Keep the existing `claim_next_work_item()` and `expire_stale_work_items()` below these helpers.

- [ ] **Step 5: Run the work item tests and verify pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_work_items.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit work item lifecycle changes**

Run:

```bash
git add backend/app/modules/crawler/agent/errors.py backend/app/modules/crawler/agent/work_items.py backend/tests/test_crawler_agent_work_items.py
git commit -m "feat: add crawler agent work item lifecycle"
```

---

### Task 2: Guard Agent WebSocket Snapshot Completion

**Files:**
- Modify: `backend/app/modules/crawler/agent/runtime.py`
- Modify: `backend/app/modules/crawler/agent/router.py`
- Modify: `backend/tests/test_crawler_agent_ws.py`

**Interfaces:**
- Consumes: `is_work_item_completable(item) -> bool` from Task 1.
- Consumes: `mark_work_item_failed(db, item, reason) -> CrawlerAgentWorkItem` from Task 1.
- Produces: `complete_work_item_from_snapshot(db, *, work_item_id: str, snapshot: AgentPageSnapshot) -> CrawlerAgentWorkItem` that ignores non-completable items and marks parser failures failed.
- Preserves: `agent.cookie_sync`, `agent.heartbeat`, `agent.task_request`, and successful `agent.page_snapshot` WebSocket behavior.

- [ ] **Step 1: Add failing WebSocket completion guard tests**

Append these tests to `backend/tests/test_crawler_agent_ws.py`:

```python
import uuid
from datetime import datetime

from backend.app.models.crawler_agent import CrawlerAgentWorkItem
from backend.tests.conftest import TestingSessionLocal


def test_agent_page_snapshot_ignores_late_completed_work_item(client, auth_headers) -> None:
    token_response = client.post("/api/crawler/agent/token/rotate", headers=auth_headers)
    token = token_response.json()["data"]["token"]
    session_response = client.post("/api/crawler/agent/sessions", json={"token": token})
    agent_session = session_response.json()["data"]["session"]

    db = TestingSessionLocal()
    try:
        agent = db.query(CrawlerAgentWorkItem).first()
        assert agent is None
        owner_response = client.get("/api/crawler/agent/status", headers=auth_headers)
        owner_agent_id = owner_response.json()["data"]["agent_id"]
        from backend.app.models.crawler_agent import CrawlerAgent
        owner_id = db.get(CrawlerAgent, uuid.UUID(owner_agent_id)).owner_id
        item = CrawlerAgentWorkItem(
            owner_id=owner_id,
            run_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            page_kind="list",
            url="https://javdb.com/actors/a",
            status="completed",
            result_json={"tasks": [{"code": "OLD"}]},
        )
        db.add(item)
        db.commit()
        item_id = str(item.id)
    finally:
        db.close()

    with client.websocket_connect(f"/api/crawler/agent/ws?session={agent_session}") as websocket:
        assert websocket.receive_json()["type"] == "server.hello"
        websocket.send_json({
            "id": "late_snapshot",
            "type": "agent.page_snapshot",
            "payload": {
                "agent_task_id": item_id,
                "snapshot": {
                    "page_kind": "list",
                    "url": "https://javdb.com/actors/a",
                    "source_page": 1,
                    "fragments": {"items": "<div class='item'></div>"},
                },
            },
        })
        message = websocket.receive_json()

    assert message["type"] == "server.ack"
    assert message["payload"]["agent_task_id"] == item_id
    assert message["payload"]["ignored"] is True
    db = TestingSessionLocal()
    try:
        refreshed = db.get(CrawlerAgentWorkItem, uuid.UUID(item_id))
        assert refreshed.status == "completed"
        assert refreshed.result_json == {"tasks": [{"code": "OLD"}]}
    finally:
        db.close()


def test_agent_page_snapshot_marks_parse_error_failed(client, auth_headers) -> None:
    token_response = client.post("/api/crawler/agent/token/rotate", headers=auth_headers)
    token = token_response.json()["data"]["token"]
    session_response = client.post("/api/crawler/agent/sessions", json={"token": token})
    agent_session = session_response.json()["data"]["session"]

    db = TestingSessionLocal()
    try:
        from backend.app.models.crawler_agent import CrawlerAgent
        agent_id = client.get("/api/crawler/agent/status", headers=auth_headers).json()["data"]["agent_id"]
        owner_id = db.get(CrawlerAgent, uuid.UUID(agent_id)).owner_id
        item = CrawlerAgentWorkItem(
            owner_id=owner_id,
            run_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            page_kind="detail",
            url="https://javdb.com/v/abc",
            status="assigned",
            claimed_until=datetime.now(),
        )
        db.add(item)
        db.commit()
        item_id = str(item.id)
    finally:
        db.close()

    with client.websocket_connect(f"/api/crawler/agent/ws?session={agent_session}") as websocket:
        assert websocket.receive_json()["type"] == "server.hello"
        websocket.send_json({
            "id": "bad_snapshot",
            "type": "agent.page_snapshot",
            "payload": {
                "agent_task_id": item_id,
                "snapshot": {
                    "page_kind": "detail",
                    "url": "https://javdb.com/v/abc",
                    "fragments": {"title": "<h1>ABC</h1>"},
                },
            },
        })
        message = websocket.receive_json()

    assert message["type"] == "server.error"
    assert message["payload"]["agent_task_id"] == item_id
    assert "missing_required_fragments" in message["payload"]["reason"]
    db = TestingSessionLocal()
    try:
        refreshed = db.get(CrawlerAgentWorkItem, uuid.UUID(item_id))
        assert refreshed.status == "failed"
        assert "missing_required_fragments" in refreshed.error_reason
    finally:
        db.close()
```

- [ ] **Step 2: Run the WebSocket tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_ws.py -q
```

Expected: FAIL because late completed work items are reparsed or because parse errors are not converted to failed work item responses.

- [ ] **Step 3: Guard `complete_work_item_from_snapshot()`**

Modify `backend/app/modules/crawler/agent/runtime.py`. Keep imports already used by the file and add Task 1 helpers:

```python
from backend.app.modules.crawler.agent.work_items import (
    is_work_item_completable,
    mark_work_item_failed,
)
```

Replace `complete_work_item_from_snapshot()` with:

```python
def complete_work_item_from_snapshot(
    db: Session,
    *,
    work_item_id: str,
    snapshot: AgentPageSnapshot,
) -> CrawlerAgentWorkItem:
    item = db.get(CrawlerAgentWorkItem, uuid.UUID(work_item_id))
    if item is None:
        raise ValueError("agent_work_item_not_found")
    if not is_work_item_completable(item):
        return item
    try:
        if item.page_kind == "list":
            item.result_json = {"tasks": parse_agent_list_snapshot(snapshot)}
        elif item.page_kind == "detail":
            item.result_json = {"detail": parse_agent_detail_snapshot(snapshot)}
        else:
            raise ValueError(f"unsupported_page_kind:{item.page_kind}")
    except Exception as exc:
        mark_work_item_failed(db, item, str(exc))
        raise
    item.status = "completed"
    item.error_reason = None
    item.claimed_until = None
    db.commit()
    db.refresh(item)
    return item
```

- [ ] **Step 4: Return ignored/error messages from WebSocket snapshot handling**

Modify `backend/app/modules/crawler/agent/router.py` imports to include `CrawlerAgentWorkItem`:

```python
from backend.app.models.crawler_agent import CrawlerAgent, CrawlerAgentSession, CrawlerAgentWorkItem
```

Modify the `agent.page_snapshot` branch in `backend/app/modules/crawler/agent/router.py` to:

```python
            if message.get("type") == "agent.page_snapshot":
                payload = message.get("payload") or {}
                if payload.get("cookies"):
                    cookies = [
                        AgentCookie.model_validate(cookie)
                        for cookie in payload.get("cookies", [])
                    ]
                    sync_javdb_cookies(cookies)
                    agent.last_cookie_sync_at = datetime.now(UTC)
                snapshot = AgentPageSnapshot.model_validate(payload["snapshot"])
                agent_task_id = str(payload["agent_task_id"])
                existing_item = db.get(CrawlerAgentWorkItem, uuid.UUID(agent_task_id))
                ignored = existing_item is None or existing_item.status not in {"pending", "assigned", "running"}
                try:
                    item = complete_work_item_from_snapshot(
                        db, work_item_id=agent_task_id, snapshot=snapshot
                    )
                except Exception as exc:
                    await websocket.send_json({
                        "id": f"err_{message.get('id')}",
                        "type": "server.error",
                        "payload": {"agent_task_id": agent_task_id, "reason": str(exc)},
                    })
                    continue
                await websocket.send_json({
                    "id": f"ack_{message.get('id')}",
                    "type": "server.ack",
                    "payload": {
                        "agent_task_id": str(item.id),
                        "ignored": ignored,
                    },
                })
                continue
```

- [ ] **Step 5: Run WebSocket and parser tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_ws.py backend/tests/test_crawler_agent_parser_bridge.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit WebSocket completion guard changes**

Run:

```bash
git add backend/app/modules/crawler/agent/runtime.py backend/app/modules/crawler/agent/router.py backend/tests/test_crawler_agent_ws.py
git commit -m "fix: guard crawler agent snapshot completion"
```

---

### Task 3: Implement Agent List Phase

**Files:**
- Create: `backend/tests/test_crawler_agent_runtime.py`
- Modify: `backend/app/modules/crawler/agent/runtime.py`
- Modify: `backend/tests/test_crawler_threaded_runtime.py`

**Interfaces:**
- Consumes: `create_work_item()` and `wait_for_work_item_result()` from Task 1.
- Consumes: `AgentUnavailableError`, `AgentWorkStopped`, `AgentWorkTimeoutError` from Task 1.
- Consumes: `parse_agent_list_snapshot()` through existing `complete_work_item_from_snapshot()`.
- Produces: `_ensure_online_agent(db, owner_id) -> CrawlerAgent`.
- Produces: `_run_agent_list_phase(db, run, task, runtime, config, *, selected_task_url_ids=None) -> None`.
- Produces: `execute_agent_crawl(..., detail_only=False, selected_task_url_ids=None)` with a working list phase.

- [ ] **Step 1: Add failing Agent unavailable and list phase tests**

Create `backend/tests/test_crawler_agent_runtime.py`:

```python
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.models.crawler_agent import CrawlerAgent, CrawlerAgentWorkItem
from backend.app.modules.crawler.agent.errors import AgentUnavailableError
from backend.app.modules.crawler.agent.runtime import execute_agent_crawl
from backend.app.modules.crawler.runs import logs as run_logs


class AgentRuntimeState:
    def __init__(self, stopped: bool = False) -> None:
        self.stopped = stopped
        self.progress: dict[str, int] = {}

    def is_stop_requested(self, run_id: str) -> bool:
        return self.stopped

    def write_progress(self, run_id: str, progress: dict[str, int]) -> None:
        self.progress = dict(progress)


def make_agent_task_and_run(db_session) -> tuple[CrawlTask, CrawlRun]:
    task = CrawlTask(id=uuid.uuid4(), name="agent-task", owner_id=uuid.uuid4(), is_skip=False)
    task.urls = [
        CrawlTaskUrl(
            position=0,
            url="https://javdb.com/actors/a",
            url_type="actors",
            final_url="https://javdb.com/actors/a",
            source="javdb",
            url_name="Actor A",
        ),
    ]
    db_session.add(task)
    db_session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        queued_at=datetime.now(),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(task)
    db_session.refresh(run)
    return task, run


def create_online_agent(db_session, owner_id) -> CrawlerAgent:
    agent = CrawlerAgent(
        owner_id=owner_id,
        token_hash="hash",
        status="online",
        name="Chrome Agent",
        last_seen_at=datetime.now(),
    )
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    return agent


def test_execute_agent_crawl_fails_fast_when_agent_offline(db_session, tmp_path, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    monkeypatch.setattr(run_logs, "RUN_LOG_DIR", str(tmp_path))

    with pytest.raises(AgentUnavailableError, match="Chrome Agent 未在线"):
        execute_agent_crawl(db_session, run, task, AgentRuntimeState())

    logs = run_logs.load_run_logs(str(run.id))
    assert any("Chrome Agent 未在线" in entry["message"] for entry in logs)


def test_execute_agent_crawl_list_phase_creates_detail_tasks_from_snapshot(db_session, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    create_online_agent(db_session, task.owner_id)

    def fake_wait(db, item, **kwargs):
        item.status = "completed"
        item.result_json = {
            "tasks": [
                {
                    "code": "ABC-001",
                    "url": "https://javdb.com/v/abc001",
                    "name": "ABC title",
                    "_task_url": "https://javdb.com/actors/a",
                    "_task_final_url": "https://javdb.com/actors/a",
                    "_task_url_type": "actors",
                    "_task_url_name": "Actor A",
                    "_task_source": "javdb",
                }
            ]
        }
        db.commit()
        db.refresh(item)
        return item

    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime.wait_for_work_item_result", fake_wait)
    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime._run_agent_detail_phase", lambda *args, **kwargs: None)

    result = execute_agent_crawl(db_session, run, task, AgentRuntimeState())

    work_items = db_session.query(CrawlerAgentWorkItem).filter(CrawlerAgentWorkItem.run_id == run.id).all()
    rows = db_session.scalars(select(CrawlRunDetailTask).where(CrawlRunDetailTask.run_id == run.id)).all()
    assert len(work_items) == 1
    assert work_items[0].page_kind == "list"
    assert work_items[0].url == "https://javdb.com/actors/a"
    assert len(rows) == 1
    assert rows[0].code == "ABC-001"
    assert rows[0].status == "pending_crawl"
    assert rows[0].source_url_name == "Actor A"
    assert result["total_tasks"] == 1
```

Append this integration guard to `backend/tests/test_crawler_threaded_runtime.py`:

```python
def test_agent_mode_routes_to_agent_runtime_without_placeholder_error(db_session, monkeypatch) -> None:
    task, run = make_task_and_run(db_session)

    class Config:
        JAVDB_FETCH_MODE = "agent"
        SECURITY_WAIT_SECONDS = 1

    called = {}

    def fake_agent_crawl(db, run_arg, task_arg, runtime, *, detail_only=False, selected_task_url_ids=None):
        called["run_id"] = run_arg.id
        return {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "skipped_tasks": 0,
            "saved": 0,
            "failed": 0,
            "skipped": 0,
        }

    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.read_crawler_runtime_config", lambda: Config())
    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime.execute_agent_crawl", fake_agent_crawl)

    result = execute_threaded_crawl(db_session, run, task, Runtime())

    assert called["run_id"] == run.id
    assert result["total_tasks"] == 0
```

- [ ] **Step 2: Run Agent runtime tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_runtime.py backend/tests/test_crawler_threaded_runtime.py::test_agent_mode_routes_to_agent_runtime_without_placeholder_error -q
```

Expected: FAIL because `execute_agent_crawl()` still raises the placeholder error and `_run_agent_list_phase` is not implemented.

- [ ] **Step 3: Implement Agent preflight, result builder, and list phase**

Modify `backend/app/modules/crawler/agent/runtime.py` to add these imports:

```python
from datetime import datetime
from typing import Any

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.app.models.crawler_agent import CrawlerAgent
from backend.app.modules.crawler.agent.errors import (
    AgentRuntimeError,
    AgentUnavailableError,
    AgentWorkStopped,
)
from backend.app.modules.crawler.agent.work_items import create_work_item, wait_for_work_item_result
from backend.app.modules.crawler.runtime.detail_queue import upsert_detail_task
from backend.app.modules.crawler.runtime.events import append_run_log_for_run, publish_run_detail_updated
from backend.app.modules.crawler.runtime.source_task_names import find_existing_movie_codes
```

Add these functions below `complete_work_item_from_snapshot()`:

```python
def _ensure_online_agent(db: Session, owner_id: uuid.UUID) -> CrawlerAgent:
    agent = (
        db.query(CrawlerAgent)
        .filter(CrawlerAgent.owner_id == owner_id)
        .filter(CrawlerAgent.status == "online")
        .order_by(CrawlerAgent.last_seen_at.desc(), CrawlerAgent.created_at.desc())
        .first()
    )
    if agent is None:
        raise AgentUnavailableError()
    return agent


def _selected_urls(task: CrawlTask, selected_task_url_ids: list[uuid.UUID] | None):
    task_urls = list(task.urls)
    if selected_task_url_ids is not None:
        selected_ids = {uuid.UUID(str(url_id)) for url_id in selected_task_url_ids}
        task_urls = [url for url in task_urls if url.id in selected_ids]
        if not task_urls:
            raise ValueError("选择的 URL 不属于该任务")
    return task_urls


def _should_persist_agent_list_item(run: CrawlRun, item: dict[str, Any]) -> bool:
    if run.crawl_mode != "incremental":
        return True
    return not (item.get("status") == "skipped" and item.get("reason") == "already_exists")


def _append_existing_source_task_ids(db: Session, task: CrawlTask, items: list[dict[str, Any]]) -> None:
    from backend.app.modules.content.movies.persistence import append_source_task_ids_for_codes

    codes = [str(item.get("code")) for item in items if item.get("code")]
    if not codes:
        return
    existing_codes = find_existing_movie_codes(db, codes)
    if existing_codes:
        append_source_task_ids_for_codes(db, existing_codes, task.id)


def _run_agent_list_phase(
    db: Session,
    run: CrawlRun,
    task: CrawlTask,
    runtime,
    config,
    *,
    selected_task_url_ids: list[uuid.UUID] | None = None,
) -> None:
    for url_entry in _selected_urls(task, selected_task_url_ids):
        if url_entry.source != "javdb":
            continue
        item = create_work_item(
            db,
            owner_id=task.owner_id,
            run_id=run.id,
            task_id=task.id,
            url_entry_id=url_entry.id,
            page_kind="list",
            url=url_entry.final_url or url_entry.url,
        )
        append_run_log_for_run(db, run, f"Chrome Agent 列表任务已创建: {item.url}", "INFO", agent_task_id=str(item.id))
        completed = wait_for_work_item_result(
            db,
            item,
            runtime=runtime,
            run_id=str(run.id),
            timeout_seconds=float(config.SECURITY_WAIT_SECONDS),
        )
        tasks = list((completed.result_json or {}).get("tasks") or [])
        for task_info in tasks:
            task_info.setdefault("_task_url", url_entry.url)
            task_info.setdefault("_task_final_url", url_entry.final_url)
            task_info.setdefault("_task_url_type", url_entry.url_type)
            task_info.setdefault("_task_url_name", url_entry.url_name)
            task_info.setdefault("_task_source", url_entry.source)
        _append_existing_source_task_ids(db, task, tasks)
        persisted = []
        for task_info in tasks:
            if not _should_persist_agent_list_item(run, task_info):
                continue
            detail = upsert_detail_task(db, run=run, task_name=task.name, item=task_info)
            if detail is not None:
                persisted.append(detail)
        db.commit()
        publish_run_detail_updated(db, run, persisted, refresh_tasks=True, reason="agent_list_completed")
        append_run_log_for_run(db, run, f"Chrome Agent 列表解析完成: 新增详情子任务 {len(persisted)} 条", "INFO")


def _build_agent_result(db: Session, run: CrawlRun) -> dict[str, Any]:
    from backend.app.models.crawl_run import CrawlRunDetailTask

    total = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).count()
    saved = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id, CrawlRunDetailTask.status == "saved").count()
    failed = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id, CrawlRunDetailTask.status.in_(["crawl_failed", "save_failed"])).count()
    skipped = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id, CrawlRunDetailTask.status == "skipped").count()
    return {
        "total_tasks": total,
        "completed_tasks": saved,
        "failed_tasks": failed,
        "skipped_tasks": skipped,
        "saved": saved,
        "failed": failed,
        "skipped": skipped,
    }


def _run_agent_detail_phase(db: Session, run: CrawlRun, task: CrawlTask, runtime, config) -> None:
    return None
```

Replace the placeholder `execute_agent_crawl()` with:

```python
def execute_agent_crawl(
    db: Session,
    run,
    task,
    runtime,
    *,
    detail_only: bool = False,
    selected_task_url_ids: list | None = None,
) -> dict:
    try:
        _ensure_online_agent(db, task.owner_id)
        if not detail_only:
            _run_agent_list_phase(
                db,
                run,
                task,
                runtime,
                read_crawler_runtime_config(),
                selected_task_url_ids=selected_task_url_ids,
            )
        _run_agent_detail_phase(db, run, task, runtime, read_crawler_runtime_config())
    except AgentWorkStopped:
        return {**_build_agent_result(db, run), "stopped": True}
    except AgentRuntimeError as exc:
        append_run_log_for_run(db, run, str(exc), "ERROR")
        raise

    return _build_agent_result(db, run)
```

Add this import at the top of `runtime.py`:

```python
from backend.app.modules.crawler.config.conf_reader import read_crawler_runtime_config
```

- [ ] **Step 4: Run list phase tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_runtime.py backend/tests/test_crawler_threaded_runtime.py::test_agent_mode_routes_to_agent_runtime_without_placeholder_error -q
```

Expected: PASS.

- [ ] **Step 5: Commit Agent list phase**

Run:

```bash
git add backend/app/modules/crawler/agent/runtime.py backend/tests/test_crawler_agent_runtime.py backend/tests/test_crawler_threaded_runtime.py
git commit -m "feat: run crawler agent list phase"
```

---

### Task 4: Implement Agent Detail Phase

**Files:**
- Modify: `backend/app/modules/crawler/agent/runtime.py`
- Modify: `backend/tests/test_crawler_agent_runtime.py`

**Interfaces:**
- Consumes: `_build_agent_result(db, run) -> dict[str, Any]` from Task 3.
- Produces: `_process_agent_detail_result(db, run, task, detail, detail_data) -> None`.
- Produces: `_run_agent_detail_phase(db, run, task, runtime, config) -> None`.
- Preserves: existing movie persistence and source task ID behavior.

- [ ] **Step 1: Add failing Agent detail, timeout, and stop tests**

Append these tests to `backend/tests/test_crawler_agent_runtime.py`:

```python
from backend.app.modules.crawler.agent.errors import AgentWorkTimeoutError
from shared.database.models.content import Movie


class FakePipeline:
    def process_item(self, item, task_name=None, task_id=None):
        return {**item, "source_task_id": task_id}


def seed_pending_detail(db_session, run, task, code: str | None = None) -> CrawlRunDetailTask:
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code=code,
        source_url="https://javdb.com/v/abc001",
        source_name="ABC title",
        source_url_name="Actor A",
        task_url="https://javdb.com/actors/a",
        task_final_url="https://javdb.com/actors/a",
        task_url_type="actors",
        status="pending_crawl",
        created_at=datetime.now(),
    )
    db_session.add(detail)
    db_session.commit()
    db_session.refresh(detail)
    return detail


def test_execute_agent_crawl_detail_phase_saves_movie(db_session, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    create_online_agent(db_session, task.owner_id)
    detail = seed_pending_detail(db_session, run, task)

    def fake_wait(db, item, **kwargs):
        item.status = "completed"
        item.result_json = {
            "detail": {
                "code": "ABC-001",
                "source_name": "ABC title",
                "source_url": "https://javdb.com/v/abc001",
            }
        }
        db.commit()
        db.refresh(item)
        return item

    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime.wait_for_work_item_result", fake_wait)
    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime.build_pipeline", lambda: FakePipeline())

    result = execute_agent_crawl(db_session, run, task, AgentRuntimeState(), detail_only=True)

    db_session.refresh(detail)
    movie = db_session.scalar(select(Movie).where(Movie.code == "ABC-001"))
    assert result["saved"] == 1
    assert detail.status == "saved"
    assert detail.item_data["code"] == "ABC-001"
    assert movie is not None
    assert str(task.id) in [str(value) for value in movie.source_task_ids]


def test_execute_agent_crawl_detail_parse_failure_marks_detail_failed(db_session, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    create_online_agent(db_session, task.owner_id)
    detail = seed_pending_detail(db_session, run, task)

    def fake_wait(db, item, **kwargs):
        item.status = "failed"
        item.error_reason = "missing_required_fragments:title"
        db.commit()
        db.refresh(item)
        raise AgentWorkFailedError(item.error_reason)

    from backend.app.modules.crawler.agent.errors import AgentWorkFailedError
    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime.wait_for_work_item_result", fake_wait)

    result = execute_agent_crawl(db_session, run, task, AgentRuntimeState(), detail_only=True)

    db_session.refresh(detail)
    assert result["failed"] == 1
    assert detail.status == "crawl_failed"
    assert "missing_required_fragments:title" in detail.error


def test_execute_agent_crawl_timeout_fails_list_run(db_session, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    create_online_agent(db_session, task.owner_id)

    def fake_wait(db, item, **kwargs):
        raise AgentWorkTimeoutError()

    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime.wait_for_work_item_result", fake_wait)

    with pytest.raises(AgentWorkTimeoutError, match="Chrome Agent 执行超时"):
        execute_agent_crawl(db_session, run, task, AgentRuntimeState())


def test_execute_agent_crawl_stop_while_waiting_returns_stopped(db_session, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    create_online_agent(db_session, task.owner_id)

    def fake_wait(db, item, **kwargs):
        from backend.app.modules.crawler.agent.errors import AgentWorkStopped
        raise AgentWorkStopped()

    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime.wait_for_work_item_result", fake_wait)

    result = execute_agent_crawl(db_session, run, task, AgentRuntimeState(stopped=True))

    assert result["stopped"] is True
```

- [ ] **Step 2: Run Agent runtime tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_runtime.py -q
```

Expected: FAIL because `_run_agent_detail_phase()` is a stub and detail failures are not mapped to `crawl_failed`.

- [ ] **Step 3: Implement Agent detail processing**

Modify `backend/app/modules/crawler/agent/runtime.py` imports:

```python
from backend.app.modules.crawler.agent.errors import (
    AgentRuntimeError,
    AgentUnavailableError,
    AgentWorkFailedError,
    AgentWorkStopped,
)
from backend.app.modules.crawler.runtime.detail_queue import claim_next_pending_detail, upsert_detail_task
from backend.app.modules.crawler.runtime.details import detail_row_to_task_info
from backend.app.modules.content.movies.persistence import append_source_task_id, upsert_movie_with_magnets
from scraper.tasks.task_utils import determine_source
```

Add a local `build_pipeline()` helper or import the existing one from threaded runtime:

```python
from backend.app.modules.crawler.runtime.threaded import build_pipeline
```

Add these functions:

```python
def _process_agent_detail_result(
    db: Session,
    run: CrawlRun,
    task: CrawlTask,
    detail,
    detail_data: dict[str, Any],
) -> None:
    pipeline = build_pipeline()
    item = {
        **detail_data,
        "source_url": detail_data.get("source_url") or detail.source_url,
        "source_name": detail_data.get("source_name") or detail.source_name,
        "code": detail_data.get("code") or detail.code,
    }
    code = item.get("code")
    if code:
        detail.code = code
    cleaned = pipeline.process_item(item, task_name=task.name, task_id=str(task.id))
    if cleaned:
        upsert_movie_with_magnets(db, {**cleaned, "source_task_ids": [task.id]})
        detail.status = "saved"
        detail.item_data = cleaned
        detail.crawled_at = datetime.now()
        detail.saved_at = datetime.now()
        detail.error = None
    else:
        detail.status = "save_failed"
        detail.error = "pipeline returned None"


def _run_agent_detail_phase(db: Session, run: CrawlRun, task: CrawlTask, runtime, config) -> None:
    while True:
        if runtime.is_stop_requested(str(run.id)):
            raise AgentWorkStopped()
        detail = claim_next_pending_detail(db, run.id)
        if detail is None:
            break
        append_run_log_for_run(
            db,
            run,
            f"[{task.name}][URL: {detail.source_url_name or detail.task_url_type or '-'}] Chrome Agent 详情开始: code={detail.code} name={detail.source_name}",
            "INFO",
            detail_id=str(detail.id),
            code=detail.code,
            source_url=detail.source_url,
            detail_status="crawling",
        )
        item = create_work_item(
            db,
            owner_id=task.owner_id,
            run_id=run.id,
            task_id=task.id,
            detail_task_id=detail.id,
            page_kind="detail",
            url=detail.source_url,
        )
        try:
            completed = wait_for_work_item_result(
                db,
                item,
                runtime=runtime,
                run_id=str(run.id),
                timeout_seconds=float(config.SECURITY_WAIT_SECONDS),
            )
            detail_data = dict((completed.result_json or {}).get("detail") or {})
            if not detail_data:
                raise AgentWorkFailedError("agent_detail_result_empty")
            _process_agent_detail_result(db, run, task, detail, detail_data)
        except AgentWorkStopped:
            raise
        except Exception as exc:
            detail.status = "crawl_failed"
            detail.error = str(exc)[:500]
            append_run_log_for_run(
                db,
                run,
                f"Chrome Agent 详情失败: {detail.error}",
                "ERROR",
                detail_id=str(detail.id),
                source_url=detail.source_url,
            )
        db.commit()
        publish_run_detail_updated(db, run, [detail])
```

Remove the stub `_run_agent_detail_phase()` from Task 3.

- [ ] **Step 4: Run Agent runtime tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_runtime.py -q
```

Expected: PASS.

- [ ] **Step 5: Run threaded runtime regression tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_runtime.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Agent detail phase**

Run:

```bash
git add backend/app/modules/crawler/agent/runtime.py backend/tests/test_crawler_agent_runtime.py
git commit -m "feat: run crawler agent detail phase"
```

---

### Task 5: Verify Agent Runtime Integration And Frontend Visibility

**Files:**
- Modify: `backend/tests/test_crawler_agent_runtime.py`
- Modify: `frontend/src/pages/crawler/runs/__tests__/run-detail-realtime.test.tsx`

**Interfaces:**
- Consumes: completed Agent runtime from Tasks 1-4.
- Produces: focused verification evidence for backend Agent runtime, crawler runtime, realtime propagation, frontend crawler tests, and build.

- [ ] **Step 1: Add a placeholder-removal regression**

Append this test to `backend/tests/test_crawler_agent_runtime.py`:

```python
def test_agent_unavailable_error_replaces_placeholder_message(db_session, tmp_path, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    monkeypatch.setattr(run_logs, "RUN_LOG_DIR", str(tmp_path))

    with pytest.raises(AgentUnavailableError) as exc_info:
        execute_agent_crawl(db_session, run, task, AgentRuntimeState())

    assert "JavDB Agent runtime is configured but Agent work execution is not available" not in str(exc_info.value)
    assert "Chrome Agent 未在线" in str(exc_info.value)
```

- [ ] **Step 2: Run the placeholder-removal regression**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_agent_runtime.py::test_agent_unavailable_error_replaces_placeholder_message -q
```

Expected: PASS after Tasks 1-4. A failure means the old placeholder message is still reachable and `execute_agent_crawl()` must be corrected before continuing.

- [ ] **Step 3: Ensure run logs expose Agent failures in backend tests**

Add this backend assertion to `test_execute_agent_crawl_fails_fast_when_agent_offline`:

```python
    logs = run_logs.load_run_logs(str(run.id))
    error_entries = [entry for entry in logs if entry["level"] == "ERROR"]
    assert any("Chrome Agent 未在线" in entry["message"] for entry in error_entries)
```

This keeps frontend behavior covered by the existing run logs UI, because run detail already renders logs returned by `getCrawlerRunLogs()`.

- [ ] **Step 4: Add a frontend log visibility regression**

Append this test to `frontend/src/pages/crawler/runs/__tests__/run-detail-realtime.test.tsx` inside `describe('RunDetail realtime event ownership', () => { ... })`:

```tsx
it('renders Chrome Agent failure reason from run logs', async () => {
  useCrawlerRuntimeStore.getState().setConnectionStatus('connected')
  vi.mocked(getCrawlerRun).mockResolvedValue({
    id: 'run-1',
    task_id: 'task-agent',
    task_name: 'Agent Task',
    status: 'failed',
    crawl_mode: 'incremental',
    queued_at: null,
    started_at: null,
    finished_at: null,
    result: null,
    error: 'Chrome Agent 未在线，无法执行 JavDB Agent 爬取',
    resumed_from: null,
    created_at: '2026-08-14T00:00:00Z',
    updated_at: null,
    logs: [],
  })
  vi.mocked(getCrawlerRunLogs).mockResolvedValue([
    {
      timestamp: '2026-08-14T00:00:01Z',
      level: 'ERROR',
      component: null,
      event: null,
      message: 'Chrome Agent 未在线，无法执行 JavDB Agent 爬取',
      context: {},
    },
  ])

  render(<RunDetailPage />, { wrapper })

  expect(await screen.findByText('Chrome Agent 未在线，无法执行 JavDB Agent 爬取')).toBeInTheDocument()
})
```

- [ ] **Step 5: Run backend Agent and crawler focused suites**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_crawler_agent_auth.py \
  backend/tests/test_crawler_agent_cookie_sync.py \
  backend/tests/test_crawler_agent_parser_bridge.py \
  backend/tests/test_crawler_agent_work_items.py \
  backend/tests/test_crawler_agent_ws.py \
  backend/tests/test_crawler_agent_runtime.py \
  backend/tests/test_crawler_threaded_runtime.py \
  backend/tests/test_crawler_runs_api.py \
  backend/tests/test_crawler_realtime_events.py \
  backend/tests/test_realtime_events.py \
  -q
```

Expected: PASS.

- [ ] **Step 6: Run frontend focused crawler visibility tests**

Run:

```bash
npm test -- src/realtime src/stores src/pages/crawler tests/crawler-run-detail.ui.test.tsx tests/crawler-runs.ui.test.tsx
```

Expected: PASS for focused crawler/realtime coverage. A failure in an unrelated existing full-suite test should be documented by test name in the implementation report; do not broaden this Agent runtime task to fix unrelated UI tests.

- [ ] **Step 7: Run frontend build**

Run:

```bash
npm run build
```

Expected: PASS.

- [ ] **Step 8: Run final diff checks**

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` exits 0. `git status --short` contains only intentional Agent runtime files plus any pre-existing unrelated dirty files that were present before execution.

- [ ] **Step 9: Commit final verification tests**

Run:

```bash
git add backend/tests/test_crawler_agent_runtime.py frontend/src/pages/crawler/runs/__tests__/run-detail-realtime.test.tsx
git commit -m "test: verify crawler agent runtime integration"
```
