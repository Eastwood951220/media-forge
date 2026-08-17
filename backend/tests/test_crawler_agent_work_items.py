"""Tests for crawler agent work-item lifecycle — phase timeouts, locked transitions, and retry limits."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from backend.app.models.crawler_agent import CrawlerAgentWorkItem
from backend.app.models.user import User
from backend.app.modules.crawler.agent.errors import (
    AgentClaimTimeoutError,
    AgentExecutionTimeoutError,
    AgentWorkFailedError,
    AgentWorkStopped,
    agent_error_message,
)
from backend.app.modules.crawler.agent.work_items import (
    claim_next_work_item,
    create_work_item,
    is_work_item_completable,
    mark_work_item_failed,
    mark_work_item_running,
    release_agent_work_items,
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


class WaitingRuntime:
    def __init__(self, stopped: bool = False) -> None:
        self.stopped = stopped

    def is_stop_requested(self, run_id: str) -> bool:
        return self.stopped


def test_wait_fails_pending_item_with_claim_timeout(
    db_session, test_user
) -> None:
    """A pending item that is never claimed fails with claim timeout after the window."""
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )
    db_session.commit()
    with pytest.raises(AgentClaimTimeoutError, match="未在 10 秒内领取"):
        ticks = [0.0]

        def inc_clock() -> float:
            ticks[0] += 500.0
            return ticks[0]

        wait_for_work_item_result(
            db_session,
            item,
            runtime=WaitingRuntime(),
            run_id=str(item.run_id),
            claim_timeout_seconds=10,
            execution_timeout_seconds=120,
            poll_interval_seconds=0,
            clock=inc_clock,
            sleep=lambda _seconds: None,
        )
    db_session.refresh(item)
    assert item.status == "failed"
    assert item.error_reason == "agent_claim_timeout"


def test_disconnect_requeues_until_third_attempt(
    db_session, test_user
) -> None:
    """Disconnect requeues up to 3 total attempts, then marks failed."""
    agent_id = uuid.uuid4()
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="detail",
        url="https://javdb.com/v/abc",
    )
    db_session.commit()

    for expected_attempt in (1, 2):
        claimed = claim_next_work_item(
            db_session,
            owner_id=str(test_user.id),
            agent_id=str(agent_id),
            execution_timeout_seconds=120,
        )
        assert claimed is not None
        assert claimed.attempt == expected_attempt
        db_session.refresh(item)
        release_agent_work_items(db_session, agent_id=str(agent_id), now=datetime.now(UTC))
        db_session.refresh(item)
        assert item.status == "pending"

    claimed = claim_next_work_item(
        db_session,
        owner_id=str(test_user.id),
        agent_id=str(agent_id),
        execution_timeout_seconds=120,
    )
    db_session.refresh(item)
    release_agent_work_items(db_session, agent_id=str(agent_id), now=datetime.now(UTC))
    db_session.refresh(item)
    assert claimed.attempt == 3
    assert item.status == "failed"
    assert item.error_reason == "agent_connection_lost"


def test_wait_fails_assigned_item_with_execution_timeout(
    db_session, test_user
) -> None:
    """An assigned item that is not completed before the execution deadline fails."""
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="detail",
        url="https://javdb.com/v/abc",
    )
    db_session.commit()
    now = datetime.now(UTC)
    claimed = claim_next_work_item(
        db_session,
        owner_id=str(test_user.id),
        agent_id=str(uuid.uuid4()),
        execution_timeout_seconds=120,
        now=now,
    )
    assert claimed is not None
    with pytest.raises(AgentExecutionTimeoutError, match="页面执行超时"):
        ticks = [0.0]

        def inc_clock() -> float:
            ticks[0] += 500.0
            return ticks[0]

        wait_for_work_item_result(
            db_session,
            claimed,
            runtime=WaitingRuntime(),
            run_id=str(item.run_id),
            claim_timeout_seconds=10,
            execution_timeout_seconds=399,
            poll_interval_seconds=0,
            clock=inc_clock,
            sleep=lambda _seconds: None,
        )
    db_session.refresh(claimed)
    assert claimed.status == "failed"
    assert claimed.error_reason == "agent_execution_timeout"


def test_create_work_item_sets_queued_at_and_pending(
    db_session, test_user
) -> None:
    """create_work_item sets queued_at and defaults to pending with 0 attempt."""
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )
    assert item.status == "pending"
    assert item.attempt == 0
    assert item.queued_at is not None


def test_claim_next_work_item_sets_assigned_phase(
    db_session, test_user
) -> None:
    """claim_next_work_item sets assigned status, assigned_at, claimed_until."""
    now = datetime.now(UTC)
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="detail",
        url="https://javdb.com/v/abc",
    )
    db_session.commit()
    claimed = claim_next_work_item(
        db_session,
        owner_id=str(test_user.id),
        agent_id=str(uuid.uuid4()),
        execution_timeout_seconds=120,
        now=now,
    )
    assert claimed is not None
    assert claimed.status == "assigned"
    assert claimed.assigned_at is not None
    assert claimed.attempt == 1
    assert claimed.claimed_until is not None


def test_mark_work_item_running_transition(
    db_session, test_user
) -> None:
    """mark_work_item_running transitions assigned → running and sets started_at."""
    now = datetime.now(UTC)
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="detail",
        url="https://javdb.com/v/abc",
    )
    db_session.commit()
    claimed = claim_next_work_item(
        db_session,
        owner_id=str(test_user.id),
        agent_id=str(uuid.uuid4()),
        execution_timeout_seconds=120,
        now=now,
    )
    assert claimed is not None
    running = mark_work_item_running(
        db_session, work_item_id=claimed.id, agent_id=claimed.assigned_agent_id,
        attempt=claimed.attempt, phase="parsing",
    )
    assert running.status == "running"
    db_session.refresh(claimed)
    assert claimed.status == "running"
    assert claimed.started_at is not None


def test_is_work_item_completable_allows_only_assigned_and_running(
    db_session, test_user
) -> None:
    """Only 'assigned' and 'running' statuses are completable per the new phase model."""
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )
    db_session.commit()
    item.status = "pending"
    assert is_work_item_completable(item) is False
    item.status = "assigned"
    assert is_work_item_completable(item) is True
    item.status = "running"
    assert is_work_item_completable(item) is True
    item.status = "completed"
    assert is_work_item_completable(item) is False
    item.status = "failed"
    assert is_work_item_completable(item) is False


def test_mark_work_item_failed_records_reason_and_finished_at(
    db_session, test_user
) -> None:
    """mark_work_item_failed sets status=failed, error_reason, and finished_at."""
    now = datetime.now(UTC)
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )
    db_session.commit()
    failed = mark_work_item_failed(
        db_session, work_item_id=item.id, reason="parser_empty_detail", now=now,
    )
    db_session.refresh(item)
    assert item.status == "failed"
    assert item.error_reason == "parser_empty_detail"
    assert item.finished_at is not None


def test_release_agent_work_items_requeues_or_fails(
    db_session, test_user
) -> None:
    """release_agent_work_items requeues assigned items (attempt<3) and fails at attempt=3."""
    now = datetime.now(UTC)
    agent_id = uuid.uuid4()
    item = create_work_item(
        db_session,
        owner_id=test_user.id,
        run_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        page_kind="list",
        url="https://javdb.com/actors/a",
    )
    db_session.commit()
    claimed = claim_next_work_item(
        db_session, owner_id=str(test_user.id), agent_id=str(agent_id),
        execution_timeout_seconds=120, now=now,
    )
    # Set attempt artificially to trigger fail path
    claimed.attempt = 3
    db_session.commit()
    release_agent_work_items(db_session, agent_id=str(agent_id), now=now)
    db_session.refresh(item)
    assert item.status == "failed"
    assert item.error_reason == "agent_connection_lost"
    assert item.finished_at is not None


def test_agent_error_message_function() -> None:
    """agent_error_message returns Chinese messages for known reason codes."""
    assert "领取" in agent_error_message("agent_claim_timeout")
    assert "超时" in agent_error_message("agent_execution_timeout")
    assert "版本" in agent_error_message("upgrade_required")
    assert agent_error_message("unknown_reason") == "unknown_reason"