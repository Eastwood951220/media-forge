import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from backend.app.models.crawler_agent import CrawlerAgentWorkItem
from backend.app.models.user import User
from backend.app.modules.crawler.agent.errors import (
    AgentWorkFailedError,
    AgentWorkStopped,
    AgentWorkTimeoutError,
)
from backend.app.modules.crawler.agent.work_items import (
    claim_next_work_item,
    create_work_item,
    expire_stale_work_items,
    is_work_item_completable,
    mark_work_item_failed,
    wait_for_work_item_result,
)


@pytest.fixture
def test_user(db_session):
    user = User(
        username="test-agent-user",
        hashed_password="x",
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_claim_next_work_item_marks_item_assigned(db_session, test_user) -> None:
    run_id = uuid.uuid4()
    task_id = uuid.uuid4()
    item = CrawlerAgentWorkItem(
        owner_id=test_user.id,
        run_id=run_id,
        task_id=task_id,
        page_kind="detail",
        url="https://javdb.com/v/abc",
        status="pending",
    )
    db_session.add(item)
    db_session.commit()

    claimed = claim_next_work_item(
        db_session,
        owner_id=str(test_user.id),
        agent_id="00000000-0000-0000-0000-000000000001",
    )

    assert claimed is not None
    assert claimed.status == "assigned"
    assert claimed.attempt == 1
    assert claimed.claimed_until is not None


def test_expire_stale_work_items_returns_assigned_items_to_pending(db_session, test_user) -> None:
    run_id = uuid.uuid4()
    task_id = uuid.uuid4()
    item = CrawlerAgentWorkItem(
        owner_id=test_user.id,
        run_id=run_id,
        task_id=task_id,
        page_kind="detail",
        url="https://javdb.com/v/abc",
        status="assigned",
        claimed_until=datetime.now(UTC) - timedelta(seconds=1),
    )
    db_session.add(item)
    db_session.commit()

    expired = expire_stale_work_items(db_session, now=datetime.now(UTC))

    assert expired == 1
    assert item.status == "pending"
    assert item.claimed_until is None


class WaitingRuntime:
    def __init__(self, stopped: bool = False) -> None:
        self.stopped = stopped

    def is_stop_requested(self, run_id: str) -> bool:
        return self.stopped


def test_create_work_item_sets_pending_defaults(db_session, test_user) -> None:
    run_id = uuid.uuid4()
    task_id = uuid.uuid4()
    detail_id = uuid.uuid4()
    url_entry_id = uuid.uuid4()

    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=run_id,
        task_id=task_id,
        detail_task_id=detail_id,
        url_entry_id=url_entry_id,
        page_kind="detail",
        url="https://javdb.com/v/abc",
    )

    assert item.status == "pending"
    assert item.owner_id == test_user.id
    assert item.run_id == run_id
    assert item.task_id == task_id
    assert item.detail_task_id == detail_id
    assert item.url_entry_id == url_entry_id
    assert item.page_kind == "detail"
    assert item.url == "https://javdb.com/v/abc"
    assert item.attempt == 0
    assert item.error_reason is None


def test_mark_work_item_failed_records_reason(db_session, test_user) -> None:
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )

    failed = mark_work_item_failed(db_session, item, "parser_empty_detail")

    assert failed.status == "failed"
    assert failed.error_reason == "parser_empty_detail"
    assert failed.claimed_until is None


def test_is_work_item_completable_allows_only_active_states(db_session, test_user) -> None:
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )

    item.status = "pending"
    assert is_work_item_completable(item) is True
    item.status = "assigned"
    assert is_work_item_completable(item) is True
    item.status = "running"
    assert is_work_item_completable(item) is True
    item.status = "completed"
    assert is_work_item_completable(item) is False
    item.status = "failed"
    assert is_work_item_completable(item) is False


def test_wait_for_work_item_result_returns_completed_item(db_session, test_user) -> None:
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )
    item.status = "completed"
    item.result_json = {"tasks": [{"code": "ABC-001"}]}
    db_session.commit()

    result = wait_for_work_item_result(
        db_session,
        item,
        runtime=WaitingRuntime(),
        run_id=str(item.run_id),
        timeout_seconds=1,
        poll_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    assert result.status == "completed"
    assert result.result_json == {"tasks": [{"code": "ABC-001"}]}


def test_wait_for_work_item_result_raises_failed_reason(db_session, test_user) -> None:
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="detail",
        url="https://javdb.com/v/abc",
    )
    mark_work_item_failed(db_session, item, "missing_required_fragments:title")

    with pytest.raises(AgentWorkFailedError, match="missing_required_fragments:title"):
        wait_for_work_item_result(
            db_session,
            item,
            runtime=WaitingRuntime(),
            run_id=str(item.run_id),
            timeout_seconds=1,
            poll_interval_seconds=0,
            sleep=lambda _seconds: None,
        )


def test_wait_for_work_item_result_raises_stopped(db_session, test_user) -> None:
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )

    with pytest.raises(AgentWorkStopped):
        wait_for_work_item_result(
            db_session,
            item,
            runtime=WaitingRuntime(stopped=True),
            run_id=str(item.run_id),
            timeout_seconds=10,
            poll_interval_seconds=0,
            sleep=lambda _seconds: None,
        )


def test_wait_for_work_item_result_raises_timeout(db_session, test_user) -> None:
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )
    ticks = iter([100.0, 100.5, 101.2])

    with pytest.raises(AgentWorkTimeoutError, match="Chrome Agent 执行超时"):
        wait_for_work_item_result(
            db_session,
            item,
            runtime=WaitingRuntime(),
            run_id=str(item.run_id),
            timeout_seconds=1,
            poll_interval_seconds=0,
            now=lambda: next(ticks),
            sleep=lambda _seconds: None,
        )
