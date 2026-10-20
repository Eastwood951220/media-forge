from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

CODE_PATTERN = re.compile(r"([A-Za-z]{2,6})[-_ ]?(\d{2,6})(?:[-_ ]([A-Za-z]{1,4}))?")


def normalize_code(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def code_from_folder_name(name: str) -> str | None:
    match = CODE_PATTERN.search(name or "")
    if match is None:
        return None
    code = f"{match.group(1)}-{match.group(2)}"
    if match.group(3):
        code = f"{code}-{match.group(3)}"
    return code.upper()


def _normalized_root(value: str) -> PurePosixPath | None:
    text = str(value or "").strip().rstrip("/")
    if not text.startswith("/"):
        return None
    root = PurePosixPath(text)
    if str(root) in ("", ".", "/"):
        return None
    return root


def cloud_to_local(scrape_root: str, media_root: str, cloud_folder: str) -> Path | None:
    root = _normalized_root(media_root)
    folder = _normalized_root(cloud_folder)
    if root is None or folder is None:
        return None
    try:
        relative = folder.relative_to(root)
    except ValueError:
        return None
    if str(relative) == ".":
        return None
    base = Path(scrape_root)
    local = base / relative
    try:
        local.resolve().relative_to(base.resolve())
    except ValueError:
        return None
    return local


def local_to_cloud(scrape_root: str, media_root: str, local_folder: str | Path) -> str | None:
    root = _normalized_root(media_root)
    if root is None:
        return None
    base = Path(scrape_root)
    try:
        relative = Path(local_folder).resolve().relative_to(base.resolve())
    except ValueError:
        return None
    return str(PurePosixPath(str(root)) / relative.as_posix())
