from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import BadZipFile, ZipFile

from backend.app.modules.backup.groups import BACKUP_FORMAT_NAME, BACKUP_FORMAT_VERSION
from backend.app.modules.backup.schemas import BackupInspectResult

MANIFEST_NAME = "manifest.json"


def _is_safe_entry(name: str) -> bool:
    """Reject absolute paths and any path part that is ``..``."""
    path = PurePosixPath(name)
    if path.is_absolute():
        return False
    if name.startswith("/") or name.startswith("\\"):
        return False
    if "\\" in name:
        # ZIP archives written on Windows may use backslash separators; treat
        # them as part separators so ``..\\evil`` cannot smuggle a traversal.
        parts = PurePosixPath(name.replace("\\", "/")).parts
    else:
        parts = path.parts
    return ".." not in parts


def assert_safe_archive_name(name: str) -> None:
    if not _is_safe_entry(name):
        raise ValueError(f"Unsafe archive entry: {name}")


def write_jsonl(zip_file: ZipFile, arcname: str, rows: Iterable[dict[str, Any]]) -> int:
    """Write JSON Lines entries and return the number of rows written."""
    count = 0
    with zip_file.open(arcname, "w") as raw:
        for row in rows:
            raw.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
            count += 1
    return count


def read_jsonl(zip_file: ZipFile, arcname: str) -> Iterator[dict[str, Any]]:
    """Yield one parsed JSON object per line with line numbers in errors."""
    with zip_file.open(arcname, "r") as raw:
        for line_number, raw_line in enumerate(raw, start=1):
            text = raw_line.decode("utf-8").strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {arcname}:{line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Invalid JSONL object in {arcname}:{line_number}")
            yield payload


def write_manifest(zip_file: ZipFile, manifest: dict[str, Any]) -> None:
    """Write the archive manifest as pretty-printed JSON."""
    zip_file.writestr(
        MANIFEST_NAME,
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
    )


def read_manifest(zip_file: ZipFile) -> dict[str, Any]:
    """Read and structurally validate ``manifest.json`` from an archive."""
    try:
        with zip_file.open(MANIFEST_NAME, "r") as raw:
            text = raw.read().decode("utf-8")
    except KeyError as exc:
        raise ValueError("Backup archive missing manifest.json") from exc
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Backup archive manifest is not valid JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Backup archive manifest must be a JSON object")
    if manifest.get("format") != BACKUP_FORMAT_NAME:
        raise ValueError("Unsupported backup format")
    if manifest.get("version") != BACKUP_FORMAT_VERSION:
        raise ValueError("Unsupported backup format version")
    return manifest


def inspect_backup_archive(path: Path) -> BackupInspectResult:
    """Inspect a local ``.mfbackup`` archive without trusting its contents."""
    try:
        with ZipFile(path) as zip_file:
            for info in zip_file.infolist():
                assert_safe_archive_name(info.filename)
            manifest = read_manifest(zip_file)
            groups = manifest.get("groups") or []
            row_counts = manifest.get("row_counts") or {}
            if not isinstance(groups, list):
                raise ValueError("Backup manifest groups must be a list")
            if not isinstance(row_counts, dict):
                raise ValueError("Backup manifest row_counts must be an object")
            return BackupInspectResult(
                manifest=manifest,
                groups=[str(group) for group in groups],  # type: ignore[list-item]
                row_counts={str(key): int(value) for key, value in row_counts.items()},
                include_sensitive=bool(manifest.get("include_sensitive", False)),
            )
    except BadZipFile as exc:
        raise ValueError("Invalid backup archive") from exc
    except OSError as exc:
        raise ValueError(f"Cannot open backup archive: {exc}") from exc


def read_text_entry(zip_file: ZipFile, arcname: str) -> str:
    """Read a small text entry (for example a config file) from an archive."""
    try:
        with zip_file.open(arcname, "r") as raw:
            return raw.read().decode("utf-8")
    except KeyError as exc:
        raise ValueError(f"Backup archive missing {arcname}") from exc
