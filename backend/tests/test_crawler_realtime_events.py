import uuid
from datetime import datetime

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.runtime import service
from backend.app.modules.realtime.bus import event_bus
from backend.tests.conftest import TestingSessionLocal


def drain(queue):
    rows = []
    while not queue.empty():
        rows.append(queue.get_nowait())
    return rows


def test_publish_run_updated_event_for_owner(admin_user) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(name="任务A", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        created_at=datetime.now(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    queue = event_bus.subscribe(str(admin_user.id))

    service.publish_run_updated(session, run)

    events = drain(queue)
    event_bus.unsubscribe(str(admin_user.id), queue)
    session.close()

    assert [event.event for event in events] == ["crawler.run.updated", "crawler.task.status.updated"]
    assert events[0].resource_id == str(run.id)
    assert events[0].payload["status"] == "running"
    assert events[1].resource_id == str(task.id)
    assert events[1].payload["task_id"] == str(task.id)
    assert events[1].payload["runtime_status"] == "running"


def test_publish_detail_updated_event_for_owner(admin_user) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(name="任务A", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        created_at=datetime.now(),
    )
    session.add(run)
    session.flush()
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code="AAA-001",
        source_url="https://example.test/aaa",
        source_name="AAA-001",
        status="saved",
        created_at=datetime.now(),
    )
    session.add(detail)
    session.commit()
    session.refresh(run)
    session.refresh(detail)
    queue = event_bus.subscribe(str(admin_user.id))

    service.publish_run_detail_updated(session, run, [detail])

    events = drain(queue)
    event_bus.unsubscribe(str(admin_user.id), queue)
    session.close()

    assert [event.event for event in events] == ["crawler.run.detail.updated"]
    assert events[0].resource_id == str(run.id)
    assert events[0].payload["run_id"] == str(run.id)
    assert events[0].payload["tasks"][0]["status"] == "saved"


def test_publish_detail_updated_skips_deleted_detail_instances(admin_user) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(name="任务A", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        created_at=datetime.now(),
    )
    session.add(run)
    session.flush()
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code="AAA-DELETE",
        source_url="https://example.test/delete",
        source_name="AAA-DELETE",
        status="crawl_failed",
        created_at=datetime.now(),
    )
    session.add(detail)
    session.commit()
    session.refresh(run)
    session.refresh(detail)
    queue = event_bus.subscribe(str(admin_user.id))

    detail_id = detail.id
    session.expire(detail)
    delete_session = TestingSessionLocal()
    try:
        row = delete_session.get(CrawlRunDetailTask, detail_id)
        if row is not None:
            delete_session.delete(row)
            delete_session.commit()
    finally:
        delete_session.close()

    service.publish_run_detail_updated(session, run, [detail])

    events = drain(queue)
    event_bus.unsubscribe(str(admin_user.id), queue)
    session.close()

    assert [event.event for event in events] == ["crawler.run.detail.updated"]
    assert events[0].payload["tasks"] == []


def test_publish_run_log_event_for_owner(admin_user) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(name="任务A", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        created_at=datetime.now(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    queue = event_bus.subscribe(str(admin_user.id))

    service.append_run_log_for_run(session, run, "入库成功: AAA-001", "INFO", code="AAA-001")

    events = drain(queue)
    event_bus.unsubscribe(str(admin_user.id), queue)
    session.close()

    assert [event.event for event in events] == ["crawler.run.log.appended"]
    assert events[0].resource_id == str(run.id)
    assert events[0].payload["run_id"] == str(run.id)
    assert events[0].payload["log"]["message"] == "入库成功: AAA-001"
    assert events[0].payload["log"]["context"]["code"] == "AAA-001"


def test_publish_detail_updated_can_request_task_refresh(admin_user) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(name="任务A", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="running", crawl_mode="incremental", created_at=datetime.now())
    session.add(run)
    session.commit()
    queue = event_bus.subscribe(str(admin_user.id))

    service.publish_run_detail_updated(session, run, [], refresh_tasks=True, reason="url_completed")

    events = drain(queue)
    event_bus.unsubscribe(str(admin_user.id), queue)
    session.close()

    assert [event.event for event in events] == ["crawler.run.detail.updated"]
    assert events[0].payload["tasks"] == []
    assert events[0].payload["refresh_tasks"] is True
    assert events[0].payload["reason"] == "url_completed"
