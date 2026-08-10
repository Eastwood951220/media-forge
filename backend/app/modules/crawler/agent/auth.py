from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime


def hash_agent_token(token: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{token}".encode("utf-8")).hexdigest()
    return f"sha256${salt}${digest}"


def verify_agent_token(token: str, token_hash: str) -> bool:
    try:
        algorithm, salt, expected = token_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "sha256":
        return False
    digest = hashlib.sha256(f"{salt}:{token}".encode("utf-8")).hexdigest()
    return secrets.compare_digest(digest, expected)


def create_agent_token() -> str:
    return f"agt_{secrets.token_urlsafe(32)}"


def create_agent_session_id() -> str:
    return f"ags_{secrets.token_urlsafe(32)}"


def session_is_expired(expires_at: datetime, *, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= current
