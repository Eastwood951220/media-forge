from __future__ import annotations

from pathlib import PurePosixPath

from backend.app.modules.storage.worker.file_candidates import (
    append_candidate,
    rejected_file,
)
from backend.app.modules.storage.worker.file_identity import (
    file_to_dict,
    is_virtual_search_path,
    raw_file_to_dict,
)
from backend.app.modules.storage.worker.file_result import ScopedSearchResult


def raw_entry_log(current_path: str, item: dict) -> dict:
    return {
        "current_path": current_path,
        "name": item["name"],
        "path": item["path"],
        "size": int(item.get("size") or 0),
        "is_dir": bool(item.get("is_dir", False)),
    }


def list_real_files_recursive(
    *,
    provider,
    current_path: str,
    search_root: str,
    config: dict,
    raw_entries: list[dict],
    rejected: list[dict],
    visited: set[str],
    depth: int,
    max_depth: int,
) -> list[dict]:
    normalized_current = str(PurePosixPath(current_path))
    if normalized_current in visited:
        rejected.append({
            "name": PurePosixPath(normalized_current).name,
            "raw_path": normalized_current,
            "resolved_path": normalized_current,
            "size": 0,
            "reason": "recursive_loop",
        })
        return []
    if depth > max_depth:
        rejected.append({
            "name": PurePosixPath(normalized_current).name,
            "raw_path": normalized_current,
            "resolved_path": normalized_current,
            "size": 0,
            "reason": "max_depth_exceeded",
        })
        return []

    visited.add(normalized_current)
    found: list[dict] = []
    try:
        entries = provider.list_files(normalized_current)
    except Exception as exc:
        rejected.append({
            "name": PurePosixPath(normalized_current).name,
            "raw_path": normalized_current,
            "resolved_path": normalized_current,
            "size": 0,
            "reason": "list_error",
            "error": str(exc),
        })
        return found

    for entry in entries:
        item = raw_file_to_dict(entry)
        raw_entries.append(raw_entry_log(normalized_current, item))
        if is_virtual_search_path(item["path"]):
            rejected.append(rejected_file(item, item, "virtual_search_path"))
            continue
        if not _path_is_under(item["path"], search_root):
            rejected.append(rejected_file(item, item, "outside_task_download_folder"))
            continue
        if item["is_dir"]:
            found.extend(list_real_files_recursive(
                provider=provider,
                current_path=item["path"],
                search_root=search_root,
                config=config,
                raw_entries=raw_entries,
                rejected=rejected,
                visited=visited,
                depth=depth + 1,
                max_depth=max_depth,
            ))
            continue
        found.append(item)
    return found


def recursive_list(provider, path: str, config: dict) -> list[dict]:
    found = []
    for entry in provider.list_files(path):
        item = file_to_dict(provider, entry)
        if item["is_dir"]:
            found.extend(recursive_list(provider, item["path"], config))
        elif _is_usable_video(item, config):
            found.append(item)
    return found


def _path_is_under(path: str, folder: str) -> bool:
    normalized_path = str(PurePosixPath(path))
    normalized_folder = str(PurePosixPath(folder))
    return normalized_path == normalized_folder or normalized_path.startswith(f"{normalized_folder}/")


def _is_usable_video(file_dict: dict, config: dict) -> bool:
    ext = PurePosixPath(file_dict["name"]).suffix.lower()
    min_bytes = int(config.get("minimum_video_size_mb", 100)) * 1024 * 1024
    return ext in set(config.get("video_extensions", [])) and int(file_dict.get("size") or 0) >= min_bytes


def find_listed_video_files(
    *,
    provider,
    search_path: str,
    search_scope: str,
    movie_code: str,
    task_download_folder: str,
    config: dict,
) -> ScopedSearchResult:
    accepted: list[dict] = []
    rejected: list[dict] = []
    raw_entries: list[dict] = []
    seen: set[str] = set()
    max_depth = int(config.get("download_scan_max_depth", 10) or 10)

    listed_files = list_real_files_recursive(
        provider=provider,
        current_path=search_path,
        search_root=task_download_folder,
        config=config,
        raw_entries=raw_entries,
        rejected=rejected,
        visited=set(),
        depth=0,
        max_depth=max_depth,
    )

    for listed in listed_files:
        append_candidate(
            raw_candidate=listed,
            candidate=listed,
            accepted=accepted,
            rejected=rejected,
            seen=seen,
            config=config,
            movie_code=movie_code,
            search_scope=search_scope,
            task_download_folder=task_download_folder,
        )

    return ScopedSearchResult(
        accepted_files=accepted,
        log_context={
            "search_path": search_path,
            "current_path": search_path,
            "search_scope": search_scope,
            "search_method": "list_sub_files",
            "raw_entries": raw_entries,
            "accepted_files": accepted,
            "rejected_files": rejected,
        },
    )
