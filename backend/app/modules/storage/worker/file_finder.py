from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from backend.app.modules.storage.worker.file_candidates import (
    append_candidate,
    is_usable_video,
    path_is_under,
    rejected_file,
)
from backend.app.modules.storage.worker.file_identity import (
    file_to_dict,
    is_virtual_search_path,
    raw_file_to_dict,
    resolve_file_candidate,
)


@dataclass
class ScopedSearchResult:
    accepted_files: list[dict]
    log_context: dict


def _recursive_list(provider, path: str, config: dict) -> list[dict]:
    found = []
    for entry in provider.list_files(path):
        item = file_to_dict(provider, entry)
        if item["is_dir"]:
            found.extend(_recursive_list(provider, item["path"], config))
        elif is_usable_video(item, config):
            found.append(item)
    return found


def _raw_entry_log(current_path: str, item: dict) -> dict:
    return {
        "current_path": current_path,
        "name": item["name"],
        "path": item["path"],
        "size": int(item.get("size") or 0),
        "is_dir": bool(item.get("is_dir", False)),
    }


def _list_real_files_recursive(
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
        raw_entries.append(_raw_entry_log(normalized_current, item))
        if is_virtual_search_path(item["path"]):
            rejected.append(rejected_file(item, item, "virtual_search_path"))
            continue
        if not path_is_under(item["path"], search_root):
            rejected.append(rejected_file(item, item, "outside_task_download_folder"))
            continue
        if item["is_dir"]:
            found.extend(_list_real_files_recursive(
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


def find_scoped_video_files(
    *,
    provider,
    search_terms: list[str],
    search_path: str,
    search_scope: str,
    movie_code: str,
    task_download_folder: str,
    config: dict,
) -> ScopedSearchResult:
    accepted: list[dict] = []
    rejected: list[dict] = []
    raw_results: list[dict] = []
    resolved_results: list[dict] = []
    original_path_results: list[dict] = []
    seen: set[str] = set()
    search_term = search_terms[0] if search_terms else movie_code

    try:
        search_results = provider.search_files(search_term, search_path)
    except Exception as exc:
        return ScopedSearchResult(
            accepted_files=[],
            log_context={
                "search_term": search_term,
                "search_path": search_path,
                "search_scope": search_scope,
                "search_method": "search_files",
                "raw_results": [],
                "resolved_results": [],
                "original_path_results": [],
                "accepted_files": [],
                "rejected_files": [{"name": "", "path": search_path, "size": 0, "reason": "search_error", "error": str(exc)}],
            },
        )

    for file_obj in search_results:
        raw_item, resolved, resolution_error, original_log = resolve_file_candidate(provider, file_obj)
        raw_results.append({key: raw_item[key] for key in ("name", "path", "size")})
        resolved_results.append({key: resolved[key] for key in ("name", "path", "size")})
        if original_log is not None:
            original_path_results.append(original_log)
        append_candidate(
            raw_candidate=raw_item,
            candidate=resolved,
            accepted=accepted,
            rejected=rejected,
            seen=seen,
            config=config,
            movie_code=movie_code,
            search_scope=search_scope,
            task_download_folder=task_download_folder,
            resolution_error=resolution_error,
        )

    try:
        listed_files = _recursive_list(provider, search_path, config)
    except Exception as exc:
        rejected.append({"name": "", "path": search_path, "size": 0, "reason": "list_error", "error": str(exc)})
        listed_files = []

    for listed in listed_files:
        raw_results.append({key: listed[key] for key in ("name", "path", "size")})
        resolved_results.append({key: listed[key] for key in ("name", "path", "size")})
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
            "search_term": search_term,
            "search_path": search_path,
            "search_scope": search_scope,
            "search_method": "search_files",
            "raw_results": raw_results,
            "resolved_results": resolved_results,
            "original_path_results": original_path_results,
            "accepted_files": accepted,
            "rejected_files": rejected,
        },
    )


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

    listed_files = _list_real_files_recursive(
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


def find_existing_video_files(provider, search_terms: list[str], search_paths: list[str], config: dict) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    movie_code = search_terms[0] if search_terms else ""
    task_download_folder = search_paths[0] if search_paths else "/"
    for path in search_paths:
        scoped = find_scoped_video_files(
            provider=provider,
            search_terms=search_terms,
            search_path=path,
            search_scope="download_root",
            movie_code=movie_code,
            task_download_folder=task_download_folder,
            config=config,
        )
        for item in scoped.accepted_files:
            if item["path"] not in seen:
                seen.add(item["path"])
                results.append(item)
        if results:
            return results
    return results


def find_recovery_video_files(
    *,
    provider,
    search_terms: list[str],
    task_download_folder: str,
    download_root: str,
    movie_code: str,
    config: dict,
) -> ScopedSearchResult:
    task_result = find_listed_video_files(
        provider=provider,
        search_path=task_download_folder,
        search_scope="recovery_task_download_folder",
        movie_code=movie_code,
        task_download_folder=task_download_folder,
        config=config,
    )
    if task_result.accepted_files:
        return task_result

    root_result = find_scoped_video_files(
        provider=provider,
        search_terms=search_terms,
        search_path=download_root,
        search_scope="recovery_download_root",
        movie_code=movie_code,
        task_download_folder=download_root,
        config=config,
    )
    return root_result
