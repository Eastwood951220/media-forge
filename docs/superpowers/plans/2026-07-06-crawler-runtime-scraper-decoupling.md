# Crawler Runtime Scraper Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the deprecated crawler SSE stack and move crawler orchestration plus movie persistence out of `scraper` into backend-owned modules.

**Architecture:** Delete `backend/app/modules/crawler/events/*` and keep realtime on `/api/events/stream`. Add backend crawler runtime boundaries for task adaptation, crawl result shaping, JavDB engine orchestration, and movie persistence. Update runtime service/tests so active backend code no longer imports `scraper.services.movie_service` or `scraper.database.repositories`.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0, pytest, React 19, Vite 8, TypeScript 6, Vitest, ESLint.

## Global Constraints

- Do not redesign the frontend.
- Do not change database schema or Alembic migrations.
- Do not change crawler task API contracts.
- Do not rewrite JavDB spider parsing logic.
- Do not change CloudDrive storage worker behavior.
- Do not optimize movie list SQL filtering in this phase.
- Keep current crawler behavior for incremental/full runs, detail restart, stopping, existing-movie dedupe, logging, and realtime updates.

---

## File Structure

### Create

- `backend/app/modules/content/movies/persistence.py`
  - Owns movie insert/reuse, source task ID append, magnet upsert, magnet weighting, best magnet selection, and movie filter cache sync.
- `backend/app/modules/crawler/runtime/results.py`
  - Owns crawler task result summaries formerly built by `scraper.services.movie_result`.
- `backend/app/modules/crawler/runtime/config.py`
  - Owns crawler runtime configuration reads such as `INCREMENTAL_EXIST_THRESHOLD`.
- `backend/app/modules/crawler/runtime/task_adapter.py`
  - Converts backend ORM crawl tasks into lightweight scraper-compatible task dataclasses.
- `backend/app/modules/crawler/runtime/engine.py`
  - Defines `CrawlerEngine`, `CrawlCallbacks`, `JavdbCrawlerEngine`, and `get_crawler_engine()`.
- `backend/tests/test_movie_persistence.py`
  - Covers backend movie/magnet/filter persistence.
- `backend/tests/test_crawler_engine.py`
  - Covers backend JavDB engine orchestration with fake spider/pipeline dependencies.

### Modify

- `backend/app/main.py`
  - Remove deprecated `crawler_events_router` import and include.
- `backend/tests/test_realtime_events.py`
  - Add `/api/crawler/stream` removal regression.
- `backend/app/modules/crawler/runtime/service.py`
  - Remove direct imports of `scraper.services.movie_service` and `scraper.database.repositories`.
  - Use backend engine and persistence factories.
- `backend/app/modules/crawler/runtime/source_task_names.py`
  - Keep list/detail dedupe checks and remove the now-duplicated source task append helper.
- `backend/tests/test_crawler_worker_service.py`
  - Patch backend engine/persistence boundaries instead of scraper classes.
- `backend/tests/test_crawler_source_task_names.py`
  - Keep dedupe helper tests and remove the old source task append helper test.
- `scraper/tests/test_movie_result.py`
  - Move or replace with backend result tests.

### Delete

- `backend/app/modules/crawler/events/__init__.py`
- `backend/app/modules/crawler/events/bus.py`
- `backend/app/modules/crawler/events/router.py`
- `backend/app/modules/crawler/events/schemas.py`
- `backend/tests/test_crawler_sse_events.py`
- `scraper/services/movie_service.py`
- `scraper/services/movie_result.py`
- `scraper/services/__init__.py`
- `scraper/database/repositories/filter_repository.py`
- `scraper/database/repositories/movie_magnet_repository.py`
- `scraper/database/repositories/movie_repository.py`
- `scraper/database/repositories/__init__.py`
- `scraper/database/__init__.py`

---

### Task 1: Remove Deprecated Crawler SSE Stack

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_realtime_events.py`
- Delete: `backend/app/modules/crawler/events/__init__.py`
- Delete: `backend/app/modules/crawler/events/bus.py`
- Delete: `backend/app/modules/crawler/events/router.py`
- Delete: `backend/app/modules/crawler/events/schemas.py`
- Delete: `backend/tests/test_crawler_sse_events.py`

**Interfaces:**
- Consumes: existing unified realtime endpoint `/api/events/stream`.
- Produces: `/api/crawler/stream` returns 404; no active backend code imports `backend.app.modules.crawler.events`.

- [ ] **Step 1: Add failing removal regression**

Append this test to `backend/tests/test_realtime_events.py`:

```python
def test_deprecated_crawler_stream_route_is_removed(client: TestClient) -> None:
    response = client.get("/api/crawler/stream?token=bad")

    assert response.status_code == 404
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_realtime_events.py::test_deprecated_crawler_stream_route_is_removed -v
```

Expected: FAIL because the deprecated route is still mounted and returns 401 for a bad token.

- [ ] **Step 3: Remove deprecated router from app startup**

In `backend/app/main.py`, delete this import:

```python
from backend.app.modules.crawler.events.router import router as crawler_events_router
```

Delete this include:

```python
app.include_router(crawler_events_router)
```

- [ ] **Step 4: Delete deprecated crawler events module and old tests**

Run:

```bash
rm backend/app/modules/crawler/events/__init__.py
rm backend/app/modules/crawler/events/bus.py
rm backend/app/modules/crawler/events/router.py
rm backend/app/modules/crawler/events/schemas.py
rm backend/tests/test_crawler_sse_events.py
```

- [ ] **Step 5: Run realtime tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 6: Verify no active old SSE references remain**

Run:

```bash
rg -n "backend\.app\.modules\.crawler\.events|crawler_events_router|/api/crawler/stream" backend/app backend/tests frontend/src
```

Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/tests/test_realtime_events.py
git add -u backend/app/modules/crawler/events backend/tests/test_crawler_sse_events.py
git commit -m "refactor: remove deprecated crawler sse stack"
```

---

### Task 2: Move Movie Persistence Into Backend Content Module

**Files:**
- Create: `backend/app/modules/content/movies/persistence.py`
- Create: `backend/tests/test_movie_persistence.py`

**Interfaces:**
- Consumes: `shared.database.models.content.Movie`, `MovieMagnet`, `MovieFilter`, SQLAlchemy `Session`.
- Produces:
  - `extract_info_hash(magnet_url: str | None) -> str`
  - `build_magnet_dedupe_key(movie_id: str, magnet: dict[str, Any]) -> str`
  - `compute_magnet_weight(magnet: dict[str, Any]) -> int`
  - `upsert_movie(session: Session, item: dict[str, Any]) -> UUID`
  - `append_source_task_id(session: Session, code: str | None, task_id: UUID) -> bool`
  - `upsert_magnets(session: Session, movie_id: UUID, movie: dict[str, Any], magnets: list[dict[str, Any]]) -> int`
  - `auto_select_best_magnet(session: Session, movie_id: UUID) -> None`
  - `upsert_movie_with_magnets(session: Session, item_data: dict[str, Any]) -> UUID`
  - `sync_movie_filters(session: Session) -> dict[str, int]`

- [ ] **Step 1: Write failing persistence tests**

Create `backend/tests/test_movie_persistence.py`:

```python
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from backend.app.modules.content.movies.persistence import (
    append_source_task_id,
    compute_magnet_weight,
    extract_info_hash,
    sync_movie_filters,
    upsert_magnets,
    upsert_movie,
    upsert_movie_with_magnets,
)
from backend.tests.conftest import TestingSessionLocal
from shared.database.models.content import Movie, MovieFilter, MovieMagnet


def test_extract_info_hash_from_magnet_url() -> None:
    assert extract_info_hash("magnet:?xt=urn:btih:ABCDEF&dn=name") == "abcdef"
    assert extract_info_hash("") == ""
    assert extract_info_hash(None) == ""


def test_upsert_movie_inserts_and_reuses_by_code() -> None:
    session = TestingSessionLocal()
    first_id = upsert_movie(session, {
        "code": "AAA-001",
        "source_url": "https://javdb.com/v/aaa001",
        "source_name": "AAA 001",
        "release_date": date(2026, 1, 1),
        "duration": 120,
        "rating": Decimal("4.5"),
        "actors": ["演员A"],
        "tags": ["标签A"],
    })
    second_id = upsert_movie(session, {
        "code": "AAA-001",
        "source_url": "https://javdb.com/v/aaa001-copy",
        "source_name": "AAA 001 copy",
    })

    assert second_id == first_id
    assert session.scalar(select(Movie).where(Movie.code == "AAA-001")).id == first_id

    session.close()


def test_append_source_task_id_adds_unique_id() -> None:
    session = TestingSessionLocal()
    movie_id = upsert_movie(session, {"code": "SRC-001", "source_url": "https://javdb.com/v/src001"})
    task_id = uuid.uuid4()

    assert append_source_task_id(session, "SRC-001", task_id) is True
    assert append_source_task_id(session, "SRC-001", task_id) is False

    movie = session.get(Movie, movie_id)
    assert [str(value) for value in movie.source_task_ids] == [str(task_id)]

    session.close()


def test_upsert_magnets_dedupes_updates_and_selects_best() -> None:
    session = TestingSessionLocal()
    movie_id = upsert_movie(session, {"code": "MAG-001", "source_url": "https://javdb.com/v/mag001"})

    saved_count = upsert_magnets(session, movie_id, {"code": "MAG-001"}, [
        {
            "magnet": "magnet:?xt=urn:btih:1111111111111111111111111111111111111111",
            "name": "small",
            "size_text": "100MB",
            "tags": [],
        },
        {
            "magnet": "magnet:?xt=urn:btih:2222222222222222222222222222222222222222",
            "name": "large subtitles",
            "size_text": "3GB",
            "tags": ["中字"],
        },
    ])

    assert saved_count == 2
    upsert_magnets(session, movie_id, {"code": "MAG-001"}, [
        {
            "magnet": "magnet:?xt=urn:btih:1111111111111111111111111111111111111111",
            "name": "small updated",
            "size_text": "200MB",
            "tags": [],
        }
    ])

    magnets = session.scalars(select(MovieMagnet).where(MovieMagnet.movie_id == movie_id)).all()
    assert len(magnets) == 2
    assert any(magnet.name == "small updated" for magnet in magnets)
    selected = [magnet for magnet in magnets if magnet.selected]
    assert len(selected) == 1
    assert selected[0].name == "large subtitles"
    assert compute_magnet_weight({"name": "中字", "size_text": "3GB", "tags": ["中字"]}) > compute_magnet_weight({"name": "plain", "size_text": "100MB"})

    session.close()


def test_upsert_movie_with_magnets_persists_movie_and_magnets() -> None:
    session = TestingSessionLocal()

    movie_id = upsert_movie_with_magnets(session, {
        "code": "FULL-001",
        "source_url": "https://javdb.com/v/full001",
        "source_name": "FULL 001",
        "magnets": [
            {
                "magnet": "magnet:?xt=urn:btih:3333333333333333333333333333333333333333",
                "name": "FULL 001",
                "size_text": "1.2GB",
            }
        ],
    })

    assert session.get(Movie, movie_id).code == "FULL-001"
    assert len(session.scalars(select(MovieMagnet).where(MovieMagnet.movie_id == movie_id)).all()) == 1

    session.close()


def test_sync_movie_filters_rebuilds_filter_cache() -> None:
    session = TestingSessionLocal()
    session.add(Movie(
        code="FILTER-001",
        source_url="https://javdb.com/v/filter001",
        source_name="Filter 001",
        actors=["演员A", "演员B"],
        tags=["标签A"],
        director="导演A",
        maker="片商A",
        series="系列A",
    ))
    session.commit()

    result = sync_movie_filters(session)

    assert result == {"actors": 2, "tags": 1, "directors": 1, "makers": 1, "series": 1}
    assert session.scalar(select(MovieFilter).where(MovieFilter.type == "actor", MovieFilter.name == "演员A")) is not None

    session.close()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_movie_persistence.py -v
```

Expected: FAIL because `backend.app.modules.content.movies.persistence` does not exist.

- [ ] **Step 3: Implement backend persistence module**

Create `backend/app/modules/content/movies/persistence.py`:

```python
from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from shared.database.models.content import Movie, MovieFilter, MovieMagnet


def extract_info_hash(magnet_url: str | None) -> str:
    if not magnet_url:
        return ""
    query = parse_qs(urlparse(magnet_url).query)
    for xt in query.get("xt", []):
        prefix = "urn:btih:"
        if xt.lower().startswith(prefix):
            return xt[len(prefix):].lower()
    return ""


def build_magnet_dedupe_key(movie_id: str, magnet: dict[str, Any]) -> str:
    info_hash = str(magnet.get("info_hash") or "").strip().lower()
    if not info_hash:
        info_hash = extract_info_hash(magnet.get("magnet") or magnet.get("magnet_url"))
    if info_hash:
        return info_hash

    parts = [
        str(movie_id),
        str(magnet.get("name") or ""),
        str(magnet.get("size_text") or ""),
        str(magnet.get("file_count") or ""),
        str(magnet.get("file_text") or ""),
        str(magnet.get("date") or ""),
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def _parse_size_mb(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return 0.0
    size_text = str(value).strip().upper()
    match = re.match(r"([\d.]+)\s*(GB|MB|KB|TB)?", size_text)
    if not match:
        return 0.0
    number = float(match.group(1))
    unit = match.group(2) or "MB"
    multipliers = {"KB": 1 / 1024, "MB": 1, "GB": 1024, "TB": 1024 * 1024}
    return number * multipliers.get(unit, 1)


def _has_chinese_sub(magnet: dict[str, Any]) -> bool:
    if magnet.get("has_chinese_sub"):
        return True
    tags = magnet.get("tags") or []
    if any("字幕" in str(tag) or "中字" in str(tag) for tag in tags):
        return True
    title = (magnet.get("title") or magnet.get("name") or "").lower()
    return any(keyword in title for keyword in ["chs", "cht", "chinese", "中字", "中文", "字幕"])


def compute_magnet_weight(magnet: dict[str, Any]) -> int:
    has_sub = _has_chinese_sub(magnet)
    size_mb = _parse_size_mb(magnet.get("size") or magnet.get("size_text"))
    is_large_sub = has_sub and size_mb > 2048

    file_count = magnet.get("file_count")
    if isinstance(file_count, (int, float)) and file_count > 0:
        file_penalty = max(0, 10000 - int(file_count) * 100)
    else:
        file_penalty = 5000

    return int(is_large_sub * 100000 + has_sub * 10000 + min(size_mb, 50000) + file_penalty)


def _movie_unique_value(item: dict[str, Any]) -> tuple[str, str]:
    code = str(item.get("code") or "").strip()
    if code:
        return "code", code
    return "source_url", str(item.get("source_url") or "").strip()


def upsert_movie(session: Session, item: dict[str, Any]) -> UUID:
    unique_field, unique_value = _movie_unique_value(item)
    if not unique_value:
        raise ValueError("movie item must include code or source_url")

    if unique_field == "code":
        existing = session.scalar(select(Movie).where(Movie.code == unique_value))
    else:
        existing = session.scalar(select(Movie).where(Movie.source_url == unique_value))
    if existing is not None:
        return existing.id

    movie = Movie(
        code=item.get("code"),
        source_url=item.get("source_url"),
        source_name=item.get("source_name", ""),
        release_date=item.get("release_date"),
        duration=item.get("duration", 0),
        director=item.get("director", ""),
        maker=item.get("maker", ""),
        series=item.get("series", ""),
        rating=item.get("rating"),
        actors=item.get("actors", []),
        tags=item.get("tags", []),
        source_task_ids=item.get("source_task_ids", []),
        cover=item.get("cover", ""),
        marked=item.get("marked", False),
        storage_summary=item.get("storage_summary", {}),
        raw_detail=item.get("raw_detail", {}),
    )
    session.add(movie)
    session.flush()
    return movie.id


def append_source_task_id(session: Session, code: str | None, task_id: UUID) -> bool:
    if not code:
        return False
    movie = session.scalar(select(Movie).where(Movie.code == code))
    if movie is None:
        return False

    existing_ids = [str(value) for value in (movie.source_task_ids or [])]
    task_id_text = str(task_id)
    if task_id_text in existing_ids:
        return False
    movie.source_task_ids = list(movie.source_task_ids or []) + [task_id]
    session.flush()
    return True


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_magnet(movie_id: UUID, magnet: dict[str, Any]) -> dict[str, Any] | None:
    magnet_url = str(magnet.get("magnet") or magnet.get("magnet_url") or "").strip()
    name = str(magnet.get("name") or "").strip()
    size_text = str(magnet.get("size_text") or "").strip()
    file_text = str(magnet.get("file_text") or "").strip()
    if not (magnet_url or name or size_text or file_text):
        return None

    info_hash = str(magnet.get("info_hash") or "").strip().lower()
    if not info_hash:
        info_hash = extract_info_hash(magnet_url)

    tags = magnet.get("tags")
    if not isinstance(tags, list):
        tags = []

    size_mb = _to_float(magnet.get("size"))
    if size_mb is None:
        size_mb = _parse_size_mb(size_text)

    return {
        "magnet_url": magnet_url,
        "info_hash": info_hash if info_hash else None,
        "dedupe_key": build_magnet_dedupe_key(str(movie_id), {**magnet, "magnet": magnet_url, "info_hash": info_hash, "name": name, "size_text": size_text, "file_text": file_text}),
        "name": name,
        "size_mb": size_mb,
        "size_text": size_text,
        "file_count": magnet.get("file_count"),
        "file_text": file_text,
        "tags": tags,
        "has_chinese_sub": bool(magnet.get("has_chinese_sub")),
        "weight": compute_magnet_weight(magnet),
        "date": magnet.get("date") or "",
        "selected": False,
        "raw_data": {},
    }


def upsert_magnets(session: Session, movie_id: UUID, movie: dict[str, Any], magnets: list[dict[str, Any]]) -> int:
    saved_count = 0
    for magnet in magnets:
        document = _normalize_magnet(movie_id, magnet)
        if document is None:
            continue
        existing = session.scalar(
            select(MovieMagnet).where(
                MovieMagnet.movie_id == movie_id,
                MovieMagnet.dedupe_key == document["dedupe_key"],
            )
        )
        if existing is None:
            session.add(MovieMagnet(movie_id=movie_id, **document))
        else:
            for key, value in document.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
        saved_count += 1
    session.flush()
    if saved_count:
        auto_select_best_magnet(session, movie_id)
    return saved_count


def auto_select_best_magnet(session: Session, movie_id: UUID) -> None:
    magnets = session.scalars(select(MovieMagnet).where(MovieMagnet.movie_id == movie_id)).all()
    if not magnets:
        return
    best = max(magnets, key=lambda magnet: magnet.weight or 0)
    for magnet in magnets:
        magnet.selected = magnet.id == best.id
    session.flush()


def upsert_movie_with_magnets(session: Session, item_data: dict[str, Any]) -> UUID:
    movie_doc = dict(item_data)
    magnets = movie_doc.pop("magnets", []) or []
    movie_id = upsert_movie(session, movie_doc)
    if magnets:
        upsert_magnets(session, movie_id, movie_doc, magnets)
    return movie_id


def sync_movie_filters(session: Session) -> dict[str, int]:
    actors: set[str] = set()
    tags: set[str] = set()
    directors: set[str] = set()
    makers: set[str] = set()
    series: set[str] = set()

    for movie in session.scalars(select(Movie)).all():
        for value in movie.actors or []:
            if isinstance(value, str) and value.strip():
                actors.add(value.strip())
        for value in movie.tags or []:
            if isinstance(value, str) and value.strip():
                tags.add(value.strip())
        if movie.director and movie.director.strip():
            directors.add(movie.director.strip())
        if movie.maker and movie.maker.strip():
            makers.add(movie.maker.strip())
        if movie.series and movie.series.strip():
            series.add(movie.series.strip())

    session.execute(delete(MovieFilter))
    for name in sorted(actors):
        session.add(MovieFilter(type="actor", name=name, count=0))
    for name in sorted(tags):
        session.add(MovieFilter(type="tag", name=name, count=0))
    for name in sorted(directors):
        session.add(MovieFilter(type="director", name=name, count=0))
    for name in sorted(makers):
        session.add(MovieFilter(type="maker", name=name, count=0))
    for name in sorted(series):
        session.add(MovieFilter(type="series", name=name, count=0))
    session.flush()

    return {
        "actors": len(actors),
        "tags": len(tags),
        "directors": len(directors),
        "makers": len(makers),
        "series": len(series),
    }
```

- [ ] **Step 4: Run persistence tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_movie_persistence.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/content/movies/persistence.py backend/tests/test_movie_persistence.py
git commit -m "refactor: move movie persistence into backend"
```

---

### Task 3: Add Backend Crawler Config, Results, And Task Adapter

**Files:**
- Create: `backend/app/modules/crawler/runtime/config.py`
- Create: `backend/app/modules/crawler/runtime/results.py`
- Create: `backend/app/modules/crawler/runtime/task_adapter.py`
- Create: `backend/tests/test_crawler_runtime_adapters.py`
- Modify: `scraper/tests/test_movie_result.py`

**Interfaces:**
- Consumes: backend ORM `CrawlTask` and `CrawlTaskUrl`; scraper task dataclasses.
- Produces:
  - `read_incremental_threshold_from_conf(base_dir: Path | None = None) -> int`
  - `summarize_detail_tasks(detail_tasks: list[dict]) -> dict`
  - `build_skipped_task_result(task) -> dict`
  - `build_task_result(task, detail_tasks: list[dict], saved_items: list[dict], stopped: bool) -> dict`
  - `to_scraper_task(task: backend.app.models.crawl_task.CrawlTask) -> scraper.tasks.task_schema.CrawlTask`

- [ ] **Step 1: Write failing adapter/result tests**

Create `backend/tests/test_crawler_runtime_adapters.py`:

```python
from datetime import datetime

from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.modules.crawler.runtime.config import read_incremental_threshold_from_conf
from backend.app.modules.crawler.runtime.results import build_task_result, summarize_detail_tasks
from backend.app.modules.crawler.runtime.task_adapter import to_scraper_task


def test_to_scraper_task_preserves_task_fields(admin_user) -> None:
    task = CrawlTask(name="任务A", owner_id=admin_user.id, is_skip=True, filter={"actor": "A"})
    task.urls = [
        CrawlTaskUrl(
            position=2,
            url="https://javdb.com/actors/a",
            url_type="actors",
            final_url="https://javdb.com/actors/a?page=1",
            source="javdb",
            has_magnet=True,
            has_chinese_sub=True,
            sort_type=1,
            url_name="演员A",
            created_at=datetime.now(),
        )
    ]

    converted = to_scraper_task(task)

    assert converted.name == "任务A"
    assert converted.is_skip is True
    assert converted.filter == {"actor": "A"}
    assert len(converted.urls) == 1
    assert converted.urls[0].url == "https://javdb.com/actors/a"
    assert converted.urls[0].final_url == "https://javdb.com/actors/a?page=1"
    assert converted.urls[0].has_magnet is True
    assert converted.urls[0].has_chinese_sub is True
    assert converted.urls[0].source == "javdb"
    assert converted.urls[0].url_name == "演员A"


def test_read_incremental_threshold_from_backend_runtime_config(tmp_path) -> None:
    config_dir = tmp_path / "data" / "configs"
    config_dir.mkdir(parents=True)
    (config_dir / "crawler.conf").write_text(
        "OTHER=1\nINCREMENTAL_EXIST_THRESHOLD=7\n",
        encoding="utf-8",
    )

    assert read_incremental_threshold_from_conf(tmp_path) == 7


def test_build_task_result_matches_existing_shape(admin_user) -> None:
    task = CrawlTask(name="任务B", owner_id=admin_user.id, is_skip=False)
    task.urls = [
        CrawlTaskUrl(position=0, url="https://javdb.com/tags/a", url_type="tags", final_url="https://javdb.com/tags/a?page=1", source="javdb")
    ]
    detail_tasks = [
        {"status": "completed", "_task_url": "https://javdb.com/tags/a", "_task_final_url": "https://javdb.com/tags/a?page=1"},
        {"status": "failed", "_task_url": "https://javdb.com/tags/a", "_task_final_url": "https://javdb.com/tags/a?page=1"},
        {"status": "skipped", "_task_url": "https://javdb.com/tags/a", "_task_final_url": "https://javdb.com/tags/a?page=1"},
    ]

    result = build_task_result(task, detail_tasks, saved_items=[{"code": "AAA-001"}], stopped=True)

    assert summarize_detail_tasks(detail_tasks) == {"total_tasks": 3, "completed_tasks": 1, "failed_tasks": 1, "skipped_tasks": 1}
    assert result["task_name"] == "任务B"
    assert result["stopped"] is True
    assert result["total_tasks"] == 3
    assert result["items"][0]["final_url"] == "https://javdb.com/tags/a?page=1"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_runtime_adapters.py -v
```

Expected: FAIL because `config.py`, `results.py`, and `task_adapter.py` do not exist.

- [ ] **Step 3: Implement crawler runtime config module**

Create `backend/app/modules/crawler/runtime/config.py`:

```python
from __future__ import annotations

from pathlib import Path


def read_incremental_threshold_from_conf(base_dir: Path | None = None) -> int:
    root = base_dir or Path.cwd().parent
    conf_path = root / "data" / "configs" / "crawler.conf"
    if not conf_path.exists():
        return 0
    for line in conf_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == "INCREMENTAL_EXIST_THRESHOLD":
            try:
                return int(value.strip())
            except (TypeError, ValueError):
                return 0
    return 0
```

- [ ] **Step 4: Implement crawler runtime results module**

Create `backend/app/modules/crawler/runtime/results.py`:

```python
from __future__ import annotations

from typing import Any

from scraper.spiders.javdb.javdb_constants import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_SKIPPED,
)


def summarize_detail_tasks(detail_tasks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_tasks": len(detail_tasks),
        "completed_tasks": sum(1 for item in detail_tasks if item.get("status") == TASK_STATUS_COMPLETED),
        "failed_tasks": sum(1 for item in detail_tasks if item.get("status") == TASK_STATUS_FAILED),
        "skipped_tasks": sum(1 for item in detail_tasks if item.get("status") == TASK_STATUS_SKIPPED),
    }


def _matching_url_tasks(entry: Any, detail_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    final_url = entry.final_url or entry.url
    return [
        item
        for item in detail_tasks
        if item.get("_task_url") == entry.url and item.get("_task_final_url") == final_url
    ]


def _url_result_item(entry: Any, detail_tasks: list[dict[str, Any]]) -> dict[str, Any]:
    matching_tasks = _matching_url_tasks(entry, detail_tasks)
    return {
        "url": entry.url,
        "final_url": entry.final_url or entry.url,
        "url_type": entry.url_type,
        "source": entry.source,
        "url_name": entry.url_name,
        "has_magnet": entry.has_magnet,
        "has_chinese_sub": entry.has_chinese_sub,
        "sort_type": entry.sort_type,
        **summarize_detail_tasks(matching_tasks),
    }


def url_result_items(task: Any, detail_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_url_result_item(entry, detail_tasks) for entry in task.urls]


def build_skipped_task_result(task: Any) -> dict[str, Any]:
    return {
        "task_name": task.name,
        "is_skip": True,
        "total_tasks": 0,
        "completed_tasks": 0,
        "failed_tasks": 0,
        "skipped_tasks": 0,
        "saved": 0,
        "items": url_result_items(task, []),
        "reason": "skipped_by_config",
    }


def build_task_result(
    task: Any,
    detail_tasks: list[dict[str, Any]],
    saved_items: list[dict[str, Any]],
    stopped: bool,
) -> dict[str, Any]:
    return {
        "task_name": task.name,
        "is_skip": task.is_skip,
        **summarize_detail_tasks(detail_tasks),
        "saved": 0,
        "items": url_result_items(task, detail_tasks),
        "stopped": stopped,
    }
```

- [ ] **Step 5: Implement task adapter**

Create `backend/app/modules/crawler/runtime/task_adapter.py`:

```python
from __future__ import annotations

from backend.app.models.crawl_task import CrawlTask as BackendCrawlTask
from scraper.tasks.task_schema import CrawlTask, CrawlTaskUrlEntry


def to_scraper_task(task: BackendCrawlTask) -> CrawlTask:
    urls = [
        CrawlTaskUrlEntry(
            url=url.url,
            url_type=url.url_type,
            has_magnet=bool(url.has_magnet),
            has_chinese_sub=bool(url.has_chinese_sub),
            sort_type=int(url.sort_type or 0),
            source=url.source,
            final_url=url.final_url,
            url_name=url.url_name,
        )
        for url in sorted(task.urls, key=lambda item: item.position)
    ]
    return CrawlTask(
        name=task.name,
        urls=urls,
        is_skip=bool(task.is_skip),
        filter=task.filter,
    )
```

- [ ] **Step 6: Move scraper movie result tests to backend module imports**

In `scraper/tests/test_movie_result.py`, replace:

```python
from scraper.services.movie_result import build_skipped_task_result, build_task_result
```

with:

```python
from backend.app.modules.crawler.runtime.results import build_skipped_task_result, build_task_result
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runtime_adapters.py scraper/tests/test_movie_result.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/crawler/runtime/config.py backend/app/modules/crawler/runtime/results.py backend/app/modules/crawler/runtime/task_adapter.py backend/tests/test_crawler_runtime_adapters.py scraper/tests/test_movie_result.py
git commit -m "refactor: add crawler runtime adapters"
```

---

### Task 4: Add Backend JavDB Crawler Engine

**Files:**
- Create: `backend/app/modules/crawler/runtime/engine.py`
- Create: `backend/tests/test_crawler_engine.py`

**Interfaces:**
- Consumes:
  - `backend.app.modules.crawler.runtime.results`
  - `backend.app.modules.crawler.runtime.task_adapter`
  - scraper primitives: `CookieManager`, `ScraplingFetcher`, `JavdbSpider`, `MoviePipeline`
- Produces:
  - `CrawlCallbacks` dataclass
  - `CrawlerEngine` protocol
  - `JavdbCrawlerEngine`
  - `get_crawler_engine() -> CrawlerEngine`

- [ ] **Step 1: Write failing engine tests**

Create `backend/tests/test_crawler_engine.py`:

```python
from backend.app.modules.crawler.runtime.engine import CrawlCallbacks, JavdbCrawlerEngine
from scraper.tasks.task_schema import CrawlTask


class FakePipeline:
    def process_item(self, item, task_name=None, task_id=None):
        return {**item, "source_task_name": task_name, "source_task_id": task_id}


class FakeSpider:
    def __init__(self):
        self.detail_tasks = [
            {
                "code": "AAA-001",
                "url": "https://javdb.com/v/aaa001",
                "name": "AAA 001",
                "status": "completed",
                "detail": {"code": "AAA-001", "source_name": "AAA 001"},
            }
        ]

    def run_task(self, task, **kwargs):
        kwargs["on_tasks_batch_created"]([
            {"code": "AAA-001", "url": "https://javdb.com/v/aaa001", "name": "AAA 001"}
        ])
        kwargs["on_detail_completed"](self.detail_tasks[0])
        return self.detail_tasks

    def run_detail_tasks(self, detail_tasks, **kwargs):
        for detail_task in detail_tasks:
            kwargs["on_detail_completed"]({
                **detail_task,
                "status": "completed",
                "detail": {"code": detail_task["code"], "source_name": detail_task["name"]},
            })
        return [{**detail_task, "status": "completed"} for detail_task in detail_tasks]


def test_crawl_task_triggers_callbacks_and_returns_result() -> None:
    batches = []
    saved = []
    logs = []
    engine = JavdbCrawlerEngine(spider_factory=lambda: FakeSpider(), pipeline_factory=lambda: FakePipeline())
    task = CrawlTask(name="任务A", urls=[])

    result = engine.crawl_task(
        task,
        task_id="task-1",
        crawl_mode="incremental",
        incremental_threshold=3,
        callbacks=CrawlCallbacks(
            on_tasks_batch_created=batches.append,
            on_item_saved=lambda task_info, item_data: saved.append((task_info, item_data)),
            log_callback=lambda message, level="INFO": logs.append((level, message)),
        ),
    )

    assert result["task_name"] == "任务A"
    assert result["total_tasks"] == 1
    assert batches[0][0]["code"] == "AAA-001"
    assert saved[0][1]["source_task_id"] == "task-1"
    assert any("详情完成" in message for _level, message in logs)


def test_crawl_detail_tasks_supports_restart_path() -> None:
    saved = []
    engine = JavdbCrawlerEngine(spider_factory=lambda: FakeSpider(), pipeline_factory=lambda: FakePipeline())
    task = CrawlTask(name="任务B", urls=[])

    result = engine.crawl_detail_tasks(
        task,
        detail_tasks=[{"code": "BBB-001", "url": "https://javdb.com/v/bbb001", "name": "BBB 001"}],
        task_id="task-2",
        callbacks=CrawlCallbacks(
            on_item_saved=lambda task_info, item_data: saved.append((task_info, item_data)),
        ),
    )

    assert result["total_tasks"] == 1
    assert saved[0][0]["code"] == "BBB-001"
    assert saved[0][1]["code"] == "BBB-001"


def test_crawl_task_returns_stopped_flag() -> None:
    engine = JavdbCrawlerEngine(spider_factory=lambda: FakeSpider(), pipeline_factory=lambda: FakePipeline())
    task = CrawlTask(name="任务C", urls=[])

    result = engine.crawl_task(
        task,
        task_id="task-3",
        crawl_mode="full",
        incremental_threshold=0,
        callbacks=CrawlCallbacks(stop_check=lambda: True),
    )

    assert result["stopped"] is True
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_engine.py -v
```

Expected: FAIL because `backend.app.modules.crawler.runtime.engine` does not exist.

- [ ] **Step 3: Implement engine module**

Create `backend/app/modules/crawler/runtime/engine.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from backend.app.modules.crawler.runtime.results import build_skipped_task_result, build_task_result
from scraper.config.settings import REQUEST_TIMEOUT
from scraper.config.sites import JAVDB_SITE
from scraper.cookies.cookie_manager import CookieManager
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher
from scraper.pipelines.movie_pipeline import MoviePipeline
from scraper.spiders.javdb.javdb_spider import JavdbSpider
from scraper.tasks.task_schema import CrawlTask


@dataclass
class CrawlCallbacks:
    stop_check: Callable[[], bool] | None = None
    log_callback: Callable[[str, str], None] | None = None
    on_item_saved: Callable[[dict[str, Any], dict[str, Any]], None] | None = None
    on_tasks_batch_created: Callable[[list[dict[str, Any]]], None] | None = None
    on_detail_failed: Callable[[dict[str, Any], str], None] | None = None
    db_check_callback: Callable[[list[str]], set[str]] | None = None
    on_detail_check_callback: Callable[[str], bool] | None = None
    on_item_already_exists: Callable[[dict[str, Any]], None] | None = None


class CrawlerEngine(Protocol):
    def crawl_task(
        self,
        task: CrawlTask,
        *,
        task_id: str | None,
        crawl_mode: str,
        incremental_threshold: int,
        callbacks: CrawlCallbacks,
    ) -> dict[str, Any]:
        ...

    def crawl_detail_tasks(
        self,
        task: CrawlTask,
        *,
        detail_tasks: list[dict[str, Any]],
        task_id: str | None,
        callbacks: CrawlCallbacks,
    ) -> dict[str, Any]:
        ...


class JavdbCrawlerEngine:
    def __init__(
        self,
        *,
        spider_factory: Callable[[], Any] | None = None,
        pipeline_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._spider_factory = spider_factory or self._build_spider
        self._pipeline_factory = pipeline_factory or MoviePipeline

    def _build_spider(self) -> JavdbSpider:
        cookie_manager = CookieManager(JAVDB_SITE["cookie_file"])
        cookies = cookie_manager.load()
        fetcher = ScraplingFetcher(
            headers=JAVDB_SITE["headers"],
            cookies=cookies,
            timeout=REQUEST_TIMEOUT,
        )
        return JavdbSpider(fetcher=fetcher)

    def crawl_task(
        self,
        task: CrawlTask,
        *,
        task_id: str | None,
        crawl_mode: str,
        incremental_threshold: int,
        callbacks: CrawlCallbacks,
    ) -> dict[str, Any]:
        if task.is_skip:
            if callbacks.log_callback:
                callbacks.log_callback(f"跳过任务: {task.name}", "INFO")
            return build_skipped_task_result(task)

        spider = self._spider_factory()
        pipeline = self._pipeline_factory()
        saved_items: list[dict[str, Any]] = []

        def collect_completed_detail(detail_task: dict[str, Any]) -> None:
            self._collect_completed_detail(
                task=task,
                task_id=task_id,
                detail_task=detail_task,
                pipeline=pipeline,
                saved_items=saved_items,
                callbacks=callbacks,
            )

        detail_tasks = spider.run_task(
            task,
            crawl_mode=crawl_mode,
            incremental_threshold=incremental_threshold,
            on_detail_completed=collect_completed_detail,
            on_tasks_batch_created=callbacks.on_tasks_batch_created,
            on_detail_failed=callbacks.on_detail_failed,
            stop_check=callbacks.stop_check,
            log_callback=callbacks.log_callback,
            db_check_callback=callbacks.db_check_callback,
            on_detail_check_callback=callbacks.on_detail_check_callback,
            on_item_already_exists=callbacks.on_item_already_exists,
        )
        stopped = callbacks.stop_check() if callbacks.stop_check else False
        return build_task_result(task=task, detail_tasks=detail_tasks, saved_items=saved_items, stopped=stopped)

    def crawl_detail_tasks(
        self,
        task: CrawlTask,
        *,
        detail_tasks: list[dict[str, Any]],
        task_id: str | None,
        callbacks: CrawlCallbacks,
    ) -> dict[str, Any]:
        if task.is_skip:
            if callbacks.log_callback:
                callbacks.log_callback(f"跳过任务: {task.name}", "INFO")
            return build_skipped_task_result(task)

        spider = self._spider_factory()
        pipeline = self._pipeline_factory()
        saved_items: list[dict[str, Any]] = []

        def collect_completed_detail(detail_task: dict[str, Any]) -> None:
            self._collect_completed_detail(
                task=task,
                task_id=task_id,
                detail_task=detail_task,
                pipeline=pipeline,
                saved_items=saved_items,
                callbacks=callbacks,
            )

        processed_tasks = spider.run_detail_tasks(
            detail_tasks,
            task_name=task.name,
            on_detail_completed=collect_completed_detail,
            on_detail_failed=callbacks.on_detail_failed,
            stop_check=callbacks.stop_check,
            log_callback=callbacks.log_callback,
            on_detail_check_callback=callbacks.on_detail_check_callback,
            on_item_already_exists=callbacks.on_item_already_exists,
        )
        stopped = callbacks.stop_check() if callbacks.stop_check else False
        return build_task_result(task=task, detail_tasks=processed_tasks, saved_items=saved_items, stopped=stopped)

    def _collect_completed_detail(
        self,
        *,
        task: CrawlTask,
        task_id: str | None,
        detail_task: dict[str, Any],
        pipeline: Any,
        saved_items: list[dict[str, Any]],
        callbacks: CrawlCallbacks,
    ) -> None:
        item = self._build_detail_item(detail_task)
        if not item:
            return

        cleaned = pipeline.process_item(item, task_name=task.name, task_id=task_id)
        if cleaned is not None:
            saved_items.append(cleaned)
            message = f"[{task.name}] 详情完成: code={cleaned.get('code')} source_task_name={cleaned.get('source_task_name')}"
            if callbacks.log_callback:
                callbacks.log_callback(message, "INFO")
            if callbacks.on_item_saved:
                callbacks.on_item_saved(detail_task, cleaned)
            return

        message = f"[{task.name}] 跳过无效数据: code={item.get('code')}"
        if callbacks.log_callback:
            callbacks.log_callback(message, "WARNING")

    def _build_detail_item(self, detail_task: dict[str, Any]) -> dict[str, Any]:
        detail = detail_task.get("detail") or {}
        if not detail:
            return {}
        source_code = detail_task.get("code")
        return {
            **detail,
            "code": detail.get("code") or source_code,
            "source_url": detail_task.get("url"),
            "source_name": detail_task.get("name") or detail.get("source_name"),
            "source_code": source_code,
        }


def get_crawler_engine() -> CrawlerEngine:
    return JavdbCrawlerEngine()
```

- [ ] **Step 4: Run engine tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_engine.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/crawler/runtime/engine.py backend/tests/test_crawler_engine.py
git commit -m "refactor: add backend crawler engine"
```

---

### Task 5: Rewire Runtime Service To Backend Boundaries

**Files:**
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/app/modules/crawler/runtime/source_task_names.py`
- Modify: `backend/tests/test_crawler_worker_service.py`
- Modify: `backend/tests/test_crawler_source_task_names.py`

**Interfaces:**
- Consumes:
  - `get_crawler_engine() -> CrawlerEngine`
  - `CrawlCallbacks`
  - `to_scraper_task(task) -> scraper.tasks.task_schema.CrawlTask`
  - `upsert_movie_with_magnets(session, item_data) -> UUID`
  - `sync_movie_filters(session) -> dict[str, int]`
- Produces: runtime service no longer imports `scraper.services.movie_service` or `scraper.database.repositories`.

- [ ] **Step 1: Update runtime test fakes to implement backend engine interface**

In `backend/tests/test_crawler_worker_service.py`, update fake crawler classes so their method names match `CrawlerEngine`.

For each fake that currently defines:

```python
def crawl_javdb_task(self, task, **kwargs):
```

rename it to:

```python
def crawl_task(self, task, *, task_id=None, crawl_mode="incremental", incremental_threshold=0, callbacks):
```

Inside each renamed method, replace callback access:

```python
kwargs["on_tasks_batch_created"](...)
kwargs["on_item_saved"](...)
kwargs["on_detail_failed"](...)
kwargs["on_item_already_exists"](...)
kwargs["db_check_callback"](...)
kwargs["on_detail_check_callback"](...)
```

with:

```python
callbacks.on_tasks_batch_created(...)
callbacks.on_item_saved(...)
callbacks.on_detail_failed(...)
callbacks.on_item_already_exists(...)
callbacks.db_check_callback(...)
callbacks.on_detail_check_callback(...)
```

Only call a callback when it is not `None`. For example:

```python
if callbacks.on_tasks_batch_created:
    callbacks.on_tasks_batch_created([
        {"code": "AAA-002", "url": "https://javdb.com/v/aaa002", "name": "AAA 002"}
    ])
```

For each fake that currently defines:

```python
def crawl_javdb_detail_tasks(self, task, detail_tasks, **kwargs):
```

rename it to:

```python
def crawl_detail_tasks(self, task, *, detail_tasks, task_id=None, callbacks):
```

Inside each renamed detail method, replace `kwargs[...]` callback usage with `callbacks.<name>`.

- [ ] **Step 2: Update runtime tests to patch backend engine factory**

In `backend/tests/test_crawler_worker_service.py`, replace every line like:

```python
monkeypatch.setattr("scraper.services.movie_service.MovieService", lambda: PersistingMovieServiceStub())
```

with:

```python
monkeypatch.setattr("backend.app.modules.crawler.runtime.service.get_crawler_engine", lambda: PersistingMovieServiceStub())
```

Replace:

```python
monkeypatch.setattr("backend.app.modules.crawler.runtime.service._persist_crawled_item", lambda db, item_data: uuid.uuid4())
```

with:

```python
monkeypatch.setattr("backend.app.modules.crawler.runtime.service.upsert_movie_with_magnets", lambda db, item_data: uuid.uuid4())
```

In `test_execute_run_marks_detail_save_failed_when_movie_persistence_fails`, delete:

```python
from scraper.database.repositories.movie_repository import MovieRepository
```

Replace:

```python
monkeypatch.setattr(MovieRepository, "upsert_movie", lambda self, item: None)
```

with:

```python
def fail_persistence(db, item_data):
    raise RuntimeError("movie repository returned no id")

monkeypatch.setattr("backend.app.modules.crawler.runtime.service.upsert_movie_with_magnets", fail_persistence)
```

- [ ] **Step 3: Run a focused runtime test and verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py::test_execute_run_persists_movie_before_marking_detail_saved -v
```

Expected: FAIL because `backend.app.modules.crawler.runtime.service.get_crawler_engine` is not imported yet.

- [ ] **Step 4: Update runtime service imports**

In `backend/app/modules/crawler/runtime/service.py`, add:

```python
from backend.app.modules.content.movies.persistence import (
    append_source_task_id,
    sync_movie_filters,
    upsert_movie_with_magnets,
)
from backend.app.modules.crawler.runtime.config import read_incremental_threshold_from_conf
from backend.app.modules.crawler.runtime.engine import CrawlCallbacks, get_crawler_engine
from backend.app.modules.crawler.runtime.task_adapter import to_scraper_task
```

- [ ] **Step 5: Remove the old source task append helper**

In `backend/app/modules/crawler/runtime/service.py`, remove `add_source_task_id_for_code` from this import:

```python
from backend.app.modules.crawler.runtime.source_task_names import (
    add_source_task_id_for_code,
    find_existing_movie_codes,
    movie_code_exists,
)
```

The remaining import should be:

```python
from backend.app.modules.crawler.runtime.source_task_names import (
    find_existing_movie_codes,
    movie_code_exists,
)
```

In `backend/app/modules/crawler/runtime/source_task_names.py`, delete:

```python
def add_source_task_id_for_code(db: Session, code: str | None, task_id: uuid.UUID) -> bool:
    ...
```

Also remove the now-unused `import uuid` from that file.

In `backend/tests/test_crawler_source_task_names.py`, remove `add_source_task_id_for_code` from the import list and delete `test_add_source_task_id_for_code_appends_once`. The equivalent behavior is now covered by `backend/tests/test_movie_persistence.py::test_append_source_task_id_adds_unique_id`.

- [ ] **Step 6: Replace incremental threshold helper**

Delete the existing `_read_incremental_threshold_from_conf` function from `backend/app/modules/crawler/runtime/service.py`.

Replace:

```python
incremental_threshold = _read_incremental_threshold_from_conf()
```

with:

```python
incremental_threshold = read_incremental_threshold_from_conf()
```

- [ ] **Step 7: Replace persistence helper**

Delete the `_persist_crawled_item` function from `backend/app/modules/crawler/runtime/service.py`.

In `on_item_saved`, replace:

```python
movie_id = _persist_crawled_item(db, item_data_with_task_ids)
```

with:

```python
movie_id = upsert_movie_with_magnets(db, item_data_with_task_ids)
```

In `on_tasks_batch_created`, replace:

```python
if add_source_task_id_for_code(db, item.get("code"), task.id):
```

with:

```python
if append_source_task_id(db, item.get("code"), task.id):
```

In `on_item_already_exists`, replace:

```python
add_source_task_id_for_code(db, code, task.id)
```

with:

```python
append_source_task_id(db, code, task.id)
```

Keep `find_existing_movie_codes` and `movie_code_exists` imports from `source_task_names.py` for dedupe checks in this task.

- [ ] **Step 8: Replace MovieService orchestration**

In `_execute_run`, before engine execution add:

```python
engine_task = to_scraper_task(task)
engine = get_crawler_engine()
```

Replace:

```python
from scraper.services.movie_service import MovieService
movie_service = MovieService()
```

with no code; the engine is already created above.

Replace:

```python
result = movie_service.crawl_javdb_detail_tasks(
    task,
    detail_tasks=[detail_row_to_task_info(detail) for detail in restartable_existing_details],
    task_id=str(run.task_id) if run.task_id else None,
    on_item_saved=on_item_saved,
    on_detail_failed=on_detail_failed,
    on_item_already_exists=on_item_already_exists,
    log_callback=log_callback,
    on_detail_check_callback=on_detail_check_callback,
    stop_check=lambda: runtime.is_stop_requested(str(run.id)),
)
```

with:

```python
result = engine.crawl_detail_tasks(
    engine_task,
    detail_tasks=[detail_row_to_task_info(detail) for detail in restartable_existing_details],
    task_id=str(run.task_id) if run.task_id else None,
    callbacks=CrawlCallbacks(
        on_item_saved=on_item_saved,
        on_detail_failed=on_detail_failed,
        on_item_already_exists=on_item_already_exists,
        log_callback=log_callback,
        on_detail_check_callback=on_detail_check_callback,
        stop_check=lambda: runtime.is_stop_requested(str(run.id)),
    ),
)
```

Replace:

```python
result = movie_service.crawl_javdb_task(
    task,
    task_id=str(run.task_id) if run.task_id else None,
    crawl_mode=run.crawl_mode,
    incremental_threshold=incremental_threshold,
    on_tasks_batch_created=on_tasks_batch_created,
    on_item_saved=on_item_saved,
    on_detail_failed=on_detail_failed,
    on_item_already_exists=on_item_already_exists,
    log_callback=log_callback,
    db_check_callback=db_check_callback,
    on_detail_check_callback=on_detail_check_callback,
    stop_check=lambda: runtime.is_stop_requested(str(run.id)),
)
```

with:

```python
result = engine.crawl_task(
    engine_task,
    task_id=str(run.task_id) if run.task_id else None,
    crawl_mode=run.crawl_mode,
    incremental_threshold=incremental_threshold,
    callbacks=CrawlCallbacks(
        on_tasks_batch_created=on_tasks_batch_created,
        on_item_saved=on_item_saved,
        on_detail_failed=on_detail_failed,
        on_item_already_exists=on_item_already_exists,
        log_callback=log_callback,
        db_check_callback=db_check_callback,
        on_detail_check_callback=on_detail_check_callback,
        stop_check=lambda: runtime.is_stop_requested(str(run.id)),
    ),
)
```

- [ ] **Step 9: Replace filter sync import**

Replace:

```python
from scraper.database.repositories.filter_repository import sync_movie_filters

sync_result = sync_movie_filters(db)
```

with:

```python
sync_result = sync_movie_filters(db)
```

because `sync_movie_filters` is now imported from backend persistence at module top.

- [ ] **Step 10: Remove obsolete ImportError fallback**

Delete this block from `_execute_run`:

```python
except ImportError:
    logger.warning("MovieService not available, marking run as completed with stub")
    append_run_log_for_run(db, run, "MovieService 不可用，使用空结果完成运行", "WARNING")
    run.result = {"total_tasks": 0, "completed_tasks": 0, "failed_tasks": 0}
    run.status = "completed"
except Exception as exc:
    raise
```

Replace it with:

```python
except Exception:
    raise
```

- [ ] **Step 11: Run runtime tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 12: Run source task helper tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_source_task_names.py -v
```

Expected: PASS.

- [ ] **Step 13: Verify runtime active code no longer imports scraper service/database or duplicate append helper**

Run:

```bash
rg -n "scraper\.services\.movie_service|scraper\.database\.repositories|MovieService|MovieRepository|MovieMagnetRepository|add_source_task_id_for_code" backend/app/modules/crawler/runtime/service.py backend/app/modules/crawler/runtime/source_task_names.py backend/tests/test_crawler_worker_service.py backend/tests/test_crawler_source_task_names.py
```

Expected: no output.

- [ ] **Step 14: Commit**

```bash
git add backend/app/modules/crawler/runtime/service.py backend/app/modules/crawler/runtime/source_task_names.py backend/tests/test_crawler_worker_service.py backend/tests/test_crawler_source_task_names.py
git commit -m "refactor: route crawler runtime through backend engine"
```

---

### Task 6: Remove Scraper Service And Database Repository Modules

**Files:**
- Delete: `scraper/services/movie_service.py`
- Delete: `scraper/services/movie_result.py`
- Delete: `scraper/services/__init__.py`
- Delete: `scraper/database/repositories/filter_repository.py`
- Delete: `scraper/database/repositories/movie_magnet_repository.py`
- Delete: `scraper/database/repositories/movie_repository.py`
- Delete: `scraper/database/repositories/__init__.py`
- Delete: `scraper/database/__init__.py`

**Interfaces:**
- Consumes: backend engine and persistence modules created in earlier tasks.
- Produces: scraper package no longer owns orchestration or database persistence modules.

- [ ] **Step 1: Verify no active imports remain**

Run:

```bash
rg -n "scraper\.services|scraper\.database" backend/app backend/tests scraper/tests scraper -g '*.py'
```

Expected before deletion: only `scraper/services/*` and `scraper/database/*` files themselves may match. If `scraper/tests/test_movie_result.py` still imports `scraper.services.movie_result`, complete Task 3 Step 6 first.

- [ ] **Step 2: Delete scraper service and database modules**

Run:

```bash
rm scraper/services/movie_service.py
rm scraper/services/movie_result.py
rm scraper/services/__init__.py
rm scraper/database/repositories/filter_repository.py
rm scraper/database/repositories/movie_magnet_repository.py
rm scraper/database/repositories/movie_repository.py
rm scraper/database/repositories/__init__.py
rm scraper/database/__init__.py
```

- [ ] **Step 3: Verify references are gone**

Run:

```bash
rg -n "scraper\.services|scraper\.database" backend/app backend/tests scraper/tests scraper -g '*.py'
```

Expected: no output.

- [ ] **Step 4: Run backend and scraper focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_movie_persistence.py backend/tests/test_crawler_engine.py backend/tests/test_crawler_runtime_adapters.py scraper/tests -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -u scraper/services scraper/database
git add scraper/tests/test_movie_result.py
git commit -m "refactor: remove scraper persistence and service modules"
```

---

### Task 7: Final Verification

**Files:**
- Modify only if previous tasks expose integration failures.

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: verified crawler runtime decoupling.

- [ ] **Step 1: Run active reference checks**

Run:

```bash
rg -n "backend\.app\.modules\.crawler\.events|/api/crawler/stream|scraper\.services\.movie_service|scraper\.database\.repositories" backend/app backend/tests frontend/src scraper -g '*.py' -g '*.ts' -g '*.tsx'
```

Expected: no output.

- [ ] **Step 2: Run backend full test suite**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 3: Run scraper tests**

Run:

```bash
source .venv/bin/activate
python -m pytest scraper/tests -v
```

Expected: PASS.

- [ ] **Step 4: Run frontend tests**

Run:

```bash
cd frontend
npm test -- --run
```

Expected: PASS.

- [ ] **Step 5: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 6: Run frontend lint**

Run:

```bash
cd frontend
npm run lint
```

Expected: PASS.

- [ ] **Step 7: Inspect final status**

Run:

```bash
git status --short
```

Expected: no unstaged tracked changes from this plan. Pre-existing untracked plan files may still appear and should not be staged unless the user explicitly asks.
