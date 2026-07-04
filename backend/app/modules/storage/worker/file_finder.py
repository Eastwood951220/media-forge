from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass
class ScopedSearchResult:
    accepted_files: list[dict]
    log_context: dict


def _raw_file_to_dict(file_obj) -> dict:
    path = getattr(file_obj, "full_path", "") or getattr(file_obj, "fullPathName", "")
    return {
        "name": getattr(file_obj, "name", "") or PurePosixPath(path).name,
        "path": path,
        "size": int(getattr(file_obj, "size", 0) or 0),
        "is_dir": bool(getattr(file_obj, "is_directory", False) or getattr(file_obj, "isDirectory", False)),
    }


def _is_virtual_search_path(path: str) -> bool:
    return "/[Search]" in str(PurePosixPath(path))


def _is_search_result(file_obj, raw_item: dict) -> bool:
    return bool(
        getattr(file_obj, "is_search_result", False)
        or getattr(file_obj, "isSearchResult", False)
        or _is_virtual_search_path(raw_item["path"])
    )


def _resolve_file_candidate(provider, file_obj) -> tuple[dict, dict, str | None, dict | None]:
    raw_item = _raw_file_to_dict(file_obj)
    resolved_item = dict(raw_item)
    if not _is_search_result(file_obj, raw_item):
        if _is_virtual_search_path(raw_item["path"]):
            return raw_item, resolved_item, "virtual_search_path", None
        return raw_item, resolved_item, None, None

    try:
        original = provider.get_original_path(raw_item["path"])
        original_log = {
            "name": raw_item["name"],
            "raw_path": raw_item["path"],
            "original_path": original,
        }
    except Exception as exc:
        original = ""
        original_log = {
            "name": raw_item["name"],
            "raw_path": raw_item["path"],
            "original_path": "",
            "error": str(exc),
        }
    if not original:
        resolved_item["path"] = ""
        return raw_item, resolved_item, "missing_original_path", original_log
    resolved_item["path"] = original
    resolved_item["name"] = PurePosixPath(original).name
    if _is_virtual_search_path(original):
        return raw_item, resolved_item, "virtual_search_path", original_log
    return raw_item, resolved_item, None, original_log


def _file_to_dict(provider, file_obj) -> dict:
    raw_item, resolved_item, reason, _original_log = _resolve_file_candidate(provider, file_obj)
    if reason is not None:
        return {
            **resolved_item,
            "resolution_error": reason,
            "raw_path": raw_item["path"],
            "resolved_path": resolved_item["path"],
        }
    return resolved_item


def _is_usable_video(file_dict: dict, config: dict) -> bool:
    ext = PurePosixPath(file_dict["name"]).suffix.lower()
    min_bytes = int(config.get("minimum_video_size_mb", 100)) * 1024 * 1024
    return ext in set(config.get("video_extensions", [])) and int(file_dict.get("size") or 0) >= min_bytes


def _path_is_under(path: str, folder: str) -> bool:
    normalized_path = str(PurePosixPath(path))
    normalized_folder = str(PurePosixPath(folder))
    return normalized_path == normalized_folder or normalized_path.startswith(f"{normalized_folder}/")


def _movie_code_matches(file_dict: dict, movie_code: str) -> bool:
    normalized_code = movie_code.upper()
    haystack = f"{file_dict.get('name', '')} {file_dict.get('path', '')}".upper()
    return normalized_code in haystack


def _rejection_reason(file_dict: dict, *, config: dict, movie_code: str, search_scope: str, task_download_folder: str) -> str | None:
    ext = PurePosixPath(file_dict["name"]).suffix.lower()
    if ext not in {str(item).lower() for item in config.get("video_extensions", [])}:
        return "extension_not_allowed"
    min_bytes = int(config.get("minimum_video_size_mb", 100)) * 1024 * 1024
    if int(file_dict.get("size") or 0) < min_bytes:
        return "below_minimum_size"
    if not _movie_code_matches(file_dict, movie_code):
        return "movie_code_mismatch"
    if search_scope == "task_download_folder" and not _path_is_under(file_dict["path"], task_download_folder):
        return "outside_task_download_folder"
    return None


def _rejected_file(raw_item: dict, resolved_item: dict, reason: str, error: str | None = None) -> dict:
    entry = {
        "name": raw_item["name"],
        "raw_path": raw_item["path"],
        "resolved_path": resolved_item.get("path", ""),
        "size": int(raw_item.get("size") or 0),
        "reason": reason,
    }
    if error:
        entry["error"] = error
    return entry


def _recursive_list(provider, path: str, config: dict) -> list[dict]:
    found = []
    for entry in provider.list_files(path):
        item = _file_to_dict(provider, entry)
        if item["is_dir"]:
            found.extend(_recursive_list(provider, item["path"], config))
        elif _is_usable_video(item, config):
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
        item = _raw_file_to_dict(entry)
        raw_entries.append(_raw_entry_log(normalized_current, item))
        if _is_virtual_search_path(item["path"]):
            rejected.append(_rejected_file(item, item, "virtual_search_path"))
            continue
        if not _path_is_under(item["path"], search_root):
            rejected.append(_rejected_file(item, item, "outside_task_download_folder"))
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
        _append_candidate(
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


def _append_candidate(
    *,
    raw_candidate: dict,
    candidate: dict,
    accepted: list[dict],
    rejected: list[dict],
    seen: set[str],
    config: dict,
    movie_code: str,
    search_scope: str,
    task_download_folder: str,
    resolution_error: str | None = None,
) -> None:
    if candidate.get("is_dir"):
        return
    if resolution_error is not None:
        rejected.append(_rejected_file(raw_candidate, candidate, resolution_error))
        return
    reason = _rejection_reason(
        candidate,
        config=config,
        movie_code=movie_code,
        search_scope=search_scope,
        task_download_folder=task_download_folder,
    )
    if reason:
        rejected.append(_rejected_file(raw_candidate, candidate, reason))
        return
    if _is_virtual_search_path(candidate["path"]):
        rejected.append(_rejected_file(raw_candidate, candidate, "virtual_search_path"))
        return
    if candidate["path"] in seen:
        rejected.append(_rejected_file(raw_candidate, candidate, "duplicate_resolved_path"))
        return
    seen.add(candidate["path"])
    accepted.append({
        "name": candidate["name"],
        "path": candidate["path"],
        "size": int(candidate.get("size") or 0),
        "is_dir": False,
    })


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
        raw_item, resolved, resolution_error, original_log = _resolve_file_candidate(provider, file_obj)
        raw_results.append({key: raw_item[key] for key in ("name", "path", "size")})
        resolved_results.append({key: resolved[key] for key in ("name", "path", "size")})
        if original_log is not None:
            original_path_results.append(original_log)
        _append_candidate(
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
        _append_candidate(
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
