from datetime import datetime

from sqlalchemy import select

from backend.app.core.security import get_password_hash
from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.models.user import User
from backend.app.modules.crawler.runtime.service import process_next_run
from backend.tests.conftest import TestingSessionLocal
from shared.database.models.content import Movie, MovieMagnet


class Runtime:
    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self.current = None
        self.progress = {}

    def claim_next_run(self):
        run_id, self._run_id = self._run_id, None
        return run_id

    def set_current_run(self, run_id):
        self.current = run_id

    def is_stop_requested(self, run_id):
        return False

    def write_progress(self, run_id, progress):
        self.progress = progress


class MovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        kwargs["on_tasks_batch_created"]([
            {"code": "AAA-001", "url": "https://javdb.com/v/aaa", "name": "AAA"}
        ])
        kwargs["on_item_saved"](
            {"code": "AAA-001", "url": "https://javdb.com/v/aaa", "name": "AAA"},
            {"code": "AAA-001", "source_url": "https://javdb.com/v/aaa", "source_name": "AAA"},
        )
        return {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}


class PersistingMovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        kwargs["on_tasks_batch_created"]([
            {"code": "AAA-002", "url": "https://javdb.com/v/aaa002", "name": "AAA 002"}
        ])
        kwargs["on_item_saved"](
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


class FailingPersistenceMovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        kwargs["on_tasks_batch_created"]([
            {"code": "AAA-003", "url": "https://javdb.com/v/aaa003", "name": "AAA 003"}
        ])
        kwargs["on_item_saved"](
            {"code": "AAA-003", "url": "https://javdb.com/v/aaa003", "name": "AAA 003"},
            {
                "code": "AAA-003",
                "source_url": "https://javdb.com/v/aaa003",
                "source_name": "AAA 003",
            },
        )
        return {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}


class ListPhaseDedupeMovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        existing_codes = kwargs["db_check_callback"](["AAA-010", "AAA-011"])
        batch = [
            {"code": "AAA-010", "url": "https://javdb.com/v/aaa010", "name": "AAA 010"},
            {"code": "AAA-011", "url": "https://javdb.com/v/aaa011", "name": "AAA 011"},
        ]
        for item in batch:
            if item["code"] in existing_codes:
                item["status"] = "skipped"
                item["reason"] = "already_exists"
        kwargs["on_tasks_batch_created"](batch)
        return {
            "total_tasks": 2,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "skipped_tasks": 1,
        }


class DetailPhaseDedupeMovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        detail_task = {"code": "AAA-020", "url": "https://javdb.com/v/aaa020", "name": "AAA 020"}
        kwargs["on_tasks_batch_created"]([detail_task])
        if kwargs["on_detail_check_callback"]("AAA-020"):
            detail_task["status"] = "skipped"
            detail_task["reason"] = "already_exists"
            kwargs["on_item_already_exists"](detail_task)
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

    # Mock the _execute_run function to avoid importing MovieService
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

    monkeypatch.setattr("backend.app.modules.crawler.runtime.service._execute_run", mock_execute_run)

    processed = process_next_run(TestingSessionLocal, runtime)

    assert processed is True
    # Refresh session to see changes from process_next_run
    session.expire_all()
    refreshed = session.get(CrawlRun, run.id)
    assert refreshed.status == "completed"
    detail = session.query(CrawlRunDetailTask).one()
    assert detail.status == "saved"


def test_execute_run_persists_movie_before_marking_detail_saved(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.service import _execute_run

    monkeypatch.setattr("scraper.services.movie_service.MovieService", lambda: PersistingMovieServiceStub())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("persist")

    _execute_run(session, session.get(CrawlRun, run.id), runtime)

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


def test_execute_run_marks_detail_save_failed_when_movie_persistence_fails(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.service import _execute_run
    from scraper.database.repositories.movie_repository import MovieRepository

    monkeypatch.setattr("scraper.services.movie_service.MovieService", lambda: FailingPersistenceMovieServiceStub())
    monkeypatch.setattr(MovieRepository, "upsert_movie", lambda self, item: None)
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("save-failed")

    _execute_run(session, session.get(CrawlRun, run.id), runtime)

    assert session.scalar(select(Movie).where(Movie.code == "AAA-003")) is None
    detail = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "AAA-003").one()
    assert detail.status == "save_failed"
    assert "movie repository returned no id" in detail.error
    refreshed = session.get(CrawlRun, run.id)
    assert refreshed.result["saved"] == 0
    assert refreshed.result["save_failed"] == 1


def test_execute_run_marks_list_phase_existing_movies_skipped(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.service import _execute_run

    monkeypatch.setattr("scraper.services.movie_service.MovieService", lambda: ListPhaseDedupeMovieServiceStub())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("list-dedupe")
    session.add(Movie(code="AAA-010", source_url="https://javdb.com/v/aaa010", source_task_ids=[]))
    session.commit()

    _execute_run(session, session.get(CrawlRun, run.id), runtime)

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
    from backend.app.modules.crawler.runtime.service import _execute_run

    monkeypatch.setattr("scraper.services.movie_service.MovieService", lambda: DetailPhaseDedupeMovieServiceStub())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("detail-dedupe")
    session.add(Movie(code="AAA-020", source_url="https://javdb.com/v/aaa020", source_task_ids=[]))
    session.commit()

    _execute_run(session, session.get(CrawlRun, run.id), runtime)

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
