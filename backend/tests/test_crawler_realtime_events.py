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
    assert events[0].payload["summary"] == {
        "total": 1,
        "pending_crawl": 0,
        "crawling": 0,
        "saved": 1,
        "skipped": 0,
        "crawl_failed": 0,
        "save_failed": 0,
        "completed": 1,
        "waiting": 0,
        "failed": 0,
    }


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
    assert events[0].payload["summary"]["total"] == 0
    assert events[0].payload["summary"]["completed"] == 0
    assert events[0].payload["summary"]["failed"] == 0


def test_publish_detail_updated_uses_display_fields_for_temporary_rows(admin_user) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(name="任务A", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="temporary",
        created_at=datetime.now(),
    )
    session.add(run)
    session.flush()
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code=None,
        source_url="https://javdb.com/v/timd036",
        source_name="临时详情页",
        source_url_name="临时任务",
        task_url="https://javdb.com/v/timd036",
        task_final_url="https://javdb.com/v/timd036",
        task_url_type="temporary_detail",
        status="saved",
        item_data={
            "code": "TIMD-036",
            "source_name": "極上メス男子ゆうきくん無限アクメ肉棒大乱交！！",
        },
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

    task_payload = events[0].payload["tasks"][0]
    assert task_payload["code"] is None
    assert task_payload["source_name"] == "临时详情页"
    assert task_payload["display_code"] == "TIMD-036"
    assert task_payload["display_source_name"] == "極上メス男子ゆうきくん無限アクメ肉棒大乱交！！"


def test_crawler_realtime_events_keep_frontend_contract(admin_user) -> None:
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
        source_url_name="入口A",
        task_url="https://example.test/list",
        task_final_url="https://example.test/list?page=1",
        task_url_type="list",
        status="saved",
        created_at=datetime.now(),
    )
    session.add(detail)
    session.commit()
    session.refresh(run)
    session.refresh(detail)
    queue = event_bus.subscribe(str(admin_user.id))

    service.publish_run_updated(session, run)
    service.publish_run_detail_updated(session, run, [detail], refresh_tasks=True, reason="detail_saved")
    service.append_run_log_for_run(session, run, "入库成功: AAA-001", "INFO", code="AAA-001")

    events = drain(queue)
    event_bus.unsubscribe(str(admin_user.id), queue)
    session.close()

    run_event = next(event for event in events if event.event == "crawler.run.updated")
    detail_event = next(event for event in events if event.event == "crawler.run.detail.updated")
    log_event = next(event for event in events if event.event == "crawler.run.log.appended")

    assert run_event.payload["id"] == str(run.id)
    assert run_event.payload["task_id"] == str(task.id)
    assert run_event.payload["status"] == "running"
    assert run_event.payload["logs"] == []

    assert detail_event.payload["run_id"] == str(run.id)
    assert detail_event.payload["refresh_tasks"] is True
    assert detail_event.payload["reason"] == "detail_saved"
    task_payload = detail_event.payload["tasks"][0]
    assert task_payload["id"] == str(detail.id)
    assert task_payload["run_id"] == str(run.id)
    assert task_payload["task_name"] == "任务A"
    assert task_payload["code"] == "AAA-001"
    assert task_payload["source_url"] == "https://example.test/aaa"
    assert task_payload["source_name"] == "AAA-001"
    assert task_payload["source_url_name"] == "入口A"
    assert task_payload["task_url"] == "https://example.test/list"
    assert task_payload["task_final_url"] == "https://example.test/list?page=1"
    assert task_payload["task_url_type"] == "list"
    assert task_payload["status"] == "saved"
    assert task_payload["error"] is None
    assert task_payload["created_at"] == detail.created_at.isoformat()
    assert task_payload["display_code"] == "AAA-001"
    assert task_payload["display_source_name"] == "AAA-001"
    assert detail_event.payload["summary"] == {
        "total": 1,
        "pending_crawl": 0,
        "crawling": 0,
        "saved": 1,
        "skipped": 0,
        "crawl_failed": 0,
        "save_failed": 0,
        "completed": 1,
        "waiting": 0,
        "failed": 0,
    }

    assert log_event.payload["run_id"] == str(run.id)
    assert log_event.payload["log"]["message"] == "入库成功: AAA-001"
    assert log_event.payload["log"]["context"]["code"] == "AAA-001"
