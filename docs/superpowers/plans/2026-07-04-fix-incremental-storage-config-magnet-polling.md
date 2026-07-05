# Fix Incremental Threshold Storage Config Magnet Polling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three runtime defects: incremental crawl threshold should stop the current URL's remaining list pages immediately, storage config UI should expose per-subtask magnet attempt limit, and storage magnet execution should poll the download folder before trying the next magnet.

**Architecture:** Keep the fixes scoped to the existing crawler spider, storage configuration UI, and storage worker. The crawler fix changes only list collection behavior when the duplicate threshold is reached; the storage config fix exposes an already-existing backend field in frontend types and form; the worker fix adds a bounded poll loop around existing file discovery so a magnet is not marked failed until `download_max_poll_count` is exhausted.

**Tech Stack:** Python 3.12+, Pytest, React 19, TypeScript 6, Vite 8, Ant Design 6, Vitest 3.

---

## Root Cause Summary

Issue 1:

- `scraper/spiders/javdb/javdb_spider.py` detects `db_skipped >= incremental_threshold`.
- It then extends `detail_tasks` with the whole page, including already-existing skipped tasks, and calls `on_tasks_batch_created(fresh_tasks)` before breaking.
- That causes already-existing list items to flow into later detail task handling or persisted detail records instead of making the current URL collection stop cleanly and move on to the next configured URL.

Issue 2:

- Backend `backend/app/modules/storage/config/schemas.py` already has `magnet_max_attempts_per_subtask`.
- Frontend `frontend/src/api/storage/storageConfig/types.ts` and `frontend/src/pages/storage/config/StorageConfigPage.tsx` do not expose the field, so users cannot configure it.

Issue 3:

- `backend/app/modules/storage/worker/steps.py` submits a magnet, then immediately calls `find_existing_video_files(provider, search_terms, search_paths, config)` once.
- The code comments say polling is not implemented.
- If the cloud download is still in progress, the worker records no files and immediately tries the next magnet, ignoring `download_max_poll_count`.

## File Structure

- Modify `scraper/spiders/javdb/javdb_spider.py`: change threshold behavior to stop the current URL after persisting only non-skipped fresh tasks from the threshold page.
- Modify `scraper/tests/test_javdb_spider_dedupe_callbacks.py`: add a regression test for threshold stopping the first URL and continuing the next URL.
- Modify `frontend/src/api/storage/storageConfig/types.ts`: add `magnet_max_attempts_per_subtask`.
- Modify `frontend/src/pages/storage/config/StorageConfigPage.tsx`: add the missing InputNumber field.
- Add or modify frontend storage config test if the project has one; otherwise validate through `npm run build`.
- Modify `backend/app/modules/storage/worker/steps.py`: add bounded polling between magnet submission and failure.
- Modify `backend/tests/test_storage_worker_pipeline.py`: add tests for polling success before max count and polling exhaustion before trying next magnet.

---

### Task 1: Fix Incremental Threshold Stop Behavior Per URL

**Files:**
- Modify: `scraper/spiders/javdb/javdb_spider.py`
- Modify: `scraper/tests/test_javdb_spider_dedupe_callbacks.py`

- [ ] **Step 1: Add failing regression test**

Append this test to `scraper/tests/test_javdb_spider_dedupe_callbacks.py`:

```python
def test_incremental_threshold_stops_current_url_and_continues_next_url(monkeypatch) -> None:
    from scraper.tasks.task_schema import CrawlTask

    spider = JavdbSpider(fetcher=Fetcher())
    monkeypatch.setattr(spider_module, "MAX_LIST_PAGES", 5)
    monkeypatch.setattr(spider_module, "random_sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(spider_module, "is_security_check_page", lambda page: False)

    fetched_urls: list[str] = []

    def fake_fetch(url: str):
        fetched_urls.append(url)
        return url

    monkeypatch.setattr(spider, "fetch", fake_fetch)

    def fake_parse(page: str, source_page: int):
        if "actors/a" in page:
            return [
                {"code": f"AAA-{i:03d}", "url": f"https://javdb.com/v/aaa{i:03d}", "name": f"AAA {i:03d}"}
                for i in range(40)
            ]
        return [
            {"code": "BBB-001", "url": "https://javdb.com/v/bbb001", "name": "BBB 001"},
        ]

    monkeypatch.setattr(spider_module, "parse_search_page", fake_parse)

    created_batches: list[list[dict]] = []
    task = CrawlTask(
        name="任务",
        urls=[
            CrawlTaskUrlEntry(url="https://javdb.com/actors/a", url_type="actors"),
            CrawlTaskUrlEntry(url="https://javdb.com/actors/b", url_type="actors"),
        ],
    )

    result = spider.collect_all_detail_tasks(
        task,
        crawl_mode="incremental",
        incremental_threshold=20,
        db_check_callback=lambda codes: {code for code in codes if code.startswith("AAA-")},
        on_tasks_batch_created=created_batches.append,
    )

    assert any("actors/a" in url and "page=1" in url for url in fetched_urls)
    assert not any("actors/a" in url and "page=2" in url for url in fetched_urls)
    assert any("actors/b" in url and "page=1" in url for url in fetched_urls)
    assert [item["code"] for item in result] == ["BBB-001"]
    assert all(item[0]["code"] != "AAA-000" for item in created_batches if item)
```

- [ ] **Step 2: Run the regression test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest scraper/tests/test_javdb_spider_dedupe_callbacks.py::test_incremental_threshold_stops_current_url_and_continues_next_url -v
```

Expected: FAIL because `result` currently includes skipped `AAA-*` tasks from the threshold page, and `created_batches` receives those skipped tasks.

- [ ] **Step 3: Change threshold page handling**

In `scraper/spiders/javdb/javdb_spider.py`, inside `collect_detail_tasks_for_url`, replace the current threshold branch:

```python
                            detail_tasks.extend(fresh_tasks)
                            if on_tasks_batch_created and fresh_tasks:
                                on_tasks_batch_created(fresh_tasks)
                            break
```

with:

```python
                            non_skipped_tasks = [
                                item for item in fresh_tasks
                                if item.get("status") != TASK_STATUS_SKIPPED
                            ]
                            if non_skipped_tasks:
                                detail_tasks.extend(non_skipped_tasks)
                                if on_tasks_batch_created:
                                    on_tasks_batch_created(non_skipped_tasks)
                            msg = (
                                f"[{task_name}] 当前 URL 达到增量阈值，"
                                "停止该 URL 后续列表页，继续下一个 URL"
                            )
                            self._emit(msg, log_callback, "INFO")
                            break
```

This keeps genuinely new items on the threshold page, drops already-existing skipped items from the detail queue, stops the current URL's later pages, and lets `collect_all_detail_tasks()` continue with the next URL.

- [ ] **Step 4: Run crawler spider tests**

Run:

```bash
source .venv/bin/activate
python -m pytest scraper/tests/test_javdb_spider_dedupe_callbacks.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scraper/spiders/javdb/javdb_spider.py scraper/tests/test_javdb_spider_dedupe_callbacks.py
git commit -m "fix: stop current url at incremental threshold"
```

---

### Task 2: Expose Per-Subtask Magnet Attempt Limit in Storage Config UI

**Files:**
- Modify: `frontend/src/api/storage/storageConfig/types.ts`
- Modify: `frontend/src/pages/storage/config/StorageConfigPage.tsx`

- [ ] **Step 1: Add TypeScript field to storage config type**

In `frontend/src/api/storage/storageConfig/types.ts`, add this field to `StorageConfig` after `download_max_poll_count`:

```typescript
  magnet_max_attempts_per_subtask: number
```

`StorageConfigUpdate` already derives from `StorageConfig`, so no separate update type change is needed.

- [ ] **Step 2: Add form field to StorageConfigPage**

In `frontend/src/pages/storage/config/StorageConfigPage.tsx`, after the existing `download_max_poll_count` form item, add:

```tsx
          <Form.Item
            name="magnet_max_attempts_per_subtask"
            label="每个子任务最多尝试磁力条数"
            tooltip="当前磁力下载轮询超过最大次数后，才会尝试下一条磁力；超过此条数后子任务失败"
          >
            <InputNumber min={1} max={50} style={{ width: '100%' }} />
          </Form.Item>
```

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS. The storage config page should now include the missing field and submit it through the existing update API.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/storage/storageConfig/types.ts frontend/src/pages/storage/config/StorageConfigPage.tsx
git commit -m "fix: expose magnet attempt limit config"
```

---

### Task 3: Poll Download Folder Before Trying the Next Magnet

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`
- Modify: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Add failing polling success test**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_execute_current_magnet_attempt_polls_until_file_appears(monkeypatch, tmp_path):
    import uuid
    from dataclasses import dataclass
    from pathlib import PurePosixPath
    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.modules.storage.worker.steps.time.sleep", lambda seconds: None)

    class Result:
        success = True
        error_message = None
        result_paths = []

    class File:
        name = "ABC-123.mp4"
        full_path = "/Downloads/storage_sub/ABC-123.mp4"
        size = 500 * 1024 * 1024
        is_directory = False
        is_search_result = False

    class PollingProvider:
        def __init__(self) -> None:
            self.list_calls = 0
            self.moved: list[tuple[list[str], str]] = []

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            return Result()

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            return []

        def list_files(self, path, force_refresh=False):
            if path.startswith("/Downloads/storage_"):
                self.list_calls += 1
                return [] if self.list_calls < 3 else [File()]
            return []

        def move_files(self, source_paths, target_folder):
            self.moved.append((source_paths, target_folder))
            return None

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_code: str = "ABC-123"
        renamed_files: list | None = None
        moved_files: list | None = None
        result: dict | None = None

    @dataclass
    class FakeContext:
        subtask: FakeSubtask
        config: dict
        provider: object

    provider = PollingProvider()
    subtask = FakeSubtask(id=uuid.uuid4())
    context = FakeContext(
        subtask=subtask,
        config={
            "download_root_folder": "/Downloads",
            "target_folder": "/Movies",
            "download_max_poll_count": 5,
            "download_poll_interval_min": 0,
            "download_poll_interval_max": 0,
            "video_extensions": [".mp4"],
            "minimum_video_size_mb": 100,
        },
        provider=provider,
    )

    success = execute_current_magnet_attempt(
        context,
        {"id": "m1", "magnet_url": "magnet:?xt=urn:btih:abc", "tags": [], "weight": 10},
    )

    assert success is True
    assert provider.list_calls == 3
    assert provider.moved == [(["/Downloads/storage_sub/ABC-123.mp4"], "/Movies/ABC-123")]
```

- [ ] **Step 2: Add failing polling exhaustion test**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_execute_current_magnet_attempt_fails_after_download_poll_limit(monkeypatch, tmp_path):
    import uuid
    from dataclasses import dataclass
    from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs
    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.modules.storage.worker.steps.time.sleep", lambda seconds: None)

    class Result:
        success = True
        error_message = None
        result_paths = []

    class EmptyProvider:
        def __init__(self) -> None:
            self.list_calls = 0

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            return Result()

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            return []

        def list_files(self, path, force_refresh=False):
            if path.startswith("/Downloads/storage_"):
                self.list_calls += 1
            return []

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_code: str = "ABC-404"

    @dataclass
    class FakeContext:
        subtask: FakeSubtask
        config: dict
        provider: object

    provider = EmptyProvider()
    subtask = FakeSubtask(id=uuid.uuid4())
    context = FakeContext(
        subtask=subtask,
        config={
            "download_root_folder": "/Downloads",
            "download_max_poll_count": 3,
            "download_poll_interval_min": 0,
            "download_poll_interval_max": 0,
            "video_extensions": [".mp4"],
            "minimum_video_size_mb": 100,
        },
        provider=provider,
    )

    success = execute_current_magnet_attempt(
        context,
        {"id": "m1", "magnet_url": "magnet:?xt=urn:btih:abc", "tags": [], "weight": 10},
    )

    assert success is False
    assert provider.list_calls == 3
    logs = read_storage_subtask_logs(str(subtask.id))
    assert any("下载轮询达到最大次数" in entry["message"] for entry in logs)
```

- [ ] **Step 3: Run polling tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_polls_until_file_appears \
  backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_fails_after_download_poll_limit \
  -v
```

Expected: FAIL because `execute_current_magnet_attempt()` searches only once and does not poll.

- [ ] **Step 4: Add polling imports and helper**

At the top of `backend/app/modules/storage/worker/steps.py`, add:

```python
import random
import time
```

Add this helper below `target_files_exist`:

```python
def poll_downloaded_video_files(context, search_terms: list[str], search_paths: list[str]) -> list[dict]:
    from backend.app.modules.storage.worker.file_finder import find_existing_video_files

    config = context.config
    max_poll_count = int(config.get("download_max_poll_count", 10) or 10)
    poll_min = float(config.get("download_poll_interval_min", 5.0) or 0)
    poll_max = float(config.get("download_poll_interval_max", poll_min) or poll_min)
    if poll_max < poll_min:
        poll_max = poll_min

    for poll_index in range(1, max_poll_count + 1):
        found_files = find_existing_video_files(context.provider, search_terms, search_paths, config)
        if found_files:
            _subtask_log(
                context,
                "INFO",
                "下载轮询发现可用视频文件",
                {
                    "poll_index": poll_index,
                    "max_poll_count": max_poll_count,
                    "file_count": len(found_files),
                    "search_paths": search_paths,
                },
            )
            return found_files

        _subtask_log(
            context,
            "INFO",
            "下载轮询未发现可用视频文件",
            {
                "poll_index": poll_index,
                "max_poll_count": max_poll_count,
                "search_paths": search_paths,
            },
        )
        if poll_index < max_poll_count:
            time.sleep(random.uniform(poll_min, poll_max))

    _subtask_log(
        context,
        "WARNING",
        "下载轮询达到最大次数，当前磁力失败",
        {
            "max_poll_count": max_poll_count,
            "search_paths": search_paths,
        },
    )
    return []
```

- [ ] **Step 5: Use polling helper after submit**

In `execute_current_magnet_attempt()`, replace:

```python
    found_files = find_existing_video_files(provider, search_terms, search_paths, config)
```

with:

```python
    found_files = poll_downloaded_video_files(context, search_terms, search_paths)
```

Keep the existing `if not found_files:` branch, but it should now run only after `download_max_poll_count` is exhausted.

- [ ] **Step 6: Make non-success submit log explicit**

In `execute_current_magnet_attempt()`, inside:

```python
    if not result.success:
```

add before `return False`:

```python
        _subtask_log(
            context,
            "WARNING",
            f"CloudDrive2 未接受磁力任务: {result.error_message}",
            {"magnet_id": magnet.get("id")},
        )
```

- [ ] **Step 7: Run storage worker pipeline tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: poll storage downloads before next magnet"
```

---

### Task 4: Verify Combined Behavior

**Files:**
- Modify only files touched by earlier tasks if tests expose a concrete failure.

- [ ] **Step 1: Run crawler regression tests**

Run:

```bash
source .venv/bin/activate
python -m pytest scraper/tests/test_javdb_spider_dedupe_callbacks.py backend/tests/test_crawler_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 2: Run storage backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_config_api.py \
  backend/tests/test_storage_task_models.py \
  backend/tests/test_storage_worker_pipeline.py \
  backend/tests/test_storage_tasks_api.py \
  -v
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Manual smoke checks**

Run backend and frontend, then verify:

- In incremental crawl mode with threshold `20`, a URL page with `40` existing DB items logs threshold reached and does not request page 2 for that same URL.
- The next configured URL starts list page collection.
- Storage config page shows `每个子任务最多尝试磁力条数`.
- A storage subtask logs download polling attempts.
- The worker tries the next magnet only after `download_max_poll_count` unsuccessful polls.
- The worker marks the subtask failed only after `magnet_max_attempts_per_subtask` candidates are exhausted.

- [ ] **Step 5: Commit verification fixes if needed**

If verification requires code changes:

```bash
git status --short
git add scraper/spiders/javdb/javdb_spider.py scraper/tests/test_javdb_spider_dedupe_callbacks.py frontend/src/api/storage/storageConfig/types.ts frontend/src/pages/storage/config/StorageConfigPage.tsx backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: stabilize incremental and storage polling"
```

If no verification changes are needed, do not create an empty commit.
