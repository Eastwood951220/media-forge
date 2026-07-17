from __future__ import annotations

from pathlib import PurePosixPath

from backend.app.modules.content.movies.storage_locations import build_movie_storage_target_folders
from backend.app.modules.content.movies.storage_scan import scan_movie_storage_locations
from backend.app.modules.content.movies.storage_scan import is_matching_video
from backend.app.modules.storage.worker.target_files import ensure_directory_chain


def _target_file_path(target_folder: str, file_name: str) -> str:
    return str(PurePosixPath(target_folder) / file_name)


def _normalize_path(path: str) -> str:
    return str(PurePosixPath(str(path or "")))


def _summary_locations(movie) -> list[dict]:
    summary = dict(getattr(movie, "storage_summary", None) or {})
    locations = summary.get("locations") or []
    return [dict(location) for location in locations if isinstance(location, dict)]


def _location_to_item(location: dict) -> dict:
    path = str(location.get("path") or "")
    name = str(location.get("file_name") or PurePosixPath(path).name)
    return {
        "name": name,
        "path": path,
        "size": int(location.get("size") or 0),
        "is_dir": False,
    }


def _source_candidates_from_summary(context, movie, target_paths: list[str]) -> list[dict]:
    normalized_targets = {_normalize_path(path) for path in target_paths}
    candidates: list[dict] = []
    for location in _summary_locations(movie):
        target_folder = _normalize_path(str(location.get("target_folder") or ""))
        if not target_folder or target_folder in normalized_targets:
            continue
        item = _location_to_item(location)
        if not item["path"]:
            continue
        if not is_matching_video(movie, item, context.config):
            continue
        try:
            found = context.provider.find_file(item["path"])
        except Exception as exc:
            context.log(
                "WARNING",
                "检查电影已有存储文件失败",
                {"path": item["path"], "error": str(exc)},
                step="prepare",
            )
            continue
        if not found or int(getattr(found, "size", 0) or 0) <= 0:
            continue
        candidates.append({
            "path": item["path"],
            "name": item["name"],
            "size": int(getattr(found, "size", 0) or item["size"]),
            "target_folder": target_folder,
            "storage_location": str(location.get("storage_location") or ""),
        })
    return sorted(candidates, key=lambda item: (item["target_folder"], item["path"]))


def _source_candidates_from_scan(context, movie, target_paths: list[str]) -> list[dict]:
    db = getattr(context, "db", None)
    if db is None:
        return []
    normalized_targets = {_normalize_path(path) for path in target_paths}
    try:
        folders = build_movie_storage_target_folders(db, movie, context.config)
        _checked_targets, locations = scan_movie_storage_locations(
            movie,
            context.provider,
            context.config,
            folders,
            "existing_movie_storage_prefetch",
        )
    except Exception as exc:
        context.log(
            "WARNING",
            "扫描电影已有存储位置失败",
            {"error": str(exc), "target_paths": target_paths},
            step="prepare",
        )
        return []

    candidates: list[dict] = []
    for location in locations:
        target_folder = _normalize_path(str(location.get("target_folder") or ""))
        if not target_folder or target_folder in normalized_targets:
            continue
        item = _location_to_item(location)
        if not item["path"] or not is_matching_video(movie, item, context.config):
            continue
        candidates.append({
            "path": item["path"],
            "name": item["name"],
            "size": item["size"],
            "target_folder": target_folder,
            "storage_location": str(location.get("storage_location") or ""),
        })
    return sorted(candidates, key=lambda item: (item["target_folder"], item["path"]))


def copy_from_existing_movie_storage(context, movie, target_paths: list[str]) -> list[dict]:
    context.log(
        "INFO",
        "检查电影已有存储位置",
        {"target_paths": target_paths},
        step="prepare",
    )
    candidates = _source_candidates_from_summary(context, movie, target_paths)
    if not candidates:
        candidates = _source_candidates_from_scan(context, movie, target_paths)
    if not candidates:
        context.log(
            "INFO",
            "未找到可用于复制的电影已有存储文件",
            {"target_paths": target_paths},
            step="prepare",
        )
        return []

    source = candidates[0]
    copied_paths: list[str] = []
    for target_folder in target_paths:
        target_file = _target_file_path(target_folder, source["name"])
        try:
            existing = context.provider.find_file(target_file)
        except Exception:
            existing = None
        if existing and int(getattr(existing, "size", 0) or 0) > 0:
            copied_paths.append(target_file)
            continue
        ensure_directory_chain(context.provider, target_folder)
        context.provider.copy_file(source["path"], target_folder)
        copied_paths.append(target_file)

    moved_file = {
        "name": source["name"],
        "path": source["path"],
        "size": source["size"],
        "renamed_name": source["name"],
        "moved_path": source["path"],
        "copied_paths": copied_paths,
        "copy_source": source["path"],
        "copy_source_target": source["target_folder"],
        "copy_reason": "existing_movie_storage",
    }
    context.log(
        "INFO",
        "已从电影已有存储复制到目标目录",
        {
            "source": source["path"],
            "source_target": source["target_folder"],
            "target_paths": target_paths,
            "copied_paths": copied_paths,
        },
        step="move_files",
    )
    return [moved_file]
