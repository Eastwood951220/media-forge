from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.config.conf_reader import read_crawler_runtime_config
from backend.app.modules.crawler.runtime.detail_queue import claim_next_pending_detail, upsert_detail_task
from backend.app.modules.crawler.runtime.details import detail_row_to_task_info
from backend.app.modules.crawler.runtime.events import append_run_log_for_run
from backend.app.modules.crawler.runtime.progress import new_progress, write_progress
from backend.app.modules.crawler.runtime.source_task_names import find_existing_movie_codes, movie_code_exists
from backend.app.modules.content.movies.persistence import append_source_task_id, upsert_movie_with_magnets
from scraper.config.sites import JAVDB_SITE
from scraper.cookies.cookie_manager import CookieManager
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher
from scraper.pipelines.movie_pipeline import MoviePipeline
from scraper.spiders.javdb.javdb_spider import JavdbSpider

logger = logging.getLogger(__name__)


def build_spider() -> JavdbSpider:
    runtime_config = read_crawler_runtime_config()
    cookies = CookieManager(JAVDB_SITE["cookie_file"]).load()
    fetcher = ScraplingFetcher(headers=JAVDB_SITE["headers"], cookies=cookies, timeout=runtime_config.REQUEST_TIMEOUT)
    return JavdbSpider(fetcher=fetcher)


def build_pipeline() -> MoviePipeline:
    return MoviePipeline()


def _worker_session_factory(db: Session) -> sessionmaker:
    return sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)


def _find_existing_movie_codes_in_worker_session(
    session_factory: sessionmaker,
    codes: list[str | None],
) -> set[str]:
    worker_db = session_factory()
    try:
        return find_existing_movie_codes(worker_db, codes)
    finally:
        worker_db.close()


def _append_run_log_in_worker_session(
    session_factory: sessionmaker,
    run: CrawlRun,
    message: str,
    level: str = "INFO",
) -> None:
    worker_db = session_factory()
    try:
        worker_run = worker_db.merge(run, load=False)
        append_run_log_for_run(worker_db, worker_run, message, level)
        worker_db.commit()
    except Exception:
        worker_db.rollback()
        raise
    finally:
        worker_db.close()


def _handle_already_exists_in_worker_session(
    session_factory: sessionmaker,
    run: CrawlRun,
    task: CrawlTask,
    task_info: dict,
) -> None:
    worker_db = session_factory()
    try:
        worker_run = worker_db.merge(run, load=False)
        worker_task = worker_db.merge(task, load=False)
        _handle_already_exists(worker_db, worker_run, worker_task, task_info)
        worker_db.commit()
    except Exception:
        worker_db.rollback()
        raise
    finally:
        worker_db.close()


def execute_threaded_crawl(db: Session, run: CrawlRun, task: CrawlTask, runtime: Any, *, detail_only: bool = False) -> dict[str, Any]:
    config = read_crawler_runtime_config()
    progress = new_progress()

    if not detail_only:
        _run_list_phase(db, run, task, runtime, config)

    _run_detail_phase(db, run, task, runtime, config, progress)
    write_progress(runtime, str(run.id), progress)

    return _build_threaded_result(db, run, task, runtime, progress)


def _run_list_phase(db: Session, run: CrawlRun, task: CrawlTask, runtime: Any, config: Any) -> None:
    spider = build_spider()
    worker_session_factory = _worker_session_factory(db)

    def _collect_url(url_entry):
        return spider.collect_detail_tasks_for_url(
            url_entry=url_entry,
            task_name=task.name,
            crawl_mode=run.crawl_mode,
            incremental_threshold=config.INCREMENTAL_EXIST_THRESHOLD,
            stop_check=lambda: runtime.is_stop_requested(str(run.id)),
            log_callback=lambda msg, level="INFO": _append_run_log_in_worker_session(
                worker_session_factory,
                run,
                msg,
                level,
            ),
            db_check_callback=lambda codes: _find_existing_movie_codes_in_worker_session(worker_session_factory, codes),
            on_item_already_exists=lambda task_info: _handle_already_exists_in_worker_session(
                worker_session_factory,
                run,
                task,
                task_info,
            ),
        )

    with ThreadPoolExecutor(max_workers=max(1, config.LIST_MAX_WORKERS)) as pool:
        futures = [pool.submit(_collect_url, entry) for entry in task.urls]
        for future in as_completed(futures):
            for item in future.result():
                upsert_detail_task(db, run=run, task_name=task.name, item=item)
            db.commit()

    append_run_log_for_run(db, run, "列表收集完成，详情子任务已持久化", "INFO")


def _handle_already_exists(db: Session, run: CrawlRun, task: CrawlTask, task_info: dict) -> None:
    code = task_info.get("code")
    if code:
        append_source_task_id(db, code, task.id)
    append_run_log_for_run(db, run, f"跳过已存在影片并追加任务ID: {code}", "INFO", code=code)


def _run_detail_phase(db: Session, run: CrawlRun, task: CrawlTask, runtime: Any, config: Any, progress: dict) -> None:
    saved_count = 0
    failed_count = 0
    skipped_count = 0

    from scraper.core.throttle import random_sleep

    while True:
        if runtime.is_stop_requested(str(run.id)):
            break
        detail = claim_next_pending_detail(db, run.id)
        if detail is None:
            break

        append_run_log_for_run(
            db, run,
            f"[{task.name}][URL: {detail.source_url_name or detail.task_url_type or '-'}] 详情开始: code={detail.code} name={detail.source_name}",
            "INFO",
            detail_id=str(detail.id), code=detail.code,
            source_url=detail.source_url, source_url_name=detail.source_url_name,
            detail_status="crawling",
        )

        try:
            _process_single_detail(db, run, task, detail, runtime)
            if detail.status == "saved":
                saved_count += 1
            elif detail.status == "skipped":
                skipped_count += 1
            else:
                failed_count += 1
            db.commit()
        except Exception as exc:
            logger.exception("Detail worker failed for %s", detail.code)
            detail.status = "crawl_failed"
            detail.error = str(exc)[:500]
            failed_count += 1
            db.commit()

        random_sleep(config.DETAIL_PAGE_DELAY_MIN, config.DETAIL_PAGE_DELAY_MAX)

    progress["saved"] = saved_count
    progress["failed"] = failed_count
    progress["skipped"] = skipped_count


def _process_single_detail(db: Session, run: CrawlRun, task: CrawlTask, detail: Any, runtime: Any) -> None:
    detail_info = detail_row_to_task_info(detail)
    spider = build_spider()
    pipeline = build_pipeline()

    result = spider.run_single_detail_task(
        detail_info,
        task_name=task.name,
        on_detail_completed=lambda t: None,
        on_detail_failed=lambda t, err: None,
        stop_check=lambda: runtime.is_stop_requested(str(run.id)),
        log_callback=lambda msg, level="INFO": None,
        on_detail_check_callback=lambda code: movie_code_exists(db, code),
        on_item_already_exists=lambda t: None,
    )

    if result.get("status") == "completed":
        detail_data = result.get("detail") or {}
        item = {
            **detail_data,
            "source_url": result.get("url") or detail.source_url,
            "source_name": result.get("name") or detail.source_name,
            "code": detail.code,
        }
        cleaned = pipeline.process_item(item, task_name=task.name, task_id=str(task.id))
        if cleaned:
            upsert_movie_with_magnets(db, {**cleaned, "source_task_ids": [task.id]})
            detail.status = "saved"
            detail.item_data = cleaned
            detail.crawled_at = datetime.now()
            detail.saved_at = datetime.now()
        else:
            detail.status = "save_failed"
            detail.error = "pipeline returned None"
    elif result.get("status") == "skipped":
        detail.status = "skipped"
        detail.error = result.get("reason", "already_exists")
    else:
        detail.status = "crawl_failed"
        detail.error = result.get("reason", "unknown error")


def _build_threaded_result(db: Session, run: CrawlRun, task: CrawlTask, runtime: Any, progress: dict) -> dict[str, Any]:
    from backend.app.models.crawl_run import CrawlRunDetailTask
    total = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).count()
    saved = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id, CrawlRunDetailTask.status == "saved").count()
    failed = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id, CrawlRunDetailTask.status.in_(["crawl_failed", "save_failed"])).count()
    skipped = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id, CrawlRunDetailTask.status == "skipped").count()

    return {
        "total_tasks": total,
        "completed_tasks": saved,
        "failed_tasks": failed,
        "skipped_tasks": skipped,
        "saved": saved,
        "failed": failed,
        "skipped": skipped,
    }
