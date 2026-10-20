import uuid

import pytest

from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem
from backend.app.modules.scraping.tasks.service import ScrapingTaskService
from shared.database.models.content import Movie


def _movie(db, code: str, *, stored: bool = True) -> Movie:
    summary = {"storage_status": "stored" if stored else "not_stored", "locations": []}
    movie = Movie(code=code, source_name=code, storage_summary=summary)
    db.add(movie)
    db.commit()
    db.refresh(movie)
    return movie


def _config() -> dict:
    return {"scrape_root": "/tmp/media", "media_root": "/media", "metadata_sources": ["javdb", "javbus"]}


def test_create_task_dedupes_movies_and_starts_queued(db_session, admin_user) -> None:
    movie = _movie(db_session, "ADN-784")
    service = ScrapingTaskService(db_session)

    task = service.create_task([movie.id, movie.id], admin_user.id, config=_config())

    assert task.status == "queued"
    assert task.total_count == 1
    assert task.created_by == admin_user.id
    assert task.config_snapshot["metadata_sources"] == ["javdb", "javbus"]
    items = db_session.query(ScrapingTaskItem).filter_by(task_id=task.id).all()
    assert [item.status for item in items] == ["pending"]


def test_create_task_rejects_unknown_movie(db_session, admin_user) -> None:
    service = ScrapingTaskService(db_session)
    with pytest.raises(ValueError, match="电影不存在"):
        service.create_task([uuid.uuid4()], admin_user.id, config=_config())


def test_create_task_rejects_empty_and_oversized_lists(db_session, admin_user) -> None:
    service = ScrapingTaskService(db_session)
    with pytest.raises(ValueError, match="至少选择"):
        service.create_task([], admin_user.id, config=_config())

    movie = _movie(db_session, "ADN-784")
    with pytest.raises(ValueError, match="最多"):
        service.create_task([movie.id] * 501, admin_user.id, config=_config())


def test_cancel_queued_task_marks_pending_items_skipped(db_session, admin_user) -> None:
    movie = _movie(db_session, "ADN-784")
    service = ScrapingTaskService(db_session)
    task = service.create_task([movie.id], admin_user.id, config=_config())

    cancelled = service.cancel_task(task.id, admin_user.id)

    assert cancelled.status == "cancelled"
    item = db_session.query(ScrapingTaskItem).filter_by(task_id=task.id).one()
    assert item.status == "skipped"
    assert item.error_message == "任务已取消"


def test_retry_creates_a_task_from_failed_and_skipped_items(db_session, admin_user) -> None:
    movie = _movie(db_session, "ADN-784")
    service = ScrapingTaskService(db_session)
    task = service.create_task([movie.id], admin_user.id, config=_config())
    item = db_session.query(ScrapingTaskItem).filter_by(task_id=task.id).one()
    item.status = "failed"
    task.status = "failed"
    task.finished_at = None
    db_session.commit()

    retried = service.retry_task(task.id, admin_user.id, config=_config())

    assert retried.id != task.id
    assert retried.status == "queued"
    assert retried.total_count == 1


def test_get_task_is_owner_scoped(db_session, admin_user) -> None:
    movie = _movie(db_session, "ADN-784")
    service = ScrapingTaskService(db_session)
    task = service.create_task([movie.id], admin_user.id, config=_config())

    with pytest.raises(LookupError):
        service.get_task(task.id, uuid.uuid4())
