from datetime import datetime

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.scripts import backfill_movie_source_task_url_ids as backfill_script
from backend.scripts.backfill_movie_source_task_url_ids import backfill_movie_source_task_url_ids
from shared.database.models.content import Movie


def _seed_backfill_case(db_session, admin_user, code: str = "BF-001") -> tuple[CrawlTaskUrl, Movie]:
    task = CrawlTask(name=f"Actor {code}", storage_location=f"Actor {code}", owner_id=admin_user.id)
    db_session.add(task)
    db_session.flush()
    task_url = CrawlTaskUrl(
        task_id=task.id,
        position=0,
        url=f"https://javdb.com/actors/{code.lower()}",
        url_type="actors",
        source="javdb",
        final_url=f"https://javdb.com/actors/{code.lower()}?page=1",
    )
    run = CrawlRun(task_id=task.id, task_name=task.name, status="completed", crawl_mode="incremental")
    movie = Movie(code=code, source_name="Backfill", source_task_ids=[task.id], source_task_url_ids=[])
    db_session.add_all([task_url, run, movie])
    db_session.flush()
    db_session.add(CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code=movie.code,
        source_url=f"https://javdb.com/v/{code.lower()}",
        source_name=movie.source_name,
        task_url=task_url.url,
        task_url_type="actors",
        status="saved",
        movie_id=movie.id,
        created_at=datetime.now(),
    ))
    db_session.commit()
    return task_url, movie


def test_backfill_movie_source_task_url_ids_dry_run_does_not_write(db_session, admin_user) -> None:
    _, movie = _seed_backfill_case(db_session, admin_user)

    result = backfill_movie_source_task_url_ids(db_session, dry_run=True)
    db_session.refresh(movie)

    assert result.movies_to_update == 1
    assert result.links_to_add == 1
    assert movie.source_task_url_ids == []


def test_backfill_movie_source_task_url_ids_updates_idempotently(db_session, admin_user) -> None:
    task_url, movie = _seed_backfill_case(db_session, admin_user, "BF-002")

    first = backfill_movie_source_task_url_ids(db_session, dry_run=False)
    second = backfill_movie_source_task_url_ids(db_session, dry_run=False)
    db_session.refresh(movie)

    assert first.movies_updated == 1
    assert first.links_added == 1
    assert second.movies_updated == 0
    assert second.links_added == 0
    assert [str(value) for value in movie.source_task_url_ids] == [str(task_url.id)]


def test_backfill_movie_source_task_url_ids_skips_unmatched_task_urls(db_session, admin_user) -> None:
    _, movie = _seed_backfill_case(db_session, admin_user, "BF-003")
    detail = db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.movie_id == movie.id).one()
    detail.task_url = "https://javdb.com/actors/missing"
    db_session.commit()

    result = backfill_movie_source_task_url_ids(db_session, dry_run=False)
    db_session.refresh(movie)

    assert result.skipped_unmatched == 1
    assert result.skipped_examples[0]["task_url"] == "https://javdb.com/actors/missing"
    assert movie.source_task_url_ids == []


def test_backfill_script_main_loads_runtime_config_before_connecting(monkeypatch) -> None:
    calls: list[str] = []

    class FakeSession:
        def close(self) -> None:
            calls.append("close")

    def fake_load_runtime_config(*, override: bool = False):
        calls.append(f"load:{override}")
        return {}

    def fake_get_session_factory():
        calls.append("factory")
        return lambda: FakeSession()

    def fake_backfill(db, *, dry_run: bool = False):
        calls.append(f"backfill:{dry_run}")
        return backfill_script.BackfillResult()

    monkeypatch.setattr(backfill_script, "load_runtime_config", fake_load_runtime_config)
    monkeypatch.setattr(backfill_script, "get_session_factory", fake_get_session_factory)
    monkeypatch.setattr(backfill_script, "backfill_movie_source_task_url_ids", fake_backfill)
    monkeypatch.setattr("sys.argv", ["backfill_movie_source_task_url_ids.py", "--dry-run"])

    backfill_script.main()

    assert calls == ["load:True", "factory", "backfill:True", "close"]
