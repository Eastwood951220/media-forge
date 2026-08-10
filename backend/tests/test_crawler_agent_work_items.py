import uuid
from datetime import UTC, datetime, timedelta

import pytest

from backend.app.models.crawler_agent import CrawlerAgentWorkItem
from backend.app.models.user import User
from backend.app.modules.crawler.agent.work_items import claim_next_work_item, expire_stale_work_items


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
