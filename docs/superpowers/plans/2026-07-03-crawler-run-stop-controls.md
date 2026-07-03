# Crawler Run Stop And Delete Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reliable stop/delete controls to crawler run list/detail pages, keep stopped runs restartable by resetting unfinished child tasks to `pending_crawl`, and delete only run records plus their child detail tasks.

**Architecture:** The backend already exposes `/api/crawler/runs/{run_id}/stop` and `/restart`; stop should keep that existing child-task retry behavior by resetting unfinished detail tasks to `pending_crawl`, while the run itself becomes `stopped`. Restart reuses the same `crawl_runs` row: it clears terminal run metadata, sets the same row back to `queued`, and enqueues the same run ID instead of creating a new run. Restart mode is stage-aware: if detail processing had not started, partial list results are discarded and the list phase starts from page 1; if detail processing had started, the worker skips list collection and only retries unfinished detail rows. The worker must pass `stop_check` into the crawler service, avoid finalizing a user-stopped run as `completed`, and preload existing detail tasks so an in-place detail restart updates existing child rows instead of creating duplicates. A new `DELETE /api/crawler/runs/{run_id}` endpoint deletes only the selected `crawl_runs` row and its `crawl_run_detail_tasks` children through the existing relationship cascade; it does not touch movies, magnets, filters, crawl task definitions, or source task links.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Redis-backed runtime state, Pytest, React 19, TypeScript 6, Ant Design 6, Vitest, React Testing Library.

---

## Current Situation

- `frontend/src/pages/crawler/runs/RunListPage.tsx` already renders stop for `queued`/`running` runs and restart for `stopped`/`failed` runs.
- `frontend/src/pages/crawler/runs/RunDetailPage.tsx` has no stop/restart controls.
- `backend/app/modules/crawler/runtime/service.py:stop_run()` sets the run to `stopped`, but resets unfinished child tasks to `pending_crawl`.
- `backend/app/modules/crawler/runtime/service.py:_execute_run()` calls `MovieService.crawl_javdb_task()` without `stop_check`, so a running worker may continue and later mark the run `completed`.
- `restart_run()` currently creates a new `crawl_runs` row with `resumed_from`. The desired behavior is in-place restart on the same run ID, so list/detail history stays on the current record.
- Current runtime always calls the full `MovieService.crawl_javdb_task()` path, which starts at list collection. In-place detail restart needs a direct detail-only path.
- There is no delete endpoint/action for run records. Deleting a run should remove only `crawl_runs` and related `crawl_run_detail_tasks`.

## Stop/Restart Semantics

- Stop is allowed only for `queued` and `running` runs.
- Stopping a run sets `crawl_runs.status = "stopped"`, `finished_at = now`, and `error = "用户停止任务"`.
- Stopping resets unfinished detail tasks to `pending_crawl` with `error = None`; terminal detail tasks `saved` and `skipped` are preserved.
- Restart is allowed for `stopped` and `failed` runs.
- Restart mutates the current run row in place: `status = "queued"`, `queued_at = now`, `started_at = None`, `finished_at = None`, `error = None`, and `result = None`.
- Restart skips terminal child tasks: `saved` and `skipped` are never retried.
- Restart resets retryable detail tasks with source statuses `pending_crawl`, `crawl_failed`, and `save_failed` to `pending_crawl`.
- List-stage restart: if no detail row has entered detail processing, delete existing child rows for the run and start list collection from page 1.
- Detail-stage restart: if any detail row has entered detail processing, keep child rows, skip list collection, and run only retryable detail rows.
- Detail processing is considered started when any detail row has `status` in `saved`, `crawl_failed`, `save_failed` or has `crawled_at`/`saved_at` set. List-stage `skipped` rows without `crawled_at` do not count as detail-started.
- Existing `pending_crawl` child rows alone do not mean detail processing started, because list collection creates child rows incrementally before detail crawling begins.
- If a stopped run has no child tasks but still has `task_id`, restart requeues the same run without precreated detail tasks; the worker will collect the task URLs again.
- Restart returns the same run ID and does not create a new `crawl_runs` row.
- Delete is available from the run list for non-running runs. Deleting a run removes the run row and its detail rows only.

## File Structure

- Modify `backend/app/modules/crawler/runtime/service.py`: centralize restart stage detection, reset unfinished details to `pending_crawl`, clear partial list-stage child rows, pass `stop_check` to `MovieService`, prevent stopped runs from being finalized as completed, make restart requeue the same run ID, use a detail-only crawl path for detail-stage restarts, and add run deletion.
- Modify `backend/app/modules/crawler/runs/router.py`: add `DELETE /api/crawler/runs/{run_id}`.
- Modify `backend/tests/test_crawler_runs_api.py`: cover stop detail reset, in-place restart for stopped queued runs with and without detail tasks, and delete semantics.
- Modify `backend/tests/test_crawler_worker_service.py`: cover worker stop-check propagation, stopped finalization, and existing detail reuse on in-place restart.
- Modify `scraper/services/movie_service.py`: add a detail-only crawl method that reuses `JavdbSpider.run_detail_tasks()` and the existing item pipeline.
- Modify `frontend/src/api/crawlerRun/index.ts`: add `deleteCrawlerRun(runId)`.
- Modify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`: add stop/restart controls in the detail card and refresh the current run after actions.
- Modify `frontend/tests/crawler-run-detail.ui.test.tsx`: test detail-page stop and restart controls.
- Modify `frontend/src/pages/crawler/runs/RunListPage.tsx`: add delete action for non-running runs.
- Modify `frontend/tests/crawler-runs.ui.test.tsx`: add list-page stop and delete regression tests.

---

### Task 1: Backend Stop And Restart State Semantics

**Files:**
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/app/modules/crawler/runs/router.py`
- Modify: `backend/tests/test_crawler_runs_api.py`

- [ ] **Step 1: Write failing API tests for pending child task reset**

In `backend/tests/test_crawler_runs_api.py`, add these tests after `test_stop_running_run_sets_stop_signal`:

```python
def test_stop_running_run_resets_unfinished_detail_tasks_to_pending(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="running", crawl_mode="incremental")
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="P", source_url="https://p", source_name="P", status="pending_crawl", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="C", source_url="https://c", source_name="C", status="crawl_failed", error="timeout", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="F", source_url="https://f", source_name="F", status="save_failed", error="db", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="S", source_url="https://s", source_name="S", status="saved", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="K", source_url="https://k", source_name="K", status="skipped", created_at=datetime.now()),
    ])
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(f"/api/crawler/runs/{run.id}/stop", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["status"] == "stopped"
    assert runtime.stopped == [str(run.id)]

    session.expire_all()
    statuses = {
        row.code: (row.status, row.error)
        for row in session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    }
    assert statuses["P"] == ("pending_crawl", None)
    assert statuses["C"] == ("pending_crawl", None)
    assert statuses["F"] == ("pending_crawl", None)
    assert statuses["S"] == ("saved", None)
    assert statuses["K"] == ("skipped", None)
```

Add this delete test after `test_restart_copies_unfinished_subtasks`:

```python
def test_delete_run_removes_only_run_and_detail_tasks(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="completed", crawl_mode="incremental")
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="A", source_url="https://a", source_name="A", status="saved", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="B", source_url="https://b", source_name="B", status="pending_crawl", created_at=datetime.now()),
    ])
    session.commit()

    response = client.delete(f"/api/crawler/runs/{run.id}", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"] == {"id": str(run.id), "deleted": True}
    session.expire_all()
    assert session.get(CrawlRun, run.id) is None
    assert session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).count() == 0
```

Add this in-place restart test after it:

```python
def test_restart_after_detail_phase_requeues_same_run_and_keeps_terminal_details(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = task_response.json()["data"]["id"]
    session = TestingSessionLocal()
    run = CrawlRun(
        task_id=task_id,
        task_name="任务",
        status="stopped",
        crawl_mode="incremental",
        queued_at=datetime.now(),
        started_at=datetime.now(),
        finished_at=datetime.now(),
        result={"stopped": True},
        error="用户停止任务",
    )
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="A", source_url="https://a", source_name="A", status="saved", created_at=datetime.now(), crawled_at=datetime.now(), saved_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="B", source_url="https://b", source_name="B", status="crawl_failed", error="timeout", created_at=datetime.now(), crawled_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="C", source_url="https://c", source_name="C", status="skipped", error="already_exists", created_at=datetime.now(), crawled_at=datetime.now()),
    ])
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(f"/api/crawler/runs/{run.id}/restart", headers=headers)

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["id"] == str(run.id)
    assert body["status"] == "queued"
    assert body["task_id"] == task_id
    assert body["started_at"] is None
    assert body["finished_at"] is None
    assert body["result"] is None
    assert body["error"] is None
    assert runtime.enqueued == [str(run.id)]

    tasks_response = client.get(f"/api/crawler/runs/{run.id}/tasks", headers=headers)
    rows = tasks_response.json()["rows"]
    assert [(row["code"], row["status"], row["error"]) for row in rows] == [
        ("A", "saved", None),
        ("B", "pending_crawl", None),
        ("C", "skipped", "already_exists"),
    ]
```

Add this list-stage restart test after it:

```python
def test_restart_after_list_phase_discards_partial_list_tasks_and_requeues_same_run(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = task_response.json()["data"]["id"]
    session = TestingSessionLocal()
    run = CrawlRun(task_id=task_id, task_name="任务", status="stopped", crawl_mode="incremental")
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="P", source_url="https://p", source_name="P", status="pending_crawl", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="K", source_url="https://k", source_name="K", status="skipped", error="already_exists", created_at=datetime.now()),
    ])
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(f"/api/crawler/runs/{run.id}/restart", headers=headers)

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["id"] == str(run.id)
    assert body["status"] == "queued"
    assert body["task_id"] == task_id
    assert runtime.enqueued == [str(run.id)]

    tasks_response = client.get(f"/api/crawler/runs/{run.id}/tasks", headers=headers)
    assert tasks_response.json()["rows"] == []
```

Add this no-detail in-place restart test after it:

```python
def test_restart_stopped_run_without_subtasks_requeues_same_run(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = task_response.json()["data"]["id"]
    session = TestingSessionLocal()
    run = CrawlRun(task_id=task_id, task_name="任务", status="stopped", crawl_mode="incremental")
    session.add(run)
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(f"/api/crawler/runs/{run.id}/restart", headers=headers)

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["id"] == str(run.id)
    assert body["status"] == "queued"
    assert body["task_id"] == task_id
    assert runtime.enqueued == [str(run.id)]

    tasks_response = client.get(f"/api/crawler/runs/{run.id}/tasks", headers=headers)
    assert tasks_response.json()["rows"] == []
```

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py::test_stop_running_run_resets_unfinished_detail_tasks_to_pending backend/tests/test_crawler_runs_api.py::test_delete_run_removes_only_run_and_detail_tasks backend/tests/test_crawler_runs_api.py::test_restart_after_detail_phase_requeues_same_run_and_keeps_terminal_details backend/tests/test_crawler_runs_api.py::test_restart_after_list_phase_discards_partial_list_tasks_and_requeues_same_run backend/tests/test_crawler_runs_api.py::test_restart_stopped_run_without_subtasks_requeues_same_run -v
```

Expected: FAIL because the delete endpoint does not exist yet and restart currently creates a new run instead of requeueing the same run.

- [ ] **Step 3: Add stop/restart constants and helper**

In `backend/app/modules/crawler/runtime/service.py`, replace:

```python
UNFINISHED_DETAIL_STATUSES = {"pending_crawl", "crawl_failed", "save_failed"}
```

with:

```python
UNFINISHED_DETAIL_STATUSES = {"pending_crawl", "crawl_failed", "save_failed"}
RESTARTABLE_DETAIL_STATUSES = UNFINISHED_DETAIL_STATUSES
TERMINAL_DETAIL_STATUSES = {"saved", "skipped"}
```

Add this helper below `cleanup_interrupted_runs()`:

```python
DETAIL_PHASE_STARTED_STATUSES = {"saved", "crawl_failed", "save_failed"}


def has_detail_phase_started(db: Session, run: CrawlRun) -> bool:
    return db.query(CrawlRunDetailTask.id).filter(
        CrawlRunDetailTask.run_id == run.id,
        (
            CrawlRunDetailTask.status.in_(DETAIL_PHASE_STARTED_STATUSES)
            | CrawlRunDetailTask.crawled_at.isnot(None)
            | CrawlRunDetailTask.saved_at.isnot(None)
        ),
    ).first() is not None


def reset_unfinished_detail_tasks_to_pending(
    db: Session,
    run: CrawlRun,
) -> list[CrawlRunDetailTask]:
    details = (
        db.query(CrawlRunDetailTask)
        .filter(
            CrawlRunDetailTask.run_id == run.id,
            CrawlRunDetailTask.status.notin_(TERMINAL_DETAIL_STATUSES),
        )
        .order_by(CrawlRunDetailTask.created_at.asc())
        .all()
    )
    for detail in details:
        detail.status = "pending_crawl"
        detail.error = None
        detail.crawled_at = None
        detail.saved_at = None
    db.flush()
    return details


def clear_run_detail_tasks(db: Session, run: CrawlRun) -> None:
    db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).delete(synchronize_session=False)
```

- [ ] **Step 4: Update cleanup for interrupted runs**

In `cleanup_interrupted_runs()`, replace the loop body:

```python
    for run in rows:
        run.status = "stopped"
        run.finished_at = run.finished_at or now
        run.error = "服务重启，任务已停止，需手动重启"
```

with:

```python
    for run in rows:
        run.status = "stopped"
        run.finished_at = run.finished_at or now
        run.error = "服务重启，任务已停止，需手动重启"
        reset_unfinished_detail_tasks_to_pending(db, run)
```

- [ ] **Step 5: Update stop_run to reset child tasks to pending**

In `CrawlerRunService.stop_run()`, replace:

```python
        self.runtime.request_stop(str(run.id))
        run.status = "stopped"
        run.finished_at = datetime.now()
        # Reset unfinished detail tasks so they can be retried on restart
        self.db.query(CrawlRunDetailTask).filter(
            CrawlRunDetailTask.run_id == run.id,
            CrawlRunDetailTask.status.in_(UNFINISHED_DETAIL_STATUSES),
        ).update({"status": "pending_crawl", "error": None})
        self.db.commit()
        self.db.refresh(run)
        publish_run_updated(self.db, run)
        return run
```

with:

```python
        self.runtime.request_stop(str(run.id))
        run.status = "stopped"
        run.finished_at = datetime.now()
        run.error = "用户停止任务"
        reset_details = reset_unfinished_detail_tasks_to_pending(self.db, run)
        self.db.commit()
        self.db.refresh(run)
        if reset_details:
            publish_run_detail_updated(self.db, run, reset_details)
        publish_run_updated(self.db, run)
        return run
```

- [ ] **Step 6: Update restart_run to requeue the same run**

Replace `CrawlerRunService.restart_run()` with:

```python
    def restart_run(self, run_id: uuid.UUID) -> CrawlRun:
        run = self.db.get(CrawlRun, run_id)
        if run is None:
            raise ValueError("运行记录不存在")
        if run.status not in {"stopped", "failed"}:
            raise ValueError("只能重启已停止或失败的运行")
        if run.task_id is None:
            restartable_count = (
                self.db.query(CrawlRunDetailTask)
                .filter(
                    CrawlRunDetailTask.run_id == run.id,
                    CrawlRunDetailTask.status.in_(RESTARTABLE_DETAIL_STATUSES),
                )
                .count()
            )
            if restartable_count == 0:
                raise ValueError("没有关联任务或未完成子任务，无法重启")

        if has_detail_phase_started(self.db, run):
            reset_unfinished_detail_tasks_to_pending(self.db, run)
        else:
            clear_run_detail_tasks(self.db, run)
        run.status = "queued"
        run.queued_at = datetime.now()
        run.started_at = None
        run.finished_at = None
        run.result = None
        run.error = None
        self.db.commit()
        self.db.refresh(run)
        self.runtime.enqueue_run(str(run.id))
        self._ensure_worker_started()
        publish_run_updated(self.db, run)
        return run
```

- [ ] **Step 7: Add the delete run endpoint**

In `backend/app/modules/crawler/runs/router.py`, add this endpoint after `get_run_logs()` and before `list_run_tasks()`:

```python
@router.delete("/{run_id}")
def delete_run(run_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status in {"queued", "running"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="运行中任务不能删除，请先停止")
    db.delete(run)
    db.commit()
    return success(data={"id": str(run_id), "deleted": True})
```

The `CrawlRun.detail_tasks` relationship already has `cascade="all, delete-orphan"`, so deleting the run row removes its `crawl_run_detail_tasks` rows without touching any movie/content/task tables.

- [ ] **Step 8: Run API tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py::test_stop_running_run_resets_unfinished_detail_tasks_to_pending backend/tests/test_crawler_runs_api.py::test_delete_run_removes_only_run_and_detail_tasks backend/tests/test_crawler_runs_api.py::test_restart_after_detail_phase_requeues_same_run_and_keeps_terminal_details backend/tests/test_crawler_runs_api.py::test_restart_after_list_phase_discards_partial_list_tasks_and_requeues_same_run backend/tests/test_crawler_runs_api.py::test_restart_stopped_run_without_subtasks_requeues_same_run -v
```

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

```bash
git add backend/app/modules/crawler/runtime/service.py backend/app/modules/crawler/runs/router.py backend/tests/test_crawler_runs_api.py
git commit -m "fix: stop and delete crawler runs"
```

---

### Task 2: Worker Stop Propagation

**Files:**
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/tests/test_crawler_worker_service.py`
- Modify: `scraper/services/movie_service.py`

- [ ] **Step 1: Write failing worker stop test**

In `backend/tests/test_crawler_worker_service.py`, add this runtime and stub near the existing `Runtime` and service stub classes:

```python
class StopRequestedRuntime(Runtime):
    def is_stop_requested(self, run_id):
        return True


class StopAwareMovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        assert kwargs["stop_check"]() is True
        kwargs["on_tasks_batch_created"]([
            {"code": "STOP-001", "url": "https://javdb.com/v/stop001", "name": "STOP 001"}
        ])
        return {
            "total_tasks": 1,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "stopped": True,
        }


class ExistingDetailReuseMovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        raise AssertionError("detail-stage restart must not run list collection")

    def crawl_javdb_detail_tasks(self, task, detail_tasks, **kwargs):
        assert [item["code"] for item in detail_tasks] == ["REUSE-001"]
        kwargs["on_item_saved"](
            {"code": "REUSE-001", "url": "https://javdb.com/v/reuse001", "name": "REUSE 001"},
            {"code": "REUSE-001", "source_url": "https://javdb.com/v/reuse001", "source_name": "REUSE 001"},
        )
        return {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}


class ListPhaseRestartMovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        kwargs["on_tasks_batch_created"]([
            {"code": "LIST-001", "url": "https://javdb.com/v/list001", "name": "LIST 001"}
        ])
        return {"total_tasks": 1, "completed_tasks": 0, "failed_tasks": 0}

    def crawl_javdb_detail_tasks(self, task, detail_tasks, **kwargs):
        raise AssertionError("list-stage restart must rerun list collection")
```

Add this test near the other `_execute_run` tests:

```python
def test_execute_run_stops_when_runtime_stop_requested(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.service import _execute_run

    monkeypatch.setattr("scraper.services.movie_service.MovieService", lambda: StopAwareMovieServiceStub())
    session = TestingSessionLocal()
    run, _runtime = create_run_with_task("stop-requested")
    runtime = StopRequestedRuntime(str(run.id))

    _execute_run(session, session.get(CrawlRun, run.id), runtime)

    session.expire_all()
    refreshed = session.get(CrawlRun, run.id)
    detail = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "STOP-001").one()
    assert refreshed.status == "stopped"
    assert refreshed.finished_at is not None
    assert refreshed.result["stopped"] is True
    assert detail.status == "pending_crawl"
    assert detail.error is None
```

Add this test after it:

```python
def test_execute_run_reuses_existing_detail_task_on_in_place_restart(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.service import _execute_run

    monkeypatch.setattr("scraper.services.movie_service.MovieService", lambda: ExistingDetailReuseMovieServiceStub())
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service._persist_crawled_item", lambda db, item_data: uuid.uuid4())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("reuse-existing")
    existing = CrawlRunDetailTask(
        run_id=run.id,
        task_name="任务",
        code="REUSE-001",
        source_url="https://javdb.com/v/reuse001",
        source_name="REUSE 001",
        status="pending_crawl",
        created_at=datetime.now(),
    )
    session.add(existing)
    session.commit()

    _execute_run(session, session.get(CrawlRun, run.id), runtime)

    session.expire_all()
    details = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "REUSE-001").all()
    assert len(details) == 1
    assert details[0].status == "saved"
    assert details[0].error is None
```

Add this test after it:

```python
def test_execute_run_does_not_treat_list_stage_pending_details_as_detail_restart(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.service import _execute_run

    monkeypatch.setattr("scraper.services.movie_service.MovieService", lambda: ListPhaseRestartMovieServiceStub())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("list-stage")
    session.add(CrawlRunDetailTask(
        run_id=run.id,
        task_name="任务",
        code="LIST-OLD",
        source_url="https://javdb.com/v/list-old",
        source_name="LIST OLD",
        status="pending_crawl",
        created_at=datetime.now(),
    ))
    session.commit()

    _execute_run(session, session.get(CrawlRun, run.id), runtime)

    session.expire_all()
    codes = [row.code for row in session.query(CrawlRunDetailTask).order_by(CrawlRunDetailTask.created_at.asc()).all()]
    assert "LIST-001" in codes
```

- [ ] **Step 2: Run worker stop test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_execute_run_stops_when_runtime_stop_requested backend/tests/test_crawler_worker_service.py::test_execute_run_reuses_existing_detail_task_on_in_place_restart backend/tests/test_crawler_worker_service.py::test_execute_run_does_not_treat_list_stage_pending_details_as_detail_restart -v
```

Expected: FAIL because `_execute_run()` does not pass `stop_check`, still marks the run `completed`, and has no detail-only restart path.

- [ ] **Step 3: Pass stop_check into MovieService**

In `backend/tests/test_crawler_worker_service.py`, if `uuid` is not already imported, add it at the top:

```python
import uuid
```

In `backend/app/modules/crawler/runtime/service.py`, inside `_execute_run()`, replace the `movie_service.crawl_javdb_task(...)` call arguments:

```python
            on_detail_check_callback=on_detail_check_callback,
        )
```

with:

```python
            on_detail_check_callback=on_detail_check_callback,
            stop_check=lambda: runtime.is_stop_requested(str(run.id)),
        )
```

- [ ] **Step 4: Add a detail-only MovieService method**

In `scraper/services/movie_service.py`, add this method above `_build_detail_item()`:

```python
    def crawl_javdb_detail_tasks(self, task: CrawlTask, detail_tasks: list[dict], task_id: str = None, stop_check=None, log_callback=None, on_item_saved=None, on_detail_failed=None, on_detail_check_callback=None, on_item_already_exists=None) -> dict:
        if task.is_skip:
            if log_callback:
                log_callback(f"跳过任务: {task.name}", "INFO")
            return build_skipped_task_result(task)

        spider = self._build_spider()
        pipeline = MoviePipeline()
        collected_items: list[dict] = []

        def collect_completed_detail(detail_task: dict) -> None:
            item = self._build_detail_item(task, detail_task)
            if not item:
                return

            cleaned = pipeline.process_item(item, task_name=task.name, task_id=task_id)
            if cleaned is not None:
                collected_items.append(cleaned)
                msg = (
                    f"[{task.name}] 详情完成: code={cleaned.get('code')} "
                    f"source_task_name={cleaned.get('source_task_name')}"
                )
                print(msg)
                if log_callback:
                    log_callback(msg, "INFO")
                if on_item_saved:
                    on_item_saved(detail_task, cleaned)
            else:
                msg = f"[{task.name}] 跳过无效数据: code={item.get('code')}"
                print(msg)
                if log_callback:
                    log_callback(msg, "WARNING")

        processed_tasks = spider.run_detail_tasks(
            detail_tasks,
            task_name=task.name,
            on_detail_completed=collect_completed_detail,
            on_detail_failed=on_detail_failed,
            stop_check=stop_check,
            log_callback=log_callback,
            on_detail_check_callback=on_detail_check_callback,
            on_item_already_exists=on_item_already_exists,
        )

        stopped = stop_check() if stop_check else False
        return build_task_result(
            task=task,
            detail_tasks=processed_tasks,
            saved_items=collected_items,
            stopped=stopped,
        )
```

- [ ] **Step 5: Preload existing detail tasks**

In `_execute_run()`, after `find_detail()` and before `on_tasks_batch_created()`, add:

```python
    existing_details = (
        db.query(CrawlRunDetailTask)
        .filter(CrawlRunDetailTask.run_id == run.id)
        .order_by(CrawlRunDetailTask.created_at.asc())
        .all()
    )
    for detail in existing_details:
        remember_detail(detail)
```

- [ ] **Step 6: Reuse existing detail rows when list collection is used**

In `on_tasks_batch_created()`, replace the loop body:

```python
            detail = CrawlRunDetailTask(
                run_id=run.id,
                task_name=task.name,
                code=item.get("code"),
                source_url=item.get("url", ""),
                source_name=item.get("name", ""),
                status="skipped" if is_skipped else "pending_crawl",
                error=reason,
                created_at=datetime.now(),
            )
            db.add(detail)
            db.flush()
            remember_detail(detail)
            created_details.append(detail)
```

with:

```python
            detail = find_detail(item)
            if detail is None:
                detail = CrawlRunDetailTask(
                    run_id=run.id,
                    task_name=task.name,
                    code=item.get("code"),
                    source_url=item.get("url", ""),
                    source_name=item.get("name", ""),
                    status="skipped" if is_skipped else "pending_crawl",
                    error=reason,
                    created_at=datetime.now(),
                )
                db.add(detail)
                db.flush()
            elif detail.status not in {"saved", "skipped"}:
                detail.status = "skipped" if is_skipped else "pending_crawl"
                detail.error = reason
                detail.item_data = None
                detail.crawled_at = None
                detail.saved_at = None
            remember_detail(detail)
            created_details.append(detail)
```

- [ ] **Step 7: Route detail-stage restarts to the detail-only method**

In `_execute_run()`, add this helper after `on_detail_check_callback()`:

```python
    def detail_row_to_task_info(detail: CrawlRunDetailTask) -> dict[str, Any]:
        return {
            "code": detail.code,
            "url": detail.source_url,
            "name": detail.source_name,
        }
```

Then replace the existing `result = movie_service.crawl_javdb_task(...)` call with:

```python
        detail_phase_restart = has_detail_phase_started(db, run)
        restartable_existing_details = [
            detail for detail in existing_details
            if detail.status in RESTARTABLE_DETAIL_STATUSES
        ]
        if detail_phase_restart and restartable_existing_details:
            append_run_log_for_run(
                db,
                run,
                f"检测到已有详情子任务 {len(restartable_existing_details)} 条，跳过列表收集直接重试详情",
                "INFO",
            )
            result = movie_service.crawl_javdb_detail_tasks(
                task,
                detail_tasks=[detail_row_to_task_info(detail) for detail in restartable_existing_details],
                task_id=str(run.task_id) if run.task_id else None,
                on_item_saved=on_item_saved,
                on_detail_failed=on_detail_failed,
                on_item_already_exists=on_item_already_exists,
                log_callback=log_callback,
                on_detail_check_callback=on_detail_check_callback,
                stop_check=lambda: runtime.is_stop_requested(str(run.id)),
            )
        else:
            result = movie_service.crawl_javdb_task(
                task,
                task_id=str(run.task_id) if run.task_id else None,
                crawl_mode=run.crawl_mode,
                on_tasks_batch_created=on_tasks_batch_created,
                on_item_saved=on_item_saved,
                on_detail_failed=on_detail_failed,
                on_item_already_exists=on_item_already_exists,
                log_callback=log_callback,
                db_check_callback=db_check_callback,
                on_detail_check_callback=on_detail_check_callback,
                stop_check=lambda: runtime.is_stop_requested(str(run.id)),
            )
```

This intentionally excludes `saved` and `skipped` rows from `restartable_existing_details`, so detail-stage restart does not recrawl terminal child tasks. It also requires `detail_phase_restart` before using the detail-only path, so list-stage `pending_crawl` rows created during list collection do not cause the restart to skip list collection.

- [ ] **Step 8: Finalize stopped runs as stopped instead of completed**

In `_execute_run()`, replace the block starting at:

```python
        total_count = _count_run_detail_tasks(db, run.id)
        saved_count = _count_run_detail_tasks(db, run.id, "saved")
        save_failed_count = _count_run_detail_tasks(db, run.id, "save_failed")
        crawl_failed_count = _count_run_detail_tasks(db, run.id, "crawl_failed")
        skipped_count = _count_run_detail_tasks(db, run.id, "skipped")
        run.result = {
            **(result or {}),
            "total_tasks": total_count,
            "saved": saved_count,
            "save_failed": save_failed_count,
            "crawl_failed": crawl_failed_count,
            "skipped_tasks": skipped_count,
        }
        run.status = "completed"
        append_run_log_for_run(
            db, run,
            f"任务完成: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}, 跳过={skipped_count}",
            "INFO",
        )
        try:
            from scraper.database.repositories.filter_repository import sync_movie_filters

            sync_result = sync_movie_filters(db)
            append_run_log_for_run(
                db, run,
                f"筛选列表已同步: 演员={sync_result['actors']}, 标签={sync_result['tags']}, "
                f"导演={sync_result['directors']}, 片商={sync_result['makers']}, 系列={sync_result['series']}",
                "INFO",
            )
        except Exception as sync_exc:
            logger.warning("Failed to sync movie filters for run %s: %s", run.id, sync_exc)
            append_run_log_for_run(db, run, f"筛选列表同步失败: {sync_exc}", "WARNING")
```

with:

```python
        stopped = runtime.is_stop_requested(str(run.id)) or bool((result or {}).get("stopped"))
        if stopped:
            reset_details = reset_unfinished_detail_tasks_to_pending(db, run)
            if reset_details:
                publish_run_detail_updated(db, run, reset_details)

        total_count = _count_run_detail_tasks(db, run.id)
        saved_count = _count_run_detail_tasks(db, run.id, "saved")
        save_failed_count = _count_run_detail_tasks(db, run.id, "save_failed")
        crawl_failed_count = _count_run_detail_tasks(db, run.id, "crawl_failed")
        skipped_count = _count_run_detail_tasks(db, run.id, "skipped")
        run.result = {
            **(result or {}),
            "total_tasks": total_count,
            "saved": saved_count,
            "save_failed": save_failed_count,
            "crawl_failed": crawl_failed_count,
            "skipped_tasks": skipped_count,
            "stopped": stopped,
        }
        if stopped:
            run.status = "stopped"
            run.error = run.error or "用户停止任务"
            append_run_log_for_run(
                db,
                run,
                f"任务已停止: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}, 跳过={skipped_count}",
                "WARNING",
            )
        else:
            run.status = "completed"
            append_run_log_for_run(
                db, run,
                f"任务完成: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}, 跳过={skipped_count}",
                "INFO",
            )
            try:
                from scraper.database.repositories.filter_repository import sync_movie_filters

                sync_result = sync_movie_filters(db)
                append_run_log_for_run(
                    db, run,
                    f"筛选列表已同步: 演员={sync_result['actors']}, 标签={sync_result['tags']}, "
                    f"导演={sync_result['directors']}, 片商={sync_result['makers']}, 系列={sync_result['series']}",
                    "INFO",
                )
            except Exception as sync_exc:
                logger.warning("Failed to sync movie filters for run %s: %s", run.id, sync_exc)
                append_run_log_for_run(db, run, f"筛选列表同步失败: {sync_exc}", "WARNING")
```

- [ ] **Step 9: Run worker tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_execute_run_stops_when_runtime_stop_requested backend/tests/test_crawler_worker_service.py::test_execute_run_reuses_existing_detail_task_on_in_place_restart backend/tests/test_crawler_worker_service.py::test_execute_run_does_not_treat_list_stage_pending_details_as_detail_restart -v
```

Expected: PASS.

- [ ] **Step 10: Commit Task 2**

```bash
git add backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_worker_service.py scraper/services/movie_service.py
git commit -m "fix: restart crawler runs in place"
```

---

### Task 3: Frontend Detail Stop/Restart Controls

**Files:**
- Modify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- Modify: `frontend/tests/crawler-run-detail.ui.test.tsx`

- [ ] **Step 1: Write failing detail-page control tests**

In `frontend/tests/crawler-run-detail.ui.test.tsx`, replace the API import:

```tsx
import { getCrawlerRun, getCrawlerRunLogs, getCrawlerRunTasks } from '../src/api/crawlerRun'
```

with:

```tsx
import {
  getCrawlerRun,
  getCrawlerRunLogs,
  getCrawlerRunTasks,
  restartCrawlerRun,
  stopCrawlerRun,
} from '../src/api/crawlerRun'
```

Replace the testing-library import:

```tsx
import { render, screen } from '@testing-library/react'
```

with:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
```

Replace the API mock:

```tsx
vi.mock('../src/api/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunLogs: vi.fn(),
  getCrawlerRunTasks: vi.fn(),
}))
```

with:

```tsx
vi.mock('../src/api/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunLogs: vi.fn(),
  getCrawlerRunTasks: vi.fn(),
  restartCrawlerRun: vi.fn(),
  stopCrawlerRun: vi.fn(),
}))
```

In `beforeEach()`, add:

```tsx
    vi.mocked(stopCrawlerRun).mockResolvedValue({
      id: 'run-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'stopped',
      crawl_mode: 'incremental',
      queued_at: '2026-07-02T00:00:00Z',
      started_at: '2026-07-02T00:00:01Z',
      finished_at: '2026-07-02T00:00:02Z',
      result: null,
      error: '用户停止任务',
      resumed_from: null,
      created_at: '2026-07-02T00:00:00Z',
      updated_at: null,
      logs: [],
    })
    vi.mocked(restartCrawlerRun).mockResolvedValue({
      id: 'run-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'queued',
      crawl_mode: 'incremental',
      queued_at: '2026-07-02T00:01:00Z',
      started_at: null,
      finished_at: null,
      result: null,
      error: null,
      resumed_from: null,
      created_at: '2026-07-02T00:01:00Z',
      updated_at: null,
      logs: [],
    })
```

Add these tests:

```tsx
  it('stops a running run from the detail page', async () => {
    vi.mocked(getCrawlerRun).mockResolvedValueOnce({
      id: 'run-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'running',
      crawl_mode: 'incremental',
      queued_at: '2026-07-02T00:00:00Z',
      started_at: '2026-07-02T00:00:01Z',
      finished_at: null,
      result: null,
      error: null,
      resumed_from: null,
      created_at: '2026-07-02T00:00:00Z',
      updated_at: null,
      logs: [],
    })
    renderDetailPage()

    await userEvent.click(await screen.findByRole('button', { name: '停止' }))

    await waitFor(() => {
      expect(stopCrawlerRun).toHaveBeenCalledWith('run-1')
    })
    await waitFor(() => {
      expect(getCrawlerRunTasks).toHaveBeenCalled()
    })
  })

  it('restarts a stopped run from the detail page', async () => {
    renderDetailPage()

    await userEvent.click(await screen.findByRole('button', { name: '重启' }))

    await waitFor(() => {
      expect(restartCrawlerRun).toHaveBeenCalledWith('run-1')
    })
  })
```

- [ ] **Step 2: Run detail-page tests and verify they fail**

Run:

```bash
cd frontend && npm test -- crawler-run-detail.ui.test.tsx
```

Expected: FAIL because `RunDetailPage` does not render stop/restart controls and the API mock import changed.

- [ ] **Step 3: Add actions to RunDetailPage imports**

In `frontend/src/pages/crawler/runs/RunDetailPage.tsx`, replace:

```tsx
import { useParams } from '@tanstack/react-router'
import { Card, Descriptions, Input, Select, Space, Table, Tag } from 'antd'
```

with:

```tsx
import { useParams } from '@tanstack/react-router'
import { ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Button, Card, Descriptions, Input, Select, Space, Table, Tag, message } from 'antd'
```

Replace:

```tsx
import { getCrawlerRun, getCrawlerRunLogs, getCrawlerRunTasks } from '@/api/crawlerRun'
```

with:

```tsx
import {
  getCrawlerRun,
  getCrawlerRunLogs,
  getCrawlerRunTasks,
  restartCrawlerRun,
  stopCrawlerRun,
} from '@/api/crawlerRun'
```

- [ ] **Step 4: Add action handlers to RunDetailPage**

After the existing state declarations, add:

```tsx
  const [actionLoading, setActionLoading] = useState<'stop' | 'restart' | null>(null)
```

After `resyncSnapshot`, add:

```tsx
  const handleStop = useCallback(async () => {
    if (!id) return
    setActionLoading('stop')
    try {
      const stoppedRun = await stopCrawlerRun(id)
      setRun(stoppedRun)
      message.success('已停止运行')
      resyncSnapshot()
    } catch (error) {
      const msg = error instanceof Error ? error.message : '停止失败'
      message.error(msg)
    } finally {
      setActionLoading(null)
    }
  }, [id, resyncSnapshot])

  const handleRestart = useCallback(async () => {
    if (!id) return
    setActionLoading('restart')
    try {
      const restartedRun = await restartCrawlerRun(id)
      setRun(restartedRun)
      message.success('已重启运行')
      resyncSnapshot()
    } catch (error) {
      const msg = error instanceof Error ? error.message : '重启失败'
      message.error(msg)
    } finally {
      setActionLoading(null)
    }
  }, [id, resyncSnapshot])
```

- [ ] **Step 5: Render stop/restart buttons in the detail card**

In `RunDetailPage.tsx`, replace:

```tsx
        <Card title={`运行详情 - ${run.task_name}`} style={{ marginBottom: 16 }}>
```

with:

```tsx
        <Card
          title={`运行详情 - ${run.task_name}`}
          extra={(
            <Space>
              {(run.status === 'queued' || run.status === 'running') && (
                <Button
                  danger
                  icon={<StopOutlined />}
                  loading={actionLoading === 'stop'}
                  onClick={() => void handleStop()}
                >
                  停止
                </Button>
              )}
              {(run.status === 'stopped' || run.status === 'failed') && (
                <Button
                  type="primary"
                  icon={<ReloadOutlined />}
                  loading={actionLoading === 'restart'}
                  onClick={() => void handleRestart()}
                >
                  重启
                </Button>
              )}
            </Space>
          )}
          style={{ marginBottom: 16 }}
        >
```

- [ ] **Step 6: Run detail-page tests and verify they pass**

Run:

```bash
cd frontend && npm test -- crawler-run-detail.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add frontend/src/pages/crawler/runs/RunDetailPage.tsx frontend/tests/crawler-run-detail.ui.test.tsx
git commit -m "feat: add crawler run detail stop controls"
```

---

### Task 4: Frontend Run List Stop/Delete Actions

**Files:**
- Modify: `frontend/src/api/crawlerRun/index.ts`
- Modify: `frontend/src/pages/crawler/runs/RunListPage.tsx`
- Modify: `frontend/tests/crawler-runs.ui.test.tsx`

- [ ] **Step 1: Add list-page stop and delete tests**

In `frontend/tests/crawler-runs.ui.test.tsx`, replace:

```tsx
import { getCrawlerRuns, restartCrawlerRun } from '../src/api/crawlerRun'
```

with:

```tsx
import { deleteCrawlerRun, getCrawlerRuns, restartCrawlerRun, stopCrawlerRun } from '../src/api/crawlerRun'
```

In the API mock, add:

```tsx
  deleteCrawlerRun: vi.fn(),
```

In `beforeEach()`, add:

```tsx
    vi.mocked(stopCrawlerRun).mockResolvedValue({ id: 'run-3', status: 'stopped' } as never)
    vi.mocked(deleteCrawlerRun).mockResolvedValue({ id: 'run-1', deleted: true } as never)
```

Add this test:

```tsx
  it('stops a running run from the list page', async () => {
    vi.mocked(getCrawlerRuns).mockResolvedValueOnce({
      rows: [{
        id: 'run-3',
        task_id: 'task-3',
        task_name: '任务C',
        status: 'running',
        crawl_mode: 'incremental',
        queued_at: '2026-07-02T00:00:00',
        started_at: '2026-07-02T00:00:01',
        finished_at: null,
        result: null,
        error: null,
        resumed_from: null,
        created_at: '2026-07-02T00:00:00',
        updated_at: null,
        logs: [],
      }],
      total: 1,
    })
    render(<RunListPage />)

    await userEvent.click(await screen.findByRole('button', { name: '停止' }))

    await waitFor(() => {
      expect(stopCrawlerRun).toHaveBeenCalledWith('run-3')
    })
  })
```

Add this delete test:

```tsx
  it('deletes a stopped run from the list page', async () => {
    render(<RunListPage />)

    await userEvent.click(await screen.findByRole('button', { name: '删除' }))
    await userEvent.click(await screen.findByRole('button', { name: '确 定' }))

    await waitFor(() => {
      expect(deleteCrawlerRun).toHaveBeenCalledWith('run-1')
    })
  })
```

- [ ] **Step 2: Run list-page tests and verify they fail**

Run:

```bash
cd frontend && npm test -- crawler-runs.ui.test.tsx
```

Expected: FAIL because `deleteCrawlerRun` does not exist and the list page does not render a delete action.

- [ ] **Step 3: Add delete API client**

In `frontend/src/api/crawlerRun/index.ts`, add after `restartCrawlerRun()`:

```ts
export function deleteCrawlerRun(runId: string): Promise<{ id: string; deleted: boolean }> {
  return request.delete<{ id: string; deleted: boolean }>(`${BASE_URL}/${runId}`)
}
```

- [ ] **Step 4: Add delete imports and handler to RunListPage**

In `frontend/src/pages/crawler/runs/RunListPage.tsx`, replace:

```tsx
import { EyeOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Button, Space, Table, Tag, message } from 'antd'
```

with:

```tsx
import { DeleteOutlined, EyeOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Button, Popconfirm, Space, Table, Tag, message } from 'antd'
```

Replace:

```tsx
import { getCrawlerRuns, restartCrawlerRun, stopCrawlerRun } from '@/api/crawlerRun'
```

with:

```tsx
import { deleteCrawlerRun, getCrawlerRuns, restartCrawlerRun, stopCrawlerRun } from '@/api/crawlerRun'
```

Add this handler after `handleRestart`:

```tsx
  const handleDelete = useCallback(async (run: CrawlRun) => {
    try {
      await deleteCrawlerRun(run.id)
      message.success('已删除运行记录')
      const nextPage = runs.length === 1 && current > 1 ? current - 1 : current
      if (nextPage !== current) {
        setCurrent(nextPage)
        return
      }
      void fetchRuns(current)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '删除失败'
      message.error(msg)
    }
  }, [current, fetchRuns, runs.length])
```

- [ ] **Step 5: Render delete action for non-running runs**

In `RunListPage.tsx`, inside the action `<Space>`, after the restart button block, add:

```tsx
          {record.status !== 'queued' && record.status !== 'running' && (
            <Popconfirm
              title="删除运行记录"
              description="仅删除运行记录和子任务记录，不会删除影片数据。"
              okText="确定"
              cancelText="取消"
              onConfirm={() => handleDelete(record)}
            >
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
              >
                删除
              </Button>
            </Popconfirm>
          )}
```

- [ ] **Step 6: Run list-page tests and verify they pass**

Run:

```bash
cd frontend && npm test -- crawler-runs.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add frontend/src/api/crawlerRun/index.ts frontend/src/pages/crawler/runs/RunListPage.tsx frontend/tests/crawler-runs.ui.test.tsx
git commit -m "feat: add crawler run delete action"
```

---

### Task 5: Regression Verification

**Files:**
- Verify: `backend/app/modules/crawler/runtime/service.py`
- Verify: `backend/app/modules/crawler/runs/router.py`
- Verify: `frontend/src/api/crawlerRun/index.ts`
- Verify: `frontend/src/pages/crawler/runs/RunListPage.tsx`
- Verify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py backend/tests/test_crawler_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd frontend && npm test -- crawler-runs.ui.test.tsx crawler-run-detail.ui.test.tsx run-detail-realtime.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. Existing Vite warnings about chunk size, dynamic imports, or plugin timings are acceptable if the command exits with status 0.

- [ ] **Step 4: Manual API sanity check**

With the backend running and an authenticated token available, stop a running run:

```bash
curl -X POST -H "Authorization: Bearer <token>" http://localhost:8000/api/crawler/runs/<run_id>/stop
curl -H "Authorization: Bearer <token>" "http://localhost:8000/api/crawler/runs/<run_id>/tasks?status=pending_crawl"
curl -X POST -H "Authorization: Bearer <token>" http://localhost:8000/api/crawler/runs/<run_id>/restart
```

Expected:

```json
{
  "stop": {
    "status": "stopped",
    "error": "用户停止任务"
  },
  "pending_tasks": [
    {
      "status": "pending_crawl",
      "error": null
    }
  ],
  "restart": {
    "id": "<run_id>",
    "status": "queued",
    "started_at": null,
    "finished_at": null,
    "error": null,
    "result": null
  }
}
```

- [ ] **Step 5: Manual delete sanity check**

With the backend running and an authenticated token available, delete a completed, failed, or stopped run:

```bash
curl -X DELETE -H "Authorization: Bearer <token>" http://localhost:8000/api/crawler/runs/<run_id>
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/crawler/runs/<run_id>
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/crawler/runs/<run_id>/tasks
```

Expected:

```json
{
  "delete": {
    "id": "<run_id>",
    "deleted": true
  },
  "detail_after_delete": 404,
  "tasks_after_delete": 404
}
```

---

## Self-Review Result

- Spec coverage: The plan covers run list stop/delete behavior, run detail stop/restart controls, stopped run status, pending reset for unfinished child tasks, worker stop propagation, in-place restart after stop, list-stage restart from page 1, detail-stage restart without list collection, and deletion limited to `crawl_runs` plus `crawl_run_detail_tasks`.
- Placeholder scan: No placeholder implementation steps remain; every code-changing step includes concrete snippets and exact commands.
- Type consistency: Child detail task statuses remain the existing set; stop resets restartable child tasks to `pending_crawl`; list-stage restart clears partial child rows before requeue; detail-stage restart requeues the same run ID and passes only `pending_crawl`, `crawl_failed`, and `save_failed` rows to the detail-only crawler; terminal `saved` and `skipped` child tasks remain unchanged.
