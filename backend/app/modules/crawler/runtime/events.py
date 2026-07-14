from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.exc import ObjectDeletedError
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.tasks.runtime_status import publish_task_status_updated

logger = logging.getLogger(__name__)


def run_owner_id(db: Session, run: CrawlRun) -> str | None:
    if run.task_id is None:
        return None
    task = db.get(CrawlTask, run.task_id)
    return str(task.owner_id) if task is not None else None


def publish_run_updated(db: Session, run: CrawlRun) -> None:
    from backend.app.modules.realtime.bus import event_bus as realtime_bus
    from backend.app.modules.realtime.schemas import make_realtime_event

    owner_id = run_owner_id(db, run)
    if owner_id is None:
        return
    payload = {
        "id": str(run.id),
        "task_id": str(run.task_id) if run.task_id else None,
        "task_name": run.task_name,
        "status": run.status,
        "crawl_mode": run.crawl_mode,
        "error": run.error,
        "logs": [],
    }
    realtime_bus.publish(
        make_realtime_event(
            event="crawler.run.updated",
            scope="crawler.run",
            owner_id=owner_id,
            resource_id=str(run.id),
            payload=payload,
        )
    )
    publish_task_status_updated(db, run)


def publish_run_detail_updated(
    db: Session,
    run: CrawlRun,
    details: list[CrawlRunDetailTask],
    *,
    refresh_tasks: bool = False,
    reason: str | None = None,
) -> None:
    from backend.app.modules.crawler.runs.router import _run_task_summary
    from backend.app.modules.realtime.bus import event_bus as realtime_bus
    from backend.app.modules.realtime.schemas import make_realtime_event

    owner_id = run_owner_id(db, run)
    if owner_id is None:
        return
    detail_payloads = []
    for detail in details:
        try:
            detail_payloads.append(
                {
                    "id": str(detail.id),
                    "run_id": str(detail.run_id),
                    "task_name": detail.task_name,
                    "code": detail.code,
                    "source_url": detail.source_url,
                    "source_name": detail.source_name,
                    "source_url_name": detail.source_url_name,
                    "task_url": detail.task_url,
                    "task_final_url": detail.task_final_url,
                    "task_url_type": detail.task_url_type,
                    "status": detail.status,
                    "error": detail.error,
                    "created_at": detail.created_at.isoformat() if detail.created_at else None,
                }
            )
        except ObjectDeletedError:
            logger.warning("Skip realtime update for deleted crawl detail task")
    payload: dict[str, Any] = {
        "run_id": str(run.id),
        "tasks": detail_payloads,
        "summary": _run_task_summary(db, run),
    }
    if refresh_tasks:
        payload["refresh_tasks"] = True
    if reason is not None:
        payload["reason"] = reason
    realtime_bus.publish(
        make_realtime_event(
            event="crawler.run.detail.updated",
            scope="crawler.run",
            owner_id=owner_id,
            resource_id=str(run.id),
            payload=payload,
        )
    )


def publish_queue_updated(db: Session, runtime: CrawlerRuntimeState, owner_id: str | None = None) -> None:
    from backend.app.modules.realtime.bus import event_bus as realtime_bus
    from backend.app.modules.realtime.schemas import make_realtime_event

    if owner_id is None:
        return
    realtime_bus.publish(
        make_realtime_event(
            event="crawler.queue.updated",
            scope="crawler.queue",
            owner_id=owner_id,
            payload=runtime.queue_status(),
        )
    )


def append_run_log_for_run(
    db: Session,
    run: CrawlRun,
    message: str,
    level: str = "INFO",
    **context: Any,
) -> None:
    from backend.app.modules.crawler.runs.logs import append_run_log, build_run_log
    from backend.app.modules.realtime.bus import event_bus as realtime_bus
    from backend.app.modules.realtime.schemas import make_realtime_event

    entry = build_run_log(level, message, **context)
    append_run_log(str(run.id), entry)
    owner_id = run_owner_id(db, run)
    if owner_id is None:
        return
    realtime_bus.publish(
        make_realtime_event(
            event="crawler.run.log.appended",
            scope="crawler.run",
            owner_id=owner_id,
            resource_id=str(run.id),
            payload={"run_id": str(run.id), "log": entry},
        )
    )
