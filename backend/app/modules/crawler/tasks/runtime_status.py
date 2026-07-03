"""Derive runtime status for crawl tasks from their latest crawl run.

Global constraint: Do not persist runtime status on CrawlTask.
Always derive it from the latest CrawlRun row.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask

# Maps CrawlRun.status -> derived task runtime status
_RUN_STATUS_TO_TASK_STATUS: dict[str, str] = {
    "queued": "running",
    "running": "running",
    "completed": "success",
    "failed": "failed",
    "stopped": "pending",
}

_DEFAULT_STATUS = "pending"


def derive_runtime_status(latest_run: CrawlRun | None) -> str:
    """Derive task runtime status from the latest crawl run.

    Args:
        latest_run: The most recent CrawlRun for a task, or None if no runs exist.

    Returns:
        One of: "pending", "running", "success", "failed"
    """
    if latest_run is None:
        return _DEFAULT_STATUS
    return _RUN_STATUS_TO_TASK_STATUS.get(latest_run.status, _DEFAULT_STATUS)


def build_task_runtime_status_response(
    task_id: uuid.UUID,
    task_name: str,
    is_skip: bool,
    latest_run: CrawlRun | None,
) -> dict:
    """Build a single task's runtime status response dict.

    Args:
        task_id: The task UUID.
        task_name: The task name.
        is_skip: Whether the task is disabled.
        latest_run: The most recent CrawlRun, or None.

    Returns:
        Dict with task_id, name, is_skip, status, latest_run_id, latest_run_status.
    """
    return {
        "task_id": str(task_id),
        "name": task_name,
        "is_skip": is_skip,
        "status": derive_runtime_status(latest_run),
        "latest_run_id": str(latest_run.id) if latest_run else None,
        "latest_run_status": latest_run.status if latest_run else None,
    }


def get_latest_runs_by_task_ids(
    db: Session,
    task_ids: list[uuid.UUID],
) -> dict[uuid.UUID, CrawlRun]:
    """Fetch the latest CrawlRun for each task ID using a subquery.

    Args:
        db: Database session.
        task_ids: List of task UUIDs.

    Returns:
        Dict mapping task_id -> latest CrawlRun.
    """
    if not task_ids:
        return {}

    # Subquery: max created_at per task_id
    latest_subq = (
        select(
            CrawlRun.task_id,
            func.max(CrawlRun.created_at).label("max_created_at"),
        )
        .where(CrawlRun.task_id.in_(task_ids))
        .group_by(CrawlRun.task_id)
        .subquery()
    )

    # Join to get full run rows
    rows = (
        db.execute(
            select(CrawlRun)
            .join(
                latest_subq,
                (CrawlRun.task_id == latest_subq.c.task_id)
                & (CrawlRun.created_at == latest_subq.c.max_created_at),
            )
        )
        .scalars()
        .all()
    )

    return {run.task_id: run for run in rows if run.task_id is not None}


def get_all_task_runtime_statuses(
    db: Session,
    owner_id: uuid.UUID,
) -> list[dict]:
    """Get derived runtime status for all tasks owned by the user.

    Args:
        db: Database session.
        owner_id: The owner's UUID.

    Returns:
        List of dicts, each with task runtime status info.
    """
    tasks = (
        db.execute(
            select(CrawlTask)
            .where(CrawlTask.owner_id == owner_id)
            .order_by(CrawlTask.created_at.desc())
        )
        .scalars()
        .all()
    )

    task_ids = [task.id for task in tasks]
    latest_runs = get_latest_runs_by_task_ids(db, task_ids)

    return [
        build_task_runtime_status_response(
            task_id=task.id,
            task_name=task.name,
            is_skip=task.is_skip,
            latest_run=latest_runs.get(task.id),
        )
        for task in tasks
    ]


def can_delete_task(latest_run: CrawlRun | None) -> bool:
    """Check whether a task can be deleted based on its runtime status.

    Tasks with a running or queued latest run cannot be deleted.

    Args:
        latest_run: The most recent CrawlRun, or None.

    Returns:
        True if the task can be deleted, False otherwise.
    """
    status = derive_runtime_status(latest_run)
    return status != "running"


def publish_task_status_updated(
    owner_id: str,
    task_id: uuid.UUID,
    status: str,
) -> None:
    """Publish a realtime event when a task's runtime status changes.

    Args:
        owner_id: The owner's UUID as string.
        task_id: The task UUID.
        status: The new derived status.
    """
    from backend.app.modules.realtime.bus import event_bus as realtime_bus
    from backend.app.modules.realtime.schemas import make_realtime_event

    realtime_bus.publish(
        make_realtime_event(
            event="crawler.task.status.updated",
            scope="crawler.task",
            owner_id=owner_id,
            resource_id=str(task_id),
            payload={"task_id": str(task_id), "status": status},
        )
    )
