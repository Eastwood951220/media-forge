from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.crawl_task import CrawlTaskUrl
from shared.database.models.content import ActressProfile, Movie


VALID_PAGE_SIZES = {8, 16, 24, 40}


def _contains_uuid(values, expected: uuid.UUID) -> bool:
    expected_text = str(expected)
    return any(str(value) == expected_text for value in (values or []))


def _matches_keyword(profile: ActressProfile, keyword: str) -> bool:
    needle = keyword.lower()
    values = [
        profile.display_name or "",
        profile.reading or "",
        *(profile.aliases or []),
        *(profile.canonical_names or []),
    ]
    return any(needle in value.lower() for value in values)


def list_actress_profiles(
    db: Session,
    *,
    page: int,
    limit: int,
    keyword: str | None = None,
    source_task_id: uuid.UUID | None = None,
) -> tuple[list[ActressProfile], int]:
    rows = list(db.scalars(select(ActressProfile).order_by(ActressProfile.created_at.desc(), ActressProfile.display_name.asc())))
    if keyword:
        rows = [row for row in rows if _matches_keyword(row, keyword)]
    if source_task_id is not None:
        rows = [row for row in rows if _contains_uuid(row.source_task_ids, source_task_id)]
    total = len(rows)
    offset = (page - 1) * limit
    return rows[offset:offset + limit], total


def recent_movies_for_profile(db: Session, profile: ActressProfile, *, limit: int = 10) -> list[Movie]:
    source_task_url_ids = {str(value) for value in (profile.source_task_url_ids or [])}
    if not source_task_url_ids:
        return []
    movies = [
        movie
        for movie in db.scalars(select(Movie)).all()
        if source_task_url_ids.intersection(str(value) for value in (movie.source_task_url_ids or []))
    ]
    return sorted(
        movies,
        key=lambda movie: (movie.release_date is not None, movie.release_date or date.min),
        reverse=True,
    )[:limit]


def external_links_for_profile(db: Session, profile: ActressProfile) -> list[CrawlTaskUrl]:
    source_task_url_ids = [uuid.UUID(str(value)) for value in (profile.source_task_url_ids or []) if value]
    if not source_task_url_ids:
        return []
    return list(db.scalars(
        select(CrawlTaskUrl)
        .where(CrawlTaskUrl.id.in_(source_task_url_ids), CrawlTaskUrl.source.in_(("javdb", "javbus")))
        .order_by(CrawlTaskUrl.position.asc(), CrawlTaskUrl.created_at.asc())
    ))
