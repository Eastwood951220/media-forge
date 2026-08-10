from datetime import UTC, datetime, timedelta

from backend.app.modules.crawler.agent.auth import (
    create_agent_session_id,
    hash_agent_token,
    session_is_expired,
    verify_agent_token,
)


def test_hash_agent_token_verifies_original_token() -> None:
    token_hash = hash_agent_token("agent-secret")

    assert verify_agent_token("agent-secret", token_hash)
    assert not verify_agent_token("wrong-secret", token_hash)


def test_agent_session_expiry_uses_utc_time() -> None:
    now = datetime(2026, 8, 10, tzinfo=UTC)

    assert not session_is_expired(now + timedelta(minutes=1), now=now)
    assert session_is_expired(now - timedelta(seconds=1), now=now)


def test_create_agent_session_id_has_agent_prefix() -> None:
    assert create_agent_session_id().startswith("ags_")
