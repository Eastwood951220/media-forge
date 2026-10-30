from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping

from backend.app.modules.jellyfin.client import JellyfinClient

logger = logging.getLogger(__name__)


@dataclass
class LibraryRefreshResult:
    library_id: str
    name: str
    accepted: bool
    error: str | None = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def snapshot_strm_files(root: Path) -> dict[Path, tuple[int, int]]:
    result: dict[Path, tuple[int, int]] = {}
    if not root.is_dir():
        return result
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(current) / name).is_symlink()]
        for name in files:
            if not name.lower().endswith(".strm"):
                continue
            path = Path(current) / name
            if path.is_symlink():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            result[path] = (stat.st_mtime_ns, stat.st_size)
    return result


def changed_strm_paths(before: Mapping[Path, tuple[int, int]], after: Mapping[Path, tuple[int, int]]) -> list[Path]:
    return sorted([path for path, signature in after.items() if before.get(path) != signature])


def wait_for_strm_changes(
    root: Path,
    before: Mapping[Path, tuple[int, int]],
    *,
    poll_seconds: float = 5,
    max_polls: int = 120,
    quiet_polls: int = 6,
    sleep_fn: Callable[[float], None] = time.sleep,
    snapshot_fn: Callable[[Path], dict[Path, tuple[int, int]]] = snapshot_strm_files,
) -> list[Path]:
    changed: set[Path] = set()
    previous = dict(before)
    quiet = 0
    for _ in range(max_polls):
        sleep_fn(poll_seconds)
        current = snapshot_fn(root)
        changed.update(changed_strm_paths(before, current))
        if changed and current == previous:
            quiet += 1
            if quiet >= quiet_polls:
                break
        else:
            quiet = 0
        previous = current
    return sorted(changed)


def _media_path(config: Mapping[str, Any], local_path: Path) -> PurePosixPath | None:
    local_root = Path(str(config.get("scrape_root") or ""))
    media_root = str(config.get("media_root") or "/media")
    if not local_root.is_absolute() or not media_root.startswith("/"):
        return None
    try:
        relative = local_path.resolve().relative_to(local_root.resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    if str(relative) == ".":
        return None
    return PurePosixPath(media_root) / relative.as_posix()


def refresh_libraries_for_paths(
    config: Mapping[str, Any],
    paths: Iterable[Path],
    *,
    client: Any | None = None,
) -> list[LibraryRefreshResult]:
    client = client or JellyfinClient(str(config.get("jellyfin_base_url") or ""), str(config.get("jellyfin_api_key") or ""))
    media_paths = [path for local in paths if (path := _media_path(config, Path(local))) is not None]
    if not media_paths:
        return []
    matched: list[dict] = []
    seen: set[str] = set()
    for library in client.get_virtual_folders():
        item_id = str(library.get("ItemId") or "")
        if not item_id or item_id in seen:
            continue
        locations = [PurePosixPath(location) for location in library.get("Locations") or [] if isinstance(location, str) and location.startswith("/")]
        if any(
            any(media == location or location in media.parents for location in locations)
            for media in media_paths
        ):
            matched.append(library)
            seen.add(item_id)
    results: list[LibraryRefreshResult] = []
    for library in matched:
        item_id = str(library["ItemId"])
        name = str(library.get("Name") or item_id)
        try:
            client.refresh_item(item_id)
            results.append(LibraryRefreshResult(item_id, name, True))
        except Exception as exc:
            results.append(LibraryRefreshResult(item_id, name, False, str(exc)[:300]))
    return results


def schedule_refresh_after_strm(config: Mapping[str, Any], before: Mapping[Path, tuple[int, int]]) -> None:
    if not config.get("jellyfin_auto_refresh_enabled"):
        return
    root = Path(str(config.get("scrape_root") or ""))
    if not root.is_dir():
        return

    def watch() -> None:
        changed = wait_for_strm_changes(root, before)
        if not changed:
            return
        try:
            results = refresh_libraries_for_paths(config, changed)
            logger.info("Jellyfin refresh after STRM changes: %s", [item.to_dict() for item in results])
        except Exception:
            logger.exception("Jellyfin refresh after STRM changes failed")

    threading.Thread(target=watch, daemon=True, name="jellyfin-strm-refresh").start()
