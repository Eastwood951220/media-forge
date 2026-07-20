from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.modules.crawler.runtime import threaded
from backend.app.modules.realtime.bus import event_bus
from backend.tests.conftest import TestingSessionLocal


@dataclass
class FakeConfig:
    LIST_MAX_WORKERS: int = 1
    INCREMENTAL_EXIST_THRESHOLD: int = 5


class FakeRuntime:
    def is_stop_requested(self, _run_id: str) -> bool:
        return False


class FakeSpider:
    def collect_detail_tasks_for_url(self, *, url_entry, task_name, crawl_mode, incremental_threshold, stop_check, log_callback, db_check_callback, on_item_already_exists):
        log_callback(f"URL完成: {url_entry.url}", "INFO")
        return [
            {
                "code": f"AAA-{url_entry.position:03d}",
                "url": url_entry.url,
                "name": f"影片{url_entry.position}",
                "_task_url_name": url_entry.url_name,
                "_task_url": url_entry.url,
                "_task_final_url": url_entry.final_url,
                "_task_url_type": url_entry.url_type,
            }
        ]


def drain(queue):
    rows = []
    while not queue.empty():
        rows.append(queue.get_nowait())
    return rows


def test_threaded_incremental_list_phase_does_not_persist_already_exists_skips(admin_user, monkeypatch) -> None:
    from backend.app.models.crawl_run import CrawlRunDetailTask

    session = TestingSessionLocal()
    task = CrawlTask(name="任务-skip-hide", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    session.add(CrawlTaskUrl(
        task_id=task.id,
        position=1,
        url="https://example.test/list-1",
        url_type="list",
        has_magnet=True,
        has_chinese_sub=False,
        sort_type=0,
        source="javdb",
        final_url="https://example.test/list-1?page=1",
        url_name="入口1",
    ))
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        created_at=datetime.now(),
    )
    session.add(run)
    session.commit()
    session.refresh(task)
    session.refresh(run)

    class SkipSpider:
        def collect_detail_tasks_for_url(self, **kwargs):
            return [
                {
                    "code": "OLD-001",
                    "url": "https://javdb.com/v/old001",
                    "name": "Old Movie",
                    "status": "skipped",
                    "reason": "already_exists",
                    "_task_url_name": "入口1",
                    "_task_url": "https://example.test/list-1",
                    "_task_final_url": "https://example.test/list-1?page=1",
                    "_task_url_type": "list",
                },
                {
                    "code": "NEW-001",
                    "url": "https://javdb.com/v/new001",
                    "name": "New Movie",
                    "_task_url_name": "入口1",
                    "_task_url": "https://example.test/list-1",
                    "_task_final_url": "https://example.test/list-1?page=1",
                    "_task_url_type": "list",
                },
            ]

    monkeypatch.setattr(threaded, "build_spider", lambda source="javdb": SkipSpider())
    monkeypatch.setattr(threaded, "_find_existing_movie_codes_in_worker_session", lambda *args, **kwargs: {"OLD-001"})

    try:
        threaded._run_list_phase(session, run, task, FakeRuntime(), FakeConfig())
        rows = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    finally:
        session.close()

    assert [row.code for row in rows] == ["NEW-001"]


def test_threaded_list_phase_publishes_refresh_after_each_url_completion(admin_user, monkeypatch) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(name="任务A", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    session.add_all([
        CrawlTaskUrl(
            task_id=task.id,
            position=1,
            url="https://example.test/list-1",
            url_type="list",
            has_magnet=True,
            has_chinese_sub=False,
            sort_type=0,
            source="javdb",
            final_url="https://example.test/list-1?page=1",
            url_name="入口1",
        ),
        CrawlTaskUrl(
            task_id=task.id,
            position=2,
            url="https://example.test/list-2",
            url_type="list",
            has_magnet=True,
            has_chinese_sub=False,
            sort_type=0,
            source="javdb",
            final_url="https://example.test/list-2?page=1",
            url_name="入口2",
        ),
    ])
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        created_at=datetime.now(),
    )
    session.add(run)
    session.commit()
    session.refresh(task)
    session.refresh(run)

    monkeypatch.setattr(threaded, "build_spider", lambda source="javdb": FakeSpider())
    monkeypatch.setattr(
        threaded,
        "_find_existing_movie_codes_in_worker_session",
        lambda session_factory, codes, task_id, db_lock: set(),
    )

    queue = event_bus.subscribe(str(admin_user.id))
    try:
        threaded._run_list_phase(session, run, task, FakeRuntime(), FakeConfig())

        events = drain(queue)
    finally:
        event_bus.unsubscribe(str(admin_user.id), queue)
        session.close()

    refresh_events = [
        event for event in events
        if event.event == "crawler.run.detail.updated"
        and event.payload.get("refresh_tasks") is True
        and event.payload.get("reason") == "url_completed"
    ]
    assert len(refresh_events) == 2
    assert all(event.resource_id == str(run.id) for event in refresh_events)
    assert all(event.payload["tasks"] == [] for event in refresh_events)
