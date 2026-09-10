from __future__ import annotations

import re

from scraper.core.security import detect_access_state
from scraper.core.utils import clean_text
from scraper.profiles.actress import ActorMetadata

MOVIE_COUNT_RE = re.compile(r"^\d+\s*部影片$")


def _all_text(node, selector: str) -> list[str]:
    values = node.css(selector).getall()
    return [str(clean_text(value)) for value in values if clean_text(value)]


def _split_comma_names(value: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for part in value.split(","):
        name = clean_text(part)
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def parse_actor_metadata(page, source_url: str = "") -> ActorMetadata:
    primary_names: list[str] = []
    aliases: list[str] = []
    seen_primary: set[str] = set()
    seen_aliases: set[str] = set()

    for raw in _all_text(page, ".actor-section-name::text"):
        for name in _split_comma_names(raw):
            if name not in seen_primary:
                seen_primary.add(name)
                primary_names.append(name)

    for raw in _all_text(page, ".section-title .section-meta::text"):
        if MOVIE_COUNT_RE.match(raw):
            continue
        for name in _split_comma_names(raw):
            if name not in seen_aliases and name not in seen_primary:
                seen_aliases.add(name)
                aliases.append(name)

    return ActorMetadata(
        primary_names=primary_names,
        aliases=aliases,
        source_url=source_url,
        source_site="javdb",
    )


def fetch_actor_metadata(fetcher, url: str) -> ActorMetadata:
    page = fetcher.get(url)
    access_state = detect_access_state(page)
    if not access_state.ok:
        raise RuntimeError(access_state.message)
    return parse_actor_metadata(page, source_url=url)
