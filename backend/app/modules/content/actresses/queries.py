from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.crawl_task import CrawlTaskUrl
from shared.database.models.content import ActressProfile, Movie


VALID_PAGE_SIZES = {8, 16, 24, 40}
HEIGHT_RANGES = {
    "149_under": (None, 149),
    "150_153": (150, 153),
    "154_157": (154, 157),
    "158_161": (158, 161),
    "162_165": (162, 165),
    "166_169": (166, 169),
    "170_over": (170, None),
}
BUST_RANGES = {
    "79_under": (None, 79),
    "80_84": (80, 84),
    "85_89": (85, 89),
    "90_94": (90, 94),
    "95_99": (95, 99),
    "100_over": (100, None),
}
WAIST_RANGES = {
    "55_under": (None, 55),
    "56_59": (56, 59),
    "60_63": (60, 63),
    "64_67": (64, 67),
    "68_69": (68, 69),
    "70_over": (70, None),
}
HIP_RANGES = {
    "80_under": (None, 80),
    "81_84": (81, 84),
    "85_88": (85, 88),
    "89_92": (89, 92),
    "93_95": (93, 95),
    "96_over": (96, None),
}
AGE_RANGES = {
    "20_under": (None, 29),
    "30s": (30, 39),
    "40s": (40, 49),
    "50s": (50, 59),
    "60s": (60, 69),
    "70s": (70, 79),
    "80s": (80, 89),
}


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


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _age_from_birth_date(birth_date: date | None, *, today: date | None = None) -> int | None:
    if birth_date is None:
        return None
    current = today or date.today()
    age = current.year - birth_date.year
    if (current.month, current.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def _matches_number_range(value: int | None, ranges: dict[str, tuple[int | None, int | None]], key: str | None) -> bool:
    if not key:
        return True
    if value is None or key not in ranges:
        return False
    minimum, maximum = ranges[key]
    if minimum is not None and value < minimum:
        return False
    if maximum is not None and value > maximum:
        return False
    return True


def list_actress_profiles(
    db: Session,
    *,
    page: int,
    limit: int,
    keyword: str | None = None,
    source_task_id: uuid.UUID | None = None,
    cup: str | None = None,
    height_range: str | None = None,
    age_range: str | None = None,
    bust_range: str | None = None,
    waist_range: str | None = None,
    hip_range: str | None = None,
    tags: str | None = None,
) -> tuple[list[ActressProfile], int]:
    rows = list(db.scalars(select(ActressProfile).order_by(ActressProfile.created_at.desc(), ActressProfile.display_name.asc())))
    if keyword:
        rows = [row for row in rows if _matches_keyword(row, keyword)]
    if source_task_id is not None:
        rows = [row for row in rows if _contains_uuid(row.source_task_ids, source_task_id)]
    if cup:
        expected_cup = cup.strip().lower()
        rows = [row for row in rows if (row.cup or "").strip().lower() == expected_cup]
    expected_tags = set(_split_csv(tags))
    if expected_tags:
        rows = [row for row in rows if expected_tags.issubset(set(row.tags or []))]
    rows = [row for row in rows if _matches_number_range(row.height_cm, HEIGHT_RANGES, height_range)]
    rows = [row for row in rows if _matches_number_range(_age_from_birth_date(row.birth_date), AGE_RANGES, age_range)]
    rows = [row for row in rows if _matches_number_range(row.bust_cm, BUST_RANGES, bust_range)]
    rows = [row for row in rows if _matches_number_range(row.waist_cm, WAIST_RANGES, waist_range)]
    rows = [row for row in rows if _matches_number_range(row.hip_cm, HIP_RANGES, hip_range)]
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
