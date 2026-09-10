from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable


def dedupe_text(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


@dataclass(slots=True)
class ActorMetadata:
    primary_names: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    source_url: str = ""
    source_site: str = ""


@dataclass(slots=True)
class ActressProfilePayload:
    display_name: str
    reading: str
    source_url: str
    image_url: str = ""
    aliases: list[str] = field(default_factory=list)
    debut_date: date | None = None
    birth_date: date | None = None
    height_cm: int | None = None
    bust_cm: int | None = None
    waist_cm: int | None = None
    hip_cm: int | None = None
    cup: str = ""
    birthplace: str = ""
    blood_type: str = ""
    hobbies: str = ""
    biography: str = ""
    exclusive_maker: str = ""
    sns_links: list[dict] = field(default_factory=list)
    representative_works: list[dict] = field(default_factory=list)
    similar_actresses: list[dict] = field(default_factory=list)
    raw_profile: dict = field(default_factory=dict)


@dataclass(slots=True)
class ActressProfileMatch:
    profile: ActressProfilePayload | None
    attempted_urls: list[str] = field(default_factory=list)
    candidate_names: list[str] = field(default_factory=list)
    matched_url: str = ""
