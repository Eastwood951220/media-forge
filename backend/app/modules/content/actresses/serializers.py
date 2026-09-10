from __future__ import annotations

from backend.app.models.crawl_task import CrawlTaskUrl
from shared.database.models.content import ActressProfile, Movie


SOURCE_LABELS = {
    "javdb": "JavDB",
    "javbus": "JavBus",
}


def serialize_recent_movie(movie: Movie) -> dict:
    return {
        "id": str(movie.id),
        "_id": str(movie.id),
        "code": movie.code or "",
        "title": movie.source_name or "",
        "cover": movie.cover or "",
        "release_date": movie.release_date.isoformat() if movie.release_date else None,
    }


def serialize_external_link(task_url: CrawlTaskUrl) -> dict:
    source = task_url.source or ""
    return {
        "id": str(task_url.id),
        "_id": str(task_url.id),
        "task_id": str(task_url.task_id),
        "source": source,
        "label": SOURCE_LABELS.get(source, source),
        "url": task_url.final_url or task_url.url or "",
        "url_type": task_url.url_type or "",
        "url_name": task_url.url_name or "",
    }


def serialize_actress_profile(
    profile: ActressProfile,
    *,
    recent_movies: list[Movie] | None = None,
    external_links: list[CrawlTaskUrl] | None = None,
) -> dict:
    payload = {
        "id": str(profile.id),
        "_id": str(profile.id),
        "display_name": profile.display_name or "",
        "reading": profile.reading or "",
        "aliases": list(profile.aliases or []),
        "canonical_names": list(profile.canonical_names or []),
        "source_url": profile.source_url or "",
        "source_site": profile.source_site or "",
        "source_task_ids": [str(value) for value in (profile.source_task_ids or [])],
        "source_task_url_ids": [str(value) for value in (profile.source_task_url_ids or [])],
        "tags": list(profile.tags or []),
        "image_url": profile.image_url or "",
        "debut_date": profile.debut_date.isoformat() if profile.debut_date else None,
        "birth_date": profile.birth_date.isoformat() if profile.birth_date else None,
        "height_cm": profile.height_cm,
        "bust_cm": profile.bust_cm,
        "waist_cm": profile.waist_cm,
        "hip_cm": profile.hip_cm,
        "cup": profile.cup or "",
        "birthplace": profile.birthplace or "",
        "blood_type": profile.blood_type or "",
        "hobbies": profile.hobbies or "",
        "biography": profile.biography or "",
        "exclusive_maker": profile.exclusive_maker or "",
        "sns_links": list(profile.sns_links or []),
        "representative_works": list(profile.representative_works or []),
        "similar_actresses": list(profile.similar_actresses or []),
        "raw_profile": dict(profile.raw_profile or {}),
        "last_fetched_at": profile.last_fetched_at.isoformat() if profile.last_fetched_at else None,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
    if recent_movies is not None:
        payload["recent_movies"] = [serialize_recent_movie(movie) for movie in recent_movies]
    if external_links is not None:
        payload["external_links"] = [serialize_external_link(link) for link in external_links]
    return payload
