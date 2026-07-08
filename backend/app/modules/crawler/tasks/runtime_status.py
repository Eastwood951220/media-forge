"""Derive runtime status for crawl tasks from their latest crawl run.

Global constraint: Do not persist runtime status on CrawlTask.
Always derive it from the latest CrawlRun row.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.app.schemas.crawl_task import (
    CrawlTaskRuntimeSnapshot,
    CrawlTaskRuntimeStats,
    CrawlTaskRuntimeStatusResponse,
)

TaskRuntimeStatus = Literal["idle", "queued", "running", "stopped"]

ACTIVE_RUN_STATUSES = {"queued", "running", "stopped"}


def derive_runtime_status(latest_run_status: str | None) -> TaskRuntimeStatus:
    """Derive task runtime status from the latest crawl run status.

    Args:
        latest_run_status: The status of the latest CrawlRun, or None if no runs exist.

    Returns:
        One of: "idle", "queued", "running", "stopped"
    """
    if latest_run_status == "queued":
        return "queued"
    if latest_run_status == "running":
        return "running"
    if latest_run_status == "stopped":
        return "stopped"
    return "idle"


def _latest_runs_by_task(db: Session, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, CrawlRun]:
    """Fetch the latest CrawlRun for each task ID.

    Args:
        db: Database session.
        task_ids: List of task UUIDs.

    Returns:
        Dict mapping task_id -> latest CrawlRun.
    """
    if not task_ids:
        return {}
    rows = (
        db.query(CrawlRun)
        .filter(CrawlRun.task_id.in_(task_ids))
        .order_by(CrawlRun.task_id.asc(), CrawlRun.created_at.desc())
        .all()
    )
    latest: dict[uuid.UUID, CrawlRun] = {}
    for row in rows:
        if row.task_id is not None and row.task_id not in latest:
            latest[row.task_id] = row
    return latest


def build_task_runtime_snapshot(task: CrawlTask, latest_run: CrawlRun | None) -> CrawlTaskRuntimeSnapshot:
    """Build a runtime snapshot for a single task.

    Args:
        task: The CrawlTask entity.
        latest_run: The most recent CrawlRun, or None.

    Returns:
        CrawlTaskRuntimeSnapshot with derived status.
    """
    return CrawlTaskRuntimeSnapshot(
        task_id=task.id,
        runtime_status=derive_runtime_status(latest_run.status if latest_run else None),
        latest_run_id=latest_run.id if latest_run else None,
        latest_run_status=latest_run.status if latest_run else None,
        last_run_at=latest_run.created_at if latest_run else None,
    )


def build_task_runtime_status_response(db: Session, owner_id: uuid.UUID) -> CrawlTaskRuntimeStatusResponse:
    """Build runtime status response for all tasks owned by the user.

    Args:
        db: Database session.
        owner_id: The owner's UUID.

    Returns:
        CrawlTaskRuntimeStatusResponse with tasks and stats.
    """
    tasks = (
        db.query(CrawlTask)
        .filter(CrawlTask.owner_id == owner_id)
        .order_by(CrawlTask.created_at.desc())
        .all()
    )
    latest_runs = _latest_runs_by_task(db, [task.id for task in tasks])
    snapshots = [build_task_runtime_snapshot(task, latest_runs.get(task.id)) for task in tasks]
    counts = {"idle": 0, "running": 0, "queued": 0, "stopped": 0}
    for snapshot in snapshots:
        counts[snapshot.runtime_status] += 1
    return CrawlTaskRuntimeStatusResponse(
        tasks=snapshots,
        stats=CrawlTaskRuntimeStats(
            total=len(snapshots),
            idle=counts["idle"],
            running=counts["running"],
            queued=counts["queued"],
            stopped=counts["stopped"],
        ),
    )


def get_task_runtime_status(
    db: Session,
    task_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> CrawlTaskRuntimeSnapshot | None:
    """Get runtime status for a specific task.

    Args:
        db: Database session.
        task_id: The task UUID.
        owner_id: The owner's UUID.

    Returns:
        CrawlTaskRuntimeSnapshot or None if task not found.
    """
    task = db.query(CrawlTask).filter(CrawlTask.id == task_id, CrawlTask.owner_id == owner_id).first()
    if task is None:
        return None
    latest_run = (
        db.query(CrawlRun)
        .filter(CrawlRun.task_id == task_id)
        .order_by(CrawlRun.created_at.desc())
        .first()
    )
    return build_task_runtime_snapshot(task, latest_run)


def can_delete_task_runtime_status(runtime_status: str) -> bool:
    """Check whether a task can be deleted based on its runtime status.

    Idle tasks have no active latest run. Stopped tasks are no longer actively
    running and can be deleted after their runtime keys are purged.
    """
    return runtime_status in {"idle", "stopped"}


def publish_task_status_updated(db: Session, run: CrawlRun) -> None:
    """Publish a realtime event when a task's runtime status changes.

    Called alongside publish_run_updated to notify frontend of status changes.

    Args:
        db: Database session.
        run: The CrawlRun that changed status.
    """
    from backend.app.modules.realtime.bus import event_bus as realtime_bus
    from backend.app.modules.realtime.schemas import make_realtime_event

    if run.task_id is None:
        return
    task = db.get(CrawlTask, run.task_id)
    if task is None:
        return
    owner_id = str(task.owner_id)
    snapshot = build_task_runtime_snapshot(task, run)
    realtime_bus.publish(
        make_realtime_event(
            event="crawler.task.status.updated",
            scope="crawler.task",
            owner_id=owner_id,
            resource_id=str(task.id),
            payload=snapshot.model_dump(mode="json"),
        )
    )
