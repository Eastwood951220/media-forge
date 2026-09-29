import uuid

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from backend.app.models.crawler_agent import CrawlerAgent
from backend.app.modules.crawler.agent.auth import find_agent_by_token, hash_agent_token
from backend.app.modules.crawler.agent.page_actions.auth import get_page_action_agent
from backend.app.modules.crawler.agent.page_actions.urls import normalize_javdb_list_url


@pytest.mark.parametrize(
    ("raw", "expected", "url_type"),
    [
        (
            "https://JAVDB.com/actors/A?page=9&t=d#results",
            "https://javdb.com/actors/A?page=1&t=d",
            "actors",
        ),
        (
            "https://javdb.com/search?z=2&page=3&q=abc&a=1&page=8",
            "https://javdb.com/search?a=1&page=1&q=abc&z=2",
            "search",
        ),
        (
            "https://javdb.com:443/future-list?sort=desc",
            "https://javdb.com/future-list?page=1&sort=desc",
            "list",
        ),
    ],
)
def test_normalize_javdb_list_url_preserves_filters_and_forces_page_one(
    raw: str,
    expected: str,
    url_type: str,
) -> None:
    normalized = normalize_javdb_list_url(raw)

    assert normalized.url == expected
    assert normalized.url_type == url_type


@pytest.mark.parametrize(
    "raw",
    [
        "https://javdb.com/",
        "https://javdb.com/v/abc",
        "https://example.com/actors/A",
        "javascript:alert(1)",
        "https://user:secret@javdb.com/actors/A",
    ],
)
def test_normalize_javdb_list_url_rejects_non_list_targets(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_javdb_list_url(raw)


def test_find_agent_by_token_returns_only_matching_agent(db_session, test_user, other_user) -> None:
    matching = CrawlerAgent(owner_id=test_user.id, token_hash=hash_agent_token("agt_matching"))
    other = CrawlerAgent(owner_id=other_user.id, token_hash=hash_agent_token("agt_other"))
    db_session.add_all([matching, other])
    db_session.commit()

    found = find_agent_by_token(db_session, "agt_matching")

    assert found is not None
    assert found.id == matching.id
    assert find_agent_by_token(db_session, "agt_missing") is None
    assert find_agent_by_token(db_session, "") is None


def test_get_page_action_agent_returns_agent_for_valid_bearer(db_session, test_user) -> None:
    agent = CrawlerAgent(owner_id=test_user.id, token_hash=hash_agent_token("agt_valid"))
    db_session.add(agent)
    db_session.commit()

    resolved = get_page_action_agent(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="agt_valid"),
        db_session,
    )

    assert resolved.id == agent.id


@pytest.mark.parametrize(
    "credentials",
    [
        None,
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-an-agent-token"),
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="agt_invalid"),
    ],
)
def test_get_page_action_agent_rejects_invalid_credentials_without_token_leak(
    credentials: HTTPAuthorizationCredentials | None,
    db_session,
) -> None:
    with pytest.raises(HTTPException) as caught:
        get_page_action_agent(credentials, db_session)

    assert caught.value.status_code == 401
    assert caught.value.detail == {
        "msg": "Agent Token 无效或已失效",
        "data": {"reason": "invalid_agent_token"},
    }
    assert "agt_invalid" not in str(caught.value.detail)
