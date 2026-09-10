from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.runtime.events import append_run_log_for_run, publish_run_detail_updated
from backend.app.modules.crawler.runtime.service import get_runtime_state
from backend.app.modules.crawler.runtime.worker import ensure_crawler_worker_started
from backend.app.modules.content.movies.magnet_persistence import upsert_magnets
from shared.database.models.content import Movie

MAGNET_REFRESH_TASK_NAME = "磁力更新"


def _ensure_display_task(db: Session, owner_id: uuid.UUID) -> CrawlTask:
    task = db.scalar(
        select(CrawlTask).where(
            CrawlTask.owner_id == owner_id,
            CrawlTask.name == MAGNET_REFRESH_TASK_NAME,
        )
    )
    if task is not None:
        return task
    task = CrawlTask(
        name=MAGNET_REFRESH_TASK_NAME,
        storage_location="",
        owner_id=owner_id,
        is_skip=True,
        status="idle",
    )
    db.add(task)
    db.flush()
    return task


def _movie_belongs_to_user(movie: Movie, owner_task_ids: set[uuid.UUID]) -> bool:
    owner_task_id_strs = {str(task_id) for task_id in owner_task_ids}
    return any(str(task_id) in owner_task_id_strs for task_id in (movie.source_task_ids or []))


def _owner_task_ids(db: Session, owner_id: uuid.UUID) -> set[uuid.UUID]:
    return set(db.scalars(select(CrawlTask.id).where(CrawlTask.owner_id == owner_id)).all())


def create_magnet_refresh_run(db: Session, owner_id: uuid.UUID, movie_ids: list[uuid.UUID]) -> CrawlRun:
    if not movie_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="movie_ids 不能为空")
    owner_task_ids = _owner_task_ids(db, owner_id)
    movies = db.scalars(select(Movie).where(Movie.id.in_(movie_ids))).all()
    valid_movies = [movie for movie in movies if _movie_belongs_to_user(movie, owner_task_ids)]
    if not valid_movies:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可更新的电影")

    display_task = _ensure_display_task(db, owner_id)
    run = CrawlRun(
        task_id=display_task.id,
        task_name=display_task.name,
        status="queued",
        crawl_mode="magnet_refresh",
        queued_at=datetime.now(),
        result={"movie_ids": [str(movie.id) for movie in valid_movies], "magnet_refresh": True},
    )
    db.add(run)
    db.flush()
    for movie in valid_movies:
        has_source_url = bool(str(movie.source_url or "").strip())
        db.add(CrawlRunDetailTask(
            run_id=run.id,
            task_name=display_task.name,
            code=movie.code,
            source_url=movie.source_url or "",
            source_name=movie.source_name or "",
            source_url_name=MAGNET_REFRESH_TASK_NAME,
            task_url=movie.source_url or "",
            task_final_url=movie.source_url or "",
            task_url_type="magnet_refresh",
            status="pending_crawl" if has_source_url else "skipped",
            error=None if has_source_url else "missing_source_url",
            item_data={"movie_id": str(movie.id), "magnet_refresh": True},
            created_at=datetime.now(),
        ))
    db.commit()
    db.refresh(run)

    runtime = get_runtime_state()
    runtime.enqueue_run(str(run.id))
    ensure_crawler_worker_started(runtime)
    return run


from scraper.fetchers.site_fetcher import build_site_fetcher
from scraper.magnets.provider import MovieDetailPayload, MovieDetailRequest, get_magnet_provider
from scraper.tasks.task_utils import determine_source

SUPPORTED_MAGNET_SOURCES = {"javdb", "javbus"}


def normalize_magnet_source(source: str | None) -> str:
    value = str(source or "").strip()
    return value if value in SUPPORTED_MAGNET_SOURCES else "javdb"


def build_magnet_provider(source: str):
    normalized = normalize_magnet_source(source)
    return get_magnet_provider(normalized, fetcher=build_site_fetcher(normalized))


def _movie_detail_request(movie: Movie, detail: CrawlRunDetailTask) -> MovieDetailRequest:
    source_url = movie.source_url or detail.source_url or ""
    source = normalize_magnet_source(determine_source(source_url))
    return MovieDetailRequest(
        source=source,
        url=source_url,
        code=movie.code or detail.code or "",
        name=movie.source_name or detail.source_name or movie.code or detail.code or source_url,
        task_url=detail.task_url or "",
        task_final_url=detail.task_final_url or "",
        task_url_type=detail.task_url_type or "",
        task_url_name=detail.source_url_name or "",
        extra={
            "detail_task_id": str(detail.id),
            "movie_id": str(movie.id),
        },
    )


def execute_magnet_refresh_run(db: Session, run: CrawlRun, runtime) -> dict:
    saved = 0
    skipped = 0
    failed = 0
    details = (
        db.query(CrawlRunDetailTask)
        .filter(CrawlRunDetailTask.run_id == run.id, CrawlRunDetailTask.status == "pending_crawl")
        .order_by(CrawlRunDetailTask.created_at.asc())
        .all()
    )
    append_run_log_for_run(db, run, f"磁力更新开始: {len(details)} 条", "INFO")
    for detail in details:
        if runtime.is_stop_requested(str(run.id)):
            break
        try:
            movie_id = uuid.UUID(str((detail.item_data or {}).get("movie_id")))
            movie = db.get(Movie, movie_id)
            if movie is None:
                detail.status = "skipped"
                detail.error = "movie_not_found"
                skipped += 1
                continue
            request = _movie_detail_request(movie, detail)
            provider = build_magnet_provider(request.source)
            payload = provider.fetch_detail_with_magnets(
                request,
                task_name=run.task_name,
                on_detail_completed=lambda task: None,
                on_detail_failed=lambda task, err: None,
                stop_check=lambda: runtime.is_stop_requested(str(run.id)),
                log_callback=lambda msg, level="INFO": None,
                on_detail_check_callback=lambda code: False,
                on_item_already_exists=lambda task_info: None,
            )
            if payload.status != "completed":
                detail.status = "crawl_failed"
                detail.error = str(payload.reason or "detail fetch failed")[:500]
                failed += 1
                continue
            detail_data = payload.data
            magnets = list(detail_data.get("magnets") or [])
            if not magnets:
                detail.status = "skipped"
                detail.error = "no_magnets_found"
                skipped += 1
                append_run_log_for_run(db, run, f"磁力更新跳过: {detail.code} 无磁力", "WARNING", source_url=detail.source_url)
                continue
            upsert_magnets(db, movie.id, {"code": movie.code}, magnets)
            detail.status = "saved"
            detail.item_data = {**(detail.item_data or {}), "updated_magnets": len(magnets)}
            detail.crawled_at = datetime.now()
            detail.saved_at = datetime.now()
            detail.error = None
            saved += 1
            append_run_log_for_run(db, run, f"磁力更新成功: {movie.code} magnets={len(magnets)}", "INFO", code=movie.code, movie_id=str(movie.id))
        except Exception as exc:
            detail.status = "save_failed"
            detail.error = str(exc)[:500]
            failed += 1
            append_run_log_for_run(db, run, f"磁力更新失败: {detail.code}: {exc}", "ERROR", code=detail.code)
        finally:
            db.commit()
            publish_run_detail_updated(db, run, [detail])
    return {
        "total_tasks": saved + skipped + failed,
        "completed_tasks": saved,
        "failed_tasks": failed,
        "skipped_tasks": skipped,
        "saved": saved,
        "failed": failed,
        "skipped": skipped,
    }
