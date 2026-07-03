from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)


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


def ensure_directory_chain(provider, folder_path: str) -> None:
    """Ensure all directories in the path exist."""
    provider.ensure_directory(folder_path)


def target_files_exist(provider, target_folder: str, filenames: list[str]) -> bool:
    """Check if all target files exist in the folder."""
    try:
        existing = provider.list_files(target_folder)
        existing_names = {getattr(f, "name", "") for f in existing}
        return all(name in existing_names for name in filenames)
    except Exception:
        return False


def execute_current_magnet_attempt(context, magnet: dict) -> bool:
    """Execute a single magnet download attempt. Returns True on success."""
    from backend.app.modules.storage.worker.file_finder import find_existing_video_files
    from backend.app.modules.storage.tasks.policies import build_video_filename

    subtask = context.subtask
    config = context.config
    provider = context.provider

    magnet_url = magnet.get("magnet_url", "")
    if not magnet_url:
        return False

    # Submit offline download
    download_root = config.get("download_root_folder", "/Downloads")
    download_folder = f"{download_root}/storage_{subtask.id}"

    try:
        ensure_directory_chain(provider, download_folder)
        result = provider.submit_offline_download(magnet_url, download_folder)
    except Exception as exc:
        logger.warning("Magnet download failed: %s", exc)
        return False

    if not result.success:
        logger.warning("Magnet download not successful: %s", result.error_message)
        return False

    # Wait for download and find files
    # In a real implementation, this would poll for download completion
    # For now, search for existing files
    search_terms = [subtask.movie_code]
    search_paths = [download_folder]

    found_files = find_existing_video_files(provider, search_terms, search_paths, config)
    if not found_files:
        return False

    # Select main videos
    main_videos = select_main_videos(found_files, config)
    if not main_videos:
        return False

    # Build target filenames and move
    tags = magnet.get("tags", [])
    target_folder = config.get("target_folder", "/Movies")
    code_folder = build_video_filename(subtask.movie_code, main_videos[0]["name"], tags, 0, 1)
    from backend.app.modules.storage.tasks.policies import code_folder_from_filename
    code_dir = code_folder_from_filename(code_folder)
    final_folder = f"{target_folder}/{code_dir}"

    try:
        ensure_directory_chain(provider, final_folder)
    except Exception as exc:
        logger.warning("Failed to create target folder: %s", exc)
        return False

    # Move files
    renamed_files = []
    for i, video in enumerate(main_videos):
        new_name = build_video_filename(subtask.movie_code, video["name"], tags, i, len(main_videos))
        target_path = f"{final_folder}/{new_name}"
        try:
            provider.move_files([video["path"]], final_folder)
            renamed_files.append({"original": video["path"], "target": target_path})
        except Exception as exc:
            logger.warning("Failed to move file: %s", exc)
            return False

    subtask.renamed_files = renamed_files
    subtask.moved_files = renamed_files
    subtask.result = {"status": "success", "files": renamed_files}

    return True


def execute_subtask_pipeline(context) -> None:
    """Execute the full subtask pipeline."""
    from backend.app.modules.storage.tasks.policies import order_magnet_candidates

    subtask = context.subtask
    config = context.config

    subtask.status = "running"
    subtask.step = "prepare"
    subtask.started_at = datetime.now(timezone.utc)

    # Get magnets for this movie
    from shared.database.models.content import Movie
    movie = context.db.get(Movie, subtask.movie_id)
    if movie is None:
        subtask.status = "failed"
        subtask.error_message = "电影不存在"
        subtask.finished_at = datetime.now(timezone.utc)
        return

    magnets = [m for m in (movie.magnets or []) if m.magnet_url]
    if not magnets:
        subtask.status = "failed"
        subtask.error_message = "无可用磁力链接"
        subtask.finished_at = datetime.now(timezone.utc)
        return

    # Order magnets by priority
    max_attempts = config.get("magnet_max_attempts_per_subtask", 3)
    magnet_dicts = [
        {
            "id": str(m.id),
            "magnet_url": m.magnet_url,
            "tags": list(m.tags or []),
            "weight": m.weight,
            "selected": m.selected,
        }
        for m in magnets
    ]
    ordered = order_magnet_candidates(magnet_dicts, max_attempts)

    # Try each magnet
    for magnet in ordered:
        subtask.step = "cloud_download"
        subtask.current_magnet_id = magnet.get("id")
        subtask.current_magnet_url = magnet.get("magnet_url", "")

        success = execute_current_magnet_attempt(context, magnet)

        attempt_record = {
            "magnet_id": magnet.get("id"),
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        attempts = list(subtask.magnet_attempts or [])
        attempts.append(attempt_record)
        subtask.magnet_attempts = attempts

        if success:
            subtask.status = "completed"
            subtask.step = "done"
            subtask.finished_at = datetime.now(timezone.utc)
            return

    # All magnets failed
    subtask.status = "failed"
    subtask.error_message = "所有磁力链接尝试均失败"
    subtask.finished_at = datetime.now(timezone.utc)
