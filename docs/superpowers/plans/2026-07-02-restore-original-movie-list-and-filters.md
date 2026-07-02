# Restore Original Movie List And Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the movie list and detail UI from the original `jav-scrapling` movies module, keeping only the detail action, while adding backend movie filters and persistent filter configuration.

**Architecture:** Backend `/api/content/movies` will keep the current auth/envelope style but add the original filter contract, option endpoints, and JSON-file persisted filter config. Frontend will use the original module split under `frontend/src/pages/content/movies`, adapted to current aliases, response envelopes, and route path; operation controls other than detail are removed.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, SQLite-compatible pytest fallback filtering, React 19, TypeScript 6, Ant Design 6, Vitest.

---

## Context Notes

- Original frontend source to restore from: `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/content/movies`.
- Current frontend target path: `frontend/src/pages/content/movies`.
- Current backend base path: `/api/content/movies`.
- Current request layer unwraps `success(data=...)` responses to `data`, and returns paginated envelopes when responses include `rows` and `total`.
- User requested frontend restore from the original project, but operation section should keep only the detail action. Do not migrate delete, mark, export, storage push, storage sync, or selection batch operations in this plan.
- Filter setting Drawer persistence will use JSON config at `data/configs/movie_filter_config.json`, matching this project's existing config-file style and avoiding a migration.

## File Structure

- Modify `backend/app/modules/content/movies/router.py`: add original filter params, task-name endpoint, filter-option endpoint, filter-config endpoints, public movie payloads, and SQLite fallback filtering.
- Create `backend/app/modules/content/movies/filter_config.py`: read/write JSON persisted movie filter config.
- Modify `backend/app/modules/content/movies/schemas.py`: expose frontend-compatible movie and magnet fields.
- Modify `backend/tests/test_content_movies_api.py`: cover backend filtering, task names, filter options, detail payload, and config persistence.
- Replace `frontend/src/api/movie/index.ts`: expose original movie API names adapted to `/api/content/movies`.
- Replace `frontend/src/api/movie/types.ts`: expose original movie list/filter config types adapted to current model fields.
- Replace `frontend/src/pages/content/movies/MovieListPage.tsx`: use original page composition with filter bar, table, detail drawer, and filter config drawer.
- Create `frontend/src/pages/content/movies/components/MovieFilterBar.tsx`.
- Create `frontend/src/pages/content/movies/components/FilterConfigDrawer.tsx`.
- Create `frontend/src/pages/content/movies/components/MovieTable.tsx`.
- Create `frontend/src/pages/content/movies/components/MovieDetailDrawer.tsx`.
- Create `frontend/src/pages/content/movies/constants/index.ts`, `movieDefaults.ts`, `movieFilterFields.ts`, `movieOptions.ts`, `movieSort.ts`.
- Create `frontend/src/pages/content/movies/hooks/useMovieFilters.ts`, `useMovieList.ts`, `useMovieDetail.ts`, `useMovieFilterConfig.ts`.
- Create `frontend/src/pages/content/movies/utils/movieFilter.ts`, `movieMagnet.ts`.
- Modify `frontend/tests/movie-list.ui.test.tsx`: verify restored filters, config drawer persistence, detail drawer, and absence of non-detail operations.

---

### Task 1: Backend Filter Config Persistence

**Files:**
- Create: `backend/app/modules/content/movies/filter_config.py`
- Modify: `backend/tests/test_content_movies_api.py`

- [ ] **Step 1: Write the failing filter-config tests**

Append these imports to `backend/tests/test_content_movies_api.py`:

```python
from backend.app.modules.content.movies import filter_config
```

Append this test:

```python
def test_movie_filter_config_persists_to_json_file(client: TestClient, admin_user, monkeypatch, tmp_path) -> None:
    headers = auth_headers(client, admin_user)
    config_path = tmp_path / "movie_filter_config.json"
    monkeypatch.setattr(filter_config, "FILTER_CONFIG_PATH", config_path)

    initial = client.get("/api/content/movies/filter-config", headers=headers)
    assert initial.status_code == HTTPStatus.OK
    assert initial.json()["data"]["_key"] == "default"
    assert initial.json()["data"]["filters"] == {}

    payload = {
        "filters": {
            "actors": {"visible": True, "order": 0, "defaultValue": "演员A"},
            "sortBy": {"visible": True, "order": 19, "defaultValue": "rating:-1"},
        }
    }
    update = client.put("/api/content/movies/filter-config", json=payload, headers=headers)
    assert update.status_code == HTTPStatus.OK
    assert update.json()["data"]["success"] is True

    loaded = client.get("/api/content/movies/filter-config", headers=headers)
    assert loaded.json()["data"]["filters"] == payload["filters"]
    assert config_path.exists()
```

- [ ] **Step 2: Run the filter-config test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_movie_filter_config_persists_to_json_file -v
```

Expected: FAIL with `ImportError` for `filter_config` or 404 for `/filter-config`.

- [ ] **Step 3: Implement config file helpers**

Create `backend/app/modules/content/movies/filter_config.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from scraper.config import settings as cfg

FILTER_CONFIG_PATH = cfg.BASE_DIR / "data" / "configs" / "movie_filter_config.json"


class FilterItemConfig(BaseModel):
    visible: bool = True
    order: int = 0
    defaultValue: Any | None = None


class MovieFilterConfigPayload(BaseModel):
    filters: dict[str, FilterItemConfig] = Field(default_factory=dict)


def read_movie_filter_config() -> dict[str, Any]:
    if not FILTER_CONFIG_PATH.exists():
        return {"_key": "default", "filters": {}}
    try:
        data = json.loads(FILTER_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"_key": "default", "filters": {}}
    filters = data.get("filters") if isinstance(data, dict) else {}
    if not isinstance(filters, dict):
        filters = {}
    return {"_key": "default", "filters": filters, "updated_at": data.get("updated_at") if isinstance(data, dict) else None}


def write_movie_filter_config(filters: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime, timezone

    FILTER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_key": "default",
        "filters": filters,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    temp_path = Path(str(FILTER_CONFIG_PATH) + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(FILTER_CONFIG_PATH)
    return payload
```

- [ ] **Step 4: Add filter-config routes**

Modify `backend/app/modules/content/movies/router.py`.

Add these imports:

```python
from backend.app.modules.content.movies.filter_config import (
    MovieFilterConfigPayload,
    read_movie_filter_config,
    write_movie_filter_config,
)
```

Add these routes above `@router.get("/{movie_id}")`:

```python
@router.get("/filter-config")
def get_filter_config(_current_user: CurrentUser) -> dict:
    return success(data=read_movie_filter_config())


@router.put("/filter-config")
def update_filter_config(body: MovieFilterConfigPayload, _current_user: CurrentUser) -> dict:
    saved = write_movie_filter_config({key: value.model_dump(exclude_none=True) for key, value in body.filters.items()})
    return success(data={"success": True, "filters": saved["filters"]})
```

- [ ] **Step 5: Run the filter-config test and verify it passes**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_movie_filter_config_persists_to_json_file -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/content/movies/filter_config.py backend/app/modules/content/movies/router.py backend/tests/test_content_movies_api.py
git commit -m "feat: persist movie filter config"
```

---

### Task 2: Backend Movie Filter Options And Task Names

**Files:**
- Modify: `backend/app/modules/content/movies/router.py`
- Modify: `backend/tests/test_content_movies_api.py`

- [ ] **Step 1: Write failing option endpoint tests**

Append this test to `backend/tests/test_content_movies_api.py`:

```python
def test_movie_filter_options_and_task_names(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    seed_movie()
    session = TestingSessionLocal()
    session.add(Movie(
        code="BBB-002",
        source_url="https://javdb.com/v/bbb",
        source_name="第二部电影",
        release_date=date(2026, 2, 2),
        duration=90,
        rating=Decimal("3.5"),
        actors=["演员B"],
        tags=["标签B"],
        director="导演B",
        maker="片商B",
        series="系列B",
        source_task_names=["任务B"],
    ))
    session.commit()
    session.close()

    task_response = client.get("/api/content/movies/task-names", headers=headers)
    actor_response = client.get("/api/content/movies/filters?type=actor", headers=headers)
    tag_response = client.get("/api/content/movies/filters?type=tag", headers=headers)
    director_response = client.get("/api/content/movies/filters?type=director", headers=headers)
    invalid_response = client.get("/api/content/movies/filters?type=bad", headers=headers)

    assert task_response.status_code == HTTPStatus.OK
    assert task_response.json()["data"] == [{"name": "任务A"}, {"name": "任务B"}]
    assert actor_response.json()["data"] == ["演员A", "演员B"]
    assert tag_response.json()["data"] == ["标签A", "标签B"]
    assert director_response.json()["data"] == ["导演B"]
    assert invalid_response.status_code == HTTPStatus.BAD_REQUEST
```

- [ ] **Step 2: Run option endpoint tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_movie_filter_options_and_task_names -v
```

Expected: FAIL because `/task-names` and `/filters` are not registered.

- [ ] **Step 3: Add option helper functions**

Modify `backend/app/modules/content/movies/router.py`.

Add these imports:

```python
from sqlalchemy import func, not_, select
```

Replace the existing `from sqlalchemy import desc, or_` line with:

```python
from sqlalchemy import func, not_, or_, select
```

Add these helpers below `ALLOWED_SORT_FIELDS`:

```python
VALID_FILTER_TYPES = {"actor", "tag", "director", "maker", "series"}


def _unique_sorted(values: list[str | None]) -> list[str]:
    return sorted({value for value in values if value})


def _sqlite_filter_values(db: Session, filter_type: str) -> list[str]:
    movies = db.query(Movie).all()
    if filter_type == "actor":
        return _unique_sorted([actor for movie in movies for actor in (movie.actors or [])])
    if filter_type == "tag":
        return _unique_sorted([tag for movie in movies for tag in (movie.tags or [])])
    return _unique_sorted([getattr(movie, filter_type) for movie in movies])
```

- [ ] **Step 4: Add task-name and filter routes**

Add these routes above `@router.get("")` in `backend/app/modules/content/movies/router.py`:

```python
@router.get("/task-names")
def list_task_names(_current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    if db.bind.dialect.name == "sqlite":
        names = _unique_sorted([name for movie in db.query(Movie).all() for name in (movie.source_task_names or [])])
    else:
        names = list(db.scalars(select(func.unnest(Movie.source_task_names).label("name")).distinct().order_by("name")).all())
        names = [name for name in names if name]
    return success(data=[{"name": name} for name in names])


@router.get("/filters")
def list_filters(
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
    type: str = Query(..., description="actor, tag, director, maker, series"),
) -> dict:
    if type not in VALID_FILTER_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid filter type: {type}")
    if db.bind.dialect.name == "sqlite":
        return success(data=_sqlite_filter_values(db, type))
    if type == "actor":
        names = db.scalars(select(func.unnest(Movie.actors).label("name")).distinct().order_by("name")).all()
    elif type == "tag":
        names = db.scalars(select(func.unnest(Movie.tags).label("name")).distinct().order_by("name")).all()
    else:
        column = getattr(Movie, type)
        names = db.scalars(select(column).where(column != "", column.is_not(None)).distinct().order_by(column.asc())).all()
    return success(data=[name for name in names if name])
```

- [ ] **Step 5: Run option endpoint tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_movie_filter_options_and_task_names -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/content/movies/router.py backend/tests/test_content_movies_api.py
git commit -m "feat: add movie filter option endpoints"
```

---

### Task 3: Backend Movie List Filters

**Files:**
- Modify: `backend/app/modules/content/movies/router.py`
- Modify: `backend/app/modules/content/movies/schemas.py`
- Modify: `backend/tests/test_content_movies_api.py`

- [ ] **Step 1: Write failing list-filter tests**

Append this helper and test to `backend/tests/test_content_movies_api.py`:

```python
def seed_filter_movies() -> None:
    session = TestingSessionLocal()
    session.add_all([
        Movie(
            code="AAA-100",
            source_url="https://javdb.com/v/aaa100",
            source_name="高分电影",
            release_date=date(2026, 1, 10),
            duration=120,
            rating=Decimal("4.8"),
            actors=["演员A", "演员C"],
            tags=["标签A"],
            director="导演A",
            maker="片商A",
            series="系列A",
            source_task_names=["任务A"],
            storage_summary={"last_status": "completed"},
        ),
        Movie(
            code="BBB-200",
            source_url="https://javdb.com/v/bbb200",
            source_name="低分电影",
            release_date=date(2026, 2, 20),
            duration=90,
            rating=Decimal("2.2"),
            actors=["演员B"],
            tags=["标签B", "标签C"],
            director="导演B",
            maker="片商B",
            series="系列B",
            source_task_names=["任务B"],
            storage_summary={"last_status": "missing"},
        ),
    ])
    session.commit()
    session.close()


def test_list_movies_supports_original_filter_contract(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    seed_filter_movies()

    response = client.get(
        "/api/content/movies",
        params={
            "search": "电影",
            "source_task_name": "任务A",
            "actors": "演员A",
            "actors_not": "演员B",
            "tags": "标签A",
            "director": "导演A",
            "maker": "片商A",
            "series": "系列A",
            "rating_min": 4,
            "rating_max": 5,
            "actors_count_min": 2,
            "actors_count_max": 2,
            "release_date_from": "2026-01-01",
            "release_date_to": "2026-01-31",
            "storage_status": "completed",
            "page": 1,
            "limit": 20,
            "sort_by": "rating",
            "sort_order": -1,
        },
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["code"] == "AAA-100"
    assert body["rows"][0]["_id"] == body["rows"][0]["id"]
    assert body["rows"][0]["source_task_name"] == "任务A"


def test_list_movies_not_stored_filter(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    session.add(Movie(code="CCC-300", source_url="https://javdb.com/v/ccc300", source_name="无存储", source_task_names=["任务C"], storage_summary={}))
    session.add(Movie(code="DDD-400", source_url="https://javdb.com/v/ddd400", source_name="已存储", source_task_names=["任务D"], storage_summary={"last_status": "completed"}))
    session.commit()
    session.close()

    response = client.get("/api/content/movies?storage_status=not_stored", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert [row["code"] for row in response.json()["rows"]] == ["CCC-300"]
```

- [ ] **Step 2: Run list-filter tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_list_movies_supports_original_filter_contract backend/tests/test_content_movies_api.py::test_list_movies_not_stored_filter -v
```

Expected: FAIL because `search`, include/exclude filters, numeric filters, page pagination, and `_id` payload are not fully supported.

- [ ] **Step 3: Add public payload helpers**

Modify `backend/app/modules/content/movies/router.py`.

Add these helpers below `_sqlite_filter_values`:

```python
def _movie_payload(movie: Movie, *, include_magnets: bool = False) -> dict:
    source_task_names = list(movie.source_task_names or [])
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
        "source_task_name": source_task_names[0] if source_task_names else "",
        "source_task_names": source_task_names,
        "marked": bool(movie.marked),
        "storage_summary": movie.storage_summary or {},
        "raw_detail": movie.raw_detail or {},
        "created_at": movie.created_at.isoformat() if movie.created_at else None,
        "updated_at": movie.updated_at.isoformat() if movie.updated_at else None,
    }
    if include_magnets:
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
            for magnet in (movie.magnets or [])
        ]
        selected = next((magnet for magnet in movie.magnets or [] if magnet.selected), None)
        payload["selected_magnet_dedupe_key"] = selected.dedupe_key if selected else None
    return payload


def _split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()] if value else []
```

- [ ] **Step 4: Add SQLite-safe Python filtering helpers**

Add these helpers below `_split_csv`:

```python
def _movie_matches_python(
    movie: Movie,
    *,
    search: str | None,
    source_task_name: str | None,
    rating_min: float | None,
    rating_max: float | None,
    actors: str | None,
    actors_not: str | None,
    actors_count_min: int | None,
    actors_count_max: int | None,
    tags: str | None,
    tags_not: str | None,
    director: str | None,
    director_not: str | None,
    maker: str | None,
    maker_not: str | None,
    series: str | None,
    series_not: str | None,
    release_date_from: str | None,
    release_date_to: str | None,
    created_at_from: str | None,
    created_at_to: str | None,
    storage_status: str | None,
) -> bool:
    if search:
        needle = search.lower()
        haystack = " ".join([movie.code or "", movie.source_name or "", movie.director or "", movie.maker or "", movie.series or ""]).lower()
        if needle not in haystack:
            return False
    if source_task_name and source_task_name not in (movie.source_task_names or []):
        return False
    if rating_min is not None and (movie.rating is None or float(movie.rating) < rating_min):
        return False
    if rating_max is not None and (movie.rating is None or float(movie.rating) > rating_max):
        return False
    movie_actors = set(movie.actors or [])
    movie_tags = set(movie.tags or [])
    if _split_csv(actors) and not set(_split_csv(actors)).issubset(movie_actors):
        return False
    if _split_csv(actors_not) and set(_split_csv(actors_not)).intersection(movie_actors):
        return False
    if _split_csv(tags) and not set(_split_csv(tags)).issubset(movie_tags):
        return False
    if _split_csv(tags_not) and set(_split_csv(tags_not)).intersection(movie_tags):
        return False
    if _split_csv(director) and movie.director not in _split_csv(director):
        return False
    if _split_csv(director_not) and movie.director in _split_csv(director_not):
        return False
    if _split_csv(maker) and movie.maker not in _split_csv(maker):
        return False
    if _split_csv(maker_not) and movie.maker in _split_csv(maker_not):
        return False
    if _split_csv(series) and movie.series not in _split_csv(series):
        return False
    if _split_csv(series_not) and movie.series in _split_csv(series_not):
        return False
    if actors_count_min is not None and len(movie.actors or []) < actors_count_min:
        return False
    if actors_count_max is not None and len(movie.actors or []) > actors_count_max:
        return False
    if release_date_from and (movie.release_date is None or movie.release_date.isoformat() < release_date_from):
        return False
    if release_date_to and (movie.release_date is None or movie.release_date.isoformat() > release_date_to):
        return False
    if created_at_from and (movie.created_at is None or movie.created_at.date().isoformat() < created_at_from):
        return False
    if created_at_to and (movie.created_at is None or movie.created_at.date().isoformat() > created_at_to):
        return False
    last_status = (movie.storage_summary or {}).get("last_status")
    if storage_status == "not_stored":
        return not last_status
    if storage_status and last_status != storage_status:
        return False
    return True
```

- [ ] **Step 5: Replace `list_movies` signature and body**

Replace the existing `list_movies` function in `backend/app/modules/content/movies/router.py` with:

```python
@router.get("")
def list_movies(
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
    skip: int | None = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, max_length=200),
    search: str | None = Query(default=None, max_length=200),
    source_task_name: str | None = Query(default=None, max_length=200),
    sort_by: str = Query(default="created_at"),
    sort_order: int | str = Query(default=-1),
    rating_min: float | None = Query(default=None, ge=0, le=5),
    rating_max: float | None = Query(default=None, ge=0, le=5),
    actors: str | None = Query(default=None),
    actors_not: str | None = Query(default=None),
    actors_count_min: int | None = Query(default=None, ge=0),
    actors_count_max: int | None = Query(default=None, ge=0),
    tags: str | None = Query(default=None),
    tags_not: str | None = Query(default=None),
    director: str | None = Query(default=None),
    director_not: str | None = Query(default=None),
    maker: str | None = Query(default=None),
    maker_not: str | None = Query(default=None),
    series: str | None = Query(default=None),
    series_not: str | None = Query(default=None),
    release_date_from: str | None = Query(default=None),
    release_date_to: str | None = Query(default=None),
    created_at_from: str | None = Query(default=None),
    created_at_to: str | None = Query(default=None),
    storage_status: str | None = Query(default=None),
) -> dict:
    search_text = search or keyword
    try:
        normalized_sort_order = int(sort_order)
    except (TypeError, ValueError):
        normalized_sort_order = 1 if sort_order == "asc" else -1
    if normalized_sort_order not in (-1, 1):
        normalized_sort_order = -1

    rows = db.query(Movie).options(selectinload(Movie.magnets)).all()
    filtered = [
        movie for movie in rows
        if _movie_matches_python(
            movie,
            search=search_text,
            source_task_name=source_task_name,
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
        )
    ]

    sort_column = sort_by if sort_by in ALLOWED_SORT_FIELDS else "created_at"
    filtered.sort(key=lambda movie: getattr(movie, sort_column) is None)
    filtered.sort(key=lambda movie: getattr(movie, sort_column) or "", reverse=normalized_sort_order == -1)

    total = len(filtered)
    offset = skip if skip is not None else (page - 1) * limit
    page_rows = filtered[offset:offset + limit]
    return paginated(rows=[_movie_payload(movie, include_magnets=True) for movie in page_rows], total=total)
```

- [ ] **Step 6: Replace detail payload to use public movie shape**

Replace the body of `get_movie` in `backend/app/modules/content/movies/router.py` with:

```python
    movie = db.query(Movie).options(selectinload(Movie.magnets)).filter(Movie.id == movie_id).first()
    if movie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    return success(data=_movie_payload(movie, include_magnets=True))
```

- [ ] **Step 7: Update schemas for frontend-compatible fields**

Modify `backend/app/modules/content/movies/schemas.py`:

Add these fields to `MovieMagnetRead`:

```python
    movie_id: uuid.UUID
    dedupe_key: str
    size_mb: Decimal | None
    file_count: int | None
    file_text: str
    tags: list[str]
    weight: int
```

Add these fields to `MovieRead`:

```python
    marked: bool
```

The router uses dict payloads, but keeping schemas aligned prevents later regressions when schema validation is reintroduced.

- [ ] **Step 8: Run list-filter tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_list_movies_supports_original_filter_contract backend/tests/test_content_movies_api.py::test_list_movies_not_stored_filter -v
```

Expected: PASS.

- [ ] **Step 9: Run all content movie API tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py -v
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/app/modules/content/movies/router.py backend/app/modules/content/movies/schemas.py backend/tests/test_content_movies_api.py
git commit -m "feat: add original movie list filters"
```

---

### Task 4: Restore Frontend Movie Module Files

**Files:**
- Replace: `frontend/src/api/movie/index.ts`
- Replace: `frontend/src/api/movie/types.ts`
- Replace: `frontend/src/pages/content/movies/MovieListPage.tsx`
- Create: `frontend/src/pages/content/movies/components/MovieFilterBar.tsx`
- Create: `frontend/src/pages/content/movies/components/FilterConfigDrawer.tsx`
- Create: `frontend/src/pages/content/movies/components/MovieTable.tsx`
- Create: `frontend/src/pages/content/movies/components/MovieDetailDrawer.tsx`
- Create: `frontend/src/pages/content/movies/constants/index.ts`
- Create: `frontend/src/pages/content/movies/constants/movieDefaults.ts`
- Create: `frontend/src/pages/content/movies/constants/movieFilterFields.ts`
- Create: `frontend/src/pages/content/movies/constants/movieOptions.ts`
- Create: `frontend/src/pages/content/movies/constants/movieSort.ts`
- Create: `frontend/src/pages/content/movies/hooks/useMovieFilters.ts`
- Create: `frontend/src/pages/content/movies/hooks/useMovieList.ts`
- Create: `frontend/src/pages/content/movies/hooks/useMovieDetail.ts`
- Create: `frontend/src/pages/content/movies/hooks/useMovieFilterConfig.ts`
- Create: `frontend/src/pages/content/movies/utils/movieFilter.ts`
- Create: `frontend/src/pages/content/movies/utils/movieMagnet.ts`

- [ ] **Step 1: Copy original movie constants, hooks, components, and utils**

Run these commands from the repo root:

```bash
mkdir -p frontend/src/pages/content/movies/components
mkdir -p frontend/src/pages/content/movies/constants
mkdir -p frontend/src/pages/content/movies/hooks
mkdir -p frontend/src/pages/content/movies/utils
```

```bash
cp /Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/content/movies/constants/*.ts frontend/src/pages/content/movies/constants/
cp /Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/content/movies/hooks/useMovieFilters.ts frontend/src/pages/content/movies/hooks/useMovieFilters.ts
cp /Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/content/movies/hooks/useMovieList.ts frontend/src/pages/content/movies/hooks/useMovieList.ts
cp /Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/content/movies/hooks/useMovieDetail.ts frontend/src/pages/content/movies/hooks/useMovieDetail.ts
cp /Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/content/movies/hooks/useMovieFilterConfig.ts frontend/src/pages/content/movies/hooks/useMovieFilterConfig.ts
cp /Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/content/movies/utils/movieFilter.ts frontend/src/pages/content/movies/utils/movieFilter.ts
cp /Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/content/movies/utils/movieMagnet.ts frontend/src/pages/content/movies/utils/movieMagnet.ts
cp /Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/content/movies/components/MovieFilterBar.tsx frontend/src/pages/content/movies/components/MovieFilterBar.tsx
cp /Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/content/movies/components/FilterConfigDrawer.tsx frontend/src/pages/content/movies/components/FilterConfigDrawer.tsx
cp /Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/content/movies/components/MovieDetailDrawer.tsx frontend/src/pages/content/movies/components/MovieDetailDrawer.tsx
```

Expected: copied files exist under `frontend/src/pages/content/movies`.

- [ ] **Step 2: Replace movie API types**

Replace `frontend/src/api/movie/types.ts` with:

```ts
export interface MovieMagnet {
  _id: string
  id: string
  movie_id?: string
  magnet?: string
  magnet_url: string
  name: string
  title?: string
  size?: string | number
  size_mb?: number
  size_text: string
  file_count?: number | null
  file_text?: string
  tags?: string[]
  has_chinese_sub: boolean
  date: string
  dedupe_key?: string
  weight?: number
  selected: boolean
}

export interface StorageLocation {
  path: string
  target_folder: string
  exists?: boolean
}

export interface Movie {
  _id: string
  id: string
  code: string
  source_url: string
  source_name: string
  cover: string
  release_date: string | null
  duration: number
  director: string
  maker: string
  series: string
  rating: number | null
  actors: string[]
  tags: string[]
  source_task_name?: string
  source_task_names: string[]
  marked: boolean
  storage_summary: {
    last_status?: string
    locations?: StorageLocation[]
    synced_at?: string
    [key: string]: unknown
  }
  raw_detail: Record<string, unknown>
  magnets?: MovieMagnet[]
  selected_magnet_dedupe_key?: string | null
  has_chinese_sub?: boolean
  size?: number | string
  magnet?: string
  created_at: string | null
  updated_at: string | null
}

export interface MovieListResponse {
  items: Movie[]
  total: number
  page: number
  limit: number
  total_pages: number
}

export interface SelectOption<T = string> {
  value: T
  label: string
}

export type MovieFilterField =
  | 'actors' | 'tags' | 'director' | 'maker' | 'series'
  | 'actorsNot' | 'tagsNot' | 'directorNot' | 'makerNot' | 'seriesNot'
  | 'storageStatus' | 'ratingMin' | 'ratingMax'
  | 'actorsCountMin' | 'actorsCountMax'
  | 'releaseDateFrom' | 'releaseDateTo'
  | 'createdAtFrom' | 'createdAtTo' | 'sortBy'

export interface MovieFilterConfigValue {
  visible: boolean
  order: number
  defaultValue?: unknown
}

export type MovieFilterConfig = Partial<Record<MovieFilterField, MovieFilterConfigValue>>
```

- [ ] **Step 3: Replace movie API client**

Replace `frontend/src/api/movie/index.ts` with:

```ts
import { request } from '@/request'
import type { Movie, MovieListResponse, StorageLocation } from './types'

export type { Movie, MovieListResponse, StorageLocation } from './types'

const BASE_URL = '/api/content/movies'

interface PaginatedMovies {
  rows: Movie[]
  total: number
}

export type FilterType = 'actor' | 'tag' | 'director' | 'maker' | 'series'

export interface FilterItemConfig {
  visible: boolean
  order: number
  defaultValue?: unknown
}

export interface MovieFilterConfigResponse {
  _key?: string
  filters: Record<string, FilterItemConfig>
  updated_at?: string
}

export interface MovieQueryParams {
  source_task_name?: string
  search?: string
  page?: number
  limit?: number
  sort_by?: string
  sort_order?: number
  rating_min?: number
  rating_max?: number
  actors?: string
  actors_not?: string
  actors_count_min?: number
  actors_count_max?: number
  tags?: string
  tags_not?: string
  director?: string
  director_not?: string
  maker?: string
  maker_not?: string
  series?: string
  series_not?: string
  release_date_from?: string
  release_date_to?: string
  created_at_from?: string
  created_at_to?: string
  storage_status?: string
}

export function fetchMovies(params: MovieQueryParams): Promise<MovieListResponse> {
  return request.get<PaginatedMovies>(BASE_URL, params).then((res) => {
    const page = params.page ?? 1
    const limit = params.limit ?? 20
    return {
      items: res.rows,
      total: res.total,
      page,
      limit,
      total_pages: Math.max(1, Math.ceil(res.total / limit)),
    }
  })
}

export function fetchMovie(id: string): Promise<Movie> {
  return request.get<Movie>(`${BASE_URL}/${id}`)
}

export function getMovies(params?: MovieQueryParams): Promise<PaginatedMovies> {
  return request.get<PaginatedMovies>(BASE_URL, params)
}

export function getMovie(id: string): Promise<Movie> {
  return fetchMovie(id)
}

export function fetchTaskNames(): Promise<{ name: string }[]> {
  return request.get<{ name: string }[]>(`${BASE_URL}/task-names`)
}

export function fetchFilters(type: FilterType): Promise<string[]> {
  return request.get<string[]>(`${BASE_URL}/filters`, { type })
}

export function fetchMovieFilterConfig(): Promise<MovieFilterConfigResponse> {
  return request.get<MovieFilterConfigResponse>(`${BASE_URL}/filter-config`)
}

export function updateMovieFilterConfig(filters: Record<string, FilterItemConfig>): Promise<{ success: boolean }> {
  return request.put<{ success: boolean }>(`${BASE_URL}/filter-config`, { filters })
}
```

- [ ] **Step 4: Fix copied imports to use current API and local types**

Run:

```bash
rg -n '@/shared/types/common|@/shared/hooks/useErrorMessage|../api|../types' frontend/src/pages/content/movies
```

Apply these replacements in copied files:

```ts
// In components/MovieDetailDrawer.tsx
import type { MovieMagnet } from '@/api/movie/types'

// In components/MovieFilterBar.tsx, components/FilterConfigDrawer.tsx, hooks/useMovieFilters.ts,
// hooks/useMovieList.ts, hooks/useMovieDetail.ts, hooks/useMovieFilterConfig.ts, utils/movieMagnet.ts
// keep relative imports for local modules and use '@/api/movie' for API functions/types.
```

In `frontend/src/pages/content/movies/hooks/useMovieFilters.ts`, replace the `getErrorMessage` import with:

```ts
function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '请求失败'
}
```

In `frontend/src/pages/content/movies/hooks/useMovieList.ts`, replace the `getErrorMessage` import with the same local function.

- [ ] **Step 5: Replace MovieTable with detail-only operations**

Replace `frontend/src/pages/content/movies/components/MovieTable.tsx` with:

```tsx
import type React from 'react'
import { Button, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { Movie } from '@/api/movie/types'

export interface MovieTableProps {
  data: Movie[]
  total: number
  page: number
  pageSize: number
  loading: boolean
  selectedRowKeys: React.Key[]
  onSelectionChange: (keys: React.Key[]) => void
  onPageChange: (page: number, size: number) => void
  onShowSizeChange: (current: number, size: number) => void
  onSortChange: (field: string, order: number) => void
  onViewDetail: (id: string) => void
}

const storageStatusColor: Record<string, string> = {
  pending: 'processing',
  running: 'processing',
  waiting_download: 'processing',
  waiting_retry: 'warning',
  downloading: 'processing',
  moving: 'processing',
  completed: 'success',
  failed: 'error',
  retryable: 'warning',
  missing: 'error',
  skipped: 'default',
}

const storageStatusText: Record<string, string> = {
  pending: '等待中',
  running: '运行中',
  waiting_download: '等待下载',
  waiting_retry: '等待重试',
  downloading: '下载中',
  moving: '移动中',
  completed: '已完成',
  failed: '失败',
  retryable: '可重试',
  missing: '文件缺失',
  skipped: '已跳过',
}

function unique(values: string[] | undefined) {
  return [...new Set(values || [])]
}

export default function MovieTable({
  data,
  total,
  page,
  pageSize,
  loading,
  selectedRowKeys,
  onSelectionChange,
  onPageChange,
  onShowSizeChange,
  onSortChange,
  onViewDetail,
}: MovieTableProps) {
  const columns: ColumnsType<Movie> = [
    { title: '番号', dataIndex: 'code', key: 'code', width: 120 },
    { title: '标题', dataIndex: 'source_name', key: 'source_name', ellipsis: true },
    {
      title: '评分',
      dataIndex: 'rating',
      key: 'rating',
      width: 80,
      sorter: true,
      render: (value: number | null) => (value != null ? value.toFixed(2) : '-'),
    },
    {
      title: '发行日期',
      dataIndex: 'release_date',
      key: 'release_date',
      width: 160,
      sorter: true,
      defaultSortOrder: 'descend',
    },
    {
      title: '时长',
      dataIndex: 'duration',
      key: 'duration',
      width: 100,
      render: (value: number) => (value != null ? `${value}分` : '-'),
    },
    {
      title: '演员',
      dataIndex: 'actors',
      key: 'actors',
      width: 180,
      ellipsis: true,
      render: (actors: string[]) => (
        <Space size={[0, 4]} wrap>
          {unique(actors).slice(0, 3).map((actor) => <Tag key={actor}>{actor}</Tag>)}
          {unique(actors).length > 3 && <Tag>+{unique(actors).length - 3}</Tag>}
        </Space>
      ),
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 240,
      ellipsis: true,
      render: (tags: string[]) => (
        <Space size={[0, 4]} wrap>
          {unique(tags).slice(0, 3).map((tag) => <Tag key={tag}>{tag}</Tag>)}
          {unique(tags).length > 3 && <Tag>+{unique(tags).length - 3}</Tag>}
        </Space>
      ),
    },
    {
      title: '存储状态',
      key: 'storage_status',
      width: 100,
      render: (_: unknown, record) => {
        const status = record.storage_summary?.last_status
        if (!status) return <Typography.Text type="secondary">-</Typography.Text>
        return <Tag color={storageStatusColor[status]}>{storageStatusText[status] || status}</Tag>
      },
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 100,
      render: (_: unknown, record) => (
        <Button type="link" size="small" onClick={() => onViewDetail(record._id)}>
          详情
        </Button>
      ),
    },
  ]

  return (
    <Table
      columns={columns}
      dataSource={data}
      rowKey="_id"
      loading={loading}
      rowSelection={{ selectedRowKeys, onChange: onSelectionChange }}
      pagination={{
        current: page,
        total,
        pageSize,
        showSizeChanger: true,
        pageSizeOptions: ['20', '50', '100'],
        showTotal: (count) => `共 ${count} 条`,
        onChange: onPageChange,
        onShowSizeChange,
      }}
      onChange={(_pagination, _filters, sorter) => {
        if (!Array.isArray(sorter) && sorter.column) {
          const field = sorter.field as string
          if (sorter.order === 'ascend') onSortChange(field, 1)
          else if (sorter.order === 'descend') onSortChange(field, -1)
          else onSortChange('created_at', -1)
        }
      }}
      scroll={{ x: 1100 }}
    />
  )
}
```

- [ ] **Step 6: Replace MovieListPage with restored composition and no extra operations**

Replace `frontend/src/pages/content/movies/MovieListPage.tsx` with:

```tsx
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { Card } from 'antd'
import { DEFAULT_MOVIE_PAGE } from './constants'
import type { FilterItemConfig } from '@/api/movie'
import type { MovieFilterConfig } from '@/api/movie/types'
import MovieDetailDrawer from './components/MovieDetailDrawer'
import FilterConfigDrawer from './components/FilterConfigDrawer'
import MovieFilterBar from './components/MovieFilterBar'
import MovieTable from './components/MovieTable'
import { useMovieDetail } from './hooks/useMovieDetail'
import { useMovieFilterConfig } from './hooks/useMovieFilterConfig'
import { useMovieFilters } from './hooks/useMovieFilters'
import { useMovieList } from './hooks/useMovieList'
import type { MovieFilterState } from './utils/movieFilter'

function parseSortDefault(config: MovieFilterConfig | undefined): { sortBy: string; sortOrder: number } | undefined {
  const raw = config?.sortBy?.defaultValue
  if (typeof raw !== 'string' || !raw.includes(':')) return undefined
  const [field, order] = raw.split(':')
  const parsed = Number(order)
  if (!field || (parsed !== 1 && parsed !== -1)) return undefined
  return { sortBy: field, sortOrder: parsed }
}

function MovieListPage() {
  const filters = useMovieFilters()
  const list = useMovieList(filters.requestParams)
  const detail = useMovieDetail()
  const configHook = useMovieFilterConfig()

  const configSortParsed = useRef(false)
  useEffect(() => {
    if (configSortParsed.current) return
    const sortDefault = parseSortDefault(configHook.config)
    if (sortDefault) {
      list.resetSort(sortDefault)
      configSortParsed.current = true
    }
  }, [configHook.config, list.resetSort])

  const handleDetailFilterClick = useCallback((field: string, value: string) => {
    detail.closeDetail()
    const fieldMap: Record<string, string> = {
      director: 'selectedDirectors',
      maker: 'selectedMakers',
      series: 'selectedSeries',
      actors: 'selectedActors',
      tags: 'selectedTags',
    }
    const stateKey = fieldMap[field]
    if (!stateKey) return
    const current = (filters.form[stateKey as keyof typeof filters.form] as string[]) || []
    if (!current.includes(value)) {
      filters.patchForm({ [stateKey]: [...current, value] } as Partial<MovieFilterState>)
    }
    list.search()
  }, [detail, filters, list])

  const handleResetFilters = useCallback(() => {
    filters.resetFilters()
    if (configHook.config) {
      const defaults: Record<string, unknown> = {}
      for (const [key, value] of Object.entries(configHook.config)) {
        if (key !== 'sortBy' && value?.defaultValue !== undefined) {
          defaults[key] = value.defaultValue
        }
      }
      if (Object.keys(defaults).length > 0) {
        filters.patchForm(defaults as Partial<MovieFilterState>)
      }
    }
    list.resetSort(parseSortDefault(configHook.config))
    list.setPage(DEFAULT_MOVIE_PAGE)
  }, [configHook.config, filters, list])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const movieId = params.get('id')
    if (movieId) {
      detail.showDetail(movieId)
      const url = new URL(window.location.href)
      url.searchParams.delete('id')
      window.history.replaceState({}, '', url.toString())
    }
  }, [])

  const filterConfig = useMemo(() => configHook.config as Record<string, FilterItemConfig>, [configHook.config])

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <MovieFilterBar
          filters={filters}
          sort={{ sortBy: list.sortBy, sortOrder: list.sortOrder, onChange: list.handleSortChange }}
          filterConfig={filterConfig}
          onSearch={list.search}
          onReset={handleResetFilters}
          onConfigClick={() => configHook.setDrawerOpen(true)}
        />
      </Card>

      <Card size="default">
        <MovieTable
          data={list.data.items}
          total={list.data.total}
          page={list.data.page}
          pageSize={list.pageSize}
          loading={list.loading}
          selectedRowKeys={list.selectedRowKeys}
          onSelectionChange={list.setSelectedRowKeys}
          onPageChange={list.handlePageChange}
          onShowSizeChange={list.handleShowSizeChange}
          onSortChange={list.handleSortChange}
          onViewDetail={detail.showDetail}
        />
      </Card>

      <MovieDetailDrawer
        open={detail.open}
        detail={detail.detail}
        onClose={detail.closeDetail}
        onFilterClick={handleDetailFilterClick}
      />

      <FilterConfigDrawer
        open={configHook.drawerOpen}
        onClose={() => configHook.setDrawerOpen(false)}
        config={filterConfig}
        onSave={(cfg) => configHook.setConfig(cfg as typeof configHook.config)}
      />
    </div>
  )
}

export default MovieListPage
```

- [ ] **Step 7: Run TypeScript to reveal copied import issues**

Run:

```bash
cd frontend
npm run build
```

Expected: FAIL if any copied import still points to `@/shared/...` or old feature paths. Fix only those import/type errors in the copied movie module, then rerun until the build reaches unrelated project errors or succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/movie frontend/src/pages/content/movies
git commit -m "feat: restore original movie list UI"
```

---

### Task 5: Frontend Movie UI Tests

**Files:**
- Modify: `frontend/tests/movie-list.ui.test.tsx`

- [ ] **Step 1: Replace movie-list UI test**

Replace `frontend/tests/movie-list.ui.test.tsx` with:

```tsx
import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MovieListPage from '../src/pages/content/movies/MovieListPage'
import {
  fetchFilters,
  fetchMovie,
  fetchMovieFilterConfig,
  fetchMovies,
  fetchTaskNames,
  updateMovieFilterConfig,
} from '../src/api/movie'

vi.mock('../src/api/movie', () => ({
  fetchMovies: vi.fn(),
  fetchMovie: vi.fn(),
  fetchTaskNames: vi.fn(),
  fetchFilters: vi.fn(),
  fetchMovieFilterConfig: vi.fn(),
  updateMovieFilterConfig: vi.fn(),
}))

function renderPage() {
  return render(
    <AntApp>
      <MovieListPage />
    </AntApp>,
  )
}

const movie = {
  _id: 'movie-1',
  id: 'movie-1',
  code: 'AAA-001',
  source_url: 'https://javdb.com/v/aaa',
  source_name: '测试电影',
  cover: '',
  release_date: '2026-01-01',
  duration: 120,
  director: '导演A',
  maker: '片商A',
  series: '系列A',
  rating: 4.5,
  actors: ['演员A'],
  tags: ['标签A'],
  source_task_name: '任务A',
  source_task_names: ['任务A'],
  marked: false,
  storage_summary: { last_status: 'completed' },
  raw_detail: {},
  created_at: '2026-07-02T00:00:00',
  updated_at: null,
  magnets: [{
    _id: 'm-1',
    id: 'm-1',
    magnet: 'magnet:?x',
    magnet_url: 'magnet:?x',
    name: '磁力A',
    title: '磁力A',
    size_text: '1.2GB',
    has_chinese_sub: true,
    date: '',
    selected: true,
    dedupe_key: 'abc',
  }],
  selected_magnet_dedupe_key: 'abc',
}

describe('MovieListPage', () => {
  beforeEach(() => {
    vi.mocked(fetchMovies).mockResolvedValue({
      items: [movie],
      total: 1,
      page: 1,
      limit: 20,
      total_pages: 1,
    })
    vi.mocked(fetchMovie).mockResolvedValue(movie)
    vi.mocked(fetchTaskNames).mockResolvedValue([{ name: '任务A' }])
    vi.mocked(fetchFilters).mockImplementation(async (type) => {
      if (type === 'actor') return ['演员A']
      if (type === 'tag') return ['标签A']
      if (type === 'director') return ['导演A']
      if (type === 'maker') return ['片商A']
      if (type === 'series') return ['系列A']
      return []
    })
    vi.mocked(fetchMovieFilterConfig).mockResolvedValue({ _key: 'default', filters: {} })
    vi.mocked(updateMovieFilterConfig).mockResolvedValue({ success: true })
  })

  it('renders restored filters and opens read-only detail', async () => {
    renderPage()

    expect(await screen.findByText('AAA-001')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('搜索番号、标题...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '配置' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '详情' }))

    expect(await screen.findByText('影片详情')).toBeInTheDocument()
    expect(screen.getByText('最佳磁力')).toBeInTheDocument()
    expect(screen.getByText('磁力A')).toBeInTheDocument()
    expect(screen.queryByText('删除')).not.toBeInTheDocument()
    expect(screen.queryByText('推送存储')).not.toBeInTheDocument()
    expect(screen.queryByText('标记')).not.toBeInTheDocument()
  })

  it('persists filter drawer settings', async () => {
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: '配置' }))
    expect(await screen.findByText('筛选条件配置')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '保存配置' }))

    await waitFor(() => {
      expect(updateMovieFilterConfig).toHaveBeenCalled()
    })
  })

  it('sends original filter params when searching', async () => {
    renderPage()

    await userEvent.type(await screen.findByPlaceholderText('搜索番号、标题...'), 'AAA')
    await userEvent.click(screen.getByRole('button', { name: '搜索' }))

    await waitFor(() => {
      expect(fetchMovies).toHaveBeenLastCalledWith(expect.objectContaining({
        search: 'AAA',
        page: 1,
        limit: 20,
        sort_by: 'created_at',
        sort_order: -1,
      }))
    })
  })
})
```

- [ ] **Step 2: Run the movie UI test and verify it passes**

Run:

```bash
cd frontend
npm test -- movie-list.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS. If the build reports unused imports from copied original files, remove the unused imports and rerun.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/movie-list.ui.test.tsx frontend/src/pages/content/movies frontend/src/api/movie
git commit -m "test: cover restored movie list UI"
```

---

### Task 6: Full Verification

**Files:**
- No planned code changes.

- [ ] **Step 1: Run backend movie tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend movie tests**

Run:

```bash
cd frontend
npm test -- movie-list.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Manual UI check**

Run backend:

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

Run frontend:

```bash
cd frontend
npm run dev
```

Expected manual behavior:

- `/content/movies` shows the original-style filter bar, table, detail drawer, and filter config drawer.
- Operation column contains only `详情`.
- Search, task name, actor, tag, director, maker, series, include/exclude filters, rating filters, actor count filters, date filters, storage status, and sort all call backend with original parameter names.
- Filter config Drawer saves visibility/order/default values, survives page reload, and reads from `data/configs/movie_filter_config.json`.
- Detail drawer matches the original layout and supports clickable actor/tag/director/maker/series values that apply filters.

---

## Self-Review

- Spec coverage:
  - Frontend movie list is restored from the original module structure in Task 4.
  - Operation column keeps only detail in Task 4 Step 5 and Task 5 tests assert other actions are absent.
  - Detail page/drawer is restored from the original `MovieDetailDrawer` in Task 4.
  - Backend list filters are added in Task 3 with original parameter names.
  - Filter setting Drawer is included in Task 4 and persistent backend config is added in Task 1.
- Placeholder scan:
  - No forbidden placeholder terms are present.
  - Code-changing steps include exact code or exact copy commands from the original project path.
- Type consistency:
  - `Movie._id`, `Movie.id`, `MovieMagnet.magnet`, and `MovieMagnet.magnet_url` are exposed to satisfy original frontend assumptions and current backend identifiers.
  - `fetchMovies` adapts current paginated `{rows,total}` response into original `{items,total,page,limit,total_pages}` shape.
  - Filter config types use `FilterItemConfig` consistently across API, hook, drawer, and page.
