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


def _seed_task_url(db_session, admin_user, code: str, position: int = 0) -> tuple[CrawlTask, CrawlTaskUrl]:
    task = CrawlTask(name=f"Task {code}", storage_location=f"Task {code}", owner_id=admin_user.id)
    db_session.add(task)
    db_session.flush()
    task_url = CrawlTaskUrl(
        task_id=task.id,
        position=position,
        url=f"https://javdb.com/actors/{code.lower()}-{position}",
        url_type="actors",
        source="javdb",
        final_url=f"https://javdb.com/actors/{code.lower()}-{position}?page=1",
    )
    db_session.add(task_url)
    db_session.flush()
    return task, task_url


def test_backfill_movie_source_task_url_ids_dry_run_does_not_write(db_session, admin_user) -> None:
    _, movie = _seed_backfill_case(db_session, admin_user)

    result = backfill_movie_source_task_url_ids(db_session, dry_run=True)
    db_session.refresh(movie)

    assert result.movies_to_update == 1
    assert result.links_to_add == 1
    assert movie.source_task_url_ids == []


def test_backfill_movie_source_task_url_ids_reports_each_candidate(db_session, admin_user) -> None:
    task_url, movie = _seed_backfill_case(db_session, admin_user, "BF-LOG")
    lines: list[str] = []

    result = backfill_movie_source_task_url_ids(db_session, dry_run=True, reporter=lines.append)

    assert result.links_to_add == 1
    assert len(lines) == 2
    assert str(movie.id) in lines[0]
    assert "BF-LOG" in lines[0]
    assert str(task_url.id) in lines[0]
    assert task_url.url in lines[0]
    assert "status=already_linked_from_source_task" in lines[1]


def test_backfill_movie_source_task_url_ids_falls_back_to_single_url_task(db_session, admin_user) -> None:
    task, task_url = _seed_task_url(db_session, admin_user, "BF-FALLBACK")
    movie = Movie(code="BF-FALLBACK", source_name="Backfill", source_task_ids=[task.id], source_task_url_ids=[])
    db_session.add(movie)
    db_session.commit()
    lines: list[str] = []

    result = backfill_movie_source_task_url_ids(db_session, dry_run=False, reporter=lines.append)
    db_session.refresh(movie)

    assert result.movies_updated == 1
    assert result.links_added == 1
    assert [str(value) for value in movie.source_task_url_ids] == [str(task_url.id)]
    assert any("status=added_from_source_task" in line and str(task_url.id) in line for line in lines)


def test_backfill_movie_source_task_url_ids_merges_all_urls_from_multi_url_task(db_session, admin_user) -> None:
    task, first_url = _seed_task_url(db_session, admin_user, "BF-MULTI", 0)
    second_url = CrawlTaskUrl(
        task_id=task.id,
        position=1,
        url="https://javdb.com/actors/bf-multi-1",
        url_type="actors",
        source="javdb",
        final_url="https://javdb.com/actors/bf-multi-1?page=1",
    )
    movie = Movie(code="BF-MULTI", source_name="Backfill", source_task_ids=[task.id], source_task_url_ids=[])
    db_session.add_all([second_url, movie])
    db_session.commit()
    lines: list[str] = []

    result = backfill_movie_source_task_url_ids(db_session, dry_run=False, reporter=lines.append)
    db_session.refresh(movie)

    assert result.movies_updated == 1
    assert result.links_added == 2
    assert [str(value) for value in movie.source_task_url_ids] == [str(first_url.id), str(second_url.id)]
    assert any(
        "status=added_from_source_task" in line
        and str(first_url.id) in line
        and str(second_url.id) in line
        for line in lines
    )


def test_backfill_movie_source_task_url_ids_adds_missing_urls_from_partially_linked_task(db_session, admin_user) -> None:
    task, first_url = _seed_task_url(db_session, admin_user, "BF-PARTIAL", 0)
    second_url = CrawlTaskUrl(
        task_id=task.id,
        position=1,
        url="https://javdb.com/actors/bf-partial-1",
        url_type="actors",
        source="javdb",
        final_url="https://javdb.com/actors/bf-partial-1?page=1",
    )
    movie = Movie(
        code="BF-PARTIAL",
        source_name="Backfill",
        source_task_ids=[task.id],
        source_task_url_ids=[first_url.id],
    )
    db_session.add_all([second_url, movie])
    db_session.commit()

    result = backfill_movie_source_task_url_ids(db_session, dry_run=False)
    db_session.refresh(movie)

    assert result.links_added == 1
    assert [str(value) for value in movie.source_task_url_ids] == [str(first_url.id), str(second_url.id)]


def test_backfill_movie_source_task_url_ids_reports_every_processed_row(db_session, admin_user) -> None:
    task_url, movie = _seed_backfill_case(db_session, admin_user, "BF-ROWS")
    movie.source_task_url_ids = [task_url.id]
    task = task_url.task
    run = db_session.query(CrawlRun).filter(CrawlRun.task_id == task.id).one()
    db_session.add(CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code="BF-MISS",
        source_url="https://javdb.com/v/bf-miss",
        source_name="Backfill",
        task_url="https://javdb.com/actors/missing",
        task_url_type="actors",
        status="saved",
        movie_id=movie.id,
        created_at=datetime.now(),
    ))
    db_session.commit()
    lines: list[str] = []

    result = backfill_movie_source_task_url_ids(db_session, dry_run=True, reporter=lines.append)

    assert result.skipped_unmatched == 1
    assert len(lines) == 3
    assert "status=already_linked" in lines[0]
    assert "ok=true" in lines[0]
    assert "status=unmatched_task_url" in lines[1]
    assert "ok=false" in lines[1]
    assert "status=already_linked_from_source_task" in lines[2]


def test_backfill_movie_source_task_url_ids_updates_idempotently(db_session, admin_user) -> None:
    task_url, movie = _seed_backfill_case(db_session, admin_user, "BF-002")

    first = backfill_movie_source_task_url_ids(db_session, dry_run=False)
    second = backfill_movie_source_task_url_ids(db_session, dry_run=False)
    db_session.refresh(movie)

    assert first.movies_updated == 1
    assert first.links_added == 1
    assert second.movies_to_update == 0
    assert second.movies_updated == 0
    assert second.links_added == 0
    assert [str(value) for value in movie.source_task_url_ids] == [str(task_url.id)]


def test_backfill_movie_source_task_url_ids_skips_unmatched_task_urls(db_session, admin_user) -> None:
    task_url, movie = _seed_backfill_case(db_session, admin_user, "BF-003")
    detail = db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.movie_id == movie.id).one()
    detail.task_url = "https://javdb.com/actors/missing"
    db_session.commit()

    result = backfill_movie_source_task_url_ids(db_session, dry_run=False)
    db_session.refresh(movie)

    assert result.skipped_unmatched == 1
    assert result.skipped_examples[0]["task_url"] == "https://javdb.com/actors/missing"
    assert [str(value) for value in movie.source_task_url_ids] == [str(task_url.id)]


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

    def fake_backfill(db, *, dry_run: bool = False, reporter=None):
        calls.append(f"backfill:{dry_run}:{reporter is not None}")
        return backfill_script.BackfillResult()

    monkeypatch.setattr(backfill_script, "load_runtime_config", fake_load_runtime_config)
    monkeypatch.setattr(backfill_script, "get_session_factory", fake_get_session_factory)
    monkeypatch.setattr(backfill_script, "backfill_movie_source_task_url_ids", fake_backfill)
    monkeypatch.setattr("sys.argv", ["backfill_movie_source_task_url_ids.py", "--dry-run"])

    backfill_script.main()

    assert calls == ["load:True", "factory", "backfill:True:True", "close"]
