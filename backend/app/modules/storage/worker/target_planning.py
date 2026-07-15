from __future__ import annotations

from dataclasses import dataclass

from backend.app.modules.storage.tasks.policies import (
    build_video_filename,
    code_folder_from_filename,
    insert_vr_directory,
    is_vr_movie_tags,
)


@dataclass(frozen=True)
class StorageAttemptPlan:
    download_root: str
    download_folder: str
    preview_name: str
    code_folder: str
    target_root: str
    target_paths: list[str]


def plan_storage_attempt(subtask, config: dict, magnet: dict, movie_tags: list[str] | None = None) -> StorageAttemptPlan:
    tags = list(magnet.get("tags") or [])
    download_root = config.get("download_root_folder", "/Downloads")
    download_folder = f"{download_root}/storage_{subtask.id}"
    preview_name = build_video_filename(subtask.movie_code, f"{subtask.movie_code}.mp4", tags, 0, 1)
    code_folder = code_folder_from_filename(preview_name)
    target_root = config.get("target_folder", "/Movies")
    target_locations = list(subtask.target_locations or [])
    selected_location = getattr(subtask, "selected_storage_location", None) or ""
    if selected_location:
        target_paths = [f"{target_root}/{selected_location}/{code_folder}"]
    else:
        target_paths = [f"{target_root}/{location}/{code_folder}" for location in target_locations] or [f"{target_root}/{code_folder}"]
    if is_vr_movie_tags(list(movie_tags or [])):
        target_paths = [insert_vr_directory(path, code_folder) for path in target_paths]
    subtask.download_path = download_folder
    subtask.target_paths = target_paths
    return StorageAttemptPlan(
        download_root=download_root,
        download_folder=download_folder,
        preview_name=preview_name,
        code_folder=code_folder,
        target_root=target_root,
        target_paths=target_paths,
    )
