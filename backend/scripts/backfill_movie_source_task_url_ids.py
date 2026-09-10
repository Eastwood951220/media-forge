from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, noload

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTaskUrl
from shared.database.models.content import Movie
from shared.database.session import get_session_factory
from shared.runtime_config import load_runtime_config


@dataclass
class BackfillResult:
    movies_to_update: int = 0
    movies_updated: int = 0
    links_to_add: int = 0
    links_added: int = 0
    skipped_unmatched: int = 0
    skipped_missing_task_urls: int = 0
    skipped_examples: list[dict] = field(default_factory=list)


def _merge(existing, value):
    current = list(existing or [])
    if str(value) in {str(item) for item in current}:
        return current, False
    return [*current, value], True


def _find_task_url_for_detail(
    task_urls_by_task: dict[str, list[CrawlTaskUrl]],
    task_id,
    detail: CrawlRunDetailTask,
):
    if task_id is None:
        return None
    urls = [value for value in (detail.task_url, detail.task_final_url) if value]
    if not urls:
        return None
    for task_url in task_urls_by_task.get(str(task_id), []):
        if task_url.url in urls or task_url.final_url in urls:
            return task_url
    return None


def _report_row(
    reporter: Callable[[str], None] | None,
    *,
    status: str,
    ok: bool,
    detail: CrawlRunDetailTask,
    task_id,
    task_url: CrawlTaskUrl | None = None,
    movie: Movie | None = None,
) -> None:
    if reporter is None:
        return
    reporter(
        (
            "status={status} ok={ok} detail_id={detail_id} movie_id={movie_id} code={code} "
            "task_id={task_id} task_url_id={task_url_id} task_url={task_url} task_final_url={task_final_url}"
        ).format(
            status=status,
            ok=str(ok).lower(),
            detail_id=detail.id,
            movie_id=movie.id if movie is not None else detail.movie_id,
            code=(movie.code if movie is not None else detail.code) or "-",
            task_id=task_id,
            task_url_id=task_url.id if task_url is not None else "-",
            task_url=detail.task_url or "-",
            task_final_url=detail.task_final_url or "-",
        )
    )


def _report_source_task_row(
    reporter: Callable[[str], None] | None,
    *,
    status: str,
    ok: bool,
    movie: Movie,
    task_id,
    task_urls: list[CrawlTaskUrl],
) -> None:
    if reporter is None:
        return
    reporter(
        (
            "status={status} ok={ok} movie_id={movie_id} code={code} task_id={task_id} "
            "task_url_count={task_url_count} task_url_ids={task_url_ids}"
        ).format(
            status=status,
            ok=str(ok).lower(),
            movie_id=movie.id,
            code=movie.code or "-",
            task_id=task_id,
            task_url_count=len(task_urls),
            task_url_ids=",".join(str(task_url.id) for task_url in task_urls) or "-",
        )
    )


def _current_and_pending_task_url_ids(movie: Movie, pending_task_url_ids_by_movie: dict) -> set[str]:
    current_task_url_ids = {str(value) for value in (movie.source_task_url_ids or [])}
    pending_task_url_ids = pending_task_url_ids_by_movie.setdefault(movie.id, set())
    return current_task_url_ids | pending_task_url_ids


def _normalize_uuid(value):
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _track_or_write_link(
    movie: Movie,
    task_url: CrawlTaskUrl,
    *,
    dry_run: bool,
    changed_movie_ids: set,
    pending_task_url_ids_by_movie: dict,
    result: BackfillResult,
) -> bool:
    pending_task_url_ids = pending_task_url_ids_by_movie.setdefault(movie.id, set())
    if str(task_url.id) in _current_and_pending_task_url_ids(movie, pending_task_url_ids_by_movie):
        return False
    pending_task_url_ids.add(str(task_url.id))
    changed_movie_ids.add(movie.id)
    result.links_to_add += 1
    if not dry_run:
        merged, _ = _merge(movie.source_task_url_ids, task_url.id)
        movie.source_task_url_ids = merged
        result.links_added += 1
    return True


def backfill_movie_source_task_url_ids(
    db: Session,
    *,
    dry_run: bool = False,
    reporter: Callable[[str], None] | None = None,
) -> BackfillResult:
    result = BackfillResult()
    rows = db.execute(
        select(CrawlRunDetailTask, CrawlRun.task_id)
        .join(CrawlRun, CrawlRun.id == CrawlRunDetailTask.run_id)
        .where(
            CrawlRunDetailTask.movie_id.is_not(None),
            CrawlRun.task_id.is_not(None),
        )
    ).all()
    fallback_movies = list(db.scalars(select(Movie).options(noload(Movie.magnets))).all())
    movies_by_id = {str(movie.id): movie for movie in fallback_movies}
    task_ids = {
        _normalize_uuid(task_id)
        for _, task_id in rows
    } | {
        _normalize_uuid(task_id)
        for movie in fallback_movies
        for task_id in (movie.source_task_ids or [])
    }
    task_urls_by_task: dict[str, list[CrawlTaskUrl]] = {str(task_id): [] for task_id in task_ids}
    if task_ids:
        task_urls = db.scalars(
            select(CrawlTaskUrl)
            .where(CrawlTaskUrl.task_id.in_(task_ids))
            .order_by(CrawlTaskUrl.task_id, CrawlTaskUrl.position, CrawlTaskUrl.id)
        ).all()
        for task_url in task_urls:
            task_urls_by_task.setdefault(str(task_url.task_id), []).append(task_url)

    changed_movie_ids = set()
    pending_task_url_ids_by_movie: dict = {}
    for detail, task_id in rows:
        task_url = _find_task_url_for_detail(task_urls_by_task, task_id, detail)
        if task_url is None:
            result.skipped_unmatched += 1
            if len(result.skipped_examples) < 5:
                result.skipped_examples.append({
                    "movie_id": str(detail.movie_id),
                    "task_id": str(task_id),
                    "task_url": detail.task_url,
                    "task_final_url": detail.task_final_url,
                })
            _report_row(
                reporter,
                status="unmatched_task_url",
                ok=False,
                detail=detail,
                task_id=task_id,
            )
            continue
        movie = movies_by_id.get(str(detail.movie_id))
        if movie is None:
            _report_row(
                reporter,
                status="missing_movie",
                ok=False,
                detail=detail,
                task_id=task_id,
                task_url=task_url,
            )
            continue
        if _track_or_write_link(
            movie,
            task_url,
            dry_run=dry_run,
            changed_movie_ids=changed_movie_ids,
            pending_task_url_ids_by_movie=pending_task_url_ids_by_movie,
            result=result,
        ):
            if dry_run:
                _report_row(
                    reporter,
                    status="dry_run_would_add",
                    ok=True,
                    detail=detail,
                    task_id=task_id,
                    task_url=task_url,
                    movie=movie,
                )
            else:
                _report_row(
                    reporter,
                    status="added",
                    ok=True,
                    detail=detail,
                    task_id=task_id,
                    task_url=task_url,
                    movie=movie,
                )
        else:
            _report_row(
                reporter,
                status="already_linked",
                ok=True,
                detail=detail,
                task_id=task_id,
                task_url=task_url,
                movie=movie,
            )

    for movie in fallback_movies:
        for task_id in movie.source_task_ids or []:
            task_urls = task_urls_by_task.get(str(task_id), [])
            linked_ids = _current_and_pending_task_url_ids(movie, pending_task_url_ids_by_movie)
            if not task_urls:
                result.skipped_missing_task_urls += 1
                _report_source_task_row(
                    reporter,
                    status="missing_task_urls",
                    ok=False,
                    movie=movie,
                    task_id=task_id,
                    task_urls=[],
                )
                continue
            if all(str(task_url.id) in linked_ids for task_url in task_urls):
                _report_source_task_row(
                    reporter,
                    status="already_linked_from_source_task",
                    ok=True,
                    movie=movie,
                    task_id=task_id,
                    task_urls=task_urls,
                )
                continue
            added_urls = []
            for task_url in task_urls:
                if _track_or_write_link(
                    movie,
                    task_url,
                    dry_run=dry_run,
                    changed_movie_ids=changed_movie_ids,
                    pending_task_url_ids_by_movie=pending_task_url_ids_by_movie,
                    result=result,
                ):
                    added_urls.append(task_url)
            if added_urls:
                _report_source_task_row(
                    reporter,
                    status="dry_run_would_add_from_source_task" if dry_run else "added_from_source_task",
                    ok=True,
                    movie=movie,
                    task_id=task_id,
                    task_urls=added_urls,
                )

    result.movies_to_update = len(changed_movie_ids)
    if dry_run:
        return result

    result.movies_updated = len(changed_movie_ids)
    if result.movies_updated:
        db.commit()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="只输出最终汇总，不逐条输出运行记录")
    parser.add_argument("--verbose", action="store_true", help="兼容参数：默认已经逐条输出运行记录")
    args = parser.parse_args()
    load_runtime_config(override=True)
    db = get_session_factory()()
    try:
        result = backfill_movie_source_task_url_ids(db, dry_run=args.dry_run, reporter=None if args.quiet else print)
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
