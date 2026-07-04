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


def _file_to_dict(provider, file_obj) -> dict:
    item = _raw_file_to_dict(file_obj)
    if getattr(file_obj, "is_search_result", False) or getattr(file_obj, "isSearchResult", False):
        original = provider.get_original_path(item["path"])
        if original:
            item["path"] = original
            item["name"] = PurePosixPath(original).name
    return item
    path = getattr(file_obj, "full_path", "") or getattr(file_obj, "fullPathName", "")
    if getattr(file_obj, "is_search_result", False) or getattr(file_obj, "isSearchResult", False):
        original = provider.get_original_path(path)
        if original:
            path = original
    return {
        "name": getattr(file_obj, "name", "") or PurePosixPath(path).name,
        "path": path,
        "size": int(getattr(file_obj, "size", 0) or 0),
        "is_dir": bool(getattr(file_obj, "is_directory", False) or getattr(file_obj, "isDirectory", False)),
    }


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


def _recursive_list(provider, path: str, config: dict) -> list[dict]:
    found = []
    for entry in provider.list_files(path):
        item = _file_to_dict(provider, entry)
        if item["is_dir"]:
            found.extend(_recursive_list(provider, item["path"], config))
        elif _is_usable_video(item, config):
            found.append(item)
    return found


def _append_candidate(
    *,
    candidate: dict,
    accepted: list[dict],
    rejected: list[dict],
    seen: set[str],
    config: dict,
    movie_code: str,
    search_scope: str,
    task_download_folder: str,
) -> None:
    if candidate.get("is_dir"):
        return
    reason = _rejection_reason(
        candidate,
        config=config,
        movie_code=movie_code,
        search_scope=search_scope,
        task_download_folder=task_download_folder,
    )
    if reason:
        rejected.append({
            "name": candidate["name"],
            "path": candidate["path"],
            "size": int(candidate.get("size") or 0),
            "reason": reason,
        })
        return
    if candidate["path"] in seen:
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
                "accepted_files": [],
                "rejected_files": [{"name": "", "path": search_path, "size": 0, "reason": "search_error", "error": str(exc)}],
            },
        )

    for file_obj in search_results:
        raw_item = _raw_file_to_dict(file_obj)
        raw_results.append({key: raw_item[key] for key in ("name", "path", "size")})
        resolved = _file_to_dict(provider, file_obj)
        resolved_results.append({key: resolved[key] for key in ("name", "path", "size")})
        _append_candidate(
            candidate=resolved,
            accepted=accepted,
            rejected=rejected,
            seen=seen,
            config=config,
            movie_code=movie_code,
            search_scope=search_scope,
            task_download_folder=task_download_folder,
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
