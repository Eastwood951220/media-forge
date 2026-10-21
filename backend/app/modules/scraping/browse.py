from __future__ import annotations

import os
from pathlib import Path
from typing import Any

MAX_ENTRIES = 500

# Quick access locations offered by the folder picker. Only the ones that exist
# in the current runtime (host process or container) are returned.
QUICK_ROOT_CANDIDATES = (
    "/mnt",
    "/media",
    "/data",
    "/app/data",
    "/Volumes",
)

BROWSE_ROOT_ENV = "SCRAPING_BROWSE_ROOT"


class DirectoryBrowseError(ValueError):
    """Raised when a directory cannot be resolved or listed."""


def default_browse_root() -> Path:
    """Return the directory the picker opens when no path is supplied.

    ``SCRAPING_BROWSE_ROOT`` lets Docker deployments start the picker at the
    mounted media directory instead of the container root.
    """
    configured = os.environ.get(BROWSE_ROOT_ENV, "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_absolute() and candidate.is_dir():
            return candidate.resolve()
    return Path(os.path.abspath(os.sep))


def _resolve_directory(raw_path: str | None) -> Path:
    text = str(raw_path or "").strip()
    if not text:
        return default_browse_root()
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise DirectoryBrowseError("目录必须是绝对路径")
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as exc:
        raise DirectoryBrowseError("目录不可访问") from exc
    if not resolved.exists():
        raise DirectoryBrowseError("目录不存在")
    if not resolved.is_dir():
        raise DirectoryBrowseError("路径不是文件夹")
    return resolved


def _quick_roots() -> list[dict[str, str]]:
    roots: list[dict[str, str]] = []
    seen: set[str] = set()
    candidates = [default_browse_root()]
    candidates.extend(Path(item) for item in QUICK_ROOT_CANDIDATES)
    candidates.append(Path.home())
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError):
            continue
        key = str(resolved)
        if key in seen or not resolved.is_dir():
            continue
        seen.add(key)
        roots.append({"name": key, "path": key})
    return roots


def list_directories(raw_path: str | None = None, include_hidden: bool = False) -> dict[str, Any]:
    """List sub folders of ``raw_path`` for the scraping folder picker."""
    directory = _resolve_directory(raw_path)
    entries: list[dict[str, str]] = []
    truncated = False
    try:
        with os.scandir(directory) as iterator:
            for entry in iterator:
                if not include_hidden and entry.name.startswith("."):
                    continue
                try:
                    if not entry.is_dir():
                        continue
                except OSError:
                    continue
                entries.append({"name": entry.name, "path": str(directory / entry.name)})
    except PermissionError as exc:
        raise DirectoryBrowseError("没有访问该目录的权限") from exc
    except OSError as exc:
        raise DirectoryBrowseError("目录不存在或不可访问") from exc

    entries.sort(key=lambda item: item["name"].lower())
    if len(entries) > MAX_ENTRIES:
        entries = entries[:MAX_ENTRIES]
        truncated = True

    parent = directory.parent
    return {
        "path": str(directory),
        "parent": None if parent == directory else str(parent),
        "entries": entries,
        "roots": _quick_roots(),
        "truncated": truncated,
    }
