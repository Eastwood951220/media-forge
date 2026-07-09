from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun
from backend.app.modules.content.movies.persistence import sync_movie_filters
from backend.app.modules.crawler.runtime.details import (
    count_run_detail_tasks,
    reset_unfinished_detail_tasks_to_pending,
)
from backend.app.modules.crawler.runtime.events import (
    append_run_log_for_run,
    publish_run_detail_updated,
    publish_run_updated,
)
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState

logger = logging.getLogger(__name__)


def _sync_movie_filters_in_isolated_session(db: Session) -> dict[str, int]:
    """Run filter cache sync outside the run-finalization transaction."""

    sync_db = Session(bind=db.get_bind())
    try:
        sync_result = sync_movie_filters(sync_db)
        sync_db.commit()
        return sync_result
    except Exception:
        sync_db.rollback()
        raise
    finally:
        sync_db.close()


def finalize_run(
    db: Session,
    run: CrawlRun,
    runtime: CrawlerRuntimeState,
    result: dict[str, Any] | None,
    *,
    stopped: bool,
) -> None:
    """Aggregate run results, set final status, and sync movie filters.

    This is called once after the engine finishes crawling, whether the run
    completed normally or was stopped by the user.
    """

    if stopped:
        reset_details = reset_unfinished_detail_tasks_to_pending(db, run)
        if reset_details:
            publish_run_detail_updated(db, run, reset_details)

    total_count = count_run_detail_tasks(db, run.id)
    saved_count = count_run_detail_tasks(db, run.id, "saved")
    save_failed_count = count_run_detail_tasks(db, run.id, "save_failed")
    crawl_failed_count = count_run_detail_tasks(db, run.id, "crawl_failed")
    skipped_count = count_run_detail_tasks(db, run.id, "skipped")
    run.result = {
        **(result or {}),
        "total_tasks": total_count,
        "saved": saved_count,
        "save_failed": save_failed_count,
        "crawl_failed": crawl_failed_count,
        "skipped_tasks": skipped_count,
        "stopped": stopped,
    }
    if stopped:
        run.status = "stopped"
        run.error = run.error or "用户停止任务"
        append_run_log_for_run(
            db,
            run,
            f"任务已停止: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}, 跳过={skipped_count}",
            "WARNING",
        )
    else:
        run.status = "completed"
        append_run_log_for_run(
            db, run,
            f"任务完成: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}, 跳过={skipped_count}",
            "INFO",
        )
        try:
            sync_result = _sync_movie_filters_in_isolated_session(db)
            append_run_log_for_run(
                db, run,
                f"筛选列表已同步: 演员={sync_result['actors']}, 标签={sync_result['tags']}, "
                f"导演={sync_result['directors']}, 片商={sync_result['makers']}, 系列={sync_result['series']}",
                "INFO",
            )
        except Exception as sync_exc:
            logger.warning("Failed to sync movie filters for run %s: %s", run.id, sync_exc)
            append_run_log_for_run(db, run, f"筛选列表同步失败: {sync_exc}", "WARNING")

    run.finished_at = datetime.now()
    db.commit()
    publish_run_updated(db, run)
