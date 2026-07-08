# Crawler Delete Purges Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent stale stopped/queued incremental crawler runs from remaining in Redis after task deletion and being observed or processed when a new full run starts.

**Architecture:** Add precise Redis cleanup primitives to `CrawlerRuntimeState` for a single run and a batch of runs. Wire task deletion through the crawler task service so deleting a stopped task removes its run IDs from the Redis queue, clears stop/progress keys, and clears `current_run_id` if it points at a deleted run. Harden the worker so a queued run that was deleted after being enqueued is skipped and cleaned from runtime state.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, Redis list/string primitives, Pytest.

## Global Constraints

- Do not clear all crawler Redis runtime state when deleting one task.
- Do not allow deletion of currently `queued` or `running` tasks.
- Allow deletion of `idle` and `stopped` crawler tasks.
- Preserve existing task delete modes: `task_only`, `task_and_movies`, `task_movies_and_cloud`.
- Preserve database cascade/delete semantics for runs, detail tasks, movies, magnets, and cloud deletion.
- Redis cleanup happens only after database delete succeeds.
- Worker processing of missing run IDs must not fail the worker loop or leave stale Redis state.

---

## File Structure

- Modify `backend/app/modules/crawler/runtime/redis_state.py`: add run-specific queue removal and key purge methods.
- Modify `backend/tests/test_crawler_runtime_redis.py`: cover queue removal, stop/progress cleanup, and current-run cleanup for deleted runs.
- Modify `backend/app/modules/crawler/tasks/runtime_status.py`: allow deletion for `stopped` tasks while still blocking `queued` and `running`.
- Modify `backend/app/modules/crawler/tasks/service.py`: collect deleted run IDs, call `delete_task()`, then purge those run IDs from Redis after successful DB commit.
- Modify `backend/tests/test_task_delete_cascade.py`: cover stopped task deletion and Redis purge through `CrawlerTaskService.delete_task()`.
- Modify `backend/app/modules/crawler/runtime/worker.py`: purge runtime keys when a claimed run no longer exists in the database.
- Modify `backend/tests/test_crawler_worker_service.py`: cover missing claimed run cleanup.

---

### Task 1: Add Run-Specific Redis Cleanup Primitives

**Files:**
- Modify: `backend/app/modules/crawler/runtime/redis_state.py`
- Test: `backend/tests/test_crawler_runtime_redis.py`

**Interfaces:**
- Produces `CrawlerRuntimeState.remove_queued_run(run_id: str) -> int`.
- Produces `CrawlerRuntimeState.purge_run(run_id: str) -> None`.
- Produces `CrawlerRuntimeState.purge_runs(run_ids: list[str]) -> None`.
- `purge_run()` removes the run from the queue, clears `stop:{run_id}`, clears `progress:{run_id}`, and clears `current_run_id` only if it equals `run_id`.

- [ ] **Step 1: Extend the fake Redis test double**

In `backend/tests/test_crawler_runtime_redis.py`, add this method to `FakeRedis`:

```python
    def lrem(self, key, count, value):
        values = self.lists.get(key, [])
        original_len = len(values)
        if count == 0:
            self.lists[key] = [item for item in values if item != value]
        elif count > 0:
            removed = 0
            next_values = []
            for item in values:
                if item == value and removed < count:
                    removed += 1
                    continue
                next_values.append(item)
            self.lists[key] = next_values
        else:
            removed = 0
            next_values = []
            for item in reversed(values):
                if item == value and removed < abs(count):
                    removed += 1
                    continue
                next_values.append(item)
            self.lists[key] = list(reversed(next_values))
        return original_len - len(self.lists.get(key, []))
```

- [ ] **Step 2: Write failing Redis cleanup tests**

Append these tests to `backend/tests/test_crawler_runtime_redis.py`:

```python
def test_remove_queued_run_removes_all_matching_queue_entries() -> None:
    runtime = CrawlerRuntimeState(FakeRedis())
    runtime.enqueue_run("run-1")
    runtime.enqueue_run("run-2")
    runtime.enqueue_run("run-1")

    assert runtime.remove_queued_run("run-1") == 2

    assert runtime.queue_status()["queue_size"] == 1
    assert runtime.claim_next_run() == "run-2"
    assert runtime.claim_next_run() is None


def test_purge_run_clears_queue_stop_progress_and_matching_current() -> None:
    runtime = CrawlerRuntimeState(FakeRedis())
    runtime.enqueue_run("run-1")
    runtime.enqueue_run("run-2")
    runtime.set_current_run("run-1")
    runtime.request_stop("run-1")
    runtime.write_progress("run-1", {"total": 9})

    runtime.purge_run("run-1")

    assert runtime.is_stop_requested("run-1") is False
    assert runtime.read_progress("run-1") == {}
    assert runtime.queue_status() == {
        "queue_size": 1,
        "is_running": False,
        "current_run_id": None,
        "stop_requested": False,
    }
    assert runtime.claim_next_run() == "run-2"


def test_purge_run_keeps_other_current_run() -> None:
    runtime = CrawlerRuntimeState(FakeRedis())
    runtime.set_current_run("run-2")
    runtime.request_stop("run-1")

    runtime.purge_run("run-1")

    assert runtime.queue_status()["current_run_id"] == "run-2"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_runtime_redis.py::test_remove_queued_run_removes_all_matching_queue_entries tests/test_crawler_runtime_redis.py::test_purge_run_clears_queue_stop_progress_and_matching_current tests/test_crawler_runtime_redis.py::test_purge_run_keeps_other_current_run -v
```

Expected: FAIL because `CrawlerRuntimeState.remove_queued_run()` and `purge_run()` do not exist.

- [ ] **Step 4: Implement run-specific cleanup**

In `backend/app/modules/crawler/runtime/redis_state.py`, add these methods after `enqueue_run()`:

```python
    def remove_queued_run(self, run_id: str) -> int:
        return int(self.redis.lrem(self.QUEUE_KEY, 0, run_id) or 0)
```

Add these methods after `clear_stop()`:

```python
    def clear_progress(self, run_id: str) -> None:
        self.redis.delete(self._progress_key(run_id))

    def purge_run(self, run_id: str) -> None:
        self.remove_queued_run(run_id)
        self.clear_stop(run_id)
        self.clear_progress(run_id)
        current = self.redis.get(self.CURRENT_KEY)
        current_run_id = current.decode() if isinstance(current, bytes) else current
        if str(current_run_id) == str(run_id):
            self.set_current_run(None)

    def purge_runs(self, run_ids: list[str]) -> None:
        for run_id in run_ids:
            self.purge_run(run_id)
```

- [ ] **Step 5: Run Redis tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_runtime_redis.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/crawler/runtime/redis_state.py backend/tests/test_crawler_runtime_redis.py
git commit -m "fix: add crawler run runtime purge"
```

---

### Task 2: Purge Deleted Task Runs From Redis

**Files:**
- Modify: `backend/app/modules/crawler/tasks/runtime_status.py`
- Modify: `backend/app/modules/crawler/tasks/service.py`
- Modify: `backend/tests/test_task_delete_cascade.py`

**Interfaces:**
- Consumes `CrawlerRuntimeState.purge_runs(run_ids: list[str]) -> None` from Task 1.
- `can_delete_task_runtime_status(runtime_status: str) -> bool` returns `True` for `idle` and `stopped`, and `False` for `queued` and `running`.
- `CrawlerTaskService.delete_task()` purges Redis runtime for deleted run IDs after `delete_task()` commits successfully.

- [ ] **Step 1: Write deletion runtime purge tests**

Append these tests to `backend/tests/test_task_delete_cascade.py`:

```python
def test_stopped_task_can_be_deleted_and_purges_runtime(monkeypatch, admin_user) -> None:
    from datetime import datetime

    from backend.app.models.crawl_run import CrawlRun
    from backend.app.modules.crawler.tasks.service import CrawlerTaskService

    session = TestingSessionLocal()
    task = CrawlTask(name="停止后删除", storage_location="测试", owner_id=admin_user.id, is_skip=False)
    session.add(task)
    session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="stopped",
        crawl_mode="incremental",
        queued_at=datetime.now(),
        finished_at=datetime.now(),
        error="用户停止任务",
    )
    session.add(run)
    session.commit()

    class Runtime:
        def __init__(self) -> None:
            self.purged: list[list[str]] = []

        def purge_runs(self, run_ids: list[str]) -> None:
            self.purged.append(run_ids)

    runtime = Runtime()
    monkeypatch.setattr("backend.app.modules.crawler.tasks.service.get_runtime_state", lambda: runtime)

    result = CrawlerTaskService(session).delete_task(task.id, admin_user.id, mode="task_only")

    assert result["deleted_task"] is True
    assert result["deleted_runs"] == 1
    assert runtime.purged == [[str(run.id)]]
    assert session.get(CrawlTask, task.id) is None


def test_delete_task_does_not_purge_runtime_when_database_delete_fails(monkeypatch, admin_user) -> None:
    from datetime import datetime

    from backend.app.models.crawl_run import CrawlRun
    from backend.app.modules.crawler.tasks.service import CrawlerTaskService

    session = TestingSessionLocal()
    task = CrawlTask(name="删除失败", storage_location="测试", owner_id=admin_user.id, is_skip=False)
    session.add(task)
    session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="stopped",
        crawl_mode="incremental",
        queued_at=datetime.now(),
        finished_at=datetime.now(),
    )
    session.add(run)
    session.commit()

    class Runtime:
        def __init__(self) -> None:
            self.purged: list[list[str]] = []

        def purge_runs(self, run_ids: list[str]) -> None:
            self.purged.append(run_ids)

    runtime = Runtime()
    monkeypatch.setattr("backend.app.modules.crawler.tasks.service.get_runtime_state", lambda: runtime)

    def fail_delete(*_args, **_kwargs):
        raise RuntimeError("delete failed")

    monkeypatch.setattr("backend.app.modules.crawler.tasks.service.delete_task", fail_delete)

    try:
        CrawlerTaskService(session).delete_task(task.id, admin_user.id, mode="task_only")
    except RuntimeError:
        pass

    assert runtime.purged == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_task_delete_cascade.py::test_stopped_task_can_be_deleted_and_purges_runtime tests/test_task_delete_cascade.py::test_delete_task_does_not_purge_runtime_when_database_delete_fails -v
```

Expected: first test FAILS because stopped tasks cannot currently be deleted and Redis is not purged.

- [ ] **Step 3: Allow stopped task deletion**

In `backend/app/modules/crawler/tasks/runtime_status.py`, replace `can_delete_task_runtime_status()` with:

```python
def can_delete_task_runtime_status(runtime_status: str) -> bool:
    """Check whether a task can be deleted based on its runtime status.

    Idle tasks have no active latest run. Stopped tasks are no longer actively
    running and can be deleted after their runtime keys are purged.
    """
    return runtime_status in {"idle", "stopped"}
```

- [ ] **Step 4: Purge runtime after successful task deletion**

In `backend/app/modules/crawler/tasks/service.py`, add import:

```python
from backend.app.models.crawl_run import CrawlRun
```

Inside `CrawlerTaskService.delete_task()`, after `ensure_delete_mode_supported(mode)` and before `try:`, add:

```python
        run_ids = [
            str(row.id)
            for row in self.db.query(CrawlRun.id)
            .filter(CrawlRun.task_id == task_id)
            .all()
        ]
```

After:

```python
                result = delete_task(self.db, task_id, mode=mode, provider=provider)
```

add:

```python
            get_runtime_state().purge_runs(run_ids)
```

The resulting block is:

```python
        try:
            with open_delete_provider(mode) as provider:
                result = delete_task(self.db, task_id, mode=mode, provider=provider)
                get_runtime_state().purge_runs(run_ids)
        except UnsupportedDeleteMode as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
```

- [ ] **Step 5: Run deletion tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_task_delete_cascade.py::test_stopped_task_can_be_deleted_and_purges_runtime tests/test_task_delete_cascade.py::test_delete_task_does_not_purge_runtime_when_database_delete_fails -v
```

Expected: PASS.

- [ ] **Step 6: Run existing task deletion tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_task_delete_cascade.py tests/test_crawler_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/tasks/runtime_status.py backend/app/modules/crawler/tasks/service.py backend/tests/test_task_delete_cascade.py
git commit -m "fix: purge crawler runtime on task delete"
```

---

### Task 3: Harden Worker Against Deleted Queued Runs

**Files:**
- Modify: `backend/app/modules/crawler/runtime/worker.py`
- Modify: `backend/tests/test_crawler_worker_service.py`

**Interfaces:**
- Consumes `CrawlerRuntimeState.purge_run(run_id: str) -> None` from Task 1.
- `process_run(db_factory, runtime, run_id)` calls `runtime.purge_run(run_id)` and returns `False` when the run no longer exists.
- Missing run IDs do not set `current_run_id`, do not crash the worker loop, and do not leave stop/progress keys behind.

- [ ] **Step 1: Add runtime purge support to worker test runtime**

In `backend/tests/test_crawler_worker_service.py`, add this field to `Runtime.__init__()`:

```python
        self.purged = []
```

Add this method to `Runtime`:

```python
    def purge_run(self, run_id):
        self.purged.append(run_id)
```

- [ ] **Step 2: Write missing run worker test**

Append this test to `backend/tests/test_crawler_worker_service.py`:

```python
def test_process_run_purges_runtime_for_missing_run() -> None:
    from backend.app.modules.crawler.runtime.worker import process_run

    run_id = str(uuid.uuid4())
    runtime = Runtime(run_id)

    processed = process_run(TestingSessionLocal, runtime, run_id)

    assert processed is False
    assert runtime.current is None
    assert runtime.purged == [run_id]
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py::test_process_run_purges_runtime_for_missing_run -v
```

Expected: FAIL because `process_run()` logs missing runs but does not purge runtime.

- [ ] **Step 4: Purge missing runs in worker**

In `backend/app/modules/crawler/runtime/worker.py`, replace:

```python
        if run is None:
            logger.error("Run %s not found", run_id)
            return False
```

with:

```python
        if run is None:
            logger.error("Run %s not found", run_id)
            runtime.purge_run(run_id)
            return False
```

- [ ] **Step 5: Run worker tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py::test_process_run_purges_runtime_for_missing_run tests/test_crawler_worker_service.py::test_process_next_run_marks_saved -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/crawler/runtime/worker.py backend/tests/test_crawler_worker_service.py
git commit -m "fix: purge deleted crawler runs in worker"
```

---

### Task 4: Focused Regression Verification

**Files:**
- No new files.
- Verify files changed in Tasks 1-3.

**Interfaces:**
- Consumes Redis purge methods, task deletion runtime purge, and worker missing-run cleanup.
- Produces verified behavior for the stop-delete-start-full scenario.

- [ ] **Step 1: Run focused runtime tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_runtime_redis.py tests/test_task_delete_cascade.py::test_stopped_task_can_be_deleted_and_purges_runtime tests/test_crawler_worker_service.py::test_process_run_purges_runtime_for_missing_run -v
```

Expected: PASS.

- [ ] **Step 2: Run related crawler API/runtime tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_runs_api.py tests/test_crawler_worker_service.py tests/test_crawler_tasks_api.py tests/test_task_delete_cascade.py -v
```

Expected: PASS. If failures come from unrelated dirty worktree changes, record the exact test names and failure messages.

- [ ] **Step 3: Manual behavior check through services**

Run this targeted script from project root:

```bash
source .venv/bin/activate
cd backend
python - <<'PY'
from datetime import datetime
from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.tasks.runtime_status import can_delete_task_runtime_status
from backend.tests.test_crawler_runtime_redis import FakeRedis

runtime = CrawlerRuntimeState(FakeRedis())
runtime.enqueue_run("old-incremental")
runtime.request_stop("old-incremental")
runtime.write_progress("old-incremental", {"total": 1})
runtime.purge_run("old-incremental")
runtime.enqueue_run("new-full")

assert runtime.claim_next_run() == "new-full"
assert runtime.claim_next_run() is None
assert runtime.is_stop_requested("old-incremental") is False
assert runtime.read_progress("old-incremental") == {}
assert can_delete_task_runtime_status("stopped") is True
assert can_delete_task_runtime_status("running") is False
print("manual runtime purge check passed")
PY
```

Expected output includes:

```text
manual runtime purge check passed
```

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: only intended implementation files remain modified, or the working tree is clean after task commits.

- [ ] **Step 5: Commit verification fixes if needed**

If verification required small corrections, commit them:

```bash
git add backend/app/modules/crawler/runtime/redis_state.py backend/app/modules/crawler/runtime/worker.py backend/app/modules/crawler/tasks/runtime_status.py backend/app/modules/crawler/tasks/service.py backend/tests/test_crawler_runtime_redis.py backend/tests/test_crawler_worker_service.py backend/tests/test_task_delete_cascade.py
git commit -m "test: verify crawler delete runtime purge"
```

If no corrections were needed, do not create an empty commit.
