from __future__ import annotations

from pathlib import PurePosixPath

from shared.database.models.content import Movie

KNOWN_STORAGE_SUFFIXES = ("", "-C", "-U", "-UC")


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
        found_locations.extend(
            _matching_locations_from_entries(
                movie=movie,
                entries=entries,
                config=config,
                target_folder=target_folder,
                storage_location=str(folder.get("storage_location") or ""),
                source=source,
            )
        )
    if not found_locations:
        found_locations.extend(_scan_category_fallback(movie, provider, config, source, checked_targets))
    return checked_targets, found_locations


def _scan_category_fallback(
    movie: Movie,
    provider,
    config: dict,
    source: str,
    checked_targets: list[str],
) -> list[dict]:
    target_root = str(config.get("target_folder") or "").rstrip("/")
    code = str(movie.code or "").upper()
    if not target_root or not code:
        return []

    try:
        root_entries = provider.list_files(target_root)
    except Exception:
        return []

    found_locations: list[dict] = []
    for entry in root_entries:
        category = remote_entry_to_dict(entry, target_root)
        if not category["is_dir"] or not category["name"]:
            continue
        category_folder = category["path"] or str(PurePosixPath(target_root) / category["name"])
        for suffix in KNOWN_STORAGE_SUFFIXES:
            code_folder_name = f"{code}{suffix}"
            code_folder = str(PurePosixPath(category_folder) / code_folder_name)
            checked_targets.append(code_folder)
            try:
                entries = provider.list_files(code_folder)
            except Exception:
                entries = []
            found_locations.extend(
                _matching_locations_from_entries(
                    movie=movie,
                    entries=entries,
                    config=config,
                    target_folder=code_folder,
                    storage_location=category["name"],
                    source=source,
                )
            )
    return found_locations


def _matching_locations_from_entries(
    *,
    movie: Movie,
    entries,
    config: dict,
    target_folder: str,
    storage_location: str,
    source: str,
) -> list[dict]:
    locations: list[dict] = []
    for entry in entries:
        item = remote_entry_to_dict(entry, target_folder)
        if is_matching_video(movie, item, config):
            locations.append({
                "path": item["path"],
                "target_folder": target_folder,
                "storage_location": storage_location,
                "file_name": item["name"],
                "size": item["size"],
                "exists": True,
                "source": source,
            })
    return locations
