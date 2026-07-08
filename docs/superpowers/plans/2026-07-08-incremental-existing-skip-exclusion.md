# Incremental Existing Skip Exclusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exclude incremental list-phase `already_exists` rows from crawler child tasks and crawl counts while still appending the current crawl task ID to existing movies.

**Architecture:** Keep existing crawler phases and statuses. Change the JavDB spider list-phase DB dedupe path so incremental `already_exists` rows are reported through `on_item_already_exists()` but not returned or sent to `on_tasks_batch_created()`. Adjust runtime `on_item_already_exists()` so list-phase calls without a persisted detail row do not increment skipped progress, while detail-phase calls with a row keep existing skipped behavior.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, Pytest, scraper JavDB spider, backend crawler runtime.

## Global Constraints

- Do not change full crawl behavior. If full crawl currently creates skipped detail rows for existing movies, that behavior remains unchanged.
- Do not introduce a new task status such as `ignored`.
- Do not change movie persistence, magnet persistence, or detail retry behavior.
- Do not change the frontend child task table beyond the fact that excluded rows no longer appear in API results.
- Preserve incremental threshold behavior: the threshold is still based on how many existing rows were found on the current list page.
- Preserve detail-phase `already_exists` behavior.

---

## File Structure

- Modify `scraper/spiders/javdb/javdb_spider.py`: add `on_item_already_exists` to list collection signatures and filter incremental list-phase existing rows before detail task creation.
- Modify `scraper/tests/test_javdb_spider_dedupe_callbacks.py`: update list-phase DB dedupe expectations and add callback coverage.
- Modify `backend/app/modules/crawler/runtime/callbacks.py`: avoid skipped progress increments when `on_item_already_exists()` is called without a persisted detail row.
- Modify `backend/tests/test_crawler_worker_service.py`: update list-phase dedupe runtime behavior and preserve detail-phase dedupe behavior.
- Run `backend/tests/test_crawler_runtime_adapters.py`: confirms result summarization remains detail-task based without adding new statuses.

---

### Task 1: Exclude Incremental List-Phase Existing Rows In The Spider

**Files:**
- Modify: `scraper/spiders/javdb/javdb_spider.py`
- Test: `scraper/tests/test_javdb_spider_dedupe_callbacks.py`

**Interfaces:**
- Produces updated signatures:
  - `JavdbSpider.collect_detail_tasks_for_url(..., on_item_already_exists=None) -> list[dict]`
  - `JavdbSpider.collect_all_detail_tasks(..., on_item_already_exists=None) -> list[dict]`
- `run_task()` passes its existing `on_item_already_exists` argument into `collect_all_detail_tasks()`.
- In incremental mode, list-phase existing rows trigger `on_item_already_exists(task)` but are excluded from returned detail tasks and `on_tasks_batch_created()` batches.
- In full mode, existing skipped row behavior remains unchanged.

- [ ] **Step 1: Replace the existing list-phase dedupe test with the new incremental behavior**

In `scraper/tests/test_javdb_spider_dedupe_callbacks.py`, replace `test_list_phase_marks_existing_codes_skipped()` with:

```python
def test_incremental_list_phase_excludes_existing_codes_from_detail_tasks(monkeypatch) -> None:
    spider = JavdbSpider(fetcher=Fetcher())
    monkeypatch.setattr(spider_module, "MAX_LIST_PAGES", 1)
    monkeypatch.setattr(spider_module, "random_sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(spider_module, "is_security_check_page", lambda page: False)
    monkeypatch.setattr(
        spider_module,
        "parse_search_page",
        lambda page, source_page: [
            {"code": "AAA-030", "url": "https://javdb.com/v/aaa030", "name": "AAA 030"},
            {"code": "AAA-031", "url": "https://javdb.com/v/aaa031", "name": "AAA 031"},
        ],
    )

    created_batches: list[list[dict]] = []
    already_exists: list[dict] = []
    result = spider.collect_detail_tasks_for_url(
        url_entry=CrawlTaskUrlEntry(url="https://javdb.com/actors/a", url_type="actors"),
        task_name="任务",
        crawl_mode="incremental",
        db_check_callback=lambda codes: {"AAA-030"},
        on_tasks_batch_created=created_batches.append,
        on_item_already_exists=already_exists.append,
    )

    assert [item["code"] for item in result] == ["AAA-031"]
    assert "status" not in result[0]
    assert [[item["code"] for item in batch] for batch in created_batches] == [["AAA-031"]]
    assert [item["code"] for item in already_exists] == ["AAA-030"]
    assert already_exists[0]["status"] == "skipped"
    assert already_exists[0]["reason"] == "already_exists"
```

- [ ] **Step 2: Add a full-mode regression test**

Append this test to `scraper/tests/test_javdb_spider_dedupe_callbacks.py`:

```python
def test_full_list_phase_keeps_existing_codes_as_skipped_tasks(monkeypatch) -> None:
    spider = JavdbSpider(fetcher=Fetcher())
    monkeypatch.setattr(spider_module, "MAX_LIST_PAGES", 1)
    monkeypatch.setattr(spider_module, "random_sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(spider_module, "is_security_check_page", lambda page: False)
    monkeypatch.setattr(
        spider_module,
        "parse_search_page",
        lambda page, source_page: [
            {"code": "AAA-050", "url": "https://javdb.com/v/aaa050", "name": "AAA 050"},
            {"code": "AAA-051", "url": "https://javdb.com/v/aaa051", "name": "AAA 051"},
        ],
    )

    created_batches: list[list[dict]] = []
    already_exists: list[dict] = []
    result = spider.collect_detail_tasks_for_url(
        url_entry=CrawlTaskUrlEntry(url="https://javdb.com/actors/a", url_type="actors"),
        task_name="任务",
        crawl_mode="full",
        db_check_callback=lambda codes: {"AAA-050"},
        on_tasks_batch_created=created_batches.append,
        on_item_already_exists=already_exists.append,
    )

    assert [item["code"] for item in result] == ["AAA-050", "AAA-051"]
    assert result[0]["status"] == "skipped"
    assert result[0]["reason"] == "already_exists"
    assert [[item["code"] for item in batch] for batch in created_batches] == [["AAA-050", "AAA-051"]]
    assert already_exists == []
```

- [ ] **Step 3: Update the threshold test expectation**

In `test_incremental_threshold_stops_current_url_and_continues_next_url()`, replace the final `created_batches` assertion:

```python
    assert all(item[0]["code"] != "AAA-000" for item in created_batches if item)
```

with:

```python
    assert [[item["code"] for item in batch] for batch in created_batches] == [["BBB-001"]]
```

- [ ] **Step 4: Run spider tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest scraper/tests/test_javdb_spider_dedupe_callbacks.py -v
```

Expected: FAIL because `collect_detail_tasks_for_url()` does not accept `on_item_already_exists`, and current incremental behavior still returns skipped existing rows.

- [ ] **Step 5: Add list-phase callback parameters**

In `scraper/spiders/javdb/javdb_spider.py`, add `on_item_already_exists=None` to `collect_detail_tasks_for_url()`:

```python
    def collect_detail_tasks_for_url(
        self,
        url_entry: CrawlTaskUrlEntry,
        task_name: str,
        crawl_mode: str = "incremental",
        incremental_threshold: int = 0,
        stop_check=None,
        log_callback=None,
        on_tasks_batch_created=None,
        db_check_callback=None,
        on_item_already_exists=None,
    ) -> list[dict]:
```

Add the same parameter to `collect_all_detail_tasks()`:

```python
    def collect_all_detail_tasks(
        self,
        task: CrawlTask,
        crawl_mode: str = "incremental",
        incremental_threshold: int = 0,
        stop_check=None,
        log_callback=None,
        on_tasks_batch_created=None,
        db_check_callback=None,
        on_item_already_exists=None,
    ) -> list[dict]:
```

When `collect_all_detail_tasks()` calls `collect_detail_tasks_for_url()`, pass the callback:

```python
                on_item_already_exists=on_item_already_exists,
```

When `run_task()` calls `collect_all_detail_tasks()`, pass its existing callback:

```python
            on_item_already_exists=on_item_already_exists,
```

- [ ] **Step 6: Replace DB dedupe block with split behavior**

In `scraper/spiders/javdb/javdb_spider.py`, inside `collect_detail_tasks_for_url()`, replace the current `# DB dedup` block through the incremental threshold handling with:

```python
            existing_count = 0
            if db_check_callback and fresh_tasks:
                codes_to_check = [t.get("code") for t in fresh_tasks if t.get("code")]
                if codes_to_check:
                    existing_codes = db_check_callback(codes_to_check)
                    if existing_codes:
                        crawlable_tasks: list[dict] = []
                        ignored_existing_tasks: list[dict] = []
                        kept_skipped_tasks: list[dict] = []
                        for t in fresh_tasks:
                            code = t.get("code")
                            if code and code in existing_codes:
                                t["status"] = TASK_STATUS_SKIPPED
                                t["reason"] = "already_exists"
                                existing_count += 1
                                if crawl_mode == "incremental":
                                    ignored_existing_tasks.append(t)
                                else:
                                    kept_skipped_tasks.append(t)
                                continue
                            crawlable_tasks.append(t)

                        if ignored_existing_tasks:
                            for task_info in ignored_existing_tasks:
                                if on_item_already_exists:
                                    on_item_already_exists(task_info)
                            msg = (
                                f"{prefix} 列表页 {page_no}: {len(ignored_existing_tasks)} 条已存在于数据库, "
                                "不创建子任务"
                            )
                            self._emit(msg, log_callback, "INFO")

                        if kept_skipped_tasks:
                            msg = f"{prefix} 列表页 {page_no}: {len(kept_skipped_tasks)} 条已存在于数据库, 跳过"
                            self._emit(msg, log_callback, "INFO")

                        fresh_tasks = [*kept_skipped_tasks, *crawlable_tasks]

                        if (
                            crawl_mode == "incremental"
                            and incremental_threshold > 0
                            and existing_count >= incremental_threshold
                        ):
                            msg = (
                                f"{prefix} 列表页 {page_no} 已存在 {existing_count} 条 "
                                f"(>= 阈值 {incremental_threshold}), 跳过后续页面"
                            )
                            self._emit(msg, log_callback, "INFO")
                            if fresh_tasks:
                                detail_tasks.extend(fresh_tasks)
                                if on_tasks_batch_created:
                                    on_tasks_batch_created(fresh_tasks)
                            msg = (
                                f"{prefix} 当前 URL 达到增量阈值，"
                                "停止该 URL 后续列表页，继续下一个 URL"
                            )
                            self._emit(msg, log_callback, "INFO")
                            break
```

Keep the existing code after this block:

```python
            detail_tasks.extend(fresh_tasks)

            if on_tasks_batch_created and fresh_tasks:
                on_tasks_batch_created(fresh_tasks)
```

- [ ] **Step 7: Run spider tests to verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest scraper/tests/test_javdb_spider_dedupe_callbacks.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add scraper/spiders/javdb/javdb_spider.py scraper/tests/test_javdb_spider_dedupe_callbacks.py
git commit -m "fix: exclude incremental existing list items"
```

---

### Task 2: Keep List-Phase Existing Rows Out Of Runtime Counts

**Files:**
- Modify: `backend/app/modules/crawler/runtime/callbacks.py`
- Modify: `backend/tests/test_crawler_worker_service.py`

**Interfaces:**
- Consumes Task 1 behavior: incremental list-phase existing rows call `callbacks.on_item_already_exists(task_info)` without a persisted `CrawlRunDetailTask`.
- Produces runtime callback behavior:
  - no detail row: append `source_task_id`, write log, do not increment skipped progress, do not publish detail update;
  - detail row exists: preserve current skipped-row behavior.

- [ ] **Step 1: Update the list-phase runtime stub**

In `backend/tests/test_crawler_worker_service.py`, replace `ListPhaseDedupeCrawlerEngineStub.crawl_task()` with:

```python
class ListPhaseDedupeCrawlerEngineStub:
    def crawl_task(self, task, *, task_id=None, crawl_mode="incremental", incremental_threshold=0, callbacks):
        existing_codes = callbacks.db_check_callback(["AAA-010", "AAA-011"])
        batch = [
            {"code": "AAA-010", "url": "https://javdb.com/v/aaa010", "name": "AAA 010"},
            {"code": "AAA-011", "url": "https://javdb.com/v/aaa011", "name": "AAA 011"},
        ]
        crawlable = []
        for item in batch:
            if item["code"] in existing_codes:
                item["status"] = "skipped"
                item["reason"] = "already_exists"
                if callbacks.on_item_already_exists:
                    callbacks.on_item_already_exists(item)
            else:
                crawlable.append(item)
        if callbacks.on_tasks_batch_created:
            callbacks.on_tasks_batch_created(crawlable)
        return {
            "total_tasks": 1,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "skipped_tasks": 0,
        }
```

- [ ] **Step 2: Update the list-phase runtime test expectations**

In `test_execute_run_marks_list_phase_existing_movies_skipped()`, rename the test:

```python
def test_execute_run_excludes_list_phase_existing_movies_from_detail_tasks(monkeypatch) -> None:
```

Replace the assertions after `execute_run(...)` with:

```python
    existing_detail = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "AAA-010").one_or_none()
    pending = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "AAA-011").one()
    movie = session.scalar(select(Movie).where(Movie.code == "AAA-010"))

    assert existing_detail is None
    assert pending.status == "pending_crawl"
    assert str(run.task_id) in [str(tid) for tid in movie.source_task_ids]
    refreshed = session.get(CrawlRun, run.id)
    assert refreshed.result["total_tasks"] == 1
    assert refreshed.result["skipped_tasks"] == 0
    assert runtime.progress == {"total": 1, "saved": 0, "failed": 0, "skipped": 0, "save_failed": 0}
```

- [ ] **Step 3: Run the list-phase runtime test to verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py::test_execute_run_excludes_list_phase_existing_movies_from_detail_tasks -v
```

Expected: FAIL because `on_item_already_exists()` currently increments skipped progress even when no detail row exists.

- [ ] **Step 4: Update `on_item_already_exists()`**

In `backend/app/modules/crawler/runtime/callbacks.py`, replace `on_item_already_exists()` with:

```python
    def on_item_already_exists(task_info: dict[str, Any]) -> None:
        detail = active_indexed_detail(task_info)
        code = task_info.get("code")
        was_skipped = detail is not None and detail.status == "skipped"
        if detail:
            detail.status = "skipped"
            detail.error = "already_exists"
            detail.crawled_at = detail.crawled_at or datetime.now()
            detail.saved_at = None
        append_source_task_id(ctx.db, code, ctx.task.id)
        if detail is not None and not was_skipped:
            increment_progress(ctx.progress, "skipped")
        write_progress(ctx.runtime, str(ctx.run.id), ctx.progress)
        ctx.db.commit()
        if detail:
            publish_run_detail_updated(ctx.db, ctx.run, [detail])
        append_run_log_for_run(ctx.db, ctx.run, f"跳过已存在影片并追加任务ID: {code}", "INFO", code=code)
```

- [ ] **Step 5: Run list-phase and detail-phase runtime tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py::test_execute_run_excludes_list_phase_existing_movies_from_detail_tasks tests/test_crawler_worker_service.py::test_execute_run_marks_detail_phase_existing_movies_skipped -v
```

Expected: PASS. The list-phase test confirms no skipped detail row and no skipped count. The detail-phase test confirms existing detail rows still become skipped and count as skipped.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/crawler/runtime/callbacks.py backend/tests/test_crawler_worker_service.py
git commit -m "fix: exclude list existing rows from crawler counts"
```

---

### Task 3: Focused Regression Verification

**Files:**
- No new files.
- Verify files changed in Tasks 1-2.

**Interfaces:**
- Consumes Task 1 spider behavior and Task 2 runtime behavior.
- Produces verified incremental list-phase existing-row exclusion without changing detail-phase existing-row behavior.

- [ ] **Step 1: Run focused crawler tests**

Run:

```bash
source .venv/bin/activate
python -m pytest scraper/tests/test_javdb_spider_dedupe_callbacks.py -v
cd backend
python -m pytest tests/test_crawler_worker_service.py::test_execute_run_excludes_list_phase_existing_movies_from_detail_tasks tests/test_crawler_worker_service.py::test_execute_run_marks_detail_phase_existing_movies_skipped tests/test_crawler_runtime_adapters.py -v
```

Expected: PASS.

- [ ] **Step 2: Run broader backend crawler tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py tests/test_crawler_runtime_adapters.py tests/test_crawler_runs_api.py -v
```

Expected: PASS. If failures come from unrelated uncommitted work, record the exact failing test names and messages.

- [ ] **Step 3: Inspect final diff**

Run:

```bash
git status --short
git diff -- scraper/spiders/javdb/javdb_spider.py scraper/tests/test_javdb_spider_dedupe_callbacks.py backend/app/modules/crawler/runtime/callbacks.py backend/tests/test_crawler_worker_service.py
```

Expected: only intended spider, runtime callback, and test files differ unless previous task commits already made the working tree clean for those paths.

- [ ] **Step 4: Commit verification fixes if needed**

If verification required small corrections, commit them:

```bash
git add scraper/spiders/javdb/javdb_spider.py scraper/tests/test_javdb_spider_dedupe_callbacks.py backend/app/modules/crawler/runtime/callbacks.py backend/tests/test_crawler_worker_service.py
git commit -m "test: verify incremental existing skip exclusion"
```

If no corrections were needed, do not create an empty commit.
