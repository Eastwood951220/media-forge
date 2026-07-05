from __future__ import annotations

from backend.app.models.storage_task import StorageMainTask, StorageSubTask


def storage_main_task_to_dict(task: StorageMainTask) -> dict:
    return {
        "id": str(task.id),
        "alias": task.alias,
        "display_name": task.display_name,
        "source": task.source,
        "storage_mode": task.storage_mode,
        "status": task.status,
        "total_count": task.total_count,
        "success_count": task.success_count,
        "failed_count": task.failed_count,
        "skipped_count": task.skipped_count,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "error_message": task.error_message,
    }


def storage_subtask_to_dict(task: StorageSubTask) -> dict:
    return {
        "id": str(task.id),
        "main_task_id": str(task.main_task_id),
        "movie_id": str(task.movie_id),
        "movie_code": task.movie_code,
        "movie_title": task.movie_title,
        "status": task.status,
        "step": task.step,
        "storage_mode": task.storage_mode,
        "selected_storage_location": task.selected_storage_location,
        "target_locations": task.target_locations or [],
        "download_path": task.download_path,
        "target_paths": task.target_paths or [],
        "magnet_attempts": task.magnet_attempts or [],
        "current_magnet_id": str(task.current_magnet_id) if task.current_magnet_id else None,
        "current_magnet_url": task.current_magnet_url,
        "renamed_files": task.renamed_files or [],
        "moved_files": task.moved_files or [],
        "skipped_files": task.skipped_files or [],
        "result": task.result or {},
        "skip_reason": task.skip_reason,
        "error_message": task.error_message,
        "queued_at": task.queued_at.isoformat() if task.queued_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }
