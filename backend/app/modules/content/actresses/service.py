from __future__ import annotations

import logging
import uuid
from datetime import datetime
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.modules.content.actresses.avjoho_parser import AvjohoProfilePayload, parse_avjoho_profile
from backend.app.modules.content.actresses.serializers import serialize_actress_profile
from scraper.core.security import detect_access_state
from scraper.fetchers.site_fetcher import build_site_fetcher
from scraper.spiders.javdb.javdb_parser import parse_actor_section_metadata
from shared.database.models.content import ActressProfile

logger = logging.getLogger(__name__)


def _dedupe_text(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _actor_urls_for_task(task: CrawlTask) -> list[CrawlTaskUrl]:
    return [url for url in task.urls if url.url_type == "actors" and url.source == "javdb"]


def _fetch_javdb_actor_metadata(url: str) -> dict[str, list[str]]:
    fetcher = build_site_fetcher("javdb")
    page = fetcher.get(url)
    access_state = detect_access_state(page)
    if not access_state.ok:
        raise HTTPException(status_code=429, detail=access_state.message)
    return parse_actor_section_metadata(page)


def _build_avjoho_candidates(names: list[str]) -> list[str]:
    return [f"https://db.avjoho.com/{quote(name)}/" for name in _dedupe_text(names)]


def _validate_avjoho_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != "db.avjoho.com":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="avjoho_url 必须是 db.avjoho.com 的 HTTP(S) URL")
    return url


def _page_to_html(page) -> str:
    if hasattr(page, "html"):
        html = page.html
        return html() if callable(html) else str(html)
    if hasattr(page, "text"):
        text = page.text
        return text() if callable(text) else str(text)
    return str(page)


def _fetch_avjoho_profile(url: str) -> AvjohoProfilePayload | None:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="ignore")
    return parse_avjoho_profile(html, url)


def _profile_matches_names(payload: AvjohoProfilePayload, names: list[str]) -> bool:
    haystack = {payload.display_name, *payload.aliases}
    return bool({name for name in names if name}.intersection(haystack))


def _find_existing_profile(db: Session, payload: AvjohoProfilePayload, canonical_names: list[str]) -> ActressProfile | None:
    profile = db.scalar(select(ActressProfile).where(ActressProfile.source_url == payload.source_url))
    if profile is not None:
        return profile
    canonical_set = {str(value) for value in canonical_names}
    for candidate in db.scalars(select(ActressProfile)):
        if canonical_set.intersection(str(value) for value in (candidate.canonical_names or [])):
            return candidate
    return None


def _merge_values(existing, incoming) -> list:
    return _dedupe_text([*(existing or []), *(incoming or [])])


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


def _upsert_profile(
    db: Session,
    payload: AvjohoProfilePayload,
    *,
    canonical_names: list[str],
    task_id: uuid.UUID,
    task_url_id: uuid.UUID,
) -> ActressProfile:
    profile = _find_existing_profile(db, payload, canonical_names)
    now = datetime.now()
    if profile is None:
        profile = ActressProfile(source_url=payload.source_url)
        db.add(profile)

    profile.display_name = payload.display_name
    profile.reading = payload.reading
    profile.aliases = _merge_values(profile.aliases, payload.aliases)
    profile.canonical_names = _merge_values(profile.canonical_names, canonical_names)
    profile.source_site = "avjoho"
    profile.source_task_ids = _merge_uuid_values(profile.source_task_ids, [task_id])
    profile.source_task_url_ids = _merge_uuid_values(profile.source_task_url_ids, [task_url_id])
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


def fetch_actresses_from_task(db: Session, task_id: uuid.UUID, avjoho_url: str | None = None) -> dict:
    task = db.get(CrawlTask, task_id, options=[selectinload(CrawlTask.urls)])
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    actor_urls = _actor_urls_for_task(task)
    if not actor_urls:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前仅支持 URL 类型为演员的任务")

    profiles: list[ActressProfile] = []
    candidates: list[str] = []
    for task_url in actor_urls:
        metadata = _fetch_javdb_actor_metadata(task_url.final_url or task_url.url)
        names = _dedupe_text([*metadata.get("primary_names", []), *metadata.get("aliases", []), task_url.url_name, task.name])
        url_candidates = [_validate_avjoho_url(avjoho_url)] if avjoho_url else _build_avjoho_candidates(names)
        candidates.extend(url_candidates)
        for candidate_url in url_candidates:
            try:
                payload = _fetch_avjoho_profile(candidate_url)
            except HTTPException:
                raise
            except Exception:
                logger.info("avjoho profile candidate failed: %s", candidate_url, exc_info=True)
                continue
            if payload is None:
                continue
            if avjoho_url is None and not _profile_matches_names(payload, names):
                continue
            profile = _upsert_profile(
                db,
                payload,
                canonical_names=_dedupe_text([*names, payload.display_name, *payload.aliases]),
                task_id=task.id,
                task_url_id=task_url.id,
            )
            profiles.append(profile)
            break

    if profiles:
        db.commit()
    return {
        "matched": bool(profiles),
        "profiles": [serialize_actress_profile(profile) for profile in profiles],
        "candidates": _dedupe_text(candidates),
        "message": "已获取女优资料" if profiles else "未匹配到 avjoho 资料，可填写 avjoho URL 手动获取",
    }
