from __future__ import annotations

from pathlib import PurePosixPath

from backend.app.modules.storage.worker.cleanup_ops import cleanup_download_folder
from backend.app.modules.storage.worker.move_ops import MoveRenamedVideosResult, move_renamed_videos
from backend.app.modules.storage.worker.rename_ops import is_rename_name_exists_error, rename_selected_videos
from backend.app.modules.storage.worker.verify_ops import verify_moved_files


def select_main_videos(files: list[dict], config: dict) -> list[dict]:
    extensions = {ext.lower() for ext in config.get("video_extensions", [])}
    minimum_size = int(config.get("minimum_video_size_mb", 100)) * 1024 * 1024
    videos = [
        file
        for file in files
        if PurePosixPath(file["name"]).suffix.lower() in extensions
        and int(file.get("size") or 0) >= minimum_size
    ]
    return sorted(videos, key=lambda file: (str(file["name"]).lower(), str(file["path"]).lower()))


def target_files_exist(provider, target_folder: str, filenames: list[str]) -> bool:
    """Check if all target files exist in the folder."""
    try:
        existing = provider.list_files(target_folder)
        existing_names = {getattr(f, "name", "") for f in existing}
        return all(name in existing_names for name in filenames)
    except Exception:
        return False


def scan_found_files(found_files: list[dict]) -> list[dict]:
    return [
        {
            "name": file["name"],
            "path": file["path"],
            "size": int(file.get("size") or 0),
            "is_dir": bool(file.get("is_dir", False)),
        }
        for file in found_files
        if not file.get("is_dir", False) and "/[Search]" not in str(file.get("path", ""))
    ]


__all__ = [
    "cleanup_download_folder",
    "is_rename_name_exists_error",
    "move_renamed_videos",
    "MoveRenamedVideosResult",
    "rename_selected_videos",
    "scan_found_files",
    "select_main_videos",
    "target_files_exist",
    "verify_moved_files",
]
