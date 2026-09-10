# Actress Scraper Provider Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move actress profile fetch and parse behavior out of backend content services and into scraper provider modules while preserving the existing actress API.

**Architecture:** Add source-neutral actress payload dataclasses under `scraper/profiles`, source-specific JavDB actor metadata and avjoho profile modules under `scraper/spiders`, and slim the backend actress service down to task validation, provider orchestration, and database upsert. Keep all FastAPI errors and SQLAlchemy persistence in backend.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0, Scrapling parser adaptors, Pytest, existing `scraper.fetchers.site_fetcher` and `scraper.fetchers.scrapling_fetcher`.

**Spec:** `docs/superpowers/specs/2026-09-10-scraper-provider-boundaries-design.md`

## Global Constraints

- Do not create or use a Git worktree for this repository; work in the current checkout.
- Stage intended source files explicitly instead of using `git add .` or `git add -A`.
- Create commits grouped by functional change.
- Preserve the public endpoint `/api/content/actresses/fetch-from-task`.
- Preserve the frontend behavior and response structure already implemented for actress list/detail pages.
- Scraper modules must not import `backend.*`.
- Backend modules may import scraper provider modules.
- Keep FastAPI `HTTPException` usage inside backend.
- The migration must not change the actress table schema.

---

## File Structure

- Create `scraper/profiles/__init__.py`: package marker and exports.
- Create `scraper/profiles/actress.py`: `ActorMetadata`, `ActressProfilePayload`, `ActressProfileMatch`, and helper `dedupe_text`.
- Create `scraper/spiders/javdb/actor_profile.py`: JavDB actor metadata parsing/fetching.
- Modify `scraper/spiders/javdb/javdb_parser.py`: keep `parse_actor_section_metadata` as a compatibility wrapper delegating to the new actor parser.
- Create `scraper/spiders/avjoho/__init__.py`: package marker and exports.
- Create `scraper/spiders/avjoho/avjoho_parser.py`: moved avjoho HTML parser.
- Create `scraper/spiders/avjoho/avjoho_spider.py`: candidate URL construction, search parsing, profile fetch, and first-match flow.
- Create `scraper/tests/test_avjoho_spider.py`: parser and spider behavior tests with fake fetchers.
- Modify `backend/app/modules/content/actresses/service.py`: replace private fetching/parsing helpers with scraper provider calls.
- Modify `backend/tests/test_avjoho_parser.py`: import parser from `scraper.spiders.avjoho.avjoho_parser`.
- Modify `backend/tests/test_content_actresses_api.py`: monkeypatch provider methods instead of backend private avjoho functions where practical.

---

### Task 1: Add Source-Neutral Actress Payloads

**Files:**
- Create: `scraper/profiles/__init__.py`
- Create: `scraper/profiles/actress.py`
- Test: `scraper/tests/test_avjoho_spider.py`

**Interfaces:**
- Produces: `dedupe_text(values: Iterable[object]) -> list[str]`.
- Produces: `ActorMetadata(primary_names: list[str], aliases: list[str], source_url: str = "", source_site: str = "")`.
- Produces: `ActressProfilePayload` with the same fields as the current backend `AvjohoProfilePayload`.
- Produces: `ActressProfileMatch(profile: ActressProfilePayload | None, attempted_urls: list[str], candidate_names: list[str], matched_url: str = "")`.

- [ ] **Step 1: Write the failing payload tests**

Create `scraper/tests/test_avjoho_spider.py` with:

```python
from datetime import date

from scraper.profiles.actress import (
    ActorMetadata,
    ActressProfileMatch,
    ActressProfilePayload,
    dedupe_text,
)


def test_dedupe_text_preserves_order_and_drops_empty_values() -> None:
    assert dedupe_text(["七瀬アリス", "", None, "七瀬アリス", "七瀬愛麗絲"]) == [
        "七瀬アリス",
        "七瀬愛麗絲",
    ]


def test_actress_payload_dataclass_keeps_current_profile_fields() -> None:
    payload = ActressProfilePayload(
        display_name="宮上唯依花",
        reading="みやうえゆいか",
        source_url="https://db.avjoho.com/example/",
        aliases=["Miyaue Yuika"],
        debut_date=date(2020, 1, 2),
        birth_date=date(1998, 3, 4),
        height_cm=163,
        bust_cm=90,
        waist_cm=59,
        hip_cm=88,
        cup="E",
        sns_links=[{"label": "X", "url": "https://x.example"}],
    )

    assert payload.display_name == "宮上唯依花"
    assert payload.aliases == ["Miyaue Yuika"]
    assert payload.sns_links == [{"label": "X", "url": "https://x.example"}]


def test_actress_match_defaults_to_no_profile() -> None:
    match = ActressProfileMatch(
        profile=None,
        attempted_urls=["https://db.avjoho.com/missing/"],
        candidate_names=["missing"],
    )

    assert match.profile is None
    assert match.matched_url == ""
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python -m pytest scraper/tests/test_avjoho_spider.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.profiles'`.

- [ ] **Step 3: Implement the payload module**

Create `scraper/profiles/__init__.py`:

```python
from scraper.profiles.actress import ActorMetadata, ActressProfileMatch, ActressProfilePayload, dedupe_text

__all__ = [
    "ActorMetadata",
    "ActressProfileMatch",
    "ActressProfilePayload",
    "dedupe_text",
]
```

Create `scraper/profiles/actress.py`:

```python
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
```

- [ ] **Step 4: Run the test and verify it passes**

Run: `python -m pytest scraper/tests/test_avjoho_spider.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scraper/profiles/__init__.py scraper/profiles/actress.py scraper/tests/test_avjoho_spider.py
git commit -m "Add actress scraper payloads"
```

---

### Task 2: Move JavDB Actor Metadata Behind a Scraper Module

**Files:**
- Create: `scraper/spiders/javdb/actor_profile.py`
- Modify: `scraper/spiders/javdb/javdb_parser.py`
- Modify: `scraper/tests/test_javdb_actor_metadata.py`

**Interfaces:**
- Produces: `parse_actor_metadata(page, source_url: str = "") -> ActorMetadata`.
- Produces: `fetch_actor_metadata(fetcher, url: str) -> ActorMetadata`.
- Preserves: `parse_actor_section_metadata(page) -> dict[str, list[str]]`.

- [ ] **Step 1: Write the failing module-level parser test**

Append to `scraper/tests/test_javdb_actor_metadata.py`:

```python
from scraper.spiders.javdb.actor_profile import parse_actor_metadata


def test_parse_actor_metadata_returns_source_neutral_payload() -> None:
    parsed = parse_actor_metadata(page("""
      <div class="column section-title">
        <h2 class="title is-4 has-text-justified">
          <span class="actor-section-name">蓮實克蕾兒, 蓮実クレア</span>
          <br>
          <span class="section-meta">安達亜美, 新田絢</span>
          <br>
          <span class="section-meta">1928 部影片</span>
        </h2>
      </div>
    """), source_url="https://javdb.com/actors/X301")

    assert parsed.primary_names == ["蓮實克蕾兒", "蓮実クレア"]
    assert parsed.aliases == ["安達亜美", "新田絢"]
    assert parsed.source_url == "https://javdb.com/actors/X301"
    assert parsed.source_site == "javdb"
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python -m pytest scraper/tests/test_javdb_actor_metadata.py -q`

Expected: FAIL with `ModuleNotFoundError` for `scraper.spiders.javdb.actor_profile`.

- [ ] **Step 3: Implement the JavDB actor profile module**

Create `scraper/spiders/javdb/actor_profile.py`:

```python
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
```

- [ ] **Step 4: Preserve the compatibility wrapper**

In `scraper/spiders/javdb/javdb_parser.py`, import the new parser:

```python
from scraper.spiders.javdb.actor_profile import parse_actor_metadata
```

Replace the body of `parse_actor_section_metadata` with:

```python
def parse_actor_section_metadata(page) -> dict[str, list[str]]:
    metadata = parse_actor_metadata(page)
    return {
        "primary_names": metadata.primary_names,
        "aliases": metadata.aliases,
    }
```

Leave `parse_page_section_name` unchanged.

- [ ] **Step 5: Run parser tests**

Run: `python -m pytest scraper/tests/test_javdb_actor_metadata.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scraper/spiders/javdb/actor_profile.py scraper/spiders/javdb/javdb_parser.py scraper/tests/test_javdb_actor_metadata.py
git commit -m "Move JavDB actor metadata parsing"
```

---

### Task 3: Move Avjoho Parser and Add Avjoho Spider

**Files:**
- Create: `scraper/spiders/avjoho/__init__.py`
- Create: `scraper/spiders/avjoho/avjoho_parser.py`
- Create: `scraper/spiders/avjoho/avjoho_spider.py`
- Modify: `scraper/tests/test_avjoho_spider.py`
- Modify: `backend/tests/test_avjoho_parser.py`

**Interfaces:**
- Produces: `parse_avjoho_profile(html: str, source_url: str) -> ActressProfilePayload | None`.
- Produces: `AvjohoActressSpider(fetcher)`.
- Produces: `AvjohoActressSpider.find_first_matching_profile(names: list[str], manual_url: str | None = None) -> ActressProfileMatch`.

- [ ] **Step 1: Move parser import test to scraper**

Modify `backend/tests/test_avjoho_parser.py`:

```python
from scraper.spiders.avjoho.avjoho_parser import parse_avjoho_profile
```

Append to `scraper/tests/test_avjoho_spider.py`:

```python
from scraper.spiders.avjoho.avjoho_spider import AvjohoActressSpider


class FakeResponse:
    def __init__(self, html: str) -> None:
        self._html = html

    @property
    def html(self):
        return self._html


class FakeFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    def get(self, url: str):
        self.requested.append(url)
        if url not in self.pages:
            raise FileNotFoundError(url)
        return FakeResponse(self.pages[url])


def test_avjoho_spider_builds_direct_profile_urls() -> None:
    spider = AvjohoActressSpider(fetcher=FakeFetcher({}))

    assert spider.build_direct_profile_urls(["七瀬アリス"]) == [
        "https://db.avjoho.com/%E4%B8%83%E7%80%AC%E3%82%A2%E3%83%AA%E3%82%B9/"
    ]


def test_avjoho_spider_matches_manual_profile_url() -> None:
    html = "<h1 class='entry-title'>七瀬アリス（ななせありす）</h1><div class='database'><table></table></div>"
    spider = AvjohoActressSpider(fetcher=FakeFetcher({"https://db.avjoho.com/nanase/": html}))

    result = spider.find_first_matching_profile(["七瀬アリス"], manual_url="https://db.avjoho.com/nanase/")

    assert result.profile is not None
    assert result.profile.display_name == "七瀬アリス"
    assert result.matched_url == "https://db.avjoho.com/nanase/"
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest backend/tests/test_avjoho_parser.py scraper/tests/test_avjoho_spider.py -q`

Expected: FAIL because `scraper.spiders.avjoho` does not exist.

- [ ] **Step 3: Move the parser implementation**

Create `scraper/spiders/avjoho/avjoho_parser.py` by moving the contents of `backend/app/modules/content/actresses/avjoho_parser.py`.

Change the payload import and class definition:

```python
from scraper.profiles.actress import ActressProfilePayload
```

Remove the local `AvjohoProfilePayload` dataclass and return `ActressProfilePayload` from `parse_avjoho_profile`.

Create `scraper/spiders/avjoho/__init__.py`:

```python
from scraper.spiders.avjoho.avjoho_parser import parse_avjoho_profile
from scraper.spiders.avjoho.avjoho_spider import AvjohoActressSpider

__all__ = ["AvjohoActressSpider", "parse_avjoho_profile"]
```

- [ ] **Step 4: Implement the avjoho spider**

Create `scraper/spiders/avjoho/avjoho_spider.py`:

```python
from __future__ import annotations

from urllib.parse import quote, urlparse

from scrapling.parser import Adaptor

from scraper.profiles.actress import ActressProfileMatch, ActressProfilePayload, dedupe_text
from scraper.spiders.avjoho.avjoho_parser import parse_avjoho_profile


class AvjohoActressSpider:
    source = "avjoho"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    @staticmethod
    def validate_profile_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != "db.avjoho.com":
            raise ValueError("avjoho_url must be an HTTP(S) URL on db.avjoho.com")
        return url

    @staticmethod
    def build_direct_profile_urls(names: list[str]) -> list[str]:
        return [f"https://db.avjoho.com/{quote(name)}/" for name in dedupe_text(names)]

    @staticmethod
    def build_search_names(names: list[str]) -> list[str]:
        variants: list[str] = []
        for name in names:
            variants.append(name)
            variants.append(str(name or "").replace("瀨", "瀬"))
        return dedupe_text(variants)

    @staticmethod
    def _page_to_html(page) -> str:
        html = getattr(page, "html", None)
        if html is not None:
            return html() if callable(html) else str(html)
        text = getattr(page, "text", None)
        if text is not None:
            return text() if callable(text) else str(text)
        return str(page)

    @staticmethod
    def _is_profile_url(url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != "db.avjoho.com":
            return False
        path = parsed.path.strip("/")
        if not path:
            return False
        excluded_prefixes = ("category/", "tag/", "page/", "search/", "feed/", "wp-", "sitemap")
        return not path.startswith(excluded_prefixes)

    @classmethod
    def parse_search_result_urls(cls, html: str) -> list[str]:
        page = Adaptor(html)
        urls: list[str] = []
        for anchor in page.css("#list .entry-title a"):
            href = str(anchor.attrib.get("href") or "").strip()
            if cls._is_profile_url(href):
                urls.append(href)
        return dedupe_text(urls)

    def find_profile_urls_by_search(self, name: str) -> list[str]:
        search_url = f"https://db.avjoho.com/?s={quote(name)}"
        html = self._page_to_html(self.fetcher.get(search_url))
        return self.parse_search_result_urls(html)

    def fetch_profile(self, url: str) -> ActressProfilePayload | None:
        html = self._page_to_html(self.fetcher.get(url))
        return parse_avjoho_profile(html, url)

    @staticmethod
    def profile_matches_names(payload: ActressProfilePayload, names: list[str]) -> bool:
        haystack = {payload.display_name, *payload.aliases}
        return bool(set(dedupe_text(names)).intersection(haystack))

    def find_first_matching_profile(self, names: list[str], manual_url: str | None = None) -> ActressProfileMatch:
        candidate_names = dedupe_text(names)
        attempted_urls: list[str] = []
        if manual_url:
            url_candidates = [self.validate_profile_url(manual_url)]
        else:
            search_candidates: list[str] = []
            for name in self.build_search_names(candidate_names):
                try:
                    search_candidates.extend(self.find_profile_urls_by_search(name))
                except Exception:
                    continue
            url_candidates = dedupe_text([*self.build_direct_profile_urls(candidate_names), *search_candidates])

        for url in url_candidates:
            attempted_urls.append(url)
            try:
                payload = self.fetch_profile(url)
            except Exception:
                continue
            if payload is None:
                continue
            if manual_url is None and not self.profile_matches_names(payload, candidate_names):
                continue
            return ActressProfileMatch(
                profile=payload,
                attempted_urls=attempted_urls,
                candidate_names=candidate_names,
                matched_url=url,
            )

        return ActressProfileMatch(
            profile=None,
            attempted_urls=attempted_urls,
            candidate_names=candidate_names,
        )
```

- [ ] **Step 5: Run parser and spider tests**

Run: `python -m pytest backend/tests/test_avjoho_parser.py scraper/tests/test_avjoho_spider.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scraper/spiders/avjoho/__init__.py scraper/spiders/avjoho/avjoho_parser.py scraper/spiders/avjoho/avjoho_spider.py scraper/tests/test_avjoho_spider.py backend/tests/test_avjoho_parser.py
git commit -m "Move avjoho profile scraping into scraper"
```

---

### Task 4: Slim Backend Actress Service to Provider Orchestration

**Files:**
- Modify: `backend/app/modules/content/actresses/service.py`
- Modify: `backend/tests/test_content_actresses_api.py`

**Interfaces:**
- Consumes: `fetch_actor_metadata(fetcher, url) -> ActorMetadata`.
- Consumes: `AvjohoActressSpider.find_first_matching_profile(names, manual_url) -> ActressProfileMatch`.
- Preserves: `fetch_actresses_from_task(db, task_id, task_url_id, avjoho_url=None) -> dict`.

- [ ] **Step 1: Update backend tests to patch provider boundaries**

In `backend/tests/test_content_actresses_api.py`, replace imports of `AvjohoProfilePayload`:

```python
from scraper.profiles.actress import ActorMetadata, ActressProfileMatch, ActressProfilePayload
```

For tests that currently monkeypatch `_fetch_javdb_actor_metadata`, patch:

```python
monkeypatch.setattr(
    actress_service,
    "fetch_actor_metadata",
    lambda fetcher, url: ActorMetadata(
        primary_names=["七瀬アリス"],
        aliases=["七瀬愛麗絲"],
        source_url=url,
        source_site="javdb",
    ),
)
```

For tests that currently monkeypatch `_fetch_avjoho_profile`, `_find_avjoho_profile_urls_by_search`, or `_build_avjoho_candidates`, patch `AvjohoActressSpider.find_first_matching_profile`:

```python
def fake_find_first_matching_profile(self, names, manual_url=None):
    payload = ActressProfilePayload(
        display_name="七瀬アリス",
        reading="ななせありす",
        source_url="https://db.avjoho.com/nanase-alice/",
        aliases=["七瀬愛麗絲"],
    )
    return ActressProfileMatch(
        profile=payload,
        attempted_urls=["https://db.avjoho.com/nanase-alice/"],
        candidate_names=list(names),
        matched_url=payload.source_url,
    )

monkeypatch.setattr(AvjohoActressSpider, "find_first_matching_profile", fake_find_first_matching_profile)
```

- [ ] **Step 2: Run backend tests and verify they fail**

Run: `python -m pytest backend/tests/test_content_actresses_api.py -q`

Expected: FAIL because `service.py` still imports backend avjoho parser helpers and does not expose the new provider boundary.

- [ ] **Step 3: Refactor service imports**

In `backend/app/modules/content/actresses/service.py`, remove imports:

```python
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from scrapling.parser import Adaptor
from backend.app.modules.content.actresses.avjoho_parser import AvjohoProfilePayload, parse_avjoho_profile
from scraper.core.security import detect_access_state
from scraper.spiders.javdb.javdb_parser import parse_actor_section_metadata
```

Add imports:

```python
from scraper.profiles.actress import ActressProfilePayload, dedupe_text
from scraper.spiders.avjoho.avjoho_spider import AvjohoActressSpider
from scraper.spiders.javdb.actor_profile import fetch_actor_metadata
```

- [ ] **Step 4: Remove backend scraping helpers**

Delete these private functions from `service.py`:

```python
_dedupe_text
_fetch_javdb_actor_metadata
_build_avjoho_candidates
_build_avjoho_search_names
_validate_avjoho_url
_page_to_html
_fetch_url_html
_fetch_avjoho_profile
_is_avjoho_profile_url
_parse_avjoho_search_result_urls
_find_avjoho_profile_urls_by_search
_profile_matches_names
```

Use `dedupe_text` from `scraper.profiles.actress` in their place.

- [ ] **Step 5: Update the fetch flow**

Replace the inner candidate/fetch loop in `fetch_actresses_from_task` with:

```python
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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    attempted_urls.extend(match.attempted_urls)
    if match.profile is None:
        continue

    profile = _upsert_profile(
        db,
        match.profile,
        canonical_names=dedupe_text([*names, match.profile.display_name, *match.profile.aliases]),
        task_id=task.id,
        task_url_id=task_url.id,
    )
    profiles.append(profile)
```

Return `attempted_urls` as the response `candidates` field to preserve the frontend contract.

- [ ] **Step 6: Run backend and scraper tests**

Run:

```bash
python -m pytest backend/tests/test_content_actresses_api.py -q
python -m pytest backend/tests/test_avjoho_parser.py scraper/tests/test_avjoho_spider.py scraper/tests/test_javdb_actor_metadata.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/content/actresses/service.py backend/tests/test_content_actresses_api.py
git commit -m "Use scraper providers for actress fetch"
```

---

### Task 5: Remove the Old Backend Avjoho Parser Module

**Files:**
- Delete: `backend/app/modules/content/actresses/avjoho_parser.py`
- Verify imports with `rg`.

**Interfaces:**
- Removes backend parser module after all imports point to `scraper.spiders.avjoho.avjoho_parser`.

- [ ] **Step 1: Search for remaining backend parser imports**

Run:

```bash
rg -n "content\\.actresses\\.avjoho_parser|AvjohoProfilePayload|parse_avjoho_profile" backend scraper
```

Expected: only scraper parser imports remain, and no import references `backend.app.modules.content.actresses.avjoho_parser`.

- [ ] **Step 2: Delete the backend parser**

Delete `backend/app/modules/content/actresses/avjoho_parser.py`.

- [ ] **Step 3: Run focused verification**

Run:

```bash
python -m pytest backend/tests/test_content_actresses_api.py backend/tests/test_avjoho_parser.py -q
python -m pytest scraper/tests/test_avjoho_spider.py scraper/tests/test_javdb_actor_metadata.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/modules/content/actresses/avjoho_parser.py backend/tests/test_avjoho_parser.py
git commit -m "Remove backend avjoho parser"
```

---

## Final Verification

- [ ] Run focused scraper tests:

```bash
python -m pytest scraper/tests/test_avjoho_spider.py scraper/tests/test_javdb_actor_metadata.py -q
```

- [ ] Run focused backend actress tests:

```bash
python -m pytest backend/tests/test_content_actresses_api.py backend/tests/test_avjoho_parser.py -q
```

- [ ] Run import search:

```bash
rg -n "urlopen|content\\.actresses\\.avjoho_parser|_fetch_avjoho|_find_avjoho|_parse_avjoho" backend/app/modules/content/actresses scraper
```

Expected: no backend service dependency on raw external HTML fetching or the old parser module.

- [ ] Check git status:

```bash
git status --short
```

Expected: clean working tree after commits.
