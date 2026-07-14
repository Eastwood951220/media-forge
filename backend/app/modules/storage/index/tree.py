from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

from backend.app.modules.storage.index.models import StorageIndexRecord


def empty_tree(target_folder: str, indexed_at: str | None, *, version: int = 1) -> dict[str, Any]:
    return {
        "version": version,
        "target_folder": target_folder,
        "indexed_at": indexed_at,
        "categories": {},
    }


def insert_record(tree: dict[str, Any], record: StorageIndexRecord) -> None:
    category = tree.setdefault("categories", {}).setdefault(
        record.storage_location,
        {
            "path": str(PurePosixPath(record.target_folder).parent),
            "code_folders": {},
        },
    )
    folder_name = PurePosixPath(record.target_folder).name
    code_folder = category.setdefault("code_folders", {}).setdefault(
        folder_name,
        {
            "path": record.target_folder,
            "code": record.code,
            "videos": [],
        },
    )
    videos = code_folder.setdefault("videos", [])
    videos[:] = [video for video in videos if video.get("path") != record.path]
    videos.append(
        {
            "path": record.path,
            "file_name": record.file_name,
            "size": record.size,
            "indexed_at": record.indexed_at,
        }
    )


def tree_from_records(
    target_folder: str,
    records: list[StorageIndexRecord],
    *,
    indexed_at: str | None,
    version: int = 1,
) -> dict[str, Any]:
    tree = empty_tree(target_folder, indexed_at=indexed_at, version=version)
    for record in records:
        insert_record(tree, record)
    return tree


def known_code_folder_paths(tree: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for category in (tree.get("categories") or {}).values():
        for code_folder in (category.get("code_folders") or {}).values():
            path = str(code_folder.get("path") or "")
            if path:
                paths.add(path)
    return paths


def group_records_by_code(tree: dict[str, Any]) -> dict[str, list[StorageIndexRecord]]:
    grouped: dict[str, list[StorageIndexRecord]] = defaultdict(list)
    for category_name, category in (tree.get("categories") or {}).items():
        for _folder_name, code_folder in (category.get("code_folders") or {}).items():
            code = str(code_folder.get("code") or "").upper()
            target_folder = str(code_folder.get("path") or "")
            for video in code_folder.get("videos") or []:
                record = StorageIndexRecord(
                    code=code,
                    path=str(video["path"]),
                    target_folder=target_folder,
                    storage_location=str(category_name),
                    file_name=str(video["file_name"]),
                    size=int(video.get("size") or 0),
                    indexed_at=str(video["indexed_at"]),
                )
                grouped[record.code].append(record)
    return dict(grouped)
