from __future__ import annotations

from pathlib import PurePosixPath

from shared.database.models.content import Movie


def remote_entry_to_dict(entry, target_folder: str) -> dict:
    path = getattr(entry, "full_path", "") or getattr(entry, "fullPathName", "")
    name = getattr(entry, "name", "") or PurePosixPath(path).name
    if not path:
        path = str(PurePosixPath(target_folder) / name)
    return {
        "name": name,
        "path": path,
        "size": int(getattr(entry, "size", 0) or 0),
        "is_dir": bool(getattr(entry, "is_directory", False) or getattr(entry, "isDirectory", False)),
    }


def is_matching_video(movie: Movie, item: dict, config: dict) -> bool:
    if item["is_dir"]:
        return False
    ext = PurePosixPath(item["name"]).suffix.lower()
    allowed_exts = {str(value).lower() for value in config.get("video_extensions", [".mp4", ".mkv", ".avi", ".wmv", ".flv", ".mov"])}
    if ext not in allowed_exts:
        return False
    min_bytes = int(config.get("minimum_video_size_mb", 100) or 100) * 1024 * 1024
    if int(item.get("size") or 0) < min_bytes:
        return False
    code = str(movie.code or "").upper()
    return bool(code and item["name"].upper().startswith(code))


def scan_movie_storage_locations(
    movie: Movie,
    provider,
    config: dict,
    folders: list[dict],
    source: str,
) -> tuple[list[str], list[dict]]:
    checked_targets: list[str] = []
    found_locations: list[dict] = []
    for folder in folders:
        target_folder = str(folder["target_folder"])
        checked_targets.append(target_folder)
        try:
            entries = provider.list_files(target_folder)
        except Exception:
            entries = []
        for entry in entries:
            item = remote_entry_to_dict(entry, target_folder)
            if is_matching_video(movie, item, config):
                found_locations.append({
                    "path": item["path"],
                    "target_folder": target_folder,
                    "storage_location": str(folder.get("storage_location") or ""),
                    "file_name": item["name"],
                    "size": item["size"],
                    "exists": True,
                    "source": source,
                })
    return checked_targets, found_locations
