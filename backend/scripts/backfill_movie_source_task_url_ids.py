from __future__ import annotations

import argparse
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTaskUrl
from shared.database.models.content import Movie
from shared.database.session import get_session_factory


@dataclass
class BackfillResult:
    movies_to_update: int = 0
    movies_updated: int = 0
    links_to_add: int = 0
    links_added: int = 0
    skipped_unmatched: int = 0
    skipped_examples: list[dict] = field(default_factory=list)


def _merge(existing, value):
    current = list(existing or [])
    if str(value) in {str(item) for item in current}:
        return current, False
    return [*current, value], True


def _find_task_url(db: Session, task_id, task_url: str | None):
    if task_id is None or not task_url:
        return None
    return db.scalar(
        select(CrawlTaskUrl).where(
            CrawlTaskUrl.task_id == task_id,
            CrawlTaskUrl.url == task_url,
        )
    )


def backfill_movie_source_task_url_ids(db: Session, *, dry_run: bool = False) -> BackfillResult:
    result = BackfillResult()
    rows = db.execute(
        select(CrawlRunDetailTask, CrawlRun.task_id)
        .join(CrawlRun, CrawlRun.id == CrawlRunDetailTask.run_id)
        .where(
            CrawlRunDetailTask.movie_id.is_not(None),
            CrawlRunDetailTask.task_url.is_not(None),
            CrawlRun.task_id.is_not(None),
        )
    ).all()
    pending_by_movie: dict = {}
    for detail, task_id in rows:
        task_url = _find_task_url(db, task_id, detail.task_url)
        if task_url is None:
            result.skipped_unmatched += 1
            if len(result.skipped_examples) < 5:
                result.skipped_examples.append({
                    "movie_id": str(detail.movie_id),
                    "task_id": str(task_id),
                    "task_url": detail.task_url,
                })
            continue
        movie = db.get(Movie, detail.movie_id)
        if movie is None:
            continue
        pending = pending_by_movie.setdefault(movie.id, {"movie": movie, "task_url_ids": []})
        if str(task_url.id) not in {str(value) for value in [*(movie.source_task_url_ids or []), *pending["task_url_ids"]]}:
            pending["task_url_ids"].append(task_url.id)
            result.links_to_add += 1

    result.movies_to_update = len(pending_by_movie)
    if dry_run:
        return result

    for pending in pending_by_movie.values():
        movie = pending["movie"]
        changed = False
        for task_url_id in pending["task_url_ids"]:
            merged, added = _merge(movie.source_task_url_ids, task_url_id)
            if added:
                movie.source_task_url_ids = merged
                result.links_added += 1
                changed = True
        if changed:
            result.movies_updated += 1
    if result.movies_updated:
        db.commit()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    db = get_session_factory()()
    try:
        result = backfill_movie_source_task_url_ids(db, dry_run=args.dry_run)
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
