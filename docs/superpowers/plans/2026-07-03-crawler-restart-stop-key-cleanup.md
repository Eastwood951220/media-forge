# Crawler Restart Stop Key Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent in-place restarted crawler runs from immediately stopping because of stale Redis stop signals.

**Architecture:** Add a focused `CrawlerRuntimeState.clear_stop(run_id)` method that deletes only the Redis stop key for one run. Call it before `restart_run()` re-enqueues the same run ID, and call it in `process_run()` cleanup as a lifecycle safety net. Tests cover Redis state behavior, restart service behavior, and worker cleanup behavior without changing crawler retry/list/detail semantics.

**Tech Stack:** FastAPI service layer, Redis runtime state wrapper, SQLAlchemy 2.0, Pytest.

---

## File Structure

- Modify `backend/app/modules/crawler/runtime/redis_state.py`: add `clear_stop(run_id)`.
- Modify `backend/app/modules/crawler/runtime/service.py`: clear stale stop key before in-place restart enqueue and after worker processing finishes.
- Modify `backend/tests/test_crawler_runtime_redis.py`: cover `clear_stop()`.
- Modify `backend/tests/test_crawler_runs_api.py`: cover restart clearing stop signal before requeueing the same run ID.
- Modify `backend/tests/test_crawler_worker_service.py`: cover process lifecycle stop-key cleanup.

---

### Task 1: Runtime Stop Key API

**Files:**
- Modify: `backend/app/modules/crawler/runtime/redis_state.py`
- Modify: `backend/tests/test_crawler_runtime_redis.py`

- [ ] **Step 1: Write failing runtime clear_stop test**

In `backend/tests/test_crawler_runtime_redis.py`, add this test after `test_stop_signal_and_cleanup()`:

```python
def test_clear_stop_signal() -> None:
    redis = FakeRedis()
    runtime = CrawlerRuntimeState(redis)

    runtime.request_stop("run-1")
    assert runtime.is_stop_requested("run-1") is True

    runtime.clear_stop("run-1")

    assert runtime.is_stop_requested("run-1") is False
    assert runtime.queue_status()["stop_requested"] is False
```

- [ ] **Step 2: Run runtime test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runtime_redis.py::test_clear_stop_signal -v
```

Expected: FAIL with `AttributeError: 'CrawlerRuntimeState' object has no attribute 'clear_stop'`.

- [ ] **Step 3: Implement clear_stop**

In `backend/app/modules/crawler/runtime/redis_state.py`, add this method immediately after `request_stop()`:

```python
    def clear_stop(self, run_id: str) -> None:
        self.redis.delete(self._stop_key(run_id))
```

- [ ] **Step 4: Run runtime test and verify it passes**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runtime_redis.py::test_clear_stop_signal -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/app/modules/crawler/runtime/redis_state.py backend/tests/test_crawler_runtime_redis.py
git commit -m "fix: add crawler runtime stop cleanup"
```

---

### Task 2: Restart Clears Stale Stop Signal

**Files:**
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/tests/test_crawler_runs_api.py`

- [ ] **Step 1: Update the fake runtime for restart assertions**

In `backend/tests/test_crawler_runs_api.py`, replace `RuntimeForStopRestart` with:

```python
class RuntimeForStopRestart(FakeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.stopped = []
        self.cleared = []

    def request_stop(self, run_id: str) -> None:
        self.stopped.append(run_id)

    def clear_stop(self, run_id: str) -> None:
        self.cleared.append(run_id)
```

- [ ] **Step 2: Add failing restart cleanup assertion**

In `backend/tests/test_crawler_runs_api.py`, in `test_restart_after_detail_phase_requeues_same_run_and_keeps_terminal_details()`, add this assertion after `assert runtime.enqueued == [str(run.id)]`:

```python
    assert runtime.cleared == [str(run.id)]
```

In `test_restart_after_list_phase_discards_partial_list_tasks_and_requeues_same_run()`, add this assertion after `assert runtime.enqueued == [str(run.id)]`:

```python
    assert runtime.cleared == [str(run.id)]
```

In `test_restart_stopped_run_without_subtasks_requeues_same_run()`, add this assertion after `assert runtime.enqueued == [str(run.id)]`:

```python
    assert runtime.cleared == [str(run.id)]
```

- [ ] **Step 3: Run restart tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py::test_restart_after_detail_phase_requeues_same_run_and_keeps_terminal_details backend/tests/test_crawler_runs_api.py::test_restart_after_list_phase_discards_partial_list_tasks_and_requeues_same_run backend/tests/test_crawler_runs_api.py::test_restart_stopped_run_without_subtasks_requeues_same_run -v
```

Expected: FAIL because `runtime.cleared` remains `[]`.

- [ ] **Step 4: Clear stop key before enqueueing restarted run**

In `backend/app/modules/crawler/runtime/service.py`, inside `CrawlerRunService.restart_run()`, replace:

```python
        self.db.commit()
        self.db.refresh(run)
        self.runtime.enqueue_run(str(run.id))
```

with:

```python
        self.db.commit()
        self.db.refresh(run)
        self.runtime.clear_stop(str(run.id))
        self.runtime.enqueue_run(str(run.id))
```

This ordering ensures a worker that immediately claims the requeued run cannot observe the old stop key.

- [ ] **Step 5: Run restart tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py::test_restart_after_detail_phase_requeues_same_run_and_keeps_terminal_details backend/tests/test_crawler_runs_api.py::test_restart_after_list_phase_discards_partial_list_tasks_and_requeues_same_run backend/tests/test_crawler_runs_api.py::test_restart_stopped_run_without_subtasks_requeues_same_run -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_runs_api.py
git commit -m "fix: clear stop signal before crawler restart"
```

---

### Task 3: Worker Lifecycle Cleanup

**Files:**
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/tests/test_crawler_worker_service.py`

- [ ] **Step 1: Add clear_stop tracking to worker Runtime fake**

In `backend/tests/test_crawler_worker_service.py`, update `Runtime.__init__()`:

```python
    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self.current = None
        self.progress = {}
        self.cleared = []
```

Add this method to `Runtime` after `write_progress()`:

```python
    def clear_stop(self, run_id):
        self.cleared.append(run_id)
```

- [ ] **Step 2: Add failing worker lifecycle assertion**

In `backend/tests/test_crawler_worker_service.py`, in `test_process_next_run_marks_saved()`, add this assertion after `assert detail.status == "saved"`:

```python
    assert runtime.cleared == [str(run.id)]
```

- [ ] **Step 3: Run worker test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_process_next_run_marks_saved -v
```

Expected: FAIL because `process_run()` never calls `runtime.clear_stop(run_id)`.

- [ ] **Step 4: Clear stop key in process_run finally**

In `backend/app/modules/crawler/runtime/service.py`, inside `process_run()`, replace:

```python
        finally:
            runtime.set_current_run(None)
            runtime.write_progress(run_id, {})
```

with:

```python
        finally:
            runtime.set_current_run(None)
            runtime.write_progress(run_id, {})
            runtime.clear_stop(run_id)
```

- [ ] **Step 5: Run worker test and verify it passes**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_process_next_run_marks_saved -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_worker_service.py
git commit -m "fix: clear crawler stop signal after run"
```

---

### Task 4: Regression Verification

**Files:**
- Verify: `backend/app/modules/crawler/runtime/redis_state.py`
- Verify: `backend/app/modules/crawler/runtime/service.py`
- Verify: `backend/tests/test_crawler_runtime_redis.py`
- Verify: `backend/tests/test_crawler_runs_api.py`
- Verify: `backend/tests/test_crawler_worker_service.py`

- [ ] **Step 1: Run focused stop-key tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runtime_redis.py::test_clear_stop_signal backend/tests/test_crawler_runs_api.py::test_restart_after_detail_phase_requeues_same_run_and_keeps_terminal_details backend/tests/test_crawler_runs_api.py::test_restart_after_list_phase_discards_partial_list_tasks_and_requeues_same_run backend/tests/test_crawler_runs_api.py::test_restart_stopped_run_without_subtasks_requeues_same_run backend/tests/test_crawler_worker_service.py::test_process_next_run_marks_saved -v
```

Expected: PASS.

- [ ] **Step 2: Run focused crawler backend suites**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runtime_redis.py backend/tests/test_crawler_runs_api.py backend/tests/test_crawler_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 3: Manual sanity check**

With the backend running and an authenticated token available, use a run that has previously been stopped:

```bash
curl -X POST -H "Authorization: Bearer <token>" http://localhost:8000/api/crawler/runs/<run_id>/restart
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/crawler/runs/queue-status
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/crawler/runs/<run_id>/logs
```

Expected:

```json
{
  "restart": {
    "id": "<run_id>",
    "status": "queued"
  },
  "queue_status_after_restart": {
    "stop_requested": false
  },
  "logs": "does not immediately contain 收到停止信号 for item 1"
}
```

---

## Self-Review Result

- Spec coverage: The plan covers `clear_stop()`, restart pre-enqueue cleanup, worker final cleanup, and regression tests for the observed stale stop key bug.
- Placeholder scan: No placeholder implementation steps remain; every code-changing step includes exact code snippets and commands.
- Type consistency: `clear_stop(run_id: str)` is consistently added to `CrawlerRuntimeState` and the fake runtime classes that participate in restart/worker tests.
