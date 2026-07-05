# Fix Storage Queued Worker Logs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix storage push tasks staying queued forever and add backend/subtask logs that show where storage execution stops.

**Architecture:** The root cause is in the dispatch boundary: `get_storage_task_service()` constructs `StorageTaskService` without a Redis `StorageRuntimeState`, and `StorageTaskService._create_main_task()` only enqueues when `self.runtime is not None`; it also never starts the storage worker. The fix injects Redis runtime through dependencies, starts the worker after enqueue/restart, and writes JSONL subtask logs at queue, worker, provider, and magnet-step boundaries so future CloudDrive2 failures are visible in the UI.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, Redis 8, Pytest, existing Media Forge storage task modules.

---

## Root Cause Summary

Observed code path:

- `backend/app/core/dependencies.py` returns `StorageTaskService(db=db, config_service=get_storage_config_service())`.
- `backend/app/modules/storage/tasks/service.py` only calls `self.runtime.enqueue_main_task(str(main_task.id))` when `self.runtime is not None`.
- Because runtime is never passed from the API dependency, new queued storage tasks are persisted but never pushed into Redis.
- `StorageTaskService._create_main_task()` also does not call `ensure_storage_worker_started(self.runtime, self.config_service.provider_factory, self.config_service)`, so even a manually injected runtime would not reliably start a worker after API task creation.
- `backend/app/modules/storage/worker/steps.py` logs to Python `logger`, but does not call `write_storage_subtask_log(str(subtask.id), level, message, context)`, so `/api/storage/tasks/subtasks/{id}/logs` stays empty for normal worker progress and failures.

This plan fixes those dispatch and logging gaps only. It does not redesign the storage pipeline or CloudDrive2 behavior.

## File Structure

- Modify `backend/app/core/dependencies.py`: inject `StorageRuntimeState(get_redis())` into `StorageTaskService`.
- Modify `backend/app/modules/storage/tasks/service.py`: start the worker after enqueue/restart and emit creation/queue logs for subtasks.
- Modify `backend/app/modules/storage/worker/runner.py`: add worker lifecycle logs and JSONL subtask logs for claim, start, provider creation failures, pipeline exceptions, stop, and final status.
- Modify `backend/app/modules/storage/worker/steps.py`: write subtask JSONL logs for prepare, magnet submit, CloudDrive2 submit result, file search, main-video selection, move, and per-magnet failure.
- Modify `backend/tests/test_storage_tasks_api.py`: assert API-created queued tasks are enqueued and worker start is requested.
- Modify `backend/tests/test_storage_worker_pipeline.py`: assert pipeline writes useful subtask logs when magnet submission fails.
- Modify `backend/tests/test_storage_worker_service.py`: assert provider creation failure is logged into the subtask log and marks the subtask failed.

---

### Task 1: Inject Redis Runtime and Start Storage Worker After API Task Creation

**Files:**
- Modify: `backend/app/core/dependencies.py`
- Modify: `backend/app/modules/storage/tasks/service.py`
- Modify: `backend/tests/test_storage_tasks_api.py`

- [ ] **Step 1: Write failing API dispatch test**

Append this test to `backend/tests/test_storage_tasks_api.py`:

```python
def test_single_push_enqueues_runtime_and_starts_worker(db_session, test_user, monkeypatch):
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.storage.tasks.schemas import StorageSinglePushRequest
    from backend.app.modules.storage.tasks.service import StorageTaskService

    movie = _movie_with_source_and_magnet(db_session, test_user.id, code="abc-queued")

    class FakeRuntime:
        def __init__(self) -> None:
            self.enqueued: list[str] = []

        def enqueue_main_task(self, task_id: str) -> None:
            self.enqueued.append(task_id)

    fake_runtime = FakeRuntime()
    started: list[str] = []

    def fake_start_worker(runtime, provider_factory, config_service):
        assert runtime is fake_runtime
        assert provider_factory is config_service.provider_factory
        started.append("started")

    monkeypatch.setattr(
        "backend.app.modules.storage.tasks.service.ensure_storage_worker_started",
        fake_start_worker,
        raising=False,
    )

    service = StorageTaskService(
        db=db_session,
        config_service=StorageConfigService(),
        runtime=fake_runtime,
    )

    main_task = service.create_single_push(
        StorageSinglePushRequest(
            movie_id=movie.id,
            storage_mode="single",
            selected_storage_location="A",
        ),
        test_user.id,
    )

    assert fake_runtime.enqueued == [str(main_task.id)]
    assert started == ["started"]
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_tasks_api.py::test_single_push_enqueues_runtime_and_starts_worker -v
```

Expected: FAIL because `ensure_storage_worker_started` is not imported/called from `StorageTaskService`.

- [ ] **Step 3: Import worker starter in service**

Add this import near the top of `backend/app/modules/storage/tasks/service.py`:

```python
from backend.app.modules.storage.worker.runner import ensure_storage_worker_started
```

- [ ] **Step 4: Start worker after enqueue in `_create_main_task`**

In `StorageTaskService._create_main_task()`, replace:

```python
        if has_queued and self.runtime is not None:
            self.runtime.enqueue_main_task(str(main_task.id))
```

with:

```python
        if has_queued and self.runtime is not None:
            self.runtime.enqueue_main_task(str(main_task.id))
            ensure_storage_worker_started(
                self.runtime,
                self.config_service.provider_factory,
                self.config_service,
            )
```

- [ ] **Step 5: Start worker after restart enqueue**

In `StorageTaskService.restart_main_task()`, after:

```python
            self.runtime.enqueue_main_task(str(task.id))
```

add:

```python
            ensure_storage_worker_started(
                self.runtime,
                self.config_service.provider_factory,
                self.config_service,
            )
```

- [ ] **Step 6: Inject runtime in FastAPI dependency**

In `backend/app/core/dependencies.py`, replace:

```python
def get_storage_task_service(db: DbSession):
    from backend.app.modules.storage.tasks.service import StorageTaskService

    return StorageTaskService(db=db, config_service=get_storage_config_service())
```

with:

```python
def get_storage_task_service(db: DbSession):
    from backend.app.modules.storage.runtime.redis_state import StorageRuntimeState
    from backend.app.modules.storage.tasks.service import StorageTaskService

    return StorageTaskService(
        db=db,
        config_service=get_storage_config_service(),
        runtime=StorageRuntimeState(get_redis()),
    )
```

- [ ] **Step 7: Run focused dispatch tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_tasks_api.py::test_single_push_enqueues_runtime_and_starts_worker backend/tests/test_storage_runtime_redis.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/dependencies.py backend/app/modules/storage/tasks/service.py backend/tests/test_storage_tasks_api.py
git commit -m "fix: start storage worker after push"
```

---

### Task 2: Add Subtask JSONL Logs at Creation, Queue, and Worker Boundaries

**Files:**
- Modify: `backend/app/modules/storage/tasks/service.py`
- Modify: `backend/app/modules/storage/worker/runner.py`
- Modify: `backend/tests/test_storage_worker_service.py`

- [ ] **Step 1: Write failing provider failure log test**

Append this test to `backend/tests/test_storage_worker_service.py`:

```python
def test_process_main_task_logs_provider_creation_failure(db_session, test_user, monkeypatch, tmp_path):
    import uuid
    from backend.app.modules.storage.worker.runner import process_main_task
    from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs
    from shared.database.models.content import Movie

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    movie = Movie(code="ABC-LOG", source_name="Title")
    db_session.add(movie)
    db_session.flush()

    main = StorageMainTask(
        alias="a",
        display_name="a",
        source="single",
        storage_mode="single",
        status="queued",
        total_count=1,
        created_by=test_user.id,
        config_snapshot={"download_root_folder": "/Downloads", "target_folder": "/Movies"},
    )
    sub = StorageSubTask(
        main_task=main,
        movie_id=movie.id,
        movie_code="ABC-LOG",
        movie_title="Title",
        status="queued",
        step="prepare",
        storage_mode="single",
    )
    db_session.add_all([main, sub])
    db_session.commit()

    class FakeRuntime:
        def should_stop(self, task_id: str) -> bool:
            return False

    class FailingProviderFactory:
        def create(self, config):
            raise RuntimeError("boom-provider")

    process_main_task(FakeRuntime(), FailingProviderFactory(), None, str(main.id))

    logs = read_storage_subtask_logs(str(sub.id))
    assert any("创建 CloudDrive2 客户端失败" in entry["message"] for entry in logs)
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_service.py::test_process_main_task_logs_provider_creation_failure -v
```

Expected: FAIL because `process_main_task` currently marks the subtask failed but does not write a JSONL subtask log.

- [ ] **Step 3: Add creation and queue logs in service**

In `backend/app/modules/storage/tasks/service.py`, import:

```python
from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
```

After creating each queued subtask in `_create_subtask()`, add:

```python
        write_storage_subtask_log(
            str(subtask.id),
            "INFO",
            "存储子任务已创建并等待执行",
            {
                "main_task_id": str(main_task.id),
                "movie_id": str(movie_id),
                "storage_mode": storage_mode,
                "target_locations": target_locations,
            },
        )
```

In `_create_subtask()` skipped branch after `self.db.flush()`, add:

```python
            write_storage_subtask_log(
                str(subtask.id),
                "INFO",
                "存储子任务已跳过",
                {
                    "main_task_id": str(main_task.id),
                    "movie_id": str(movie_id),
                    "skip_reason": skip_reason,
                },
            )
```

- [ ] **Step 4: Add worker boundary logs in runner**

In `backend/app/modules/storage/worker/runner.py`, import:

```python
from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
```

Inside `process_main_task`, after setting `main_task.status = "running"`, add:

```python
        logger.info("Storage main task %s claimed by worker", task_id)
```

Before creating the provider for each queued subtask, add:

```python
            write_storage_subtask_log(
                str(subtask.id),
                "INFO",
                "存储 worker 开始执行子任务",
                {
                    "main_task_id": str(main_task.id),
                    "movie_id": str(subtask.movie_id),
                    "step": subtask.step,
                },
            )
```

In provider creation exception block, before `db.commit()`, add:

```python
                write_storage_subtask_log(
                    str(subtask.id),
                    "ERROR",
                    f"创建 CloudDrive2 客户端失败: {exc}",
                    {"main_task_id": str(main_task.id)},
                )
```

In the `except Exception as exc` block that currently calls `logger.exception("Storage subtask %s failed", subtask.id)`, add this JSONL log before the `logger.exception` call:

```python
                write_storage_subtask_log(
                    str(subtask.id),
                    "ERROR",
                    f"存储子任务执行失败: {exc}",
                    {
                        "main_task_id": str(main_task.id),
                        "step": subtask.step,
                    },
                )
```

After `execute_subtask_pipeline(context)` succeeds, add:

```python
                write_storage_subtask_log(
                    str(subtask.id),
                    "INFO",
                    "存储子任务执行结束",
                    {
                        "main_task_id": str(main_task.id),
                        "status": subtask.status,
                        "step": subtask.step,
                    },
                )
```

- [ ] **Step 5: Run worker log test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_service.py::test_process_main_task_logs_provider_creation_failure -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/storage/tasks/service.py backend/app/modules/storage/worker/runner.py backend/tests/test_storage_worker_service.py
git commit -m "fix: log storage worker boundaries"
```

---

### Task 3: Add Pipeline Logs Around Magnet Submission and Selection

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`
- Modify: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Write failing magnet failure log test**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_execute_current_magnet_attempt_logs_submit_failure(tmp_path, monkeypatch):
    import uuid
    from dataclasses import dataclass
    from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs
    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    class FailingProvider:
        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            raise RuntimeError("cloud-submit-failed")

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_code: str = "ABC-FAIL"

    @dataclass
    class FakeContext:
        subtask: FakeSubtask
        config: dict
        provider: object

    subtask = FakeSubtask(id=uuid.uuid4())
    context = FakeContext(
        subtask=subtask,
        config={"download_root_folder": "/Downloads", "video_extensions": [".mp4"], "minimum_video_size_mb": 100},
        provider=FailingProvider(),
    )

    success = execute_current_magnet_attempt(
        context,
        {"id": "m1", "magnet_url": "magnet:?xt=urn:btih:abc", "tags": [], "weight": 10},
    )

    assert success is False
    logs = read_storage_subtask_logs(str(subtask.id))
    assert any("提交磁力失败" in entry["message"] for entry in logs)
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_logs_submit_failure -v
```

Expected: FAIL because `execute_current_magnet_attempt()` only writes Python logger warnings.

- [ ] **Step 3: Add helper logger in pipeline steps**

At the top of `backend/app/modules/storage/worker/steps.py`, add:

```python
from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
```

Add this helper below `logger = logging.getLogger(__name__)`:

```python
def _subtask_log(context, level: str, message: str, extra: dict | None = None) -> None:
    subtask_id = getattr(context.subtask, "id", None)
    if subtask_id is None:
        return
    write_storage_subtask_log(str(subtask_id), level, message, extra or {})
```

- [ ] **Step 4: Log magnet submission boundary**

In `execute_current_magnet_attempt()`, before `ensure_directory_chain(provider, download_folder)`, add:

```python
    _subtask_log(
        context,
        "INFO",
        "准备提交磁力到 CloudDrive2",
        {
            "magnet_id": magnet.get("id"),
            "download_folder": download_folder,
        },
    )
```

In the `except Exception as exc` block around `provider.submit_offline_download`, replace the existing warning-only behavior with:

```python
        logger.warning("Magnet download failed: %s", exc)
        _subtask_log(
            context,
            "ERROR",
            f"提交磁力失败: {exc}",
            {
                "magnet_id": magnet.get("id"),
                "download_folder": download_folder,
            },
        )
        return False
```

After successful `result = provider.submit_offline_download(magnet_url, download_folder)`, add:

```python
        _subtask_log(
            context,
            "INFO",
            "CloudDrive2 已接收磁力任务",
            {
                "magnet_id": magnet.get("id"),
                "download_folder": download_folder,
                "result_paths": getattr(result, "result_paths", []),
            },
        )
```

- [ ] **Step 5: Log no files and no main videos**

Before `return False` when `found_files` is empty, add:

```python
        _subtask_log(
            context,
            "WARNING",
            "未在下载目录找到可用视频文件",
            {"magnet_id": magnet.get("id"), "search_paths": search_paths},
        )
```

Before `return False` when `main_videos` is empty, add:

```python
        _subtask_log(
            context,
            "WARNING",
            "扫描到文件但未识别到主视频",
            {"magnet_id": magnet.get("id"), "file_count": len(found_files)},
        )
```

- [ ] **Step 6: Log move success and failure**

In the move `except Exception as exc` block, add:

```python
            _subtask_log(
                context,
                "ERROR",
                f"移动文件失败: {exc}",
                {"source": video["path"], "target_folder": final_folder},
            )
```

After all moves succeed and before `return True`, add:

```python
    _subtask_log(
        context,
        "INFO",
        "磁力任务处理成功",
        {"magnet_id": magnet.get("id"), "files": renamed_files},
    )
```

- [ ] **Step 7: Log pipeline start and each magnet attempt**

In `execute_subtask_pipeline()`, after setting `subtask.started_at`, add:

```python
    _subtask_log(context, "INFO", "存储子任务 pipeline 开始", {"movie_id": str(subtask.movie_id)})
```

Inside the magnet loop before `success = execute_current_magnet_attempt(context, magnet)`, add:

```python
        _subtask_log(
            context,
            "INFO",
            "开始尝试磁力",
            {
                "magnet_id": magnet.get("id"),
                "weight": magnet.get("weight"),
                "selected": magnet.get("selected"),
            },
        )
```

After `success = execute_current_magnet_attempt(context, magnet)`, add:

```python
        _subtask_log(
            context,
            "INFO" if success else "WARNING",
            "磁力尝试完成" if success else "磁力尝试失败，准备尝试下一条",
            {"magnet_id": magnet.get("id"), "success": success},
        )
```

- [ ] **Step 8: Run pipeline log test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_logs_submit_failure -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: log storage magnet pipeline"
```

---

### Task 4: Verify Queued Task Advances and Logs Are Visible

**Files:**
- Modify only files touched by earlier tasks if tests expose a concrete failure.

- [ ] **Step 1: Run backend storage tests**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_tasks_api.py \
  backend/tests/test_storage_runtime_redis.py \
  backend/tests/test_storage_worker_pipeline.py \
  backend/tests/test_storage_worker_service.py \
  backend/tests/test_storage_realtime_events.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run broader touched-area tests**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_config_api.py \
  backend/tests/test_realtime_events.py \
  backend/tests/test_content_movies_api.py \
  -v
```

Expected: PASS.

- [ ] **Step 3: Manual smoke test**

Start backend:

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

Create a single storage push from the movie list and verify:

- main task changes from `queued` to `running` or terminal status;
- subtask logs include `存储子任务已创建并等待执行`;
- subtask logs include `存储 worker 开始执行子任务`;
- subtask logs include either `CloudDrive2 已接收磁力任务` or `提交磁力失败`;
- CloudDrive2 receives an offline download request when the provider is reachable.

- [ ] **Step 4: Commit verification-only fixes if needed**

If Step 1 or Step 2 required code changes:

```bash
git status --short
git add backend/app/core/dependencies.py backend/app/modules/storage/tasks/service.py backend/app/modules/storage/worker/runner.py backend/app/modules/storage/worker/steps.py backend/tests/test_storage_tasks_api.py backend/tests/test_storage_worker_pipeline.py backend/tests/test_storage_worker_service.py
git commit -m "fix: stabilize storage queued task execution"
```

If no files changed during verification, do not create a commit.
