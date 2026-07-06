import logging
import threading
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.dependencies import get_redis
from shared.database.session import get_session_factory
from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.modules.crawler.runtime.details import (
    RESTARTABLE_DETAIL_STATUSES,
    clear_run_detail_tasks,
    has_detail_phase_started,
    reset_unfinished_detail_tasks_to_pending,
)
from backend.app.modules.crawler.runtime.events import (
    publish_run_detail_updated,
    publish_run_updated,
)
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.runtime.worker import (
    cleanup_interrupted_runs,
    ensure_crawler_worker_started,
    process_next_run,
    process_run,
)
from backend.app.modules.crawler.runtime.source_task_names import (
    find_existing_movie_codes,
    movie_code_exists,
)
from backend.app.modules.content.movies.persistence import (
    append_source_task_id,
    sync_movie_filters,
    upsert_movie_with_magnets,
)
from backend.app.modules.crawler.runtime.config import read_incremental_threshold_from_conf
from backend.app.modules.crawler.runtime.engine import CrawlCallbacks, get_crawler_engine
from backend.app.modules.crawler.runtime.task_adapter import to_scraper_task
from backend.app.modules.crawler.tasks.runtime_status import (
    derive_runtime_status,
    publish_task_status_updated,
)

logger = logging.getLogger(__name__)


def get_runtime_state() -> CrawlerRuntimeState:
    return CrawlerRuntimeState(get_redis())


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
        self._ensure_worker_started()
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
        run.error = "用户停止任务"
        reset_details = reset_unfinished_detail_tasks_to_pending(self.db, run)
        self.db.commit()
        self.db.refresh(run)
        if reset_details:
            publish_run_detail_updated(self.db, run, reset_details)
        publish_run_updated(self.db, run)
        return run

    def restart_run(self, run_id: uuid.UUID) -> CrawlRun:
        run = self.db.get(CrawlRun, run_id)
        if run is None:
            raise ValueError("运行记录不存在")
        if run.status not in {"stopped", "failed"}:
            raise ValueError("只能重启已停止或失败的运行")
        if run.task_id is None:
            restartable_count = (
                self.db.query(CrawlRunDetailTask)
                .filter(
                    CrawlRunDetailTask.run_id == run.id,
                    CrawlRunDetailTask.status.in_(RESTARTABLE_DETAIL_STATUSES),
                )
                .count()
            )
            if restartable_count == 0:
                raise ValueError("没有关联任务或未完成子任务，无法重启")

        if has_detail_phase_started(self.db, run):
            reset_unfinished_detail_tasks_to_pending(self.db, run)
        else:
            clear_run_detail_tasks(self.db, run)
        run.status = "queued"
        run.queued_at = datetime.now()
        run.started_at = None
        run.finished_at = None
        run.result = None
        run.error = None
        self.db.commit()
        self.db.refresh(run)
        self.runtime.clear_stop(str(run.id))
        self.runtime.enqueue_run(str(run.id))
        self._ensure_worker_started()
        publish_run_updated(self.db, run)
        return run

    def _ensure_worker_started(self) -> None:
        ensure_crawler_worker_started(self.runtime)
