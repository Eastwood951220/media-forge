import threading
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.modules.crawler.runs import logs as run_logs
from backend.app.modules.crawler.runtime.threaded import execute_threaded_crawl
from shared.database.models.content import Movie


class Runtime:
    def __init__(self) -> None:
        self.progress: dict[str, int] = {}

    def is_stop_requested(self, run_id: str) -> bool:
        return False

    def write_progress(self, run_id: str, progress: dict[str, int]) -> None:
        self.progress = dict(progress)


class FakeSpider:
    def __init__(self) -> None:
        self.list_started = False
        self.detail_started = False

    def collect_detail_tasks_for_url(self, *, url_entry, task_name, crawl_mode, incremental_threshold, stop_check, log_callback, db_check_callback, on_item_already_exists):
        self.list_started = True
        assert self.detail_started is False
        return [
            {"code": f"{url_entry.url_type}-001", "url": f"https://javdb.com/v/{url_entry.url_type}001", "name": url_entry.url_type}
        ]

    def run_single_detail_task(self, task, *, task_name, on_detail_completed, on_detail_failed, stop_check, log_callback, on_detail_check_callback, on_item_already_exists):
        self.detail_started = True
        completed = {**task, "status": "completed", "detail": {"code": task["code"], "source_name": task["name"]}}
        on_detail_completed(completed)
        return completed


class FakePipeline:
    def process_item(self, item, task_name=None, task_id=None):
        return {**item, "source_task_id": task_id}


def make_task_and_run(db_session) -> tuple[CrawlTask, CrawlRun]:
    task = CrawlTask(id=uuid.uuid4(), name="threaded", owner_id=uuid.uuid4(), is_skip=False)
    task.urls = [
        CrawlTaskUrl(position=0, url="https://javdb.com/a", url_type="A", final_url="https://javdb.com/a", source="javdb"),
        CrawlTaskUrl(position=1, url="https://javdb.com/b", url_type="B", final_url="https://javdb.com/b", source="javdb"),
    ]
    db_session.add(task)
    db_session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="running", crawl_mode="incremental", queued_at=datetime.now())
    db_session.add(run)
    db_session.commit()
    db_session.refresh(task)
    db_session.refresh(run)
    return task, run


def test_execute_threaded_crawl_finishes_list_before_detail(db_session, monkeypatch) -> None:
    task, run = make_task_and_run(db_session)
    spider = FakeSpider()
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_spider", lambda: spider)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_pipeline", lambda: FakePipeline())

    result = execute_threaded_crawl(db_session, run, task, Runtime())

    assert result["total_tasks"] == 2
    assert result["saved"] == 2
    rows = db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    assert sorted(row.status for row in rows) == ["saved", "saved"]


def test_list_phase_db_callbacks_use_isolated_sessions(db_session, monkeypatch, tmp_path) -> None:
    task, run = make_task_and_run(db_session)
    suffix = run.id.hex[:8]
    db_session.add(Movie(code=f"A-{suffix}", source_name="Existing A"))
    db_session.commit()
    monkeypatch.setattr(run_logs, "RUN_LOG_DIR", str(tmp_path))

    main_thread_id = threading.get_ident()

    def guard_session_method(method_name: str) -> None:
        original = getattr(db_session, method_name)

        def guarded(*args, **kwargs):
            if threading.get_ident() != main_thread_id:
                raise AssertionError("main crawler session was used from a list worker thread")
            return original(*args, **kwargs)

        monkeypatch.setattr(db_session, method_name, guarded)

    for method_name in ("get", "scalars", "scalar", "flush", "commit", "add", "add_all", "merge"):
        if hasattr(db_session, method_name):
            guard_session_method(method_name)

    class DedupeSpider(FakeSpider):
        def collect_detail_tasks_for_url(
            self,
            *,
            url_entry,
            task_name,
            crawl_mode,
            incremental_threshold,
            stop_check,
            log_callback,
            db_check_callback,
            on_item_already_exists,
        ):
            self.list_started = True
            log_callback(f"worker collected {url_entry.url_type}")
            code = f"{url_entry.url_type}-{suffix}"
            existing_codes = db_check_callback([code])
            if code in existing_codes:
                on_item_already_exists(
                    {
                        "code": code,
                        "url": f"https://javdb.com/v/{url_entry.url_type.lower()}{suffix}",
                        "name": url_entry.url_type,
                    }
                )
                return []
            return [
                {
                    "code": code,
                    "url": f"https://javdb.com/v/{url_entry.url_type.lower()}{suffix}",
                    "name": url_entry.url_type,
                }
            ]

    spider = DedupeSpider()
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_spider", lambda: spider)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_pipeline", lambda: FakePipeline())

    result = execute_threaded_crawl(db_session, run, task, Runtime())

    assert result["total_tasks"] == 1
    assert result["saved"] == 1
    assert spider.list_started is True
    assert spider.detail_started is True
    rows = db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    assert [row.code for row in rows] == [f"B-{suffix}"]
    assert rows[0].status == "saved"
    logs = run_logs.load_run_logs(str(run.id))
    skipped_log = next(entry for entry in logs if entry["message"].startswith("跳过已存在影片并追加任务ID"))
    assert skipped_log["context"] == {"code": f"A-{suffix}"}


@pytest.mark.parametrize("crawl_mode", ["incremental", "full"])
def test_threaded_list_db_check_appends_source_task_id_without_already_exists_callback(db_session, monkeypatch, crawl_mode) -> None:
    task, run = make_task_and_run(db_session)
    run.crawl_mode = crawl_mode
    existing_code = f"A-{run.id.hex[:8]}"
    db_session.add(Movie(code=existing_code, source_name="Existing A", source_task_ids=[]))
    db_session.commit()

    class DbCheckOnlySpider(FakeSpider):
        def collect_detail_tasks_for_url(
            self,
            *,
            url_entry,
            task_name,
            crawl_mode,
            incremental_threshold,
            stop_check,
            log_callback,
            db_check_callback,
            on_item_already_exists,
        ):
            self.list_started = True
            if url_entry.url_type == "A":
                assert existing_code in db_check_callback([existing_code])
                return []
            return [
                {
                    "code": f"B-{run.id.hex[:8]}",
                    "url": f"https://javdb.com/v/b{run.id.hex[:8]}",
                    "name": "B",
                }
            ]

    spider = DbCheckOnlySpider()
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_spider", lambda: spider)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_pipeline", lambda: FakePipeline())

    result = execute_threaded_crawl(db_session, run, task, Runtime())
    movie = db_session.scalar(select(Movie).where(Movie.code == existing_code))

    assert result["total_tasks"] == 1
    assert result["saved"] == 1
    assert str(task.id) in [str(value) for value in movie.source_task_ids]


def test_list_phase_snapshots_worker_inputs_before_main_commit(db_session, monkeypatch) -> None:
    task, run = make_task_and_run(db_session)
    suffix = run.id.hex[:8]
    db_session.add(Movie(code=f"B-{suffix}", source_name="Existing B"))
    db_session.commit()

    main_thread_id = threading.get_ident()
    first_list_commit_seen = threading.Event()

    def guard_session_method(method_name: str) -> None:
        original = getattr(db_session, method_name)

        def guarded(*args, **kwargs):
            if threading.get_ident() != main_thread_id:
                raise AssertionError("main crawler session was used from a list worker thread")
            return original(*args, **kwargs)

        monkeypatch.setattr(db_session, method_name, guarded)

    for method_name in ("get", "scalars", "scalar", "flush", "add", "add_all", "merge", "refresh", "execute"):
        if hasattr(db_session, method_name):
            guard_session_method(method_name)

    original_commit = db_session.commit

    def guarded_commit(*args, **kwargs):
        if threading.get_ident() != main_thread_id:
            raise AssertionError("main crawler session was used from a list worker thread")
        result = original_commit(*args, **kwargs)
        first_list_commit_seen.set()
        return result

    monkeypatch.setattr(db_session, "commit", guarded_commit)

    class ExpirationRaceSpider(FakeSpider):
        def collect_detail_tasks_for_url(
            self,
            *,
            url_entry,
            task_name,
            crawl_mode,
            incremental_threshold,
            stop_check,
            log_callback,
            db_check_callback,
            on_item_already_exists,
        ):
            if url_entry.url_type == "A":
                return [
                    {
                        "code": f"A-{suffix}",
                        "url": f"https://javdb.com/v/a{suffix}",
                        "name": url_entry.url_type,
                    }
                ]

            assert first_list_commit_seen.wait(timeout=2), "main thread did not commit the first list future"
            log_callback(f"worker collected {url_entry.url_type}")
            code = f"{url_entry.url_type}-{suffix}"
            assert code in db_check_callback([code])
            on_item_already_exists(
                {
                    "code": code,
                    "url": f"https://javdb.com/v/{url_entry.url_type.lower()}{suffix}",
                    "name": url_entry.url_type,
                }
            )
            return []

    spider = ExpirationRaceSpider()
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_spider", lambda: spider)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_pipeline", lambda: FakePipeline())

    result = execute_threaded_crawl(db_session, run, task, Runtime())

    assert result["total_tasks"] == 1
    assert result["saved"] == 1
    rows = db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    assert [row.code for row in rows] == [f"A-{suffix}"]


def test_temporary_run_skips_list_phase_and_processes_seeded_detail(db_session, monkeypatch) -> None:
    task, run = make_task_and_run(db_session)
    run.crawl_mode = "temporary"
    run.result = {"temporary": True, "detail_url_count": 1}
    db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).delete()
    db_session.add(CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code=None,
        source_url="https://javdb.com/v/temp001",
        source_name="临时详情页",
        source_url_name="临时任务",
        task_url="https://javdb.com/v/temp001",
        task_final_url="https://javdb.com/v/temp001",
        task_url_type="temporary_detail",
        status="pending_crawl",
        created_at=datetime.now(),
    ))
    db_session.commit()

    class TempSpider(FakeSpider):
        def collect_detail_tasks_for_url(self, **kwargs):
            raise AssertionError("temporary run must not collect list URLs")

        def run_single_detail_task(self, task, **kwargs):
            self.detail_started = True
            completed = {
                **task,
                "status": "completed",
                "detail": {"code": "TEMP-001", "source_name": "Temp Movie"},
            }
            kwargs["on_detail_completed"](completed)
            return completed

    spider = TempSpider()
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_spider", lambda: spider)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_pipeline", lambda: FakePipeline())

    result = execute_threaded_crawl(db_session, run, task, Runtime(), detail_only=True)

    row = db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).one()
    assert result["total_tasks"] == 1
    assert result["saved"] == 1
    assert row.status == "saved"
    assert row.item_data["code"] == "TEMP-001"
    movie = db_session.scalar(select(Movie).where(Movie.code == "TEMP-001"))
    assert movie is not None
    assert str(task.id) in [str(value) for value in movie.source_task_ids]


def test_detail_skip_existing_appends_source_task_id(db_session, monkeypatch) -> None:
    task, run = make_task_and_run(db_session)
    run.crawl_mode = "temporary"
    db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).delete()
    db_session.add(Movie(code="TEMP-EXIST", source_name="Existing", source_task_ids=[]))
    db_session.add(CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code=None,
        source_url="https://javdb.com/v/exist",
        source_name="临时详情页",
        source_url_name="临时任务",
        task_url_type="temporary_detail",
        status="pending_crawl",
        created_at=datetime.now(),
    ))
    db_session.commit()

    class ExistingSpider(FakeSpider):
        def collect_detail_tasks_for_url(self, **kwargs):
            raise AssertionError("temporary run must not collect list URLs")

        def run_single_detail_task(self, task, **kwargs):
            payload = {**task, "code": "TEMP-EXIST", "status": "skipped", "reason": "already_exists"}
            kwargs["on_item_already_exists"](payload)
            return payload

    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_spider", lambda: ExistingSpider())
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_pipeline", lambda: FakePipeline())

    result = execute_threaded_crawl(db_session, run, task, Runtime(), detail_only=True)
    movie = db_session.scalar(select(Movie).where(Movie.code == "TEMP-EXIST"))
    row = db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).one()

    assert result["skipped"] == 1
    assert row.status == "skipped"
    assert row.error == "already_exists"
    assert str(task.id) in [str(value) for value in movie.source_task_ids]


def test_temporary_detail_run_persists_parsed_code_and_title(db_session, monkeypatch) -> None:
    task = CrawlTask(id=uuid.uuid4(), name="temporary-task", owner_id=uuid.uuid4(), is_skip=False)
    db_session.add(task)
    db_session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="temporary",
        queued_at=datetime.now(),
    )
    db_session.add(run)
    db_session.flush()
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code=None,
        source_url="https://javdb.com/v/timd036",
        source_name="临时详情页",
        source_url_name="临时任务",
        task_url="https://javdb.com/v/timd036",
        task_final_url="https://javdb.com/v/timd036",
        task_url_type="temporary_detail",
        status="pending_crawl",
        created_at=datetime.now(),
    )
    db_session.add(detail)
    db_session.commit()
    db_session.refresh(task)
    db_session.refresh(run)

    class TemporarySpider:
        def run_single_detail_task(
            self,
            task_info,
            *,
            task_name,
            on_detail_completed,
            on_detail_failed,
            stop_check,
            log_callback,
            on_detail_check_callback,
            on_item_already_exists,
        ):
            return {
                **task_info,
                "status": "completed",
                "url": task_info["url"],
                "detail": {
                    "code": "TIMD-036",
                    "source_name": "極上メス男子ゆうきくん無限アクメ肉棒大乱交！！",
                    "source_url": task_info["url"],
                },
            }

    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_spider", lambda: TemporarySpider())
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_pipeline", lambda: FakePipeline())

    result = execute_threaded_crawl(db_session, run, task, Runtime(), detail_only=True)

    assert result["saved"] == 1
    db_session.expire_all()
    row = db_session.get(CrawlRunDetailTask, detail.id)
    assert row.status == "saved"
    assert row.code == "TIMD-036"
    assert row.source_name == "極上メス男子ゆうきくん無限アクメ肉棒大乱交！！"
    assert row.item_data["code"] == "TIMD-036"
    assert row.item_data["source_name"] == "極上メス男子ゆうきくん無限アクメ肉棒大乱交！！"


def test_detail_page_code_replaces_existing_list_stage_code(db_session, monkeypatch) -> None:
    task, run = make_task_and_run(db_session)
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code="LIST-036",
        source_url="https://javdb.com/v/timd036",
        source_name="List Stage Title",
        status="pending_crawl",
        created_at=datetime.now(),
    )
    db_session.add(detail)
    db_session.commit()
    db_session.refresh(task)
    db_session.refresh(run)

    class DetailCodeSpider:
        def run_single_detail_task(
            self,
            task_info,
            *,
            task_name,
            on_detail_completed,
            on_detail_failed,
            stop_check,
            log_callback,
            on_detail_check_callback,
            on_item_already_exists,
        ):
            return {
                **task_info,
                "status": "completed",
                "url": task_info["url"],
                "detail": {
                    "code": "TIMD-036",
                    "source_name": "Detail Stage Title",
                    "source_url": task_info["url"],
                },
            }

    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_spider", lambda: DetailCodeSpider())
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_pipeline", lambda: FakePipeline())

    result = execute_threaded_crawl(db_session, run, task, Runtime(), detail_only=True)

    assert result["saved"] == 1
    db_session.expire_all()
    row = db_session.get(CrawlRunDetailTask, detail.id)
    assert row.code == "TIMD-036"
    assert row.source_name == "Detail Stage Title"
    assert row.item_data["code"] == "TIMD-036"
