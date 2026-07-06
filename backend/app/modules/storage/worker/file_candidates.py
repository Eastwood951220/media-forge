from __future__ import annotations

from pathlib import PurePosixPath

from backend.app.modules.storage.worker.file_identity import is_virtual_search_path


def is_usable_video(file_dict: dict, config: dict) -> bool:
    ext = PurePosixPath(file_dict["name"]).suffix.lower()
    min_bytes = int(config.get("minimum_video_size_mb", 100)) * 1024 * 1024
    return ext in set(config.get("video_extensions", [])) and int(file_dict.get("size") or 0) >= min_bytes


def path_is_under(path: str, folder: str) -> bool:
    normalized_path = str(PurePosixPath(path))
    normalized_folder = str(PurePosixPath(folder))
    return normalized_path == normalized_folder or normalized_path.startswith(f"{normalized_folder}/")


def movie_code_matches(file_dict: dict, movie_code: str) -> bool:
    normalized_code = movie_code.upper()
    haystack = f"{file_dict.get('name', '')} {file_dict.get('path', '')}".upper()
    return normalized_code in haystack


def rejection_reason(file_dict: dict, *, config: dict, movie_code: str, search_scope: str, task_download_folder: str) -> str | None:
    ext = PurePosixPath(file_dict["name"]).suffix.lower()
    if ext not in {str(item).lower() for item in config.get("video_extensions", [])}:
        return "extension_not_allowed"
    min_bytes = int(config.get("minimum_video_size_mb", 100)) * 1024 * 1024
    if int(file_dict.get("size") or 0) < min_bytes:
        return "below_minimum_size"
    if not movie_code_matches(file_dict, movie_code):
        return "movie_code_mismatch"
    if search_scope == "task_download_folder" and not path_is_under(file_dict["path"], task_download_folder):
        return "outside_task_download_folder"
    return None


def rejected_file(raw_item: dict, resolved_item: dict, reason: str, error: str | None = None) -> dict:
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


def append_candidate(
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
        rejected.append(rejected_file(raw_candidate, candidate, resolution_error))
        return
    reason = rejection_reason(
        candidate,
        config=config,
        movie_code=movie_code,
        search_scope=search_scope,
        task_download_folder=task_download_folder,
    )
    if reason:
        rejected.append(rejected_file(raw_candidate, candidate, reason))
        return
    if is_virtual_search_path(candidate["path"]):
        rejected.append(rejected_file(raw_candidate, candidate, "virtual_search_path"))
        return
    if candidate["path"] in seen:
        rejected.append(rejected_file(raw_candidate, candidate, "duplicate_resolved_path"))
        return
    seen.add(candidate["path"])
    accepted.append({
        "name": candidate["name"],
        "path": candidate["path"],
        "size": int(candidate.get("size") or 0),
        "is_dir": False,
    })
