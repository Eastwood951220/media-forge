import threading
import uuid
from datetime import datetime

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
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


def test_list_phase_db_callbacks_use_isolated_sessions(db_session, monkeypatch) -> None:
    task, run = make_task_and_run(db_session)
    suffix = run.id.hex[:8]
    db_session.add(Movie(code=f"A-{suffix}", source_name="Existing A"))
    db_session.commit()

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
