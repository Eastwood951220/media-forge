import uuid
from datetime import datetime

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.modules.crawler.runtime.detail_queue import (
    claim_next_pending_detail,
    reset_crawling_details_to_pending,
    upsert_detail_task,
)


def make_run(db_session) -> CrawlRun:
    run = CrawlRun(
        id=uuid.uuid4(),
        task_id=None,
        task_name="queue-test",
        status="running",
        crawl_mode="incremental",
        queued_at=datetime.now(),
    )
    db_session.add(run)
    db_session.commit()
    return run


def test_upsert_detail_task_dedupes_by_code(db_session) -> None:
    run = make_run(db_session)
    item = {"code": "AAA-001", "url": "https://javdb.com/v/aaa001", "name": "AAA 001"}

    first = upsert_detail_task(db_session, run=run, task_name=run.task_name, item=item)
    second = upsert_detail_task(db_session, run=run, task_name=run.task_name, item={**item, "name": "Duplicate"})
    db_session.commit()

    rows = db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    assert first is not None
    assert second is None
    assert len(rows) == 1
    assert rows[0].code == "AAA-001"


def test_claim_next_pending_detail_marks_row_crawling(db_session) -> None:
    run = make_run(db_session)
    first = CrawlRunDetailTask(
        run_id=run.id,
        task_name=run.task_name,
        code="AAA-001",
        source_url="https://javdb.com/v/aaa001",
        source_name="AAA 001",
        status="pending_crawl",
        created_at=datetime(2026, 1, 1, 1, 0, 0),
    )
    second = CrawlRunDetailTask(
        run_id=run.id,
        task_name=run.task_name,
        code="AAA-002",
        source_url="https://javdb.com/v/aaa002",
        source_name="AAA 002",
        status="pending_crawl",
        created_at=datetime(2026, 1, 1, 2, 0, 0),
    )
    db_session.add_all([second, first])
    db_session.commit()

    claimed = claim_next_pending_detail(db_session, run.id)

    assert claimed is not None
    assert claimed.code == "AAA-001"
    assert claimed.status == "crawling"


def test_reset_crawling_details_to_pending(db_session) -> None:
    run = make_run(db_session)
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name=run.task_name,
        code="AAA-003",
        source_url="https://javdb.com/v/aaa003",
        source_name="AAA 003",
        status="crawling",
        error="interrupted",
        created_at=datetime.now(),
    )
    db_session.add(detail)
    db_session.commit()

    reset = reset_crawling_details_to_pending(db_session, run)
    db_session.commit()

    assert [row.code for row in reset] == ["AAA-003"]
    db_session.refresh(detail)
    assert detail.status == "pending_crawl"
    assert detail.error is None
