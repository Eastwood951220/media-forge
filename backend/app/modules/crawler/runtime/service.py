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
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.runtime.source_task_names import (
    add_source_task_id_for_code,
    find_existing_movie_codes,
    movie_code_exists,
)
from backend.app.modules.crawler.tasks.runtime_status import (
    derive_runtime_status,
    publish_task_status_updated,
)

logger = logging.getLogger(__name__)

UNFINISHED_DETAIL_STATUSES = {"pending_crawl", "crawl_failed", "save_failed"}
RESTARTABLE_DETAIL_STATUSES = UNFINISHED_DETAIL_STATUSES
TERMINAL_DETAIL_STATUSES = {"saved", "skipped"}
DETAIL_PHASE_STARTED_STATUSES = {"saved", "crawl_failed", "save_failed"}

_worker_lock = threading.Lock()
_worker_running = False


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
        reset_unfinished_detail_tasks_to_pending(db, run)
        publish_task_status_updated(db, run)
    db.commit()
    return len(rows)


def has_detail_phase_started(db: Session, run: CrawlRun) -> bool:
    return db.query(CrawlRunDetailTask.id).filter(
        CrawlRunDetailTask.run_id == run.id,
        (
            CrawlRunDetailTask.status.in_(DETAIL_PHASE_STARTED_STATUSES)
            | CrawlRunDetailTask.crawled_at.isnot(None)
            | CrawlRunDetailTask.saved_at.isnot(None)
        ),
    ).first() is not None


def reset_unfinished_detail_tasks_to_pending(
    db: Session,
    run: CrawlRun,
) -> list[CrawlRunDetailTask]:
    details = (
        db.query(CrawlRunDetailTask)
        .filter(
            CrawlRunDetailTask.run_id == run.id,
            CrawlRunDetailTask.status.notin_(TERMINAL_DETAIL_STATUSES),
        )
        .order_by(CrawlRunDetailTask.created_at.asc())
        .all()
    )
    for detail in details:
        detail.status = "pending_crawl"
        detail.error = None
        detail.crawled_at = None
        detail.saved_at = None
    db.flush()
    return details


def clear_run_detail_tasks(db: Session, run: CrawlRun) -> None:
    db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).delete(synchronize_session=False)


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
        global _worker_running
        with _worker_lock:
            if _worker_running:
                return
            _worker_running = True
            thread = threading.Thread(target=self._worker_loop, daemon=True)
            thread.start()

    def _worker_loop(self) -> None:
        global _worker_running
        try:
            while True:
                run_id = self.runtime.claim_next_run()
                if run_id is None:
                    break
                process_run(get_session_factory(), self.runtime, run_id)
        finally:
            with _worker_lock:
                _worker_running = False


def process_next_run(db_factory: sessionmaker, runtime: CrawlerRuntimeState) -> bool:
    run_id = runtime.claim_next_run()
    if run_id is None:
        return False
    return process_run(db_factory, runtime, run_id)


def process_run(db_factory: sessionmaker, runtime: CrawlerRuntimeState, run_id: str) -> bool:
    db = db_factory()
    try:
        run = db.get(CrawlRun, uuid.UUID(run_id))
        if run is None:
            logger.error("Run %s not found", run_id)
            return False

        run.status = "running"
        run.started_at = datetime.now()
        db.commit()
        publish_run_updated(db, run)

        runtime.set_current_run(run_id)

        try:
            _execute_run(db, run, runtime)
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            run.status = "failed"
            run.error = str(exc)[:1000]
            run.finished_at = datetime.now()
            db.commit()
            publish_run_updated(db, run)
        finally:
            runtime.set_current_run(None)
            runtime.write_progress(run_id, {})
            runtime.clear_stop(run_id)

        return True
    finally:
        db.close()


def _append_run_log(run_id: str, message: str, level: str = "INFO", **context: Any) -> dict[str, Any] | None:
    from backend.app.modules.crawler.runs.logs import append_run_log, build_run_log

    entry = build_run_log(level, message, **context)
    try:
        append_run_log(run_id, entry)
    except Exception as exc:
        logger.warning("Failed to append crawler run log for %s: %s", run_id, exc)
        return None
    return entry


def _run_owner_id(db: Session, run: CrawlRun) -> str | None:
    if run.task_id is None:
        return None
    task = db.get(CrawlTask, run.task_id)
    return str(task.owner_id) if task is not None else None


def publish_run_updated(db: Session, run: CrawlRun) -> None:
    from backend.app.modules.realtime.bus import event_bus as realtime_bus
    from backend.app.modules.realtime.schemas import make_realtime_event

    owner_id = _run_owner_id(db, run)
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
) -> None:
    from backend.app.modules.realtime.bus import event_bus as realtime_bus
    from backend.app.modules.realtime.schemas import make_realtime_event

    owner_id = _run_owner_id(db, run)
    if owner_id is None:
        return
    realtime_bus.publish(
        make_realtime_event(
            event="crawler.run.detail.updated",
            scope="crawler.run",
            owner_id=owner_id,
            resource_id=str(run.id),
            payload={
                "run_id": str(run.id),
                "tasks": [
                    {
                        "id": str(detail.id),
                        "run_id": str(detail.run_id),
                        "task_name": detail.task_name,
                        "code": detail.code,
                        "source_url": detail.source_url,
                        "source_name": detail.source_name,
                        "status": detail.status,
                        "error": detail.error,
                        "created_at": detail.created_at.isoformat() if detail.created_at else None,
                    }
                    for detail in details
                ],
            },
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
    owner_id = _run_owner_id(db, run)
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


def _persist_crawled_item(db: Session, item_data: dict[str, Any]) -> uuid.UUID:
    from scraper.database.repositories.movie_magnet_repository import MovieMagnetRepository
    from scraper.database.repositories.movie_repository import MovieRepository

    movie_doc = dict(item_data)
    magnets = movie_doc.pop("magnets", []) or []
    repository = MovieRepository(session=db)
    magnet_repository = MovieMagnetRepository(session=db)
    movie_id = repository.upsert_movie(movie_doc)
    if movie_id is None:
        raise RuntimeError("movie repository returned no id")

    if magnets:
        magnet_repository.upsert_many(movie_id, movie_doc, magnets)
        magnet_repository.auto_select_best_magnet(str(movie_id))

    return movie_id


def _count_run_detail_tasks(db: Session, run_id: uuid.UUID, status: str | None = None) -> int:
    query = db.query(func.count(CrawlRunDetailTask.id)).filter(CrawlRunDetailTask.run_id == run_id)
    if status is not None:
        query = query.filter(CrawlRunDetailTask.status == status)
    return int(query.scalar() or 0)


def _execute_run(db: Session, run: CrawlRun, runtime: CrawlerRuntimeState) -> None:
    """Execute a crawler run."""
    from backend.app.models.crawl_task import CrawlTask

    task = db.get(CrawlTask, run.task_id) if run.task_id else None
    if task is None:
        raise ValueError("关联任务不存在")

    # Build task URLs
    task_urls = [{"url": u.url, "url_type": u.url_type} for u in task.urls]
    if not task_urls:
        raise ValueError("任务没有URL")

    # Track progress
    progress = {"total": 0, "saved": 0, "failed": 0, "skipped": 0, "save_failed": 0}
    detail_tasks_by_code: dict[str, CrawlRunDetailTask] = {}
    detail_tasks_by_source_url: dict[str, CrawlRunDetailTask] = {}

    def remember_detail(detail: CrawlRunDetailTask) -> None:
        if detail.code:
            detail_tasks_by_code[detail.code] = detail
        if detail.source_url:
            detail_tasks_by_source_url[detail.source_url] = detail

    def find_detail(task_info: dict[str, Any], item_data: dict[str, Any] | None = None) -> CrawlRunDetailTask | None:
        item_data = item_data or {}
        code = item_data.get("code") or task_info.get("code")
        source_url = task_info.get("url") or task_info.get("source_url") or item_data.get("source_url")
        if code and code in detail_tasks_by_code:
            return detail_tasks_by_code[code]
        if source_url and source_url in detail_tasks_by_source_url:
            return detail_tasks_by_source_url[source_url]
        return None

    def on_tasks_batch_created(items: list[dict[str, Any]]) -> None:
        skipped_count = 0
        created_details: list[CrawlRunDetailTask] = []
        for item in items:
            is_skipped = item.get("status") == "skipped"
            reason = item.get("reason") if is_skipped else None
            detail = find_detail(item)
            if detail is None:
                detail = CrawlRunDetailTask(
                    run_id=run.id,
                    task_name=task.name,
                    code=item.get("code"),
                    source_url=item.get("url", ""),
                    source_name=item.get("name", ""),
                    status="skipped" if is_skipped else "pending_crawl",
                    error=reason,
                    created_at=datetime.now(),
                )
                db.add(detail)
                db.flush()
            elif detail.status not in {"saved", "skipped"}:
                detail.status = "skipped" if is_skipped else "pending_crawl"
                detail.error = reason
                detail.item_data = None
                detail.crawled_at = None
                detail.saved_at = None
            remember_detail(detail)
            created_details.append(detail)
            if is_skipped:
                skipped_count += 1
                if add_source_task_id_for_code(db, item.get("code"), task.id):
                    append_run_log_for_run(db, run, f"已存在影片追加任务ID: {item.get('code')} -> {task.id}", "INFO", code=item.get("code"))
        progress["total"] += len(items)
        progress["skipped"] += skipped_count
        runtime.write_progress(str(run.id), progress)
        db.commit()
        publish_run_detail_updated(db, run, created_details)
        if items:
            append_run_log_for_run(db, run, f"创建子任务 {len(items)} 条，跳过 {skipped_count} 条")

    def on_item_saved(task_info: dict[str, Any], item_data: dict[str, Any]) -> None:
        detail = find_detail(task_info, item_data)
        code = item_data.get("code") or task_info.get("code") or "-"
        # Inject source_task_ids into item_data for persistence
        item_data_with_task_ids = {**item_data, "source_task_ids": [task.id]}
        try:
            movie_id = _persist_crawled_item(db, item_data_with_task_ids)
            if detail:
                detail.status = "saved"
                detail.item_data = item_data
                detail.error = None
                detail.crawled_at = datetime.now()
                detail.saved_at = datetime.now()
            progress["saved"] += 1
            append_run_log_for_run(db, run, f"入库成功: {code}", "INFO", code=code, movie_id=str(movie_id))
        except Exception as exc:
            if detail:
                detail.status = "save_failed"
                detail.item_data = item_data
                detail.error = str(exc)[:500]
                detail.crawled_at = datetime.now()
                detail.saved_at = None
            progress["save_failed"] += 1
            append_run_log_for_run(db, run, f"入库失败: {code}: {exc}", "ERROR", code=code)
        runtime.write_progress(str(run.id), progress)
        db.commit()
        if detail:
            publish_run_detail_updated(db, run, [detail])

    def on_detail_failed(task_info: dict[str, Any], error: str) -> None:
        detail = find_detail(task_info)
        if detail:
            detail.status = "crawl_failed"
            detail.error = error[:500]
            detail.crawled_at = datetime.now()
        progress["failed"] += 1
        runtime.write_progress(str(run.id), progress)
        db.commit()
        if detail:
            publish_run_detail_updated(db, run, [detail])
        append_run_log_for_run(db, run, f"爬取失败: {task_info.get('code') or task_info.get('url')}: {error}", "ERROR")

    def on_item_already_exists(task_info: dict[str, Any]) -> None:
        detail = find_detail(task_info)
        code = task_info.get("code")
        was_skipped = detail is not None and detail.status == "skipped"
        if detail:
            detail.status = "skipped"
            detail.error = "already_exists"
            detail.crawled_at = detail.crawled_at or datetime.now()
            detail.saved_at = None
        add_source_task_id_for_code(db, code, task.id)
        if not was_skipped:
            progress["skipped"] += 1
        runtime.write_progress(str(run.id), progress)
        db.commit()
        if detail:
            publish_run_detail_updated(db, run, [detail])
        append_run_log_for_run(db, run, f"跳过已存在影片并追加任务ID: {code}", "INFO", code=code)

    def log_callback(message: str, level: str = "INFO") -> None:
        append_run_log_for_run(db, run, message, level)

    def db_check_callback(codes: list[str]) -> set[str]:
        existing_codes = find_existing_movie_codes(db, codes)
        if existing_codes:
            append_run_log_for_run(db, run, f"列表阶段发现已存在影片 {len(existing_codes)} 条", "INFO")
        return existing_codes

    def on_detail_check_callback(code: str) -> bool:
        exists = movie_code_exists(db, code)
        if exists:
            append_run_log_for_run(db, run, f"详情阶段跳过已存在影片: {code}", "INFO", code=code)
        return exists

    def detail_row_to_task_info(detail: CrawlRunDetailTask) -> dict[str, Any]:
        return {
            "code": detail.code,
            "url": detail.source_url,
            "name": detail.source_name,
        }

    # Preload existing detail tasks for in-place restart
    existing_details = (
        db.query(CrawlRunDetailTask)
        .filter(CrawlRunDetailTask.run_id == run.id)
        .order_by(CrawlRunDetailTask.created_at.asc())
        .all()
    )
    for detail in existing_details:
        remember_detail(detail)

    # Execute crawl
    try:
        from scraper.services.movie_service import MovieService
        movie_service = MovieService()

        detail_phase_restart = has_detail_phase_started(db, run)
        restartable_existing_details = [
            detail for detail in existing_details
            if detail.status in RESTARTABLE_DETAIL_STATUSES
        ]
        if detail_phase_restart and restartable_existing_details:
            append_run_log_for_run(
                db,
                run,
                f"检测到已有详情子任务 {len(restartable_existing_details)} 条，跳过列表收集直接重试详情",
                "INFO",
            )
            result = movie_service.crawl_javdb_detail_tasks(
                task,
                detail_tasks=[detail_row_to_task_info(detail) for detail in restartable_existing_details],
                task_id=str(run.task_id) if run.task_id else None,
                on_item_saved=on_item_saved,
                on_detail_failed=on_detail_failed,
                on_item_already_exists=on_item_already_exists,
                log_callback=log_callback,
                on_detail_check_callback=on_detail_check_callback,
                stop_check=lambda: runtime.is_stop_requested(str(run.id)),
            )
        else:
            result = movie_service.crawl_javdb_task(
                task,
                task_id=str(run.task_id) if run.task_id else None,
                crawl_mode=run.crawl_mode,
                on_tasks_batch_created=on_tasks_batch_created,
                on_item_saved=on_item_saved,
                on_detail_failed=on_detail_failed,
                on_item_already_exists=on_item_already_exists,
                log_callback=log_callback,
                db_check_callback=db_check_callback,
                on_detail_check_callback=on_detail_check_callback,
                stop_check=lambda: runtime.is_stop_requested(str(run.id)),
            )

        stopped = runtime.is_stop_requested(str(run.id)) or bool((result or {}).get("stopped"))
        if stopped:
            reset_details = reset_unfinished_detail_tasks_to_pending(db, run)
            if reset_details:
                publish_run_detail_updated(db, run, reset_details)

        total_count = _count_run_detail_tasks(db, run.id)
        saved_count = _count_run_detail_tasks(db, run.id, "saved")
        save_failed_count = _count_run_detail_tasks(db, run.id, "save_failed")
        crawl_failed_count = _count_run_detail_tasks(db, run.id, "crawl_failed")
        skipped_count = _count_run_detail_tasks(db, run.id, "skipped")
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
                from scraper.database.repositories.filter_repository import sync_movie_filters

                sync_result = sync_movie_filters(db)
                append_run_log_for_run(
                    db, run,
                    f"筛选列表已同步: 演员={sync_result['actors']}, 标签={sync_result['tags']}, "
                    f"导演={sync_result['directors']}, 片商={sync_result['makers']}, 系列={sync_result['series']}",
                    "INFO",
                )
            except Exception as sync_exc:
                logger.warning("Failed to sync movie filters for run %s: %s", run.id, sync_exc)
                append_run_log_for_run(db, run, f"筛选列表同步失败: {sync_exc}", "WARNING")
    except ImportError:
        logger.warning("MovieService not available, marking run as completed with stub")
        append_run_log_for_run(db, run, "MovieService 不可用，使用空结果完成运行", "WARNING")
        run.result = {"total_tasks": 0, "completed_tasks": 0, "failed_tasks": 0}
        run.status = "completed"
    except Exception as exc:
        raise

    run.finished_at = datetime.now()
    db.commit()
    publish_run_updated(db, run)
