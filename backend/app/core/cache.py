"""Best-effort Redis JSON cache helpers.

Caching here is a latency optimization only. Every helper swallows Redis and
serialization failures and behaves like a cache miss, so callers keep working
when Redis is unavailable or not initialized yet.

Only values that change rarely and are cheap to recompute belong in this cache,
and every writer must invalidate the keys it can change.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from backend.app.core.dependencies import get_redis

logger = logging.getLogger(__name__)

# Namespace owned by this application, so a shared Redis database stays safe.
PREFIX = "mediaforge:cache"


def cache_key(*parts: object) -> str:
    """Build a namespaced cache key from ordered parts."""
    return ":".join([PREFIX, *(str(part) for part in parts)])


def read_json(key: str) -> Any | None:
    """Return the cached JSON value, or None on a miss or Redis failure.

    None always means "not cached": callers must not cache None values.
    """
    try:
        raw = get_redis().get(key)
    except Exception:
        logger.debug("Cache read failed for %s", key, exc_info=True)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("Discarding malformed cache entry %s", key)
        delete_keys(key)
        return None


def write_json(key: str, value: Any, *, ttl_seconds: int) -> None:
    """Cache a JSON-serializable value, ignoring Redis failures."""
    try:
        get_redis().set(key, json.dumps(value, ensure_ascii=False), ex=ttl_seconds)
    except Exception:
        logger.debug("Cache write failed for %s", key, exc_info=True)


def delete_keys(*keys: str) -> None:
    """Drop specific cache keys, ignoring Redis failures."""
    if not keys:
        return
    try:
        get_redis().delete(*keys)
    except Exception:
        logger.debug("Cache delete failed for %s", keys, exc_info=True)


def read_through_json(key: str, *, ttl_seconds: int, producer: Callable[[], Any]) -> Any:
    """Return the cached value, computing and caching it on a miss."""
    cached = read_json(key)
    if cached is not None:
        return cached
    value = producer()
    if value is not None:
        write_json(key, value, ttl_seconds=ttl_seconds)
    return value


def clear_namespace() -> None:
    """Delete every cache entry owned by this application.

    Used at startup, after interrupted-run recovery rewrites run statuses
    without going through the realtime publishers that normally invalidate.
    """
    try:
        client = get_redis()
        for key in client.scan_iter(match=f"{PREFIX}:*", count=500):
            client.delete(key)
    except Exception:
        logger.debug("Cache namespace clear failed", exc_info=True)
