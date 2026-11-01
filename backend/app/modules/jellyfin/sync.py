from __future__ import annotations

import hashlib
import json
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Mapping

from sqlalchemy.orm import Session

from backend.app.models.jellyfin_sync import JellyfinSyncState
from backend.app.modules.scraping.paths import normalize_code
from shared.database.models.content import Movie

_sync_lock = threading.Lock()


@dataclass
class JellyfinSyncResult:
    total_count: int
    matched_count: int
    ambiguous_count: int
    synced_at: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def config_fingerprint(config: Mapping[str, Any]) -> str:
    values = [str(config.get(key) or "") for key in (
        "jellyfin_base_url", "jellyfin_api_key", "media_root", "scrape_root",
    )]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def get_sync_state(db: Session) -> JellyfinSyncState:
    state = db.get(JellyfinSyncState, 1)
    if state is None:
        state = JellyfinSyncState(id=1)
        db.add(state)
        db.flush()
    return state


def _folder_key(path: str) -> str | None:
    if not path or not path.startswith("/"):
        return None
    normalized = PurePosixPath(path)
    return str(normalized.parent if normalized.suffix else normalized)


def _folder_suffix(path: str) -> tuple[str, ...]:
    return PurePosixPath(path).parts[-2:]


def sync_jellyfin_watch_state(
    db: Session,
    client: Any,
    *,
    page_size: int = 200,
    fingerprint: str | None = None,
) -> JellyfinSyncResult:
    if not _sync_lock.acquire(blocking=False):
        raise RuntimeError("Jellyfin 观看状态同步正在进行")
    try:
        return _sync_locked(db, client, page_size=page_size, fingerprint=fingerprint)
    finally:
        _sync_lock.release()


def _sync_locked(db: Session, client: Any, *, page_size: int, fingerprint: str | None) -> JellyfinSyncResult:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    state = get_sync_state(db)
    state.status = "running"
    state.last_attempt_at = now
    state.last_error = None
    db.commit()
    try:
        user_id = client.get_root_user_id()
        items: list[dict] = []
        start = 0
        while True:
            page = client.get_items(user_id, start, page_size)
            rows = page["Items"]
            items.extend(rows)
            start += len(rows)
            total = int(page.get("TotalRecordCount", start))
            if not rows or start >= total:
                break
        by_folder: dict[str, list[dict]] = {}
        by_suffix: dict[tuple[str, ...], list[dict]] = {}
        by_code: dict[str, list[dict]] = {}
        for item in items:
            key = _folder_key(str(item.get("Path") or ""))
            if key:
                by_folder.setdefault(key, []).append(item)
                by_suffix.setdefault(_folder_suffix(key), []).append(item)
                code = normalize_code(PurePosixPath(key).name)
                if code:
                    by_code.setdefault(code, []).append(item)
        movies = db.query(Movie).all()
        local_folder_counts: dict[str, int] = {}
        local_suffix_counts: Counter[tuple[str, ...]] = Counter()
        local_code_counts = Counter(normalize_code(movie.code or "") for movie in movies)
        for movie in movies:
            key = str(PurePosixPath(movie.scraping_folder or ""))
            if movie.scraping_folder:
                local_folder_counts[key] = local_folder_counts.get(key, 0) + 1
                local_suffix_counts[_folder_suffix(key)] += 1
        matched = ambiguous = 0
        for movie in movies:
            key = str(PurePosixPath(movie.scraping_folder or ""))
            candidates = by_folder.get(key, []) if movie.scraping_folder else []
            duplicate_local = local_folder_counts.get(key, 0) > 1
            if not candidates and not duplicate_local and movie.scraping_folder:
                suffix = _folder_suffix(key)
                candidates = by_suffix.get(suffix, [])
                duplicate_local = local_suffix_counts[suffix] > 1
            if not candidates and not duplicate_local:
                code = normalize_code(movie.code or "")
                if code:
                    candidates = by_code.get(code, [])
                    duplicate_local = local_code_counts[code] > 1
            if len(candidates) != 1 or duplicate_local:
                movie.jellyfin_item_id = None
                movie.jellyfin_playback_position_ticks = None
                movie.jellyfin_watch_status = None if candidates or duplicate_local else "not_in_library"
                ambiguous += bool(candidates) or duplicate_local
                continue
            item = candidates[0]
            user_data = item.get("UserData") or {}
            position = int(user_data.get("PlaybackPositionTicks") or 0)
            movie.jellyfin_item_id = str(item["Id"])
            movie.jellyfin_playback_position_ticks = position
            movie.jellyfin_watch_status = (
                "played" if user_data.get("Played") else
                "in_progress" if position > 0 else "unplayed"
            )
            matched += 1
        state = get_sync_state(db)
        state.status = "success"
        state.last_success_at = now
        state.last_error = None
        state.config_fingerprint = fingerprint
        db.commit()
        return JellyfinSyncResult(len(items), matched, ambiguous, now.isoformat())
    except Exception as exc:
        db.rollback()
        state = get_sync_state(db)
        state.status = "failed"
        key = str(getattr(client, "api_key", "") or "")
        state.last_error = str(exc).replace(key, "***")[:1000] if key else str(exc)[:1000]
        db.commit()
        raise
