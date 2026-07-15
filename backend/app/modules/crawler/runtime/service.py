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
from backend.app.modules.crawler.runtime.detail_queue import upsert_detail_task
from backend.app.modules.crawler.runtime.details import (
    ENDED_RUN_STATUSES,
    RESTARTABLE_DETAIL_STATUSES,
    clear_run_detail_tasks,
    has_detail_phase_started,
    reset_unfinished_detail_tasks_to_pending,
)
from backend.app.modules.crawler.runtime.events import (
    append_run_log_for_run,
    publish_run_detail_updated,
    publish_run_updated,
)
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.runtime.retry import (
    ensure_run_can_restart,
    mark_details_for_retry,
    prepare_run_for_restart,
    select_retry_details,
)
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

    def create_run(
        self,
        task: CrawlTask,
        crawl_mode: str,
        *,
        selected_task_url_ids: list[uuid.UUID] | None = None,
    ) -> CrawlRun:
        if crawl_mode not in {"incremental", "full"}:
            raise ValueError("crawl_mode must be incremental or full")
        result = None
        if selected_task_url_ids is not None:
            selected_ids = [str(url_id) for url_id in selected_task_url_ids]
            result = {
                "url_subset": True,
                "selected_task_url_ids": selected_ids,
                "selected_task_url_count": len(selected_ids),
            }
        run = CrawlRun(
            task_id=task.id,
            task_name=task.name,
            status="queued",
            crawl_mode=crawl_mode,
            queued_at=datetime.now(),
            result=result,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        self.runtime.enqueue_run(str(run.id))
        self._ensure_worker_started()
        return run

    def create_temporary_detail_run(self, task: CrawlTask, detail_urls: list[str]) -> CrawlRun:
        run = CrawlRun(
            task_id=task.id,
            task_name=task.name,
            status="queued",
            crawl_mode="temporary",
            queued_at=datetime.now(),
            result={"temporary": True, "detail_url_count": len(detail_urls)},
        )
        self.db.add(run)
        self.db.flush()
        for detail_url in detail_urls:
            upsert_detail_task(
                self.db,
                run=run,
                task_name=task.name,
                item={
                    "url": detail_url,
                    "source_url": detail_url,
                    "name": "临时详情页",
                    "source_name": "临时详情页",
                    "_task_url_name": "临时任务",
                    "_task_url": detail_url,
                    "_task_final_url": detail_url,
                    "_task_url_type": "temporary_detail",
                },
            )
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
        ensure_run_can_restart(self.db, run)
        prepare_run_for_restart(self.db, run)
        self.db.commit()
        self.db.refresh(run)
        self.runtime.clear_stop(str(run.id))
        self.runtime.enqueue_run(str(run.id))
        self._ensure_worker_started()
        publish_run_updated(self.db, run)
        return run

    def retry_failed_details(
        self,
        run_id: uuid.UUID,
        *,
        detail_ids: list[uuid.UUID] | None = None,
        retry_all: bool = False,
    ) -> CrawlRun:
        run = self.db.get(CrawlRun, run_id)
        if run is None:
            raise ValueError("运行记录不存在")
        details, retry_label = select_retry_details(
            self.db,
            run,
            detail_ids=detail_ids,
            retry_all=retry_all,
        )
        mark_details_for_retry(details)

        run.status = "queued"
        run.queued_at = datetime.now()
        run.started_at = None
        run.finished_at = None
        run.result = {"detail_retry": True}
        run.error = None
        self.db.commit()
        self.db.refresh(run)

        self.runtime.clear_stop(str(run.id))
        self.runtime.enqueue_run(str(run.id))
        self._ensure_worker_started()
        publish_run_detail_updated(self.db, run, details)
        publish_run_updated(self.db, run)
        append_run_log_for_run(self.db, run, f"重新爬取{retry_label}失败子任务: {len(details)} 条", "INFO")
        return run

    def _ensure_worker_started(self) -> None:
        ensure_crawler_worker_started(self.runtime)
