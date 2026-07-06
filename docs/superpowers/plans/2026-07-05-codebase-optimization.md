# Codebase Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up confirmed dead code, remove one unused legacy API, and extract low-risk backend movie/storage boundaries without changing current user-facing behavior.

**Architecture:** Keep the current FastAPI and React module layout, but move movie query/serialization/provider lifecycle concerns out of large routers. Delete only code proven unused by current frontend/runtime references; because `/api/crawler/stream` has backend tests, mark it deprecated instead of deleting it in this phase.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0, pytest, React 19, Vite 8, TypeScript 6, Vitest, ESLint.

## Global Constraints

- Keep scope anchored to the Media Forge refactor and optimization of the original `jav-scrapling` project.
- Do not redesign the UI.
- Do not change database schema or Alembic migrations.
- Do not migrate all frontend data loading to TanStack Query in this phase.
- Do not rewrite the storage worker pipeline.
- Do not fully decouple backend crawler runtime from the `scraper` package in this phase.
- Preserve current frontend routes, screens, refresh behavior, and request semantics.
- Run backend full pytest and frontend test/build/lint before completion.

---

## File Structure

### Create

- `backend/app/modules/content/movies/queries.py`
  - Owns movie filter value lookup, Python-side movie matching, sorting, and pagination.
- `backend/app/modules/content/movies/serializers.py`
  - Owns movie and magnet response payload assembly.
- `backend/app/modules/content/movies/storage_sync_service.py`
  - Owns movie storage status sync orchestration and realtime publication.
- `backend/tests/test_removed_legacy_apis.py`
  - Locks the removed `/api/movies` route behavior.
- `backend/tests/test_content_movie_serializers.py`
  - Locks movie payload serialization outside the router.

### Modify

- `backend/app/main.py`
  - Remove `/api/movies` router import/include.
  - Keep `/api/crawler/stream` include because existing tests cover it.
- `backend/app/modules/crawler/events/router.py`
  - Mark `/api/crawler/stream` as deprecated in OpenAPI metadata.
- `backend/tests/test_crawler_sse_events.py`
  - Add OpenAPI deprecation coverage for `/api/crawler/stream`.
- `backend/app/modules/content/movies/router.py`
  - Delegate filtering, serialization, and storage sync orchestration.
- `backend/app/modules/storage/config/service.py`
  - Add a provider lifecycle context manager.
- `backend/tests/test_storage_config_api.py`
  - Add lifecycle close-on-success and close-on-error tests.
- `frontend/src/api/movie/index.ts`
  - Remove unreferenced `getMovies`, `getMovie`, and `fetchTaskNames` exports.

### Delete

- `backend/app/modules/movies/router.py`
- `frontend/src/lib/axios.ts`
- `frontend/src/api/crawler/sse.ts`
- `frontend/src/hooks/useCrawlerSSE/index.ts`

---

### Task 1: Frontend Dead Code Cleanup

**Files:**
- Delete: `frontend/src/lib/axios.ts`
- Delete: `frontend/src/api/crawler/sse.ts`
- Delete: `frontend/src/hooks/useCrawlerSSE/index.ts`
- Modify: `frontend/src/api/movie/index.ts`

**Interfaces:**
- Consumes: current frontend API usage through `frontend/src/request` and `frontend/src/realtime/eventSourceClient.ts`.
- Produces: `frontend/src/api/movie/index.ts` exports only active movie API helpers:
  - `fetchMovies(params: MovieQueryParams): Promise<MovieListResponse>`
  - `fetchMovie(id: string): Promise<Movie>`
  - `syncMovieStorageStatus(payload: MovieStorageSyncPayload): Promise<MovieStorageSyncResponse>`
  - `deleteMovies(payload: MovieDeletePayload): Promise<MovieDeleteResult>`
  - `fetchFilters(type: FilterType): Promise<string[]>`
  - `fetchMovieFilterConfig(): Promise<MovieFilterConfigResponse>`
  - `updateMovieFilterConfig(filters: Record<string, FilterItemConfig>): Promise<{ success: boolean }>`

- [ ] **Step 1: Verify current legacy frontend references**

Run:

```bash
rg -n "lib/axios|api/crawler/sse|useCrawlerSSE|fetchTaskNames|getMovies\(|getMovie\(" frontend/src
```

Expected before cleanup: output includes only the legacy files themselves and the unused exports in `frontend/src/api/movie/index.ts`.

- [ ] **Step 2: Delete legacy frontend files**

Remove:

```bash
rm frontend/src/lib/axios.ts
rm frontend/src/api/crawler/sse.ts
rm -r frontend/src/hooks/useCrawlerSSE
```

- [ ] **Step 3: Remove stale movie API exports**

In `frontend/src/api/movie/index.ts`, delete these functions exactly:

```ts
export function getMovies(params?: MovieQueryParams): Promise<PaginatedMovies> {
  return request.get<PaginatedMovies>(BASE_URL, params)
}

export function getMovie(id: string): Promise<Movie> {
  return fetchMovie(id)
}

export function fetchTaskNames(): Promise<{ name: string }[]> {
  return request.get<{ name: string }[]>(`${BASE_URL}/task-names`)
}
```

Keep `interface PaginatedMovies` because `fetchMovies` still uses it.

- [ ] **Step 4: Verify references are gone**

Run:

```bash
rg -n "lib/axios|api/crawler/sse|useCrawlerSSE|fetchTaskNames|getMovies\(|getMovie\(" frontend/src
```

Expected: no output.

- [ ] **Step 5: Run focused frontend verification**

Run:

```bash
cd frontend
npm test -- --run frontend/src/pages/content/movies/__tests__/movie-delete.test.tsx frontend/src/pages/content/movies/__tests__/movie-storage-sync.test.tsx
npm run build
```

Expected: Vitest passes and TypeScript/Vite build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/movie/index.ts
git add -u frontend/src/lib/axios.ts frontend/src/api/crawler/sse.ts frontend/src/hooks/useCrawlerSSE
git commit -m "refactor: remove unused frontend legacy clients"
```

---

### Task 2: Remove Unused Backend `/api/movies` Legacy Route

**Files:**
- Create: `backend/tests/test_removed_legacy_apis.py`
- Modify: `backend/app/main.py`
- Delete: `backend/app/modules/movies/router.py`

**Interfaces:**
- Consumes: current authenticated test client fixture from `backend/tests/conftest.py`.
- Produces: no mounted `/api/movies` route. Current `/api/content/movies` remains unchanged.

- [ ] **Step 1: Write failing route removal test**

Create `backend/tests/test_removed_legacy_apis.py`:

```python
from http import HTTPStatus

from fastapi.testclient import TestClient


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_legacy_movies_route_is_removed(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)

    response = client.get("/api/movies", headers=headers)

    assert response.status_code == HTTPStatus.NOT_FOUND
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_removed_legacy_apis.py::test_legacy_movies_route_is_removed -v
```

Expected: FAIL because `/api/movies` is currently mounted and returns a non-404 response for authenticated requests.

- [ ] **Step 3: Remove route import and include**

In `backend/app/main.py`, delete:

```python
from backend.app.modules.movies.router import router as movies_router
```

Also delete:

```python
app.include_router(movies_router)
```

- [ ] **Step 4: Delete legacy router file**

Run:

```bash
rm backend/app/modules/movies/router.py
rmdir backend/app/modules/movies
```

If `rmdir` fails because `__pycache__` exists, remove only the tracked Python file and leave ignored cache files alone:

```bash
rm -f backend/app/modules/movies/router.py
```

- [ ] **Step 5: Verify route removal test passes**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_removed_legacy_apis.py::test_legacy_movies_route_is_removed -v
```

Expected: PASS.

- [ ] **Step 6: Verify no active code references remain**

Run:

```bash
rg -n "/api/movies|modules\.movies|movies_router" backend/app backend/tests frontend/src
```

Expected: only `backend/tests/test_removed_legacy_apis.py` may mention `/api/movies`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/tests/test_removed_legacy_apis.py
git add -u backend/app/modules/movies/router.py
git commit -m "refactor: remove legacy movies route"
```

---

### Task 3: Mark Old Crawler SSE Route Deprecated

**Files:**
- Modify: `backend/app/modules/crawler/events/router.py`
- Modify: `backend/tests/test_crawler_sse_events.py`

**Interfaces:**
- Consumes: existing `/api/crawler/stream` behavior and tests.
- Produces: `/api/crawler/stream` remains available but is marked deprecated in OpenAPI.

- [ ] **Step 1: Add failing deprecation test**

Append this test to `backend/tests/test_crawler_sse_events.py` inside `class TestSSERouter`:

```python
    def test_stream_endpoint_is_marked_deprecated(self, client: TestClient):
        schema = client.get("/openapi.json").json()

        operation = schema["paths"]["/api/crawler/stream"]["get"]

        assert operation["deprecated"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_sse_events.py::TestSSERouter::test_stream_endpoint_is_marked_deprecated -v
```

Expected: FAIL with `KeyError: 'deprecated'` or assertion failure because the route is not marked deprecated yet.

- [ ] **Step 3: Mark route deprecated**

In `backend/app/modules/crawler/events/router.py`, change:

```python
@router.get("/api/crawler/stream")
```

to:

```python
@router.get("/api/crawler/stream", deprecated=True)
```

Also replace the module docstring first paragraph with:

```python
"""Deprecated SSE streaming endpoint for crawler real-time events.

This endpoint is retained for backward compatibility because backend tests still
cover it. Current frontend pages use the unified ``/api/events/stream`` realtime
channel instead.
"""
```

- [ ] **Step 4: Run old SSE tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_sse_events.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/crawler/events/router.py backend/tests/test_crawler_sse_events.py
git commit -m "docs: mark crawler SSE route deprecated"
```

---

### Task 4: Extract Content Movie Serializers

**Files:**
- Create: `backend/app/modules/content/movies/serializers.py`
- Create: `backend/tests/test_content_movie_serializers.py`
- Modify: `backend/app/modules/content/movies/router.py`

**Interfaces:**
- Consumes:
  - `shared.database.models.content.Movie`
  - optional SQLAlchemy `Session`
  - `backend.app.modules.content.movies.storage_status.normalized_movie_storage_status`
- Produces:
  - `serialize_movie(movie: Movie, *, include_magnets: bool = False, db: Session | None = None) -> dict`
  - `movie_storage_locations(movie: Movie, db: Session | None) -> list[str]`

- [ ] **Step 1: Write failing serializer tests**

Create `backend/tests/test_content_movie_serializers.py`:

```python
import uuid
from datetime import date
from decimal import Decimal

from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.content.movies.serializers import serialize_movie
from backend.tests.conftest import TestingSessionLocal
from shared.database.models.content import Movie, MovieMagnet


def test_serialize_movie_includes_magnets_and_storage_locations(admin_user) -> None:
    session = TestingSessionLocal()
    task_id = uuid.uuid4()
    movie = Movie(
        code="AAA-001",
        source_url="https://javdb.com/v/aaa",
        source_name="测试电影",
        release_date=date(2026, 1, 1),
        duration=120,
        director="导演A",
        maker="片商A",
        series="系列A",
        rating=Decimal("4.5"),
        actors=["演员A"],
        tags=["标签A"],
        source_task_ids=[task_id],
        storage_summary={"storage_status": "stored"},
    )
    session.add(movie)
    session.add(CrawlTask(id=task_id, name="任务A", owner_id=admin_user.id, storage_location="/target/A"))
    session.flush()
    session.add(
        MovieMagnet(
            movie_id=movie.id,
            magnet_url="magnet:?xt=urn:btih:abc",
            dedupe_key="abc",
            name="磁力A",
            selected=True,
        )
    )
    session.commit()

    payload = serialize_movie(movie, include_magnets=True, db=session)

    assert payload["id"] == str(movie.id)
    assert payload["code"] == "AAA-001"
    assert payload["storage_status"] == "stored"
    assert payload["storage_locations"] == ["/target/A"]
    assert payload["magnets"][0]["magnet_url"].startswith("magnet:")
    assert payload["selected_magnet_dedupe_key"] == "abc"

    session.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movie_serializers.py -v
```

Expected: FAIL because `backend.app.modules.content.movies.serializers` does not exist.

- [ ] **Step 3: Create serializer module**

Create `backend/app/modules/content/movies/serializers.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
from shared.database.models.content import Movie


def movie_storage_locations(movie: Movie, db: Session | None) -> list[str]:
    source_task_ids = [str(tid) for tid in (movie.source_task_ids or [])]
    if db is None or not source_task_ids:
        return []

    from backend.app.models.crawl_task import CrawlTask

    locations: list[str] = []
    for task_id_text in source_task_ids:
        try:
            task_id = uuid.UUID(task_id_text)
        except (TypeError, ValueError):
            continue
        crawl_task = db.get(CrawlTask, task_id)
        if crawl_task and crawl_task.storage_location and crawl_task.storage_location not in locations:
            locations.append(crawl_task.storage_location)
    return locations


def serialize_movie(movie: Movie, *, include_magnets: bool = False, db: Session | None = None) -> dict:
    source_task_ids = [str(tid) for tid in (movie.source_task_ids or [])]
    payload = {
        "_id": str(movie.id),
        "id": str(movie.id),
        "code": movie.code or "",
        "source_url": movie.source_url or "",
        "source_name": movie.source_name or "",
        "cover": movie.cover or "",
        "release_date": movie.release_date.isoformat() if movie.release_date else None,
        "duration": movie.duration or 0,
        "director": movie.director or "",
        "maker": movie.maker or "",
        "series": movie.series or "",
        "rating": float(movie.rating) if movie.rating is not None else None,
        "actors": list(movie.actors or []),
        "tags": list(movie.tags or []),
        "source_task_ids": source_task_ids,
        "storage_locations": movie_storage_locations(movie, db),
        "marked": bool(movie.marked),
        "storage_status": normalized_movie_storage_status(movie),
        "storage_summary": movie.storage_summary or {},
        "raw_detail": movie.raw_detail or {},
        "created_at": movie.created_at.isoformat() if movie.created_at else None,
        "updated_at": movie.updated_at.isoformat() if movie.updated_at else None,
    }
    if include_magnets:
        magnets = list(movie.magnets or [])
        payload["magnets"] = [
            {
                "_id": str(magnet.id),
                "id": str(magnet.id),
                "movie_id": str(magnet.movie_id),
                "magnet": magnet.magnet_url,
                "magnet_url": magnet.magnet_url,
                "name": magnet.name or "",
                "title": magnet.name or "",
                "size": magnet.size_text or "",
                "size_mb": float(magnet.size_mb or 0),
                "size_text": magnet.size_text or "",
                "file_count": magnet.file_count,
                "file_text": magnet.file_text or "",
                "tags": magnet.tags or [],
                "has_chinese_sub": bool(magnet.has_chinese_sub),
                "date": magnet.date or "",
                "dedupe_key": magnet.dedupe_key or "",
                "weight": magnet.weight or 0,
                "selected": bool(magnet.selected),
            }
            for magnet in magnets
        ]
        selected = next((magnet for magnet in magnets if magnet.selected), None)
        payload["selected_magnet_dedupe_key"] = selected.dedupe_key if selected else None
    return payload
```

- [ ] **Step 4: Replace router helper usage**

In `backend/app/modules/content/movies/router.py`:

1. Add import:

```python
from backend.app.modules.content.movies.serializers import serialize_movie
```

2. Delete the existing `_movie_payload` function.

3. Replace each call:

```python
_movie_payload(movie, include_magnets=True, db=db)
```

with:

```python
serialize_movie(movie, include_magnets=True, db=db)
```

- [ ] **Step 5: Run focused backend tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movie_serializers.py tests/test_content_movies_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/content/movies/serializers.py backend/app/modules/content/movies/router.py backend/tests/test_content_movie_serializers.py
git commit -m "refactor: extract movie serializers"
```

---

### Task 5: Extract Content Movie Query Helpers

**Files:**
- Create: `backend/app/modules/content/movies/queries.py`
- Modify: `backend/app/modules/content/movies/router.py`
- Modify: `backend/tests/test_content_movies_api.py`

**Interfaces:**
- Consumes:
  - `Movie`
  - `MovieFilter`
  - SQLAlchemy `Session`
- Produces:
  - `VALID_FILTER_TYPES: set[str]`
  - `ALLOWED_SORT_FIELDS: dict[str, Any]`
  - `MovieListFilters` dataclass
  - `list_filter_values(db: Session, filter_type: str) -> list[str]`
  - `list_movies_page(db: Session, filters: MovieListFilters, *, sort_by: str, sort_order: int | str, page: int, limit: int, skip: int | None) -> tuple[list[Movie], int]`

- [ ] **Step 1: Add API regression test for query extraction**

Append this test to `backend/tests/test_content_movies_api.py`:

```python
def test_movie_list_query_helpers_preserve_sort_and_storage_filter(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    seed_filter_movies()

    response = client.get(
        "/api/content/movies?storage_status=stored&sort_by=rating&sort_order=-1&page=1&limit=10",
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["code"] == "AAA-100"
```

- [ ] **Step 2: Run regression test before refactor**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movies_api.py::test_movie_list_query_helpers_preserve_sort_and_storage_filter -v
```

Expected: PASS before refactor. This locks behavior before moving code.

- [ ] **Step 3: Create query helper module**

Create `backend/app/modules/content/movies/queries.py` by moving the existing router logic into these exact public names:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
from shared.database.models.content import Movie, MovieFilter


ALLOWED_SORT_FIELDS = {
    "created_at": Movie.created_at,
    "updated_at": Movie.updated_at,
    "code": Movie.code,
    "source_name": Movie.source_name,
    "release_date": Movie.release_date,
    "rating": Movie.rating,
}

VALID_FILTER_TYPES = {"actor", "tag", "director", "maker", "series"}


@dataclass(frozen=True)
class MovieListFilters:
    search: str | None = None
    source_task_id: str | None = None
    rating_min: float | None = None
    rating_max: float | None = None
    actors: str | None = None
    actors_not: str | None = None
    actors_count_min: int | None = None
    actors_count_max: int | None = None
    tags: str | None = None
    tags_not: str | None = None
    director: str | None = None
    director_not: str | None = None
    maker: str | None = None
    maker_not: str | None = None
    series: str | None = None
    series_not: str | None = None
    release_date_from: str | None = None
    release_date_to: str | None = None
    created_at_from: str | None = None
    created_at_to: str | None = None
    storage_status: str | None = None


def split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()] if value else []


def unique_sorted(values: list[str | None]) -> list[str]:
    return sorted({value for value in values if value})


def sqlite_filter_values(db: Session, filter_type: str) -> list[str]:
    movies = db.query(Movie).all()
    if filter_type == "actor":
        return unique_sorted([actor for movie in movies for actor in (movie.actors or [])])
    if filter_type == "tag":
        return unique_sorted([tag for movie in movies for tag in (movie.tags or [])])
    return unique_sorted([getattr(movie, filter_type) for movie in movies])


def cached_filter_values(db: Session, filter_type: str) -> list[str]:
    return list(db.scalars(
        select(MovieFilter.name)
        .where(MovieFilter.type == filter_type, MovieFilter.name != "")
        .distinct()
        .order_by(MovieFilter.name.asc())
    ).all())


def list_filter_values(db: Session, filter_type: str) -> list[str]:
    cached_names = cached_filter_values(db, filter_type)
    if cached_names:
        return cached_names

    if db.bind.dialect.name == "sqlite":
        return sqlite_filter_values(db, filter_type)
    if filter_type == "actor":
        names = db.scalars(select(func.unnest(Movie.actors).label("name")).distinct().order_by("name")).all()
    elif filter_type == "tag":
        names = db.scalars(select(func.unnest(Movie.tags).label("name")).distinct().order_by("name")).all()
    else:
        column = getattr(Movie, filter_type)
        names = db.scalars(select(column).where(column != "", column.is_not(None)).distinct().order_by(column.asc())).all()
    return [name for name in names if name]


def movie_matches(movie: Movie, filters: MovieListFilters) -> bool:
    if filters.search:
        needle = filters.search.lower()
        haystack = " ".join([movie.code or "", movie.source_name or "", movie.director or "", movie.maker or "", movie.series or ""]).lower()
        if needle not in haystack:
            return False
    if filters.source_task_id:
        task_ids = [str(tid) for tid in (movie.source_task_ids or [])]
        if filters.source_task_id not in task_ids:
            return False
    if filters.rating_min is not None and (movie.rating is None or float(movie.rating) < filters.rating_min):
        return False
    if filters.rating_max is not None and (movie.rating is None or float(movie.rating) > filters.rating_max):
        return False
    movie_actors = set(movie.actors or [])
    movie_tags = set(movie.tags or [])
    if split_csv(filters.actors) and not set(split_csv(filters.actors)).issubset(movie_actors):
        return False
    if split_csv(filters.actors_not) and set(split_csv(filters.actors_not)).intersection(movie_actors):
        return False
    if split_csv(filters.tags) and not set(split_csv(filters.tags)).issubset(movie_tags):
        return False
    if split_csv(filters.tags_not) and set(split_csv(filters.tags_not)).intersection(movie_tags):
        return False
    if split_csv(filters.director) and movie.director not in split_csv(filters.director):
        return False
    if split_csv(filters.director_not) and movie.director in split_csv(filters.director_not):
        return False
    if split_csv(filters.maker) and movie.maker not in split_csv(filters.maker):
        return False
    if split_csv(filters.maker_not) and movie.maker in split_csv(filters.maker_not):
        return False
    if split_csv(filters.series) and movie.series not in split_csv(filters.series):
        return False
    if split_csv(filters.series_not) and movie.series in split_csv(filters.series_not):
        return False
    if filters.actors_count_min is not None and len(movie.actors or []) < filters.actors_count_min:
        return False
    if filters.actors_count_max is not None and len(movie.actors or []) > filters.actors_count_max:
        return False
    if filters.release_date_from and (movie.release_date is None or movie.release_date.isoformat() < filters.release_date_from):
        return False
    if filters.release_date_to and (movie.release_date is None or movie.release_date.isoformat() > filters.release_date_to):
        return False
    if filters.created_at_from and (movie.created_at is None or movie.created_at.date().isoformat() < filters.created_at_from):
        return False
    if filters.created_at_to and (movie.created_at is None or movie.created_at.date().isoformat() > filters.created_at_to):
        return False
    if filters.storage_status and normalized_movie_storage_status(movie) != filters.storage_status:
        return False
    return True


def normalize_sort_order(sort_order: int | str) -> int:
    try:
        normalized = int(sort_order)
    except (TypeError, ValueError):
        normalized = 1 if sort_order == "asc" else -1
    return normalized if normalized in (-1, 1) else -1


def list_movies_page(
    db: Session,
    filters: MovieListFilters,
    *,
    sort_by: str,
    sort_order: int | str,
    page: int,
    limit: int,
    skip: int | None,
) -> tuple[list[Movie], int]:
    rows = db.query(Movie).options(selectinload(Movie.magnets)).all()
    filtered = [movie for movie in rows if movie_matches(movie, filters)]

    normalized_sort_order = normalize_sort_order(sort_order)
    sort_column = sort_by if sort_by in ALLOWED_SORT_FIELDS else "created_at"
    filtered.sort(key=lambda movie: getattr(movie, sort_column) is None)
    filtered.sort(key=lambda movie: getattr(movie, sort_column) or "", reverse=normalized_sort_order == -1)

    total = len(filtered)
    offset = skip if skip is not None else (page - 1) * limit
    return filtered[offset:offset + limit], total
```

- [ ] **Step 4: Update router to delegate query work**

In `backend/app/modules/content/movies/router.py`, add:

```python
from backend.app.modules.content.movies.queries import (
    VALID_FILTER_TYPES,
    MovieListFilters,
    list_filter_values,
    list_movies_page,
)
```

Delete these router-local items:

```python
ALLOWED_SORT_FIELDS
VALID_FILTER_TYPES
_unique_sorted
_sqlite_filter_values
_cached_filter_values
_split_csv
_movie_matches_python
```

Replace the body of `list_filters` after the type validation with:

```python
    return success(data=list_filter_values(db, type))
```

Replace the filtering/sorting/pagination body of `list_movies` with:

```python
    search_text = search or keyword
    rows, total = list_movies_page(
        db,
        MovieListFilters(
            search=search_text,
            source_task_id=source_task_id,
            rating_min=rating_min,
            rating_max=rating_max,
            actors=actors,
            actors_not=actors_not,
            actors_count_min=actors_count_min,
            actors_count_max=actors_count_max,
            tags=tags,
            tags_not=tags_not,
            director=director,
            director_not=director_not,
            maker=maker,
            maker_not=maker_not,
            series=series,
            series_not=series_not,
            release_date_from=release_date_from,
            release_date_to=release_date_to,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            storage_status=storage_status,
        ),
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        limit=limit,
        skip=skip,
    )
    return paginated(rows=[serialize_movie(movie, include_magnets=True, db=db) for movie in rows], total=total)
```

In `sync_movie_storage_statuses`, replace the repeated `_movie_matches_python` call with `MovieListFilters(**filters)` and `movie_matches` only if the service extraction has not yet moved that code. Prefer Task 7 for that final move.

- [ ] **Step 5: Run focused API tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movies_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/content/movies/queries.py backend/app/modules/content/movies/router.py backend/tests/test_content_movies_api.py
git commit -m "refactor: extract movie query helpers"
```

---

### Task 6: Add Storage Provider Lifecycle Helper

**Files:**
- Modify: `backend/app/modules/storage/config/service.py`
- Modify: `backend/tests/test_storage_config_api.py`

**Interfaces:**
- Consumes: `StorageConfigService.get_raw_config()`, `CloudDriveClientFactory.create(config)`, `CloudDrive2Gateway`.
- Produces: `StorageConfigService.open_provider() -> Iterator[tuple[dict[str, Any], CloudDrive2Gateway]]`.

- [ ] **Step 1: Add provider lifecycle tests**

Append this test code to `backend/tests/test_storage_config_api.py`:

```python
def test_storage_config_service_open_provider_closes_client(monkeypatch, tmp_path) -> None:
    from backend.app.modules.storage.config.service import StorageConfigService
    from shared.runtime_config import RuntimeConfigPaths

    class FakeClient:
        closed = False

        def close(self):
            self.closed = True

    class FakeFactory:
        client = FakeClient()

        def normalize_host(self, value: str) -> str:
            return value

        def create(self, config):
            return self.client

    class FakeGateway:
        def __init__(self, client):
            self.client = client

    paths = RuntimeConfigPaths(
        base_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
    )
    service = StorageConfigService(paths=paths, provider_factory=FakeFactory(), gateway_class=FakeGateway)

    with service.open_provider() as (config, provider):
        assert config["grpc_host"]
        assert provider.client is service.provider_factory.client

    assert service.provider_factory.client.closed is True


def test_storage_config_service_open_provider_closes_client_on_error(monkeypatch, tmp_path) -> None:
    from backend.app.modules.storage.config.service import StorageConfigService
    from shared.runtime_config import RuntimeConfigPaths

    class FakeClient:
        closed = False

        def close(self):
            self.closed = True

    class FakeFactory:
        client = FakeClient()

        def normalize_host(self, value: str) -> str:
            return value

        def create(self, config):
            return self.client

    class FakeGateway:
        def __init__(self, client):
            self.client = client

    paths = RuntimeConfigPaths(
        base_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
    )
    service = StorageConfigService(paths=paths, provider_factory=FakeFactory(), gateway_class=FakeGateway)

    try:
        with service.open_provider():
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert service.provider_factory.client.closed is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_config_api.py::test_storage_config_service_open_provider_closes_client tests/test_storage_config_api.py::test_storage_config_service_open_provider_closes_client_on_error -v
```

Expected: FAIL because `open_provider` does not exist.

- [ ] **Step 3: Implement lifecycle helper**

In `backend/app/modules/storage/config/service.py`, add imports:

```python
from collections.abc import Iterator
from contextlib import contextmanager
```

Inside `class StorageConfigService`, add:

```python
    @contextmanager
    def open_provider(self) -> Iterator[tuple[dict[str, Any], CloudDrive2Gateway]]:
        config = self.get_raw_config()
        client = self.provider_factory.create(config)
        try:
            yield config, self.gateway_class(client)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
```

- [ ] **Step 4: Run storage config tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_config_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/storage/config/service.py backend/tests/test_storage_config_api.py
git commit -m "refactor: add storage provider lifecycle helper"
```

---

### Task 7: Extract Movie Storage Sync Service

**Files:**
- Create: `backend/app/modules/content/movies/storage_sync_service.py`
- Modify: `backend/app/modules/content/movies/router.py`
- Modify: `backend/app/modules/content/movies/queries.py`
- Modify: `backend/tests/test_content_movies_api.py`

**Interfaces:**
- Consumes:
  - `StorageConfigService.open_provider()`
  - `sync_movie_storage_status`
  - `publish_movie_storage_updated`
  - `list_movies_page`
- Produces:
  - `MovieStorageSyncResultPayload` dataclass with `to_dict() -> dict`
  - `sync_movies_storage_statuses(db: Session, *, user_id: str, movies: list[Movie], config_service: StorageConfigService | None = None) -> MovieStorageSyncResultPayload`
  - `select_movies_for_storage_sync(db: Session, *, movie_ids: list[uuid.UUID] | None, filters: dict) -> list[Movie]`

- [ ] **Step 1: Add regression test for storage sync close-on-error path**

Append this test to `backend/tests/test_content_movies_api.py`:

```python
def test_movie_storage_sync_closes_provider_client_on_sync_error(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    movie_id = seed_movie()

    class FakeClient:
        closed = False

        def close(self):
            self.closed = True

    fake_client = FakeClient()

    class FakeFactory:
        def normalize_host(self, value: str) -> str:
            return value

        def create(self, config):
            return fake_client

    class FakeGateway:
        def __init__(self, client):
            self.client = client

    from backend.app.modules.storage.config.service import StorageConfigService

    monkeypatch.setattr(StorageConfigService, "provider_factory", FakeFactory(), raising=False)
    monkeypatch.setattr(StorageConfigService, "gateway_class", FakeGateway, raising=False)

    def fail_sync(*args, **kwargs):
        raise RuntimeError("sync failed")

    monkeypatch.setattr("backend.app.modules.content.movies.storage_status.sync_movie_storage_status", fail_sync)

    response = client.post("/api/content/movies/storage-sync", json={"movie_ids": [movie_id]}, headers=headers)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert fake_client.closed is True
```

If this monkeypatch shape does not match current construction during implementation, keep the test intent but patch `StorageConfigService.open_provider` with a context manager that records close. The expected behavior remains: provider lifecycle closes even when sync raises.

- [ ] **Step 2: Run test to verify current behavior**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movies_api.py::test_movie_storage_sync_closes_provider_client_on_sync_error -v
```

Expected before refactor: FAIL if the test targets the new service import path, or PASS if current route already closes correctly. If it passes, continue and preserve behavior during extraction.

- [ ] **Step 3: Create storage sync service**

Create `backend/app/modules/content/movies/storage_sync_service.py`:

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session, selectinload

from backend.app.modules.content.movies.queries import MovieListFilters, list_movies_page
from backend.app.modules.content.movies.storage_status import STORAGE_STATUS_STORED, sync_movie_storage_status
from backend.app.modules.storage.config.service import StorageConfigService
from shared.database.models.content import Movie


@dataclass(frozen=True)
class MovieStorageSyncResultPayload:
    total: int
    stored_count: int
    not_stored_count: int
    results: list[dict]

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "stored_count": self.stored_count,
            "not_stored_count": self.not_stored_count,
            "results": self.results,
        }


def select_movies_for_storage_sync(
    db: Session,
    *,
    movie_ids: list[uuid.UUID] | None,
    filters: dict,
) -> list[Movie]:
    query = db.query(Movie).options(selectinload(Movie.magnets))
    if movie_ids:
        return query.filter(Movie.id.in_(movie_ids)).all()

    rows, _total = list_movies_page(
        db,
        MovieListFilters(
            search=filters.get("search"),
            source_task_id=filters.get("source_task_id"),
            rating_min=filters.get("rating_min"),
            rating_max=filters.get("rating_max"),
            actors=filters.get("actors"),
            actors_not=filters.get("actors_not"),
            actors_count_min=filters.get("actors_count_min"),
            actors_count_max=filters.get("actors_count_max"),
            tags=filters.get("tags"),
            tags_not=filters.get("tags_not"),
            director=filters.get("director"),
            director_not=filters.get("director_not"),
            maker=filters.get("maker"),
            maker_not=filters.get("maker_not"),
            series=filters.get("series"),
            series_not=filters.get("series_not"),
            release_date_from=filters.get("release_date_from"),
            release_date_to=filters.get("release_date_to"),
            created_at_from=filters.get("created_at_from"),
            created_at_to=filters.get("created_at_to"),
            storage_status=filters.get("storage_status"),
        ),
        sort_by="created_at",
        sort_order=-1,
        page=1,
        limit=100000,
        skip=0,
    )
    return rows


def sync_movies_storage_statuses(
    db: Session,
    *,
    user_id: str,
    movies: list[Movie],
    config_service: StorageConfigService | None = None,
) -> MovieStorageSyncResultPayload:
    from backend.app.modules.storage.tasks.events import publish_movie_storage_updated

    service = config_service or StorageConfigService()
    with service.open_provider() as (config, provider):
        results = [
            sync_movie_storage_status(
                db=db,
                movie=movie,
                provider=provider,
                config=config,
                source="manual_sync",
            )
            for movie in movies
        ]

    db.commit()

    for movie in movies:
        publish_movie_storage_updated(db, user_id, movie.id)

    stored_count = sum(1 for result in results if result.status == STORAGE_STATUS_STORED)
    return MovieStorageSyncResultPayload(
        total=len(results),
        stored_count=stored_count,
        not_stored_count=len(results) - stored_count,
        results=[
            {
                "movie_id": result.movie_id,
                "status": result.status,
                "found_count": result.found_count,
                "checked_targets": result.checked_targets,
                "locations": result.locations,
            }
            for result in results
        ],
    )
```

- [ ] **Step 4: Update router storage sync endpoint**

In `backend/app/modules/content/movies/router.py`, add:

```python
from backend.app.modules.content.movies.storage_sync_service import (
    select_movies_for_storage_sync,
    sync_movies_storage_statuses as sync_movies_storage_statuses_service,
)
```

Replace the body of `sync_movie_storage_statuses` after dependency arguments with:

```python
    filters = body.filters.model_dump() if body.filters else {}
    movies = select_movies_for_storage_sync(db, movie_ids=body.movie_ids, filters=filters)
    payload = sync_movies_storage_statuses_service(
        db,
        user_id=str(current_user.id),
        movies=movies,
    )
    return success(data=payload.to_dict())
```

Keep the endpoint function name unchanged so route registration and tests remain stable.

- [ ] **Step 5: Run focused movie API tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movies_api.py tests/test_movie_delete_service.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/content/movies/storage_sync_service.py backend/app/modules/content/movies/router.py backend/app/modules/content/movies/queries.py backend/tests/test_content_movies_api.py
git commit -m "refactor: extract movie storage sync service"
```

---

### Task 8: Use Provider Lifecycle Helper In Movie Cloud Delete

**Files:**
- Modify: `backend/app/modules/content/movies/router.py`
- Modify: `backend/tests/test_content_movies_api.py`

**Interfaces:**
- Consumes: `StorageConfigService.open_provider()`.
- Produces: movie delete endpoint keeps existing modes and responses while centralizing provider close behavior.

- [ ] **Step 1: Add cloud delete close-on-error regression test**

Append this test to `backend/tests/test_content_movies_api.py`:

```python
def test_movie_cloud_delete_closes_provider_client_on_delete_error(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    movie_id = seed_movie()

    closed = {"value": False}

    class FakeProvider:
        def delete_file(self, path):
            raise RuntimeError("delete failed")

    from contextlib import contextmanager
    from backend.app.modules.storage.config.service import StorageConfigService

    @contextmanager
    def fake_open_provider(self):
        try:
            yield {}, FakeProvider()
        finally:
            closed["value"] = True

    monkeypatch.setattr(StorageConfigService, "open_provider", fake_open_provider)

    response = client.post(
        "/api/content/movies/delete",
        json={"movie_ids": [movie_id], "mode": "cloud_only"},
        headers=headers,
    )

    assert response.status_code in {HTTPStatus.BAD_GATEWAY, HTTPStatus.INTERNAL_SERVER_ERROR}
    assert closed["value"] is True
```

- [ ] **Step 2: Run test before change**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movies_api.py::test_movie_cloud_delete_closes_provider_client_on_delete_error -v
```

Expected before router update: FAIL because `delete_content_movies` does not use `StorageConfigService.open_provider`.

- [ ] **Step 3: Update delete endpoint provider handling**

In `backend/app/modules/content/movies/router.py`, replace this pattern:

```python
    provider = None
    client = None
    if body.mode in {"cloud_only", "database_and_cloud"}:
        config_service = StorageConfigService()
        config = config_service.get_raw_config()
        client = config_service.provider_factory.create(config)
        provider = config_service.gateway_class(client)

    try:
        result = delete_movies(db=db, movies=movies, mode=body.mode, provider=provider)
        db.commit()
```

with:

```python
    config_service = StorageConfigService()

    try:
        if body.mode in {"cloud_only", "database_and_cloud"}:
            with config_service.open_provider() as (_config, provider):
                result = delete_movies(db=db, movies=movies, mode=body.mode, provider=provider)
        else:
            result = delete_movies(db=db, movies=movies, mode=body.mode, provider=None)
        db.commit()
```

Delete the old `finally` block that manually closes `client`.

- [ ] **Step 4: Run focused delete tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movies_api.py::test_delete_content_movies_database_only tests/test_content_movies_api.py::test_delete_content_movies_cloud_only tests/test_movie_delete_service.py -v
```

If the exact test names differ, list delete tests first:

```bash
cd backend
python -m pytest --collect-only tests/test_content_movies_api.py | rg "delete"
```

Then run the collected delete tests plus `tests/test_movie_delete_service.py`.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/content/movies/router.py backend/tests/test_content_movies_api.py
git commit -m "refactor: use storage provider lifecycle for movie delete"
```

---

### Task 9: Full Verification And Cleanup

**Files:**
- Modify only if verification exposes small integration issues from previous tasks.

**Interfaces:**
- Consumes all previous task outputs.
- Produces a verified codebase with no confirmed stale references.

- [ ] **Step 1: Run backend reference checks**

Run:

```bash
rg -n "/api/movies|modules\.movies|movies_router" backend/app backend/tests frontend/src
rg -n "lib/axios|api/crawler/sse|useCrawlerSSE|fetchTaskNames|getMovies\(|getMovie\(" frontend/src
```

Expected:

- first command may mention only `backend/tests/test_removed_legacy_apis.py`;
- second command has no output.

- [ ] **Step 2: Run backend full test suite**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 3: Run frontend full test suite**

Run:

```bash
cd frontend
npm test -- --run
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: TypeScript and Vite production build succeed.

- [ ] **Step 5: Run frontend lint**

Run:

```bash
cd frontend
npm run lint
```

Expected: PASS.

- [ ] **Step 6: Inspect final git status**

Run:

```bash
git status --short
```

Expected: only intentional tracked changes from this plan are present. The pre-existing untracked plan files may still appear:

```text
?? docs/superpowers/plans/2026-07-05-movie-delete-and-cloud-cleanup.md
?? docs/superpowers/plans/2026-07-05-movie-storage-status-sync.md
```

Do not stage those two pre-existing files unless the user explicitly asks.

- [ ] **Step 7: Leave verification fixes explicit**

If verification exposes an integration issue, fix the exact failing task that
introduced it and rerun that task's focused tests before rerunning full
verification. Commit the fix with the same file-specific staging discipline used
in the task that introduced the issue. Do not create an empty commit.
