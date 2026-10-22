from datetime import datetime, timezone

import pytest

from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem
from backend.app.modules.scraping.images import ArtworkResult
from backend.app.modules.scraping.tasks import worker
from backend.app.modules.scraping.tasks.logs import read_scraping_item_logs
from shared.database.models.content import Movie


@pytest.fixture(autouse=True)
def isolated_scraping_logs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))


def _seed_task(db, admin_user, status="queued"):
    movie = Movie(code="ADN-784", source_name="ADN-784", storage_summary={"storage_status": "stored", "locations": []})
    db.add(movie)
    db.flush()
    task = ScrapingTask(status=status, total_count=1, created_by=admin_user.id, queued_at=datetime.now(timezone.utc))
    db.add(task)
    db.flush()
    item = ScrapingTaskItem(task_id=task.id, movie_id=movie.id, movie_code="ADN-784", movie_title="ADN-784", status="pending")
    db.add(item)
    db.commit()
    return task, item


def test_run_task_success_transitions(db_session, admin_user, monkeypatch) -> None:
    task, item = _seed_task(db_session, admin_user)
    task_id = task.id
    item_id = str(item.id)

    def fake_run_item(db, item, *, config, **kwargs):
        item.status = "success"
        item.source = "javbus"
        item.duration_ms = 10

    monkeypatch.setattr("backend.app.modules.scraping.tasks.worker.run_item", fake_run_item)
    monkeypatch.setattr(worker, "_open_session", lambda: db_session)
    monkeypatch.setattr(worker, "get_scraping_config", lambda: {"metadata_sources": ["javdb", "javbus"]})
    monkeypatch.setattr(worker, "publish_scraping_task_updated", lambda task: None)
    monkeypatch.setattr(worker, "publish_scraping_item_updated", lambda owner_id, item: None)
    published: list[tuple] = []
    monkeypatch.setattr(worker, "publish_movie_scraping_updated", lambda *args: published.append(args))

    worker.run_task(task_id)

    db_session.expire_all()
    stored = db_session.get(ScrapingTask, task_id)
    assert stored.status == "success"
    assert stored.success_count == 1
    assert stored.finished_at is not None
    assert published and published[0][0] == str(admin_user.id)
    assert [entry["message"] for entry in read_scraping_item_logs(item_id)] == ["开始刮削", "刮削完成"]


def test_run_task_partial_failure_and_skips(db_session, admin_user, monkeypatch) -> None:
    task, item = _seed_task(db_session, admin_user)
    task_id = task.id
    item_id = str(item.id)

    def fake_run_item(db, item, *, config, **kwargs):
        item.status = "failed"
        item.error_message = "boom"

    monkeypatch.setattr("backend.app.modules.scraping.tasks.worker.run_item", fake_run_item)
    monkeypatch.setattr(worker, "_open_session", lambda: db_session)
    monkeypatch.setattr(worker, "get_scraping_config", lambda: {"metadata_sources": ["javdb"]})
    monkeypatch.setattr(worker, "publish_scraping_task_updated", lambda task: None)
    monkeypatch.setattr(worker, "publish_scraping_item_updated", lambda owner_id, item: None)

    worker.run_task(task_id)

    db_session.expire_all()
    stored = db_session.get(ScrapingTask, task_id)
    assert stored.status == "failed"
    assert stored.failed_count == 1
    assert read_scraping_item_logs(item_id)[-1]["message"] == "boom"


def test_cancel_between_items_marks_pending_skipped(db_session, admin_user, monkeypatch) -> None:
    task, first = _seed_task(db_session, admin_user)
    extra = Movie(code="BBB-001", source_name="BBB-001", storage_summary={"storage_status": "stored", "locations": []})
    db_session.add(extra)
    db_session.flush()
    second = ScrapingTaskItem(task_id=task.id, movie_id=extra.id, movie_code="BBB-001", movie_title="BBB-001", status="pending")
    db_session.add(second)
    task.total_count = 2
    db_session.commit()
    task_id = task.id
    second_id = str(second.id)

    def fake_run_item(db, item, *, config, **kwargs):
        item.status = "success"
        task_row = db.get(ScrapingTask, task_id)
        task_row.cancel_requested = True
        db.commit()

    monkeypatch.setattr("backend.app.modules.scraping.tasks.worker.run_item", fake_run_item)
    monkeypatch.setattr(worker, "_open_session", lambda: db_session)
    monkeypatch.setattr(worker, "get_scraping_config", lambda: {"metadata_sources": ["javdb"]})
    monkeypatch.setattr(worker, "publish_scraping_task_updated", lambda task: None)
    monkeypatch.setattr(worker, "publish_scraping_item_updated", lambda owner_id, item: None)

    worker.run_task(task_id)

    db_session.expire_all()
    stored = db_session.get(ScrapingTask, task_id)
    assert stored.status == "cancelled"
    assert stored.skipped_count == 1
    remaining = db_session.query(ScrapingTaskItem).filter_by(task_id=task_id, status="skipped").count()
    assert remaining == 1
    assert read_scraping_item_logs(second_id)[-1]["message"] == "任务已取消"


def test_cleanup_marks_running_tasks_failed(db_session, admin_user) -> None:
    task, _item = _seed_task(db_session, admin_user, status="running")

    stopped = worker.cleanup_interrupted_scraping_tasks(db_session)

    db_session.expire_all()
    stored = db_session.get(ScrapingTask, task.id)
    assert stopped == 1
    assert stored.status == "failed"
    assert stored.error_message == "任务中断，需重试"
    assert read_scraping_item_logs(str(_item.id))[-1]["message"] == "任务中断，需重试"


def test_run_item_passes_site_referer_to_artwork(db_session, admin_user, monkeypatch, tmp_path) -> None:
    from backend.app.modules.scraping.sources import SourceMetadata
    from backend.app.modules.scraping.tasks import item_runner

    movie = Movie(
        code="ADN-784",
        source_name="ADN-784",
        storage_summary={"storage_status": "stored", "locations": [{"target_folder": "/media/ADN-784"}]},
    )
    db_session.add(movie)
    db_session.flush()
    task = ScrapingTask(
        status="running",
        total_count=1,
        created_by=admin_user.id,
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(task)
    db_session.flush()
    item = ScrapingTaskItem(
        task_id=task.id,
        movie_id=movie.id,
        movie_code="ADN-784",
        movie_title="ADN-784",
        status="pending",
    )
    db_session.add(item)
    db_session.commit()

    folder = tmp_path / "ADN-784"
    folder.mkdir()

    monkeypatch.setattr(
        item_runner,
        "fetch_by_priority",
        lambda code, sources: SourceMetadata(
            site_key="JavDB",
            title="ADN-784",
            cover_url="https://javdb.com/cover.jpg",
        ),
    )
    captured: dict[str, object] = {}

    def fake_write_artwork(folder_arg, *, cover_url, source_cover_url=None, backdrop_urls, landscape_urls, referer=None, cover_referer=None, transport=None):
        captured.update(
            folder=str(folder_arg),
            cover_url=cover_url,
            backdrop_urls=backdrop_urls,
            landscape_urls=landscape_urls,
            referer=referer,
        )
        return ArtworkResult(written=1, available={"folder.jpg"})

    monkeypatch.setattr(item_runner, "write_artwork", fake_write_artwork)

    item_runner.run_item(
        db_session,
        item,
        config={
            "scrape_root": str(tmp_path),
            "media_root": "/media",
            "metadata_sources": ["javdb"],
        },
    )

    assert captured["referer"] == "https://javdb.com/"
    assert captured["cover_url"] == "https://javdb.com/cover.jpg"


def _seed_item_for_movie(db, admin_user, movie) -> ScrapingTaskItem:
    db.add(movie)
    db.flush()
    task = ScrapingTask(
        status="running",
        total_count=1,
        created_by=admin_user.id,
        queued_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.flush()
    item = ScrapingTaskItem(
        task_id=task.id,
        movie_id=movie.id,
        movie_code=movie.code,
        movie_title=movie.source_name,
        status="pending",
    )
    db.add(item)
    db.commit()
    return item


def test_run_item_fills_missing_metadata_and_renders_set_and_actors(
    db_session, admin_user, monkeypatch, tmp_path
) -> None:
    from backend.app.modules.scraping.sources import SourceMetadata
    from backend.app.modules.scraping.tasks import item_runner

    movie = Movie(
        code="ADN-784",
        source_name="ADN-784 あなた、許して…。",
        storage_summary={"storage_status": "stored", "locations": [{"target_folder": "/media/ADN-784"}]},
    )
    item = _seed_item_for_movie(db_session, admin_user, movie)
    movie_id = movie.id
    folder = tmp_path / "ADN-784"
    folder.mkdir()

    monkeypatch.setattr(
        item_runner,
        "fetch_by_priority",
        lambda code, sources: SourceMetadata(
            site_key="JavBus",
            title="ADN-784 あなた、許して…。",
            premiered="2026-07-03",
            studio="アタッカーズ",
            series="あなた、許して…。",
            actors=["北野未奈"],
            cover_url="https://www.javbus.com/cover.jpg",
        ),
    )
    monkeypatch.setattr(item_runner, "write_artwork", lambda *args, **kwargs: ArtworkResult(written=1, available={"folder.jpg"}))

    item_runner.run_item(
        db_session,
        item,
        config={
            "scrape_root": str(tmp_path),
            "media_root": "/media",
            "metadata_sources": ["javbus"],
        },
    )

    assert item.status == "success"
    nfo = (folder / "movie.nfo").read_text(encoding="utf-8")
    assert "<set>" in nfo
    assert "<name>あなた、許して…。</name>" in nfo
    assert "北野未奈" in nfo
    assert "<premiered>2026-07-03</premiered>" in nfo

    db_session.expire_all()
    stored = db_session.get(Movie, movie_id)
    assert stored.series == "あなた、許して…。"
    assert stored.maker == "アタッカーズ"
    assert stored.actors == ["北野未奈"]
    assert stored.release_date is not None
    assert stored.release_date.isoformat() == "2026-07-03"
    assert [entry["step"] for entry in read_scraping_item_logs(str(item.id))] == [
        "locate_folder", "fetch_metadata", "write_artwork", "write_nfo", "refresh_status",
    ]


def test_run_task_logs_unexpected_exception(db_session, admin_user, monkeypatch) -> None:
    task, item = _seed_task(db_session, admin_user)
    item_id = str(item.id)
    item_uuid = item.id
    task_id = task.id
    monkeypatch.setattr(worker, "_open_session", lambda: db_session)
    monkeypatch.setattr(worker, "run_item", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("network down")))
    monkeypatch.setattr(worker, "publish_movie_scraping_updated", lambda *args: None)

    worker.run_task(task_id)

    assert db_session.get(ScrapingTaskItem, item_uuid).status == "failed"
    assert read_scraping_item_logs(item_id)[-1]["message"] == "RuntimeError: network down"


def test_run_task_logs_early_skip_for_unstored_movie(db_session, admin_user, monkeypatch) -> None:
    task, item = _seed_task(db_session, admin_user)
    task_id = task.id
    item_uuid = item.id
    movie_id = item.movie_id
    item_id = str(item.id)
    movie = db_session.get(Movie, movie_id)
    movie.storage_summary = {"storage_status": "not_stored", "locations": []}
    db_session.commit()
    monkeypatch.setattr(worker, "_open_session", lambda: db_session)

    worker.run_task(task_id)

    assert db_session.get(ScrapingTaskItem, item_uuid).status == "skipped"
    assert read_scraping_item_logs(item_id)[-1]["message"] == "未存储"


def test_run_item_falls_back_to_scan_index_folder(db_session, admin_user, monkeypatch, tmp_path) -> None:
    from datetime import date

    from backend.app.modules.scraping.tasks import item_runner

    movie = Movie(
        code="ADN-784",
        source_name="ADN-784",
        cover="https://www.javbus.com/cover.jpg",
        release_date=date(2026, 7, 3),
        maker="アタッカーズ",
        series="あなた、許して…。",
        actors=["北野未奈"],
        tags=["ドラマ"],
        storage_summary={"storage_status": "stored", "locations": [{"target_folder": "/other/ADN-784"}]},
    )
    item = _seed_item_for_movie(db_session, admin_user, movie)
    folder = tmp_path / "ADN-784"
    folder.mkdir()
    (folder / "ADN-784.strm").write_text("http://example.com/v.mkv", encoding="utf-8")

    monkeypatch.setattr(
        item_runner,
        "fetch_by_priority",
        lambda code, sources: None,
    )
    monkeypatch.setattr(item_runner, "write_artwork", lambda *args, **kwargs: ArtworkResult(written=1, available={"folder.jpg"}))

    item_runner.run_item(
        db_session,
        item,
        config={
            "scrape_root": str(tmp_path),
            "media_root": "/media",
            "metadata_sources": ["javdb"],
        },
    )

    assert item.status == "success"
    assert item.folder == "/media/ADN-784"
    assert (folder / "movie.nfo").exists()


def test_run_item_uses_source_url_referer_for_complete_db_movie(
    db_session, admin_user, monkeypatch, tmp_path
) -> None:
    from datetime import date

    from backend.app.modules.scraping.tasks import item_runner

    movie = Movie(
        code="ADN-784",
        source_name="ADN-784",
        source_url="https://javdb.com/v/abc123",
        cover="https://javdb.com/cover.jpg",
        release_date=date(2026, 7, 3),
        maker="アタッカーズ",
        series="あなた、許して…。",
        actors=["北野未奈"],
        tags=["ドラマ"],
        storage_summary={"storage_status": "stored", "locations": [{"target_folder": "/media/ADN-784"}]},
    )
    item = _seed_item_for_movie(db_session, admin_user, movie)
    (tmp_path / "ADN-784").mkdir()

    monkeypatch.setattr(
        item_runner,
        "fetch_by_priority",
        lambda code, sources: None,
    )
    captured: dict[str, object] = {}

    def fake_write_artwork(folder_arg, *, cover_url, source_cover_url=None, backdrop_urls, landscape_urls, referer=None, cover_referer=None, transport=None):
        captured["referer"] = referer
        return ArtworkResult(written=1, available={"folder.jpg"})

    monkeypatch.setattr(item_runner, "write_artwork", fake_write_artwork)

    item_runner.run_item(
        db_session,
        item,
        config={
            "scrape_root": str(tmp_path),
            "media_root": "/media",
            "metadata_sources": ["javdb"],
        },
    )

    assert item.status == "success"
    assert captured["referer"] == "https://javdb.com/"


def test_run_item_fetches_fanza_artwork_for_complete_movie_without_overwriting_fields(
    db_session, admin_user, monkeypatch, tmp_path
) -> None:
    from datetime import date

    from backend.app.modules.scraping.sources import SourceMetadata
    from backend.app.modules.scraping.tasks import item_runner

    movie = Movie(
        code="MIDA-819", source_name="Existing title", cover="https://old/cover.jpg",
        release_date=date(2025, 1, 1), maker="Existing maker", series="Existing series",
        actors=["Existing actor"], tags=["Existing tag"],
        storage_summary={"storage_status": "stored", "locations": [{"target_folder": "/media/MIDA-819"}]},
    )
    item = _seed_item_for_movie(db_session, admin_user, movie)
    folder = tmp_path / "MIDA-819"
    folder.mkdir()
    fetched: list[tuple[str, list[str]]] = []
    captured: dict[str, object] = {}

    def fake_fetch(code, sources):
        fetched.append((code, sources))
        return SourceMetadata(
            site_key="FANZA", cover_url="https://new/cover.jpg", studio="New maker",
            preview_urls=["https://new/sample-1.jpg", "https://new/sample-2.jpg"],
        )

    def fake_write(folder_arg, **kwargs):
        captured.update(kwargs)
        return ArtworkResult(written=2, available={"folder.jpg", "backdrop.jpg"})

    monkeypatch.setattr(item_runner, "fetch_by_priority", fake_fetch)
    monkeypatch.setattr(item_runner, "write_artwork", fake_write)
    item_runner.run_item(db_session, item, config={"scrape_root": str(tmp_path), "media_root": "/media", "metadata_sources": ["fanza", "javdb"]})

    assert fetched == [("MIDA-819", ["fanza", "javdb"])]
    assert item.source == "fanza"
    assert movie.maker == "Existing maker"
    assert captured["cover_url"] == "https://old/cover.jpg"
    assert captured["source_cover_url"] == "https://new/cover.jpg"
    assert captured["backdrop_urls"] == ["https://new/sample-1.jpg", "https://new/sample-2.jpg"]
    nfo = (folder / "movie.nfo").read_text(encoding="utf-8")
    assert "<fanart>/media/MIDA-819/backdrop.jpg</fanart>" in nfo


def test_worker_loop_rechecks_queue_before_retiring(db_session, admin_user, monkeypatch) -> None:
    task, _item = _seed_task(db_session, admin_user)
    task_id = task.id
    claims = [None, task, None, None]
    processed: list = []

    monkeypatch.setattr(worker, "_open_session", lambda: db_session)
    monkeypatch.setattr(worker, "_claim_next_task", lambda db: claims.pop(0) if claims else None)
    monkeypatch.setattr(worker, "run_task", lambda claimed_id: processed.append(claimed_id))
    monkeypatch.setattr(worker, "_worker_running", True)
    monkeypatch.setattr(worker, "_worker_generation", 7)

    worker._worker_loop(7)

    assert processed == [task_id]
    assert worker._worker_running is False


def test_ensure_scraping_worker_starts_after_idle_retire(db_session, admin_user, monkeypatch) -> None:
    spawned: list[int] = []

    monkeypatch.setattr(worker, "_open_session", lambda: db_session)
    monkeypatch.setattr(worker, "_claim_next_task", lambda db: None)
    monkeypatch.setattr(worker, "_spawn_worker", lambda generation: spawned.append(generation))
    monkeypatch.setattr(worker, "_worker_running", True)
    monkeypatch.setattr(worker, "_worker_generation", 3)

    worker._worker_loop(3)
    assert worker._worker_running is False

    _seed_task(db_session, admin_user)
    worker.ensure_scraping_worker_started()

    assert spawned == [4]
    assert worker._worker_running is True


def test_run_task_does_not_refresh_the_task_row(db_session, admin_user, monkeypatch) -> None:
    task, _item = _seed_task(db_session, admin_user)
    task_id = task.id
    refresh_calls: list[tuple] = []

    def fake_run_item(db, item, *, config, **kwargs):
        item.status = "success"
        item.duration_ms = 10

    monkeypatch.setattr("backend.app.modules.scraping.tasks.worker.run_item", fake_run_item)
    monkeypatch.setattr(worker, "_open_session", lambda: db_session)
    monkeypatch.setattr(worker, "get_scraping_config", lambda: {"metadata_sources": ["javdb"]})
    monkeypatch.setattr(worker, "publish_scraping_task_updated", lambda task: None)
    monkeypatch.setattr(worker, "publish_scraping_item_updated", lambda owner_id, item: None)
    monkeypatch.setattr(worker, "publish_movie_scraping_updated", lambda *args: None)
    monkeypatch.setattr(db_session, "refresh", lambda *args, **kwargs: refresh_calls.append(args))

    worker.run_task(task_id)

    db_session.expire_all()
    stored = db_session.get(ScrapingTask, task_id)
    assert stored.status == "success"
    assert stored.success_count == 1
    assert refresh_calls == []
