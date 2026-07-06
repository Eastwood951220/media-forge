from __future__ import annotations

from datetime import datetime, timezone

from backend.app.modules.storage.tasks.policies import order_magnet_candidates


def magnet_dicts_from_movie(movie) -> list[dict]:
    return [
        {
            "id": str(m.id),
            "magnet_url": m.magnet_url,
            "tags": list(m.tags or []),
            "weight": m.weight,
            "selected": m.selected,
        }
        for m in (movie.magnets or [])
        if m.magnet_url
    ]


def ordered_magnet_attempts(movie, max_attempts: int) -> list[dict]:
    return order_magnet_candidates(magnet_dicts_from_movie(movie), max_attempts)


def append_magnet_attempt(subtask, magnet: dict, success: bool) -> None:
    attempt_record = {
        "magnet_id": magnet.get("id"),
        "success": success,
        "status": subtask.status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    attempts = list(subtask.magnet_attempts or [])
    attempts.append(attempt_record)
    subtask.magnet_attempts = attempts
