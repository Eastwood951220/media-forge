from datetime import datetime, timezone

from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem
from backend.app.modules.scraping.tasks import worker
from shared.database.models.content import Movie


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


def test_run_task_partial_failure_and_skips(db_session, admin_user, monkeypatch) -> None:
    task, _item = _seed_task(db_session, admin_user)
    task_id = task.id

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


def test_cleanup_marks_running_tasks_failed(db_session, admin_user) -> None:
    task, _item = _seed_task(db_session, admin_user, status="running")

    stopped = worker.cleanup_interrupted_scraping_tasks(db_session)

    db_session.expire_all()
    stored = db_session.get(ScrapingTask, task.id)
    assert stopped == 1
    assert stored.status == "failed"
    assert stored.error_message == "任务中断，需重试"
