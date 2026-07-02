import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_redis
from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState

logger = logging.getLogger(__name__)

UNFINISHED_DETAIL_STATUSES = {"pending_crawl", "crawl_failed", "save_failed"}


def get_runtime_state() -> CrawlerRuntimeState:
    return CrawlerRuntimeState(get_redis())


def cleanup_interrupted_runs(db: Session, runtime: CrawlerRuntimeState) -> int:
    runtime.cleanup_runtime()
    rows = db.query(CrawlRun).filter(CrawlRun.status.in_(["queued", "running"])).all()
    now = datetime.now()
    for run in rows:
        run.status = "stopped"
        run.finished_at = run.finished_at or now
        run.error = "服务重启，任务已停止，需手动重启"
    db.commit()
    return len(rows)


class CrawlerRunService:
    def __init__(self, db: Session, runtime: CrawlerRuntimeState) -> None:
        self.db = db
        self.runtime = runtime

    def create_run(self, task: CrawlTask, crawl_mode: str) -> CrawlRun:
        if crawl_mode not in {"incremental", "full"}:
            raise ValueError("crawl_mode must be incremental or full")
        run = CrawlRun(
            task_id=task.id,
            task_name=task.name,
            status="queued",
            crawl_mode=crawl_mode,
            queued_at=datetime.now(),
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        self.runtime.enqueue_run(str(run.id))
        return run

    def stop_run(self, run_id: uuid.UUID) -> CrawlRun:
        run = self.db.get(CrawlRun, run_id)
        if run is None:
            raise ValueError("运行记录不存在")
        if run.status not in {"queued", "running"}:
            raise ValueError("任务当前未在运行中")
        self.runtime.request_stop(str(run.id))
        run.status = "stopped"
        run.finished_at = datetime.now()
        self.db.commit()
        self.db.refresh(run)
        return run

    def restart_run(self, run_id: uuid.UUID) -> CrawlRun:
        old_run = self.db.get(CrawlRun, run_id)
        if old_run is None:
            raise ValueError("运行记录不存在")
        if old_run.status not in {"stopped", "failed"}:
            raise ValueError("只能重启已停止或失败的运行")
        details = (
            self.db.query(CrawlRunDetailTask)
            .filter(
                CrawlRunDetailTask.run_id == old_run.id,
                CrawlRunDetailTask.status.in_(UNFINISHED_DETAIL_STATUSES),
            )
            .order_by(CrawlRunDetailTask.created_at.asc())
            .all()
        )
        if not details:
            raise ValueError("没有未完成的子任务")
        new_run = CrawlRun(
            task_id=old_run.task_id,
            task_name=old_run.task_name,
            status="queued",
            crawl_mode=old_run.crawl_mode,
            queued_at=datetime.now(),
            resumed_from=old_run.id,
        )
        self.db.add(new_run)
        self.db.flush()
        for detail in details:
            self.db.add(CrawlRunDetailTask(
                run_id=new_run.id,
                task_name=detail.task_name,
                code=detail.code,
                source_url=detail.source_url,
                source_name=detail.source_name,
                status=detail.status,
                error=None,
                item_data=detail.item_data,
                created_at=datetime.now(),
                crawled_at=None,
                saved_at=None,
            ))
        self.db.commit()
        self.db.refresh(new_run)
        self.runtime.enqueue_run(str(new_run.id))
        return new_run
