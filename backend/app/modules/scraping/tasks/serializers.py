from __future__ import annotations

from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem


def task_to_dict(task: ScrapingTask) -> dict:
    return {
        "id": str(task.id),
        "status": task.status,
        "total_count": task.total_count,
        "success_count": task.success_count,
        "failed_count": task.failed_count,
        "skipped_count": task.skipped_count,
        "cancel_requested": bool(task.cancel_requested),
        "created_by": str(task.created_by),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "queued_at": task.queued_at.isoformat() if task.queued_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "error_message": task.error_message,
    }


def item_to_dict(item: ScrapingTaskItem) -> dict:
    return {
        "id": str(item.id),
        "task_id": str(item.task_id),
        "movie_id": str(item.movie_id),
        "movie_code": item.movie_code,
        "movie_title": item.movie_title,
        "status": item.status,
        "source": item.source,
        "folder": item.folder,
        "duration_ms": item.duration_ms,
        "error_message": item.error_message,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
