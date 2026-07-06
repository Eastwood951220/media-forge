import uuid
from datetime import datetime
from queue import Empty

from sqlalchemy import select

from backend.app.core.security import get_password_hash
from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.models.user import User
from backend.app.modules.crawler.runtime.service import process_next_run
from backend.tests.conftest import TestingSessionLocal
from shared.database.models.content import Movie, MovieFilter, MovieMagnet


class Runtime:
    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self.current = None
        self.progress = {}
        self.cleared = []

    def claim_next_run(self):
        run_id, self._run_id = self._run_id, None
        return run_id

    def set_current_run(self, run_id):
        self.current = run_id

    def is_stop_requested(self, run_id):
        return False

    def write_progress(self, run_id, progress):
        self.progress = progress

    def clear_stop(self, run_id):
        self.cleared.append(run_id)


class CrawlerEngineStub:
    def crawl_task(self, task, *, task_id=None, crawl_mode="incremental", incremental_threshold=0, callbacks):
        if callbacks.on_tasks_batch_created:
            callbacks.on_tasks_batch_created([
                {"code": "AAA-001", "url": "https://javdb.com/v/aaa", "name": "AAA"}
            ])
        if callbacks.on_item_saved:
            callbacks.on_item_saved(
                {"code": "AAA-001", "url": "https://javdb.com/v/aaa", "name": "AAA"},
                {"code": "AAA-001", "source_url": "https://javdb.com/v/aaa", "source_name": "AAA"},
            )
        return {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}


class PersistingCrawlerEngineStub:
    def crawl_task(self, task, *, task_id=None, crawl_mode="incremental", incremental_threshold=0, callbacks):
        if callbacks.on_tasks_batch_created:
            callbacks.on_tasks_batch_created([
                {"code": "AAA-002", "url": "https://javdb.com/v/aaa002", "name": "AAA 002"}
            ])
        if callbacks.on_item_saved:
            callbacks.on_item_saved(
                {"code": "AAA-002", "url": "https://javdb.com/v/aaa002", "name": "AAA 002"},
                {
                    "code": "AAA-002",
                    "source_url": "https://javdb.com/v/aaa002",
                    "source_name": "AAA 002",
                    "title": "AAA 002",
                    "magnets": [
                        {
                            "magnet": "magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                            "name": "AAA 002",
                            "size_text": "1.2GB",
                        }
                    ],
                },
            )
        return {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}


class FilterSyncCrawlerEngineStub:
    def crawl_task(self, task, *, task_id=None, crawl_mode="incremental", incremental_threshold=0, callbacks):
        if callbacks.on_tasks_batch_created:
            callbacks.on_tasks_batch_created([
                {"code": "FILTER-001", "url": "https://javdb.com/v/filter001", "name": "FILTER 001"}
            ])
        if callbacks.on_item_saved:
            callbacks.on_item_saved(
                {"code": "FILTER-001", "url": "https://javdb.com/v/filter001", "name": "FILTER 001"},
                {
                    "code": "FILTER-001",
                    "source_url": "https://javdb.com/v/filter001",
                    "source_name": "FILTER 001",
                    "title": "FILTER 001",
                    "actors": ["演员缓存A", "演员缓存B"],
                    "tags": ["标签缓存A"],
                    "director": "导演缓存A",
                    "maker": "片商缓存A",
                    "series": "系列缓存A",
                },
            )
        return {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}


class FailingPersistenceCrawlerEngineStub:
    def crawl_task(self, task, *, task_id=None, crawl_mode="incremental", incremental_threshold=0, callbacks):
        if callbacks.on_tasks_batch_created:
            callbacks.on_tasks_batch_created([
                {"code": "AAA-003", "url": "https://javdb.com/v/aaa003", "name": "AAA 003"}
            ])
        if callbacks.on_item_saved:
            callbacks.on_item_saved(
                {"code": "AAA-003", "url": "https://javdb.com/v/aaa003", "name": "AAA 003"},
                {
                    "code": "AAA-003",
                    "source_url": "https://javdb.com/v/aaa003",
                    "source_name": "AAA 003",
                },
            )
        return {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}


class ListPhaseDedupeCrawlerEngineStub:
    def crawl_task(self, task, *, task_id=None, crawl_mode="incremental", incremental_threshold=0, callbacks):
        existing_codes = callbacks.db_check_callback(["AAA-010", "AAA-011"])
        batch = [
            {"code": "AAA-010", "url": "https://javdb.com/v/aaa010", "name": "AAA 010"},
            {"code": "AAA-011", "url": "https://javdb.com/v/aaa011", "name": "AAA 011"},
        ]
        for item in batch:
            if item["code"] in existing_codes:
                item["status"] = "skipped"
                item["reason"] = "already_exists"
        if callbacks.on_tasks_batch_created:
            callbacks.on_tasks_batch_created(batch)
        return {
            "total_tasks": 2,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "skipped_tasks": 1,
        }


class DetailPhaseDedupeCrawlerEngineStub:
    def crawl_task(self, task, *, task_id=None, crawl_mode="incremental", incremental_threshold=0, callbacks):
        detail_task = {"code": "AAA-020", "url": "https://javdb.com/v/aaa020", "name": "AAA 020"}
        if callbacks.on_tasks_batch_created:
            callbacks.on_tasks_batch_created([detail_task])
        if callbacks.on_detail_check_callback and callbacks.on_detail_check_callback("AAA-020"):
            detail_task["status"] = "skipped"
            detail_task["reason"] = "already_exists"
            if callbacks.on_item_already_exists:
                callbacks.on_item_already_exists(detail_task)
        return {
            "total_tasks": 1,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "skipped_tasks": 1,
        }


def create_run_with_task(code: str = "task-code") -> tuple[CrawlRun, Runtime]:
    session = TestingSessionLocal()
    user = User(username=f"worker-{code}", hashed_password=get_password_hash("pw"), role="admin")
    session.add(user)
    session.flush()
    task = CrawlTask(name=f"任务-{code}", owner_id=user.id, is_skip=False)
    task.urls = [
        CrawlTaskUrl(
            position=0,
            url="https://javdb.com/actors/a",
            url_type="actors",
            final_url="https://javdb.com/actors/a?page=1",
            source="javdb",
        )
    ]
    session.add(task)
    session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="queued", crawl_mode="incremental", queued_at=datetime.now())
    session.add(run)
    session.commit()
    runtime = Runtime(str(run.id))
    return run, runtime


def drain_realtime_events(queue) -> list:
    events = []
    while True:
        try:
            events.append(queue.get_nowait())
        except Empty:
            return events


def test_process_next_run_marks_saved(monkeypatch) -> None:
    session = TestingSessionLocal()
    user = User(username="worker-user", hashed_password=get_password_hash("pw"), role="admin")
    session.add(user)
    session.flush()
    task = CrawlTask(name="任务", owner_id=user.id, is_skip=False)
    task.urls = [CrawlTaskUrl(position=0, url="https://javdb.com/actors/a", url_type="actors", final_url="https://javdb.com/actors/a?page=1", source="javdb")]
    session.add(task)
    session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="queued", crawl_mode="incremental", queued_at=datetime.now())
    session.add(run)
    session.commit()
    runtime = Runtime(str(run.id))

    # Mock _execute_run so this test only verifies queue processing.
    def mock_execute_run(db, run_obj, runtime_obj):
        run_obj.status = "completed"
        run_obj.result = {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}
        run_obj.finished_at = datetime.now()
        db.commit()
        detail = CrawlRunDetailTask(
            run_id=run_obj.id,
            task_name="任务",
            code="AAA-001",
            source_url="https://javdb.com/v/aaa",
            source_name="AAA",
            status="saved",
            created_at=datetime.now(),
        )
        db.add(detail)
        db.commit()

    monkeypatch.setattr("backend.app.modules.crawler.runtime.worker.execute_run", mock_execute_run)

    processed = process_next_run(TestingSessionLocal, runtime)

    assert processed is True
    # Refresh session to see changes from process_next_run
    session.expire_all()
    refreshed = session.get(CrawlRun, run.id)
    assert refreshed.status == "completed"
    detail = session.query(CrawlRunDetailTask).one()
    assert detail.status == "saved"
    assert runtime.cleared == [str(run.id)]


def test_execute_run_persists_movie_before_marking_detail_saved(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.executor import execute_run

    monkeypatch.setattr("backend.app.modules.crawler.runtime.executor.get_crawler_engine", lambda: PersistingCrawlerEngineStub())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("persist")

    execute_run(session, session.get(CrawlRun, run.id), runtime)

    movie = session.scalar(select(Movie).where(Movie.code == "AAA-002"))
    assert movie is not None
    assert movie.source_url == "https://javdb.com/v/aaa002"
    # source_task_ids should contain the task ID (compare as strings for SQLite compatibility)
    assert str(run.task_id) in [str(tid) for tid in movie.source_task_ids]
    magnets = session.scalars(select(MovieMagnet).where(MovieMagnet.movie_id == movie.id)).all()
    assert len(magnets) == 1

    detail = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "AAA-002").one()
    assert detail.status == "saved"
    assert detail.saved_at is not None
    refreshed = session.get(CrawlRun, run.id)
    assert refreshed.result["saved"] == 1
    assert refreshed.result["save_failed"] == 0


def test_execute_run_publishes_run_detail_events_to_realtime_bus(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.executor import execute_run
    from backend.app.modules.realtime.bus import event_bus as realtime_bus

    monkeypatch.setattr("backend.app.modules.crawler.runtime.executor.get_crawler_engine", lambda: PersistingCrawlerEngineStub())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("realtime")
    task = session.get(CrawlTask, run.task_id)
    owner_id = str(task.owner_id)
    queue = realtime_bus.subscribe(owner_id)

    try:
        execute_run(session, session.get(CrawlRun, run.id), runtime)
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


def test_execute_run_syncs_movie_filters_after_movie_persistence(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.executor import execute_run

    monkeypatch.setattr("backend.app.modules.crawler.runtime.executor.get_crawler_engine", lambda: FilterSyncCrawlerEngineStub())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("filter-sync")

    execute_run(session, session.get(CrawlRun, run.id), runtime)

    rows = session.scalars(select(MovieFilter).order_by(MovieFilter.type.asc(), MovieFilter.name.asc())).all()
    assert [(row.type, row.name, row.count) for row in rows] == [
        ("actor", "演员缓存A", 0),
        ("actor", "演员缓存B", 0),
        ("director", "导演缓存A", 0),
        ("maker", "片商缓存A", 0),
        ("series", "系列缓存A", 0),
        ("tag", "标签缓存A", 0),
    ]


def test_execute_run_marks_detail_save_failed_when_movie_persistence_fails(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.executor import execute_run

    def fail_persistence(db, item_data):
        raise RuntimeError("movie repository returned no id")

    monkeypatch.setattr("backend.app.modules.crawler.runtime.executor.get_crawler_engine", lambda: FailingPersistenceCrawlerEngineStub())
    monkeypatch.setattr("backend.app.modules.crawler.runtime.executor.upsert_movie_with_magnets", fail_persistence)
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("save-failed")

    execute_run(session, session.get(CrawlRun, run.id), runtime)

    assert session.scalar(select(Movie).where(Movie.code == "AAA-003")) is None
    detail = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "AAA-003").one()
    assert detail.status == "save_failed"
    assert "movie repository returned no id" in detail.error
    refreshed = session.get(CrawlRun, run.id)
    assert refreshed.result["saved"] == 0
    assert refreshed.result["save_failed"] == 1


def test_execute_run_marks_list_phase_existing_movies_skipped(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.executor import execute_run

    monkeypatch.setattr("backend.app.modules.crawler.runtime.executor.get_crawler_engine", lambda: ListPhaseDedupeCrawlerEngineStub())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("list-dedupe")
    session.add(Movie(code="AAA-010", source_url="https://javdb.com/v/aaa010", source_task_ids=[]))
    session.commit()

    execute_run(session, session.get(CrawlRun, run.id), runtime)

    skipped = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "AAA-010").one()
    pending = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "AAA-011").one()
    movie = session.scalar(select(Movie).where(Movie.code == "AAA-010"))

    assert skipped.status == "skipped"
    assert skipped.error == "already_exists"
    assert skipped.saved_at is None
    assert pending.status == "pending_crawl"
    # source_task_ids should contain the run's task_id (compare as strings for SQLite compatibility)
    assert str(run.task_id) in [str(tid) for tid in movie.source_task_ids]
    refreshed = session.get(CrawlRun, run.id)
    assert refreshed.result["skipped_tasks"] == 1


def test_execute_run_marks_detail_phase_existing_movies_skipped(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.executor import execute_run

    monkeypatch.setattr("backend.app.modules.crawler.runtime.executor.get_crawler_engine", lambda: DetailPhaseDedupeCrawlerEngineStub())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("detail-dedupe")
    session.add(Movie(code="AAA-020", source_url="https://javdb.com/v/aaa020", source_task_ids=[]))
    session.commit()

    execute_run(session, session.get(CrawlRun, run.id), runtime)

    detail = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "AAA-020").one()
    movie = session.scalar(select(Movie).where(Movie.code == "AAA-020"))

    assert detail.status == "skipped"
    assert detail.error == "already_exists"
    assert detail.crawled_at is not None
    assert detail.saved_at is None
    # source_task_ids should contain the run's task_id (compare as strings for SQLite compatibility)
    assert str(run.task_id) in [str(tid) for tid in movie.source_task_ids]
    refreshed = session.get(CrawlRun, run.id)
    assert refreshed.result["skipped_tasks"] == 1


class StopRequestedRuntime(Runtime):
    def is_stop_requested(self, run_id):
        return True


class StopAwareCrawlerEngineStub:
    def crawl_task(self, task, *, task_id=None, crawl_mode="incremental", incremental_threshold=0, callbacks):
        assert callbacks.stop_check() is True
        if callbacks.on_tasks_batch_created:
            callbacks.on_tasks_batch_created([
                {"code": "STOP-001", "url": "https://javdb.com/v/stop001", "name": "STOP 001"}
            ])
        return {
            "total_tasks": 1,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "stopped": True,
        }


class ExistingDetailReuseCrawlerEngineStub:
    def crawl_task(self, task, *, task_id=None, crawl_mode="incremental", incremental_threshold=0, callbacks):
        raise AssertionError("detail-stage restart must not run list collection")

    def crawl_detail_tasks(self, task, *, detail_tasks, task_id=None, callbacks):
        assert [item["code"] for item in detail_tasks] == ["REUSE-001"]
        if callbacks.on_item_saved:
            callbacks.on_item_saved(
                {"code": "REUSE-001", "url": "https://javdb.com/v/reuse001", "name": "REUSE 001"},
                {"code": "REUSE-001", "source_url": "https://javdb.com/v/reuse001", "source_name": "REUSE 001"},
            )
        return {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}


class ListPhaseRestartCrawlerEngineStub:
    def crawl_task(self, task, *, task_id=None, crawl_mode="incremental", incremental_threshold=0, callbacks):
        if callbacks.on_tasks_batch_created:
            callbacks.on_tasks_batch_created([
                {"code": "LIST-001", "url": "https://javdb.com/v/list001", "name": "LIST 001"}
            ])
        return {"total_tasks": 1, "completed_tasks": 0, "failed_tasks": 0}

    def crawl_detail_tasks(self, task, *, detail_tasks, task_id=None, callbacks):
        raise AssertionError("list-stage restart must rerun list collection")


def test_execute_run_stops_when_runtime_stop_requested(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.executor import execute_run

    monkeypatch.setattr("backend.app.modules.crawler.runtime.executor.get_crawler_engine", lambda: StopAwareCrawlerEngineStub())
    session = TestingSessionLocal()
    run, _runtime = create_run_with_task("stop-requested")
    runtime = StopRequestedRuntime(str(run.id))

    execute_run(session, session.get(CrawlRun, run.id), runtime)

    session.expire_all()
    refreshed = session.get(CrawlRun, run.id)
    detail = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "STOP-001").one()
    assert refreshed.status == "stopped"
    assert refreshed.finished_at is not None
    assert refreshed.result["stopped"] is True
    assert detail.status == "pending_crawl"
    assert detail.error is None


def test_execute_run_reuses_existing_detail_task_on_in_place_restart(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.executor import execute_run

    monkeypatch.setattr("backend.app.modules.crawler.runtime.executor.get_crawler_engine", lambda: ExistingDetailReuseCrawlerEngineStub())
    monkeypatch.setattr("backend.app.modules.crawler.runtime.executor.upsert_movie_with_magnets", lambda db, item_data: uuid.uuid4())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("reuse-existing")
    existing = CrawlRunDetailTask(
        run_id=run.id,
        task_name="任务",
        code="REUSE-001",
        source_url="https://javdb.com/v/reuse001",
        source_name="REUSE 001",
        status="save_failed",
        created_at=datetime.now(),
    )
    session.add(existing)
    session.commit()

    execute_run(session, session.get(CrawlRun, run.id), runtime)

    session.expire_all()
    details = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "REUSE-001").all()
    assert len(details) == 1
    assert details[0].status == "saved"
    assert details[0].error is None


def test_execute_run_does_not_treat_list_stage_pending_details_as_detail_restart(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.executor import execute_run

    monkeypatch.setattr("backend.app.modules.crawler.runtime.executor.get_crawler_engine", lambda: ListPhaseRestartCrawlerEngineStub())
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

    execute_run(session, session.get(CrawlRun, run.id), runtime)

    session.expire_all()
    codes = [row.code for row in session.query(CrawlRunDetailTask).order_by(CrawlRunDetailTask.created_at.asc()).all()]
    assert "LIST-001" in codes


def test_crawler_runtime_service_keeps_public_runtime_imports() -> None:
    from backend.app.modules.crawler.runtime import service

    assert callable(service.process_next_run)
    assert callable(service.process_run)
    assert callable(service.publish_run_updated)
    assert callable(service.publish_run_detail_updated)


def test_detail_task_index_finds_by_code_and_source_url() -> None:
    import uuid
    from backend.app.models.crawl_run import CrawlRunDetailTask
    from backend.app.modules.crawler.runtime.detail_index import DetailTaskIndex

    detail = CrawlRunDetailTask(
        run_id=uuid.uuid4(),
        task_name="task",
        code="ABC-001",
        source_url="https://example.test/abc",
        source_name="Movie",
        status="pending_crawl",
    )
    index = DetailTaskIndex()
    index.remember(detail)

    assert index.find({"code": "ABC-001"}) is detail
    assert index.find({"url": "https://example.test/abc"}) is detail
    assert index.find({"code": "ABC-002"}) is None


def test_progress_helpers_write_runtime_progress() -> None:
    from backend.app.modules.crawler.runtime.progress import increment_progress, new_progress, write_progress

    class Runtime:
        def __init__(self) -> None:
            self.writes: list[tuple[str, dict[str, int]]] = []

        def write_progress(self, run_id: str, progress: dict[str, int]) -> None:
            self.writes.append((run_id, dict(progress)))

    runtime = Runtime()
    progress = new_progress()
    increment_progress(progress, "saved")
    increment_progress(progress, "total", 3)
    write_progress(runtime, "run-1", progress)

    assert runtime.writes == [("run-1", {"total": 3, "saved": 1, "failed": 0, "skipped": 0, "save_failed": 0})]
