# Fix Realtime Stream Run Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make crawler run detail receive live log, detail-task, and run-status updates through the current `/api/events/stream` EventSource endpoint after the initial `system.connected` event.

**Architecture:** Keep the canonical realtime channel under `backend/app/modules/realtime` and route crawler runtime updates into that bus. Do not remove the older `/api/crawler/stream` code in this fix; instead stop relying on the old crawler event bus for `RunDetailPage`, which already subscribes to `/api/events/stream`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pytest, React 19, TypeScript 6, browser EventSource, Vitest.

---

## Current Failure

The attached log shows this sequence:

- `/api/events/stream?token=...` connects at `2026-07-03 12:06:54`.
- The SSE response sends one event: `system.connected`.
- The crawler continues producing backend logs and detail progress through `12:07:08`.
- The run detail page receives no further pushed events.

The current code has two event systems:

- `backend/app/modules/realtime/*`: new user-scoped `RealtimeEventBus`, served by `/api/events/stream`.
- `backend/app/modules/crawler/events/*`: older crawler SSE bus, served by `/api/crawler/stream`.

`frontend/src/pages/crawler/runs/RunDetailPage.tsx` uses the new `frontend/src/realtime/eventSourceClient.ts`, which connects to `/api/events/stream`. But `backend/app/modules/crawler/runtime/service.py` still publishes most runtime events to the old `backend.app.modules.crawler.events.bus.event_bus`. That is why `/api/events/stream` only sends `system.connected`.

## File Structure

- Modify `backend/app/modules/crawler/runtime/service.py`: route runtime status/detail/log events through existing realtime helpers instead of the old crawler event bus.
- Modify `backend/tests/test_crawler_worker_service.py`: add a failing regression test that subscribes to `backend.app.modules.realtime.bus.event_bus` and proves `_execute_run()` publishes run-detail events.
- Modify `frontend/tests/realtime-event-source-client.test.ts`: add a client regression test for `crawler.run.log.appended` dispatch. No frontend production code should be needed unless the test exposes a real client gap.
- Verify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`: no code change expected; it already subscribes to `crawler.run.updated`, `crawler.run.detail.updated`, and `crawler.run.log.appended`.

## Non-Goals

- Do not delete `/api/crawler/stream` in this fix.
- Do not migrate every old crawler SSE test in `backend/tests/test_crawler_sse_events.py`.
- Do not add Redis pub/sub fanout. This fix stays within the current process-local realtime bus design.
- Do not reintroduce polling on `RunDetailPage`.

---

### Task 1: Prove Runtime Events Miss `/api/events/stream`

**Files:**
- Modify: `backend/tests/test_crawler_worker_service.py`

- [ ] **Step 1: Add imports for realtime queue assertions**

Modify the top of `backend/tests/test_crawler_worker_service.py`.

Change:

```python
from datetime import datetime
```

to:

```python
from datetime import datetime
from queue import Empty
```

The file already imports `select`, `CrawlRun`, `CrawlTask`, and `TestingSessionLocal`; no other import changes are needed for this step.

- [ ] **Step 2: Add a helper to drain realtime events**

Append this helper after `create_run_with_task()`:

```python
def drain_realtime_events(queue) -> list:
    events = []
    while True:
        try:
            events.append(queue.get_nowait())
        except Empty:
            return events
```

- [ ] **Step 3: Write the failing runtime realtime test**

Append this test after `test_execute_run_persists_movie_before_marking_detail_saved`:

```python
def test_execute_run_publishes_run_detail_events_to_realtime_bus(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.service import _execute_run
    from backend.app.modules.realtime.bus import event_bus as realtime_bus

    monkeypatch.setattr("scraper.services.movie_service.MovieService", lambda: PersistingMovieServiceStub())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("realtime")
    task = session.get(CrawlTask, run.task_id)
    owner_id = str(task.owner_id)
    queue = realtime_bus.subscribe(owner_id)

    try:
        _execute_run(session, session.get(CrawlRun, run.id), runtime)
        events = drain_realtime_events(queue)
    finally:
        realtime_bus.unsubscribe(owner_id, queue)

    event_names = [event.event for event in events]
    assert "crawler.run.detail.updated" in event_names
    assert "crawler.run.log.appended" in event_names
    assert "crawler.run.updated" in event_names

    log_events = [event for event in events if event.event == "crawler.run.log.appended"]
    assert any(event.payload["run_id"] == str(run.id) and "入库成功" in event.payload["log"]["message"] for event in log_events)

    detail_events = [event for event in events if event.event == "crawler.run.detail.updated"]
    assert any(
        event.resource_id == str(run.id)
        and event.payload["run_id"] == str(run.id)
        and any(task_payload["status"] == "saved" for task_payload in event.payload["tasks"])
        for event in detail_events
    )
```

- [ ] **Step 4: Run the failing test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_execute_run_publishes_run_detail_events_to_realtime_bus -v
```

Expected: FAIL because the runtime currently publishes log/status/task events to `backend.app.modules.crawler.events.bus.event_bus`, while this test subscribes to `backend.app.modules.realtime.bus.event_bus`.

- [ ] **Step 5: Keep the failing test unstaged until implementation passes**

Do not commit yet. This is the RED step; commit it together with the implementation after the focused test passes.

---

### Task 2: Publish Runtime Logs To The Realtime Bus

**Files:**
- Modify: `backend/app/modules/crawler/runtime/service.py`

- [ ] **Step 1: Add runtime payload imports**

In `backend/app/modules/crawler/runtime/service.py`, keep the old crawler event imports for now because status/detail publish calls are removed in Task 3. Add this import near the other crawler run imports:

```python
from backend.app.modules.crawler.runs.schemas import CrawlRunDetailTaskRead, CrawlRunRead
```

- [ ] **Step 2: Add serializers for realtime payloads**

Add these helpers immediately after `process_run()` and before `_append_run_log()`:

```python
def _run_payload(run: CrawlRun) -> dict[str, Any]:
    payload = CrawlRunRead.model_validate(run).model_dump(mode="json")
    payload["logs"] = []
    return payload


def _detail_payload(detail: CrawlRunDetailTask) -> dict[str, Any]:
    return CrawlRunDetailTaskRead.model_validate(detail).model_dump(mode="json")
```

- [ ] **Step 3: Make `_append_run_log` return the persisted entry**

Replace `_append_run_log()` with:

```python
def _append_run_log(run_id: str, message: str, level: str = "INFO", **context: Any) -> dict[str, Any] | None:
    from backend.app.modules.crawler.runs.logs import append_run_log, build_run_log

    entry = build_run_log(level, message, **context)
    try:
        append_run_log(run_id, entry)
    except Exception as exc:
        logger.warning("Failed to append crawler run log for %s: %s", run_id, exc)
        return None
    return entry
```

- [ ] **Step 4: Replace `append_run_log_for_run()` with the realtime implementation**

Replace the existing `append_run_log_for_run()` function with:

```python
def append_run_log_for_run(
    db: Session,
    run: CrawlRun,
    message: str,
    level: str = "INFO",
    **context: Any,
) -> None:
    from backend.app.modules.realtime.bus import event_bus as realtime_bus
    from backend.app.modules.realtime.schemas import make_realtime_event

    entry = _append_run_log(str(run.id), message, level, **context)
    if entry is None:
        return

    owner_id = _run_owner_id(db, run)
    if owner_id is None:
        return

    realtime_bus.publish(
        make_realtime_event(
            event="crawler.run.log.appended",
            scope="crawler.run",
            owner_id=owner_id,
            resource_id=str(run.id),
            payload={"run_id": str(run.id), "log": entry},
        )
    )
```

- [ ] **Step 5: Replace `_execute_run()` log calls**

In `_execute_run()`, replace every call shaped like:

```python
_append_run_log(str(run.id), "message", "LEVEL", key=value)
```

with:

```python
append_run_log_for_run(db, run, "message", "LEVEL", key=value)
```

Apply these exact replacements:

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
append_run_log_for_run(db, run, f"筛选列表已同步: 演员={sync_result['actors']}, 标签={sync_result['tags']}, 导演={sync_result['directors']}, 片商={sync_result['makers']}, 系列={sync_result['series']}", "INFO")
append_run_log_for_run(db, run, f"筛选列表同步失败: {sync_exc}", "WARNING")
append_run_log_for_run(db, run, "MovieService 不可用，使用空结果完成运行", "WARNING")
```

- [ ] **Step 6: Run the focused test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_execute_run_publishes_run_detail_events_to_realtime_bus -v
```

Expected: still FAIL on missing `crawler.run.detail.updated` or `crawler.run.updated`, but `crawler.run.log.appended` should now be present in the drained realtime events.

- [ ] **Step 7: Keep Task 2 changes unstaged until Task 3 passes**

Do not commit yet. The focused test is intentionally still red until status and detail events are moved to the realtime bus in Task 3.

---

### Task 3: Publish Run Status And Detail Updates To The Realtime Bus

**Files:**
- Modify: `backend/app/modules/crawler/runtime/service.py`

- [ ] **Step 1: Replace `publish_run_updated()` with serializer-based payload**

Replace `publish_run_updated()` with:

```python
def publish_run_updated(db: Session, run: CrawlRun) -> None:
    from backend.app.modules.realtime.bus import event_bus as realtime_bus
    from backend.app.modules.realtime.schemas import make_realtime_event

    owner_id = _run_owner_id(db, run)
    if owner_id is None:
        return
    realtime_bus.publish(
        make_realtime_event(
            event="crawler.run.updated",
            scope="crawler.run",
            owner_id=owner_id,
            resource_id=str(run.id),
            payload=_run_payload(run),
        )
    )
```

- [ ] **Step 2: Replace `publish_run_detail_updated()` with full detail payloads**

Replace `publish_run_detail_updated()` with:

```python
def publish_run_detail_updated(
    db: Session,
    run: CrawlRun,
    details: list[CrawlRunDetailTask],
) -> None:
    from backend.app.modules.realtime.bus import event_bus as realtime_bus
    from backend.app.modules.realtime.schemas import make_realtime_event

    owner_id = _run_owner_id(db, run)
    if owner_id is None or not details:
        return
    realtime_bus.publish(
        make_realtime_event(
            event="crawler.run.detail.updated",
            scope="crawler.run",
            owner_id=owner_id,
            resource_id=str(run.id),
            payload={
                "run_id": str(run.id),
                "tasks": [_detail_payload(detail) for detail in details],
            },
        )
    )
```

- [ ] **Step 3: Publish running and failed status from `process_run()`**

In `process_run()`, replace this block:

```python
        db.commit()
        event_bus.publish(RunStatusEvent(
            run_id=run_id,
            status="running",
            task_name=run.task_name or "",
        ))
```

with:

```python
        db.commit()
        publish_run_updated(db, run)
```

In the `except Exception as exc:` block inside `process_run()`, replace:

```python
            db.commit()
            event_bus.publish(RunStatusEvent(
                run_id=run_id,
                status="failed",
                task_name=run.task_name or "",
                error=str(exc)[:1000],
            ))
```

with:

```python
            db.commit()
            publish_run_updated(db, run)
```

- [ ] **Step 4: Publish created detail tasks**

Inside `_execute_run()`, in `on_tasks_batch_created()`, add a list before the loop:

```python
        created_details: list[CrawlRunDetailTask] = []
```

After each `remember_detail(detail)`, add:

```python
            created_details.append(detail)
```

After the existing `db.commit()` in `on_tasks_batch_created()`, add:

```python
        publish_run_detail_updated(db, run, created_details)
```

- [ ] **Step 5: Publish detail updates after saved/save_failed**

Inside `on_item_saved()`, after the existing `db.commit()` at the end of the function, add:

```python
        if detail:
            publish_run_detail_updated(db, run, [detail])
```

The end of `on_item_saved()` should look like:

```python
        ))
        db.commit()
        if detail:
            publish_run_detail_updated(db, run, [detail])
```

- [ ] **Step 6: Publish detail updates after crawl_failed**

Inside `on_detail_failed()`, after the existing `db.commit()`, add:

```python
        if detail:
            publish_run_detail_updated(db, run, [detail])
```

The block should look like:

```python
        progress["failed"] += 1
        runtime.write_progress(str(run.id), progress)
        db.commit()
        if detail:
            publish_run_detail_updated(db, run, [detail])
```

- [ ] **Step 7: Publish detail updates after already_exists**

Inside `on_item_already_exists()`, after the existing `db.commit()`, add:

```python
        if detail:
            publish_run_detail_updated(db, run, [detail])
```

The block should look like:

```python
        if not was_skipped:
            progress["skipped"] += 1
        runtime.write_progress(str(run.id), progress)
        db.commit()
        if detail:
            publish_run_detail_updated(db, run, [detail])
```

- [ ] **Step 8: Publish completed status after `finished_at` is committed**

Near the end of `_execute_run()`, remove this old publish block:

```python
        event_bus.publish(RunStatusEvent(
            run_id=str(run.id),
            status="completed",
            task_name=run.task_name or "",
        ))
```

Replace the function ending:

```python
    run.finished_at = datetime.now()
    db.commit()
```

with:

```python
    run.finished_at = datetime.now()
    db.commit()
    publish_run_updated(db, run)
```

- [ ] **Step 9: Remove old crawler-event imports from runtime service**

After Steps 1-8, remove these imports from `backend/app/modules/crawler/runtime/service.py`:

```python
from backend.app.modules.crawler.events.bus import event_bus
from backend.app.modules.crawler.events.schemas import (
    RunLogEvent,
    RunProgressEvent,
    RunStatusEvent,
    TaskStatusEvent,
)
```

Run this search:

```bash
rg -n "RunLogEvent|RunProgressEvent|RunStatusEvent|TaskStatusEvent|crawler.events.bus|event_bus\\.publish" backend/app/modules/crawler/runtime/service.py
```

Expected: no matches.

- [ ] **Step 10: Run the focused realtime runtime test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_execute_run_publishes_run_detail_events_to_realtime_bus -v
```

Expected: PASS. The realtime queue should contain `crawler.run.log.appended`, `crawler.run.detail.updated`, and `crawler.run.updated`.

- [ ] **Step 11: Commit Task 1-3 together**

```bash
git add backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_worker_service.py
git commit -m "fix: publish crawler run updates to realtime stream"
```

---

### Task 4: Frontend EventSource Client Regression

**Files:**
- Modify: `frontend/tests/realtime-event-source-client.test.ts`

- [ ] **Step 1: Add a log-event dispatch test**

Append this test to `frontend/tests/realtime-event-source-client.test.ts`:

```ts
  it('delivers crawler run log appended events to subscribers', () => {
    const handler = vi.fn()
    subscribeRealtime('crawler.run.log.appended', handler)
    connectRealtime()

    FakeEventSource.instances[0].emit('crawler.run.log.appended', {
      id: 'event-log-1',
      event: 'crawler.run.log.appended',
      scope: 'crawler.run',
      resource_id: 'run-1',
      owner_id: 'user-1',
      payload: {
        run_id: 'run-1',
        log: {
          timestamp: '2026-07-03T04:06:58Z',
          level: 'INFO',
          component: 'crawler.run',
          event: 'run_log',
          message: '详情 1/53 跳过',
          context: { reason: 'already_exists' },
        },
      },
      created_at: '2026-07-03T04:06:58Z',
    })

    expect(handler).toHaveBeenCalledWith(expect.objectContaining({
      event: 'crawler.run.log.appended',
      resource_id: 'run-1',
      payload: expect.objectContaining({
        run_id: 'run-1',
        log: expect.objectContaining({
          message: '详情 1/53 跳过',
        }),
      }),
    }))
  })
```

- [ ] **Step 2: Run the frontend realtime client test**

Run:

```bash
cd frontend && npm test -- realtime-event-source-client.test.ts
```

Expected: PASS. If it fails because `crawler.run.log.appended` is missing from `EVENT_NAMES`, add it to `frontend/src/realtime/eventSourceClient.ts` and `frontend/src/realtime/types.ts`; in the current repository it is already listed, so no production frontend change should be needed.

- [ ] **Step 3: Commit Task 4**

```bash
git add frontend/tests/realtime-event-source-client.test.ts
git commit -m "test: cover realtime crawler log events"
```

---

### Task 5: Regression Verification

**Files:**
- Verify: `backend/app/modules/crawler/runtime/service.py`
- Verify: `backend/app/modules/realtime/router.py`
- Verify: `frontend/src/realtime/eventSourceClient.ts`
- Verify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_realtime_events.py backend/tests/test_crawler_worker_service.py -v
```

Expected: PASS. This verifies the `/api/events/stream` event model and the crawler runtime realtime publish path.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd frontend && npm test -- realtime-event-source-client.test.ts
```

Expected: PASS. This verifies the client dispatches `crawler.run.log.appended` events to subscribers.

- [ ] **Step 3: Run backend suite**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/ -v
```

Expected: PASS. This catches regressions in old crawler SSE tests, realtime tests, run APIs, and crawler worker behavior.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. Existing Vite warnings about large chunks or dynamic imports are acceptable if the command exits with status 0.

- [ ] **Step 5: Manual stream sanity check**

Start the backend, open a run detail page, then start a crawler run. In browser devtools, inspect `/api/events/stream?token=...`.

Expected event sequence:

```text
event: system.connected
event: crawler.run.updated
event: crawler.run.detail.updated
event: crawler.run.log.appended
event: crawler.run.detail.updated
event: crawler.run.updated
```

The exact count depends on the run, but after `system.connected` there must be crawler events while backend logs continue.

---

## Self-Review Result

- Spec coverage: The plan addresses the observed symptom, the old/new event bus mismatch, backend runtime publish points, frontend EventSource dispatch, and focused regression verification.
- Placeholder scan: No placeholder tasks remain; each code step includes concrete edits or complete snippets.
- Type consistency: Backend events use `RealtimeEvent` names already consumed by `frontend/src/realtime/types.ts`, and payloads match `RunDetailPage.tsx` expectations: `CrawlerRun`, `{ run_id, tasks }`, and `{ run_id, log }`.
