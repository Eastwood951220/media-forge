from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.modules.content.actresses.serializers import serialize_actress_profile
from scraper.fetchers.site_fetcher import build_site_fetcher
from scraper.profiles.actress import ActressProfilePayload, dedupe_text
from scraper.spiders.avjoho.avjoho_spider import (
    AvjohoActressSpider,
    ProfileSourceInvalidUrl,
    ProfileSourceNotFound,
)
from scraper.spiders.javdb.actor_profile import fetch_actor_metadata
from shared.database.models.content import ActressProfile

logger = logging.getLogger(__name__)


def _selected_actor_url_for_task(task: CrawlTask, task_url_id: uuid.UUID) -> CrawlTaskUrl:
    task_url = next((url for url in task.urls if url.id == task_url_id), None)
    if task_url is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务 URL 不存在")
    if task_url.url_type != "actors" or task_url.source != "javdb":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前仅支持 URL 类型为演员的 JavDB URL")
    return task_url


def _find_existing_profile(db: Session, payload: ActressProfilePayload, canonical_names: list[str]) -> ActressProfile | None:
    profile = db.scalar(select(ActressProfile).where(ActressProfile.source_url == payload.source_url))
    if profile is not None:
        return profile
    canonical_set = {str(value) for value in canonical_names}
    for candidate in db.scalars(select(ActressProfile)):
        if canonical_set.intersection(str(value) for value in (candidate.canonical_names or [])):
            return candidate
    return None


def _merge_values(existing, incoming) -> list:
    return dedupe_text([*(existing or []), *(incoming or [])])


def _merge_uuid_values(existing, incoming) -> list:
    values: list = []
    seen: set[str] = set()
    for value in [*(existing or []), *(incoming or [])]:
        if value is None:
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        values.append(value)
    return values


def _task_tag_names(task: CrawlTask) -> list[str]:
    return dedupe_text(sorted(tag.name for tag in (task.tags or []) if tag.name))


def _upsert_profile(
    db: Session,
    payload: ActressProfilePayload,
    *,
    canonical_names: list[str],
    task_id: uuid.UUID,
    task_url_id: uuid.UUID,
    tag_names: list[str],
) -> ActressProfile:
    profile = _find_existing_profile(db, payload, canonical_names)
    now = datetime.now()
    existing_profile = profile is not None
    if profile is None:
        profile = ActressProfile(source_url=payload.source_url)
        db.add(profile)

    profile.source_task_ids = _merge_uuid_values(profile.source_task_ids, [task_id])
    profile.source_task_url_ids = _merge_uuid_values(profile.source_task_url_ids, [task_url_id])
    profile.tags = _merge_values(profile.tags, tag_names)
    if existing_profile:
        db.flush()
        return profile

    profile.display_name = payload.display_name
    profile.reading = payload.reading
    profile.aliases = _merge_values(profile.aliases, payload.aliases)
    profile.canonical_names = _merge_values(profile.canonical_names, canonical_names)
    profile.source_site = "avjoho"
    profile.image_url = payload.image_url
    profile.debut_date = payload.debut_date
    profile.birth_date = payload.birth_date
    profile.height_cm = payload.height_cm
    profile.bust_cm = payload.bust_cm
    profile.waist_cm = payload.waist_cm
    profile.hip_cm = payload.hip_cm
    profile.cup = payload.cup
    profile.birthplace = payload.birthplace
    profile.blood_type = payload.blood_type
    profile.hobbies = payload.hobbies
    profile.biography = payload.biography
    profile.exclusive_maker = payload.exclusive_maker
    profile.sns_links = payload.sns_links
    profile.representative_works = payload.representative_works
    profile.similar_actresses = payload.similar_actresses
    profile.raw_profile = payload.raw_profile
    profile.last_fetched_at = now
    db.flush()
    return profile


def update_actress_tags(db: Session, profile_id: uuid.UUID, tags: list[str]) -> ActressProfile:
    profile = db.get(ActressProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="女优资料不存在")
    profile.tags = dedupe_text(tags)
    db.commit()
    db.refresh(profile)
    return profile


def fetch_actresses_from_task(
    db: Session,
    task_id: uuid.UUID,
    task_url_id: uuid.UUID,
    avjoho_url: str | None = None,
) -> dict:
    task = db.get(CrawlTask, task_id, options=[selectinload(CrawlTask.urls), selectinload(CrawlTask.tags)])
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    actor_url = _selected_actor_url_for_task(task, task_url_id)

    javdb_fetcher = build_site_fetcher("javdb")
    avjoho_spider = AvjohoActressSpider(fetcher=build_site_fetcher("avjoho"))

    profiles: list[ActressProfile] = []
    attempted_urls: list[str] = []
    for task_url in [actor_url]:
        try:
            metadata = fetch_actor_metadata(javdb_fetcher, task_url.final_url or task_url.url)
        except RuntimeError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc

        names = dedupe_text([
            *metadata.primary_names,
            *metadata.aliases,
            task_url.url_name,
            task.name,
        ])
        try:
            match = avjoho_spider.find_first_matching_profile(names, manual_url=avjoho_url)
        except ProfileSourceInvalidUrl as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="avjoho_url 必须是 db.avjoho.com 的 HTTP(S) URL",
            ) from exc
        except ProfileSourceNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        attempted_urls.extend(match.attempted_urls)
        if match.profile is None:
            continue

        profile = _upsert_profile(
            db,
            match.profile,
            canonical_names=dedupe_text([*names, match.profile.display_name, *match.profile.aliases]),
            task_id=task.id,
            task_url_id=task_url.id,
            tag_names=_task_tag_names(task),
        )
        profiles.append(profile)

    if profiles:
        db.commit()
    else:
        logger.info(
            "actress profile not matched: task=%s task_url=%s candidates=%s",
            task.id,
            actor_url.id,
            len(attempted_urls),
        )
    return {
        "matched": bool(profiles),
        "profiles": [serialize_actress_profile(profile) for profile in profiles],
        "candidates": dedupe_text(attempted_urls),
        "message": "已获取女优资料" if profiles else "未匹配到 avjoho 资料，可填写 avjoho URL 手动获取",
    }
