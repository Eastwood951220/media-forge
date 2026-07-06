# Movie Delete And Cloud Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add single and batch delete actions to the movie list with three modes: delete database only, delete cloud storage only, and delete both database and cloud storage.

**Architecture:** Add a shared backend movie deletion service that can delete movie database rows and CloudDrive storage folders. The movie list API and crawler task delete API both call this service, so crawler task mode `task_movies_and_cloud` is completed instead of returning `501`. The frontend reuses the crawler task delete confirmation pattern: a second confirmation modal with a delete-mode dropdown, used by both single-row and batch movie deletion.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, CloudDrive2 gateway, pytest, React 19, TypeScript, Ant Design 6, Vitest.

---

## File Structure

- Create `backend/app/modules/content/movies/delete_service.py`
  - Defines movie delete modes.
  - Extracts CloudDrive folder paths from movie storage metadata.
  - Deletes cloud folders through `provider.delete_file(folder_path)`.
  - Deletes movie rows and cascaded magnets.
  - Supports optional `storage_location_filter` for crawler-task scoped cloud deletion.
- Modify `backend/app/modules/content/movies/schemas.py`
  - Add movie delete request and response models.
- Modify `backend/app/modules/content/movies/router.py`
  - Add `POST /api/content/movies/delete` before `/{movie_id}`.
- Modify `backend/app/modules/crawler/tasks/delete_service.py`
  - Replace the unimplemented `task_movies_and_cloud` branch with shared cloud cleanup.
  - Keep existing `task_only` and `task_and_movies` behavior.
- Modify `backend/app/modules/crawler/tasks/router.py`
  - Create a CloudDrive provider only for `task_movies_and_cloud`.
  - Return a normal success response instead of `501`.
- Modify backend tests:
  - `backend/tests/test_movie_delete_service.py`
  - `backend/tests/test_content_movies_api.py`
  - `backend/tests/test_task_delete_cascade.py`
- Modify `frontend/src/api/movie/index.ts`
  - Add `deleteMovies(payload)`.
- Modify `frontend/src/api/movie/types.ts`
  - Add movie delete mode/result types.
- Modify `frontend/src/pages/content/movies/components/MovieTable.tsx`
  - Add per-row delete action.
- Modify `frontend/src/pages/content/movies/MovieListPage.tsx`
  - Add batch delete button and modal confirmation flow.
- Modify crawler task frontend types and success message:
  - `frontend/src/api/crawlTask/types.ts`
  - `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Add frontend movie list delete tests under `frontend/src/pages/content/movies/__tests__/`.

## Behavior Rules

- Movie list deletion modes:
  - `database_only`: delete selected movie rows and cascaded magnets; do not call CloudDrive.
  - `cloud_only`: delete CloudDrive storage folders; keep movie rows; clear storage locations and set storage status to `not_stored`.
  - `database_and_cloud`: delete CloudDrive storage folders first; if cloud deletion succeeds, delete movie rows and cascaded magnets.
- Single delete and batch delete use the same backend endpoint.
- Batch delete only deletes selected rows. It must not delete all filtered movies when nothing is selected.
- Cloud deletion removes folder paths, not video file paths.
- For storage metadata like:

```python
tasks = [
    "/嘿嘿嘿/日本/巨乳/ABC-123/ABC-123.mp4",
    "/嘿嘿嘿/日本/巨乳/ABC-456/ABC-456.mp4",
]
```

the service deletes:

```python
[
    "/嘿嘿嘿/日本/巨乳/ABC-123",
    "/嘿嘿嘿/日本/巨乳/ABC-456",
]
```

- Folder extraction sources, in order:
  - `movie.storage_summary["locations"][].target_folder`
  - parent folder of `movie.storage_summary["locations"][].path`
  - parent folder of each string in `movie.storage_summary["tasks"]`
  - each string in `movie.storage_summary["target_folders"]`
- Duplicate folder paths are deleted once.
- Missing cloud folders are treated as already deleted and do not fail the request.
- Other CloudDrive errors fail the request. In `database_and_cloud`, database rows are not deleted when cloud deletion fails.
- Crawler task deletion modes:
  - `task_only`: current behavior.
  - `task_and_movies`: current behavior.
  - `task_movies_and_cloud`: delete cloud folders for movies associated with the crawler task, scoped to that task's `storage_location`, then apply the same database behavior as `task_and_movies`.

## Task 1: Shared Movie Delete Service

**Files:**
- Create: `backend/app/modules/content/movies/delete_service.py`
- Test: `backend/tests/test_movie_delete_service.py`

- [ ] **Step 1: Write the failing folder extraction test**

Create `backend/tests/test_movie_delete_service.py` with this content:

```python
import uuid

from shared.database.models.content import Movie, MovieMagnet


def test_collect_cloud_delete_folders_deletes_number_folders_not_video_files() -> None:
    from backend.app.modules.content.movies.delete_service import collect_cloud_delete_folders

    movie = Movie(
        code="ABC-123",
        source_name="folder extraction",
        storage_summary={
            "locations": [
                {
                    "path": "/嘿嘿嘿/日本/巨乳/ABC-123/ABC-123.mp4",
                    "target_folder": "/嘿嘿嘿/日本/巨乳/ABC-123",
                    "storage_location": "巨乳",
                },
                {
                    "path": "/嘿嘿嘿/日本/巨乳/ABC-456/ABC-456.mp4",
                    "storage_location": "巨乳",
                },
            ],
            "tasks": [
                "/嘿嘿嘿/日本/巨乳/ABC-123/ABC-123.mp4",
                "/嘿嘿嘿/日本/巨乳/ABC-456/ABC-456.mp4",
            ],
        },
    )

    assert collect_cloud_delete_folders(movie) == [
        "/嘿嘿嘿/日本/巨乳/ABC-123",
        "/嘿嘿嘿/日本/巨乳/ABC-456",
    ]
```

- [ ] **Step 2: Write the failing service mode test**

Append this test to `backend/tests/test_movie_delete_service.py`:

```python
def test_delete_movies_cloud_only_deletes_folders_and_keeps_database_rows(db_session):
    from backend.app.modules.content.movies.delete_service import delete_movies

    movie = Movie(
        code="ABC-123",
        source_name="cloud only",
        storage_summary={
            "storage_status": "stored",
            "last_status": "stored",
            "locations": [
                {
                    "path": "/Movies/A/ABC-123/ABC-123.mp4",
                    "target_folder": "/Movies/A/ABC-123",
                    "storage_location": "A",
                }
            ],
        },
    )
    db_session.add(movie)
    db_session.flush()
    movie_id = movie.id

    class Provider:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def delete_file(self, path: str):
            self.deleted.append(path)

    provider = Provider()

    result = delete_movies(
        db=db_session,
        movies=[movie],
        mode="cloud_only",
        provider=provider,
    )

    assert result.deleted_movies == 0
    assert result.deleted_magnets == 0
    assert result.updated_movies == 1
    assert result.cloud_deleted_folders == ["/Movies/A/ABC-123"]
    assert provider.deleted == ["/Movies/A/ABC-123"]
    assert db_session.get(Movie, movie_id) is not None
    assert db_session.get(Movie, movie_id).storage_summary["storage_status"] == "not_stored"
    assert db_session.get(Movie, movie_id).storage_summary["locations"] == []
```

- [ ] **Step 3: Write the failing database-and-cloud test**

Append this test to `backend/tests/test_movie_delete_service.py`:

```python
def test_delete_movies_database_and_cloud_deletes_movie_after_cloud_cleanup(db_session):
    from backend.app.modules.content.movies.delete_service import delete_movies

    movie = Movie(
        code="ABC-456",
        source_name="database and cloud",
        storage_summary={
            "locations": [
                {
                    "path": "/Movies/A/ABC-456/ABC-456.mp4",
                    "target_folder": "/Movies/A/ABC-456",
                    "storage_location": "A",
                }
            ],
        },
    )
    db_session.add(movie)
    db_session.flush()
    magnet = MovieMagnet(
        movie_id=movie.id,
        magnet_url="magnet:?xt=urn:btih:abc456",
        dedupe_key=uuid.uuid4().hex,
        name="ABC-456",
    )
    db_session.add(magnet)
    db_session.flush()
    movie_id = movie.id

    class Provider:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def delete_file(self, path: str):
            self.deleted.append(path)

    provider = Provider()

    result = delete_movies(
        db=db_session,
        movies=[movie],
        mode="database_and_cloud",
        provider=provider,
    )

    assert result.deleted_movies == 1
    assert result.deleted_magnets == 1
    assert result.cloud_deleted_folders == ["/Movies/A/ABC-456"]
    assert db_session.get(Movie, movie_id) is None
```

- [ ] **Step 4: Write the failing scoped cloud delete test for shared movies**

Append this test to `backend/tests/test_movie_delete_service.py`:

```python
def test_delete_movies_cloud_only_with_storage_location_filter_keeps_other_locations(db_session):
    from backend.app.modules.content.movies.delete_service import delete_movies

    movie = Movie(
        code="ABC-789",
        source_name="shared source",
        storage_summary={
            "storage_status": "stored",
            "last_status": "stored",
            "locations": [
                {
                    "path": "/Movies/A/ABC-789/ABC-789.mp4",
                    "target_folder": "/Movies/A/ABC-789",
                    "storage_location": "A",
                },
                {
                    "path": "/Movies/B/ABC-789/ABC-789.mp4",
                    "target_folder": "/Movies/B/ABC-789",
                    "storage_location": "B",
                },
            ],
        },
    )
    db_session.add(movie)
    db_session.flush()

    class Provider:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def delete_file(self, path: str):
            self.deleted.append(path)

    provider = Provider()

    result = delete_movies(
        db=db_session,
        movies=[movie],
        mode="cloud_only",
        provider=provider,
        storage_location_filter="A",
    )

    assert result.cloud_deleted_folders == ["/Movies/A/ABC-789"]
    assert provider.deleted == ["/Movies/A/ABC-789"]
    assert movie.storage_summary["storage_status"] == "stored"
    assert movie.storage_summary["locations"] == [
        {
            "path": "/Movies/B/ABC-789/ABC-789.mp4",
            "target_folder": "/Movies/B/ABC-789",
            "storage_location": "B",
        }
    ]
```

- [ ] **Step 5: Run the service tests and verify they fail**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_movie_delete_service.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `backend.app.modules.content.movies.delete_service`.

- [ ] **Step 6: Implement the shared delete service**

Create `backend/app/modules/content/movies/delete_service.py` with this content:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.modules.content.movies.storage_status import (
    STORAGE_STATUS_NOT_STORED,
    STORAGE_STATUS_STORED,
    set_movie_storage_status,
)
from shared.database.models.content import Movie, MovieMagnet

logger = logging.getLogger(__name__)

MovieDeleteMode = Literal["database_only", "cloud_only", "database_and_cloud"]
MOVIE_DELETE_MODES = {"database_only", "cloud_only", "database_and_cloud"}


class UnsupportedMovieDeleteMode(ValueError):
    pass


class CloudMovieDeleteError(RuntimeError):
    def __init__(self, failed_folders: list[dict]) -> None:
        super().__init__("删除云存储文件夹失败")
        self.failed_folders = failed_folders


@dataclass
class MovieDeleteResult:
    deleted_movies: int = 0
    deleted_magnets: int = 0
    updated_movies: int = 0
    cloud_deleted_folders: list[str] = field(default_factory=list)
    cloud_missing_folders: list[str] = field(default_factory=list)
    cloud_failed_folders: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "deleted_movies": self.deleted_movies,
            "deleted_magnets": self.deleted_magnets,
            "updated_movies": self.updated_movies,
            "cloud_deleted_folders": self.cloud_deleted_folders,
            "cloud_missing_folders": self.cloud_missing_folders,
            "cloud_failed_folders": self.cloud_failed_folders,
        }


def collect_cloud_delete_folders(movie: Movie, *, storage_location_filter: str | None = None) -> list[str]:
    summary = dict(movie.storage_summary or {})
    folders: list[str] = []

    for item in summary.get("locations") or []:
        if not isinstance(item, dict):
            continue
        if storage_location_filter and str(item.get("storage_location") or "") != storage_location_filter:
            continue
        target_folder = str(item.get("target_folder") or "").strip()
        path = str(item.get("path") or "").strip()
        if target_folder:
            folders.append(target_folder)
        elif path:
            folders.append(_folder_from_path(path))

    for path in summary.get("tasks") or []:
        if isinstance(path, str) and path.strip():
            folder = _folder_from_path(path.strip())
            if _path_matches_storage_location(folder, storage_location_filter):
                folders.append(folder)

    for path in summary.get("target_folders") or []:
        if isinstance(path, str) and path.strip() and _path_matches_storage_location(path, storage_location_filter):
            folders.append(str(PurePosixPath(path.strip())))

    return _dedupe_paths(folders)


def delete_movies(
    *,
    db: Session,
    movies: list[Movie],
    mode: MovieDeleteMode,
    provider=None,
    storage_location_filter: str | None = None,
) -> MovieDeleteResult:
    if mode not in MOVIE_DELETE_MODES:
        raise UnsupportedMovieDeleteMode(f"Unsupported movie delete mode: {mode}")
    if mode in {"cloud_only", "database_and_cloud"} and provider is None:
        raise ValueError("删除云存储需要 CloudDrive provider")

    result = MovieDeleteResult()
    if mode in {"cloud_only", "database_and_cloud"}:
        _delete_cloud_folders_for_movies(
            movies=movies,
            provider=provider,
            result=result,
            storage_location_filter=storage_location_filter,
        )
        if result.cloud_failed_folders:
            raise CloudMovieDeleteError(result.cloud_failed_folders)

    if mode == "cloud_only":
        for movie in movies:
            remaining_locations = _remaining_locations_after_cloud_delete(
                movie,
                storage_location_filter=storage_location_filter,
            )
            set_movie_storage_status(
                movie,
                STORAGE_STATUS_STORED if remaining_locations else STORAGE_STATUS_NOT_STORED,
                source="movie_delete_cloud_only",
                locations=remaining_locations,
            )
            result.updated_movies += 1
        db.flush()
        return result

    if mode in {"database_only", "database_and_cloud"}:
        for movie in movies:
            magnet_count = int(
                db.query(MovieMagnet)
                .filter(MovieMagnet.movie_id == movie.id)
                .count()
            )
            result.deleted_magnets += magnet_count
            db.delete(movie)
            result.deleted_movies += 1
        db.flush()
    return result


def _delete_cloud_folders_for_movies(
    *,
    movies: list[Movie],
    provider,
    result: MovieDeleteResult,
    storage_location_filter: str | None,
) -> None:
    folders = _dedupe_paths([
        folder
        for movie in movies
        for folder in collect_cloud_delete_folders(movie, storage_location_filter=storage_location_filter)
    ])
    for folder in folders:
        try:
            provider.delete_file(folder)
            result.cloud_deleted_folders.append(folder)
        except Exception as exc:
            if _is_missing_cloud_path_error(exc):
                result.cloud_missing_folders.append(folder)
                continue
            result.cloud_failed_folders.append({"path": folder, "error": str(exc)})


def _folder_from_path(path: str) -> str:
    normalized = PurePosixPath(path)
    if normalized.suffix:
        return str(normalized.parent)
    return str(normalized)


def _dedupe_paths(paths: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = str(PurePosixPath(path))
        if not normalized or normalized == "." or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _is_missing_cloud_path_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(token in message for token in ["not found", "不存在", "文件不存在", "目录不存在", "404"])


def _path_matches_storage_location(path: str, storage_location_filter: str | None) -> bool:
    if not storage_location_filter:
        return True
    parts = [part for part in PurePosixPath(path).parts if part not in {"", "/"}]
    return storage_location_filter in parts


def _remaining_locations_after_cloud_delete(movie: Movie, *, storage_location_filter: str | None) -> list[dict]:
    locations = [
        item
        for item in (movie.storage_summary or {}).get("locations") or []
        if isinstance(item, dict)
    ]
    if not storage_location_filter:
        return []
    return [
        item
        for item in locations
        if str(item.get("storage_location") or "") != storage_location_filter
    ]
```

- [ ] **Step 7: Run the service tests and verify they pass**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_movie_delete_service.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit the shared service**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/content/movies/delete_service.py backend/tests/test_movie_delete_service.py
git commit -m "feat: add shared movie delete service"
```

Expected: commit succeeds.

## Task 2: Movie Delete API

**Files:**
- Modify: `backend/app/modules/content/movies/schemas.py`
- Modify: `backend/app/modules/content/movies/router.py`
- Test: `backend/tests/test_content_movies_api.py`

- [ ] **Step 1: Write the failing movie delete API test**

Append this test to `backend/tests/test_content_movies_api.py`:

```python
def test_delete_movies_database_only_api_deletes_selected_movies(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    movie = Movie(code="DEL-DB-001", source_url="https://example.test/delete-db", source_name="delete db")
    session.add(movie)
    session.commit()
    movie_id = str(movie.id)
    session.close()

    response = client.post(
        "/api/content/movies/delete",
        json={"movie_ids": [movie_id], "mode": "database_only"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["deleted_movies"] == 1
    assert client.get(f"/api/content/movies/{movie_id}", headers=headers).status_code == HTTPStatus.NOT_FOUND
```

- [ ] **Step 2: Write the failing cloud-only API test**

Append this test to `backend/tests/test_content_movies_api.py`:

```python
def test_delete_movies_cloud_only_api_deletes_cloud_folders_and_keeps_movie(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    movie = Movie(
        code="DEL-CLOUD-001",
        source_url="https://example.test/delete-cloud",
        source_name="delete cloud",
        storage_summary={
            "storage_status": "stored",
            "last_status": "stored",
            "locations": [
                {
                    "path": "/Movies/A/DEL-CLOUD-001/DEL-CLOUD-001.mp4",
                    "target_folder": "/Movies/A/DEL-CLOUD-001",
                    "storage_location": "A",
                }
            ],
        },
    )
    session.add(movie)
    session.commit()
    movie_id = str(movie.id)
    session.close()

    deleted: list[str] = []

    class Factory:
        def create(self, config):
            return object()

    class Gateway:
        def __init__(self, client):
            return None

        def delete_file(self, path):
            deleted.append(path)

    monkeypatch.setattr(
        "backend.app.modules.content.movies.router.StorageConfigService",
        lambda: type("ConfigService", (), {
            "get_raw_config": lambda self: {"target_folder": "/Movies"},
            "provider_factory": Factory(),
            "gateway_class": Gateway,
        })(),
    )

    response = client.post(
        "/api/content/movies/delete",
        json={"movie_ids": [movie_id], "mode": "cloud_only"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    assert deleted == ["/Movies/A/DEL-CLOUD-001"]
    detail = client.get(f"/api/content/movies/{movie_id}", headers=headers).json()["data"]
    assert detail["storage_status"] == "not_stored"
    assert detail["storage_summary"]["locations"] == []
```

- [ ] **Step 3: Run the movie delete API tests and verify they fail**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_content_movies_api.py::test_delete_movies_database_only_api_deletes_selected_movies \
  backend/tests/test_content_movies_api.py::test_delete_movies_cloud_only_api_deletes_cloud_folders_and_keeps_movie \
  -q
```

Expected: FAIL with `404` for `/api/content/movies/delete`.

- [ ] **Step 4: Add delete schemas**

In `backend/app/modules/content/movies/schemas.py`, add these models after `MovieStorageSyncResponse`:

```python
class MovieDeleteRequest(BaseModel):
    movie_ids: list[uuid.UUID]
    mode: str = "database_only"


class MovieDeleteResponse(BaseModel):
    deleted_movies: int
    deleted_magnets: int
    updated_movies: int
    cloud_deleted_folders: list[str]
    cloud_missing_folders: list[str]
    cloud_failed_folders: list[dict[str, Any]]
```

- [ ] **Step 5: Add the movie delete endpoint**

In `backend/app/modules/content/movies/router.py`, update the schema import:

```python
from backend.app.modules.content.movies.schemas import MovieDeleteRequest, MovieStorageSyncRequest
```

Add these imports near the existing storage config import usage:

```python
from backend.app.modules.content.movies.delete_service import (
    CloudMovieDeleteError,
    UnsupportedMovieDeleteMode,
    delete_movies,
)
from backend.app.modules.storage.config.service import StorageConfigService
```

Add this route before `@router.get("/{movie_id}")`:

```python
@router.post("/delete")
def delete_content_movies(
    body: MovieDeleteRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    if not body.movie_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择要删除的影片")

    movies = db.query(Movie).options(selectinload(Movie.magnets)).filter(Movie.id.in_(body.movie_ids)).all()
    if not movies:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="影片不存在")

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
    except UnsupportedMovieDeleteMode as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CloudMovieDeleteError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "删除云存储文件夹失败", "failed_folders": exc.failed_folders},
        ) from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    if body.mode == "cloud_only":
        from backend.app.modules.storage.tasks.events import publish_movie_storage_updated
        for movie in movies:
            publish_movie_storage_updated(db, str(current_user.id), movie.id)

    return success(msg="删除成功", data=result.to_dict())
```

- [ ] **Step 6: Run the movie delete API tests and verify they pass**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_content_movies_api.py::test_delete_movies_database_only_api_deletes_selected_movies \
  backend/tests/test_content_movies_api.py::test_delete_movies_cloud_only_api_deletes_cloud_folders_and_keeps_movie \
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit the movie delete API**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/content/movies/schemas.py backend/app/modules/content/movies/router.py backend/tests/test_content_movies_api.py
git commit -m "feat: add movie delete api"
```

Expected: commit succeeds.

## Task 3: Complete Crawler Task Cloud Delete Mode

**Files:**
- Modify: `backend/app/modules/crawler/tasks/delete_service.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Test: `backend/tests/test_task_delete_cascade.py`

- [ ] **Step 1: Write the failing crawler cloud delete test**

Append this test to `backend/tests/test_task_delete_cascade.py`:

```python
def test_delete_task_movies_and_cloud_deletes_task_movies_and_cloud_folders(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post(
        "/api/crawler/tasks",
        json={
            "name": "云删除任务",
            "storage_location": "巨乳",
            "is_skip": False,
            "urls": [{"url": "https://javdb.com/actors/cloud", "url_type": "actors"}],
        },
        headers=headers,
    )
    task_id = task_response.json()["data"]["id"]

    session = TestingSessionLocal()
    movie = Movie(
        code="CLOUD-001",
        source_url="https://javdb.com/v/cloud001",
        source_name="云删除影片",
        source_task_ids=[uuid.UUID(task_id)],
        storage_summary={
            "locations": [
                {
                    "path": "/Movies/巨乳/CLOUD-001/CLOUD-001.mp4",
                    "target_folder": "/Movies/巨乳/CLOUD-001",
                    "storage_location": "巨乳",
                }
            ],
        },
    )
    session.add(movie)
    session.commit()
    session.close()

    deleted: list[str] = []

    class Factory:
        def create(self, config):
            return object()

    class Gateway:
        def __init__(self, client):
            return None

        def delete_file(self, path):
            deleted.append(path)

    monkeypatch.setattr(
        "backend.app.modules.crawler.tasks.router.StorageConfigService",
        lambda: type("ConfigService", (), {
            "get_raw_config": lambda self: {"target_folder": "/Movies"},
            "provider_factory": Factory(),
            "gateway_class": Gateway,
        })(),
    )

    response = client.delete(f"/api/crawler/tasks/{task_id}?mode=task_movies_and_cloud", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()["data"]
    assert body["deleted_task"] is True
    assert body["deleted_movies"] == 1
    assert body["cloud_delete"] == "completed"
    assert body["cloud_deleted_folders"] == ["/Movies/巨乳/CLOUD-001"]
    assert deleted == ["/Movies/巨乳/CLOUD-001"]
```

- [ ] **Step 2: Run the crawler cloud delete test and verify it fails**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_task_delete_cascade.py::test_delete_task_movies_and_cloud_deletes_task_movies_and_cloud_folders -q
```

Expected: FAIL with `501` from the current `task_movies_and_cloud` branch.

- [ ] **Step 3: Extend crawler delete result fields**

In `backend/app/modules/crawler/tasks/delete_service.py`, remove `CloudDeleteNotImplemented` and add fields to `DeleteTaskResult`:

```python
    cloud_deleted_folders: list[str] | None = None
    cloud_missing_folders: list[str] | None = None
    cloud_failed_folders: list[dict] | None = None
```

In `to_dict()`, add:

```python
            "cloud_deleted_folders": self.cloud_deleted_folders or [],
            "cloud_missing_folders": self.cloud_missing_folders or [],
            "cloud_failed_folders": self.cloud_failed_folders or [],
```

- [ ] **Step 4: Reuse the shared movie delete service in crawler task deletion**

In `backend/app/modules/crawler/tasks/delete_service.py`, add imports:

```python
from backend.app.modules.content.movies.delete_service import CloudMovieDeleteError, delete_movies
```

Change the `delete_task()` signature:

```python
def delete_task(
    db: Session,
    task_id: uuid.UUID,
    *,
    mode: DeleteMode = "task_only",
    provider=None,
) -> DeleteTaskResult:
```

Remove the branch that raises for `task_movies_and_cloud`.

Before the movie loop, add:

```python
    cloud_deleted_folders: list[str] = []
    cloud_missing_folders: list[str] = []
    cloud_failed_folders: list[dict] = []
```

Replace:

```python
    if mode == "task_and_movies":
```

with:

```python
    if mode in {"task_and_movies", "task_movies_and_cloud"}:
```

Inside that block, before processing movies, add:

```python
        if mode == "task_movies_and_cloud":
            if provider is None:
                raise ValueError("删除云存储需要 CloudDrive provider")
            cloud_result = delete_movies(
                db=db,
                movies=movies,
                mode="cloud_only",
                provider=provider,
                storage_location_filter=task.storage_location or None,
            )
            cloud_deleted_folders = cloud_result.cloud_deleted_folders
            cloud_missing_folders = cloud_result.cloud_missing_folders
            cloud_failed_folders = cloud_result.cloud_failed_folders
```

At the return, change:

```python
        cloud_delete="skipped" if mode != "task_movies_and_cloud" else "pending",
```

to:

```python
        cloud_delete="completed" if mode == "task_movies_and_cloud" else "skipped",
        cloud_deleted_folders=cloud_deleted_folders,
        cloud_missing_folders=cloud_missing_folders,
        cloud_failed_folders=cloud_failed_folders,
```

- [ ] **Step 5: Update the crawler task router to create a provider**

In `backend/app/modules/crawler/tasks/router.py`, remove the import of `CloudDeleteNotImplemented`.

Add this import:

```python
from backend.app.modules.storage.config.service import StorageConfigService
```

Before calling `delete_task()`, add:

```python
    provider = None
    client = None
    if mode == "task_movies_and_cloud":
        config_service = StorageConfigService()
        config = config_service.get_raw_config()
        client = config_service.provider_factory.create(config)
        provider = config_service.gateway_class(client)
```

Replace:

```python
        result = delete_task(db, task_id, mode=mode)
```

with:

```python
        result = delete_task(db, task_id, mode=mode, provider=provider)
```

Remove the `except CloudDeleteNotImplemented` block.

Add this `finally` after exception handling by wrapping the call in `try/finally`:

```python
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
```

- [ ] **Step 6: Run crawler delete tests and verify they pass**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_task_delete_cascade.py::test_delete_task_movies_and_cloud_deletes_task_movies_and_cloud_folders \
  backend/tests/test_task_delete_cascade.py::test_delete_task_with_task_and_movies_mode \
  backend/tests/test_task_delete_cascade.py::test_delete_task_only_keeps_movies \
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit crawler cloud delete**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/crawler/tasks/delete_service.py backend/app/modules/crawler/tasks/router.py backend/tests/test_task_delete_cascade.py
git commit -m "feat: complete crawler cloud delete mode"
```

Expected: commit succeeds.

## Task 4: Frontend Movie Delete API Types

**Files:**
- Modify: `frontend/src/api/movie/types.ts`
- Modify: `frontend/src/api/movie/index.ts`

- [ ] **Step 1: Add movie delete types**

In `frontend/src/api/movie/types.ts`, add:

```typescript
export type MovieDeleteMode = 'database_only' | 'cloud_only' | 'database_and_cloud'

export interface MovieDeleteResult {
  deleted_movies: number
  deleted_magnets: number
  updated_movies: number
  cloud_deleted_folders: string[]
  cloud_missing_folders: string[]
  cloud_failed_folders: Array<Record<string, unknown>>
}
```

- [ ] **Step 2: Add movie delete API**

In `frontend/src/api/movie/index.ts`, update the import:

```typescript
import type { Movie, MovieDeleteMode, MovieDeleteResult, MovieListResponse, MovieStorageStatus } from './types'
```

Then add:

```typescript
export interface MovieDeletePayload {
  movie_ids: string[]
  mode: MovieDeleteMode
}

export function deleteMovies(payload: MovieDeletePayload): Promise<MovieDeleteResult> {
  return request.post<MovieDeleteResult>(`${BASE_URL}/delete`, payload)
}
```

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Commit API typing**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add frontend/src/api/movie/types.ts frontend/src/api/movie/index.ts
git commit -m "feat: add movie delete api client"
```

Expected: commit succeeds.

## Task 5: Movie List Delete UI

**Files:**
- Modify: `frontend/src/pages/content/movies/components/MovieTable.tsx`
- Modify: `frontend/src/pages/content/movies/MovieListPage.tsx`
- Test: `frontend/src/pages/content/movies/__tests__/movie-delete.test.tsx`

- [ ] **Step 1: Write the failing movie delete UI test**

Create `frontend/src/pages/content/movies/__tests__/movie-delete.test.tsx` with this content:

```typescript
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MovieListPage from '../MovieListPage'
import { deleteMovies, fetchMovieFilterConfig, fetchMovies } from '@/api/movie'

vi.mock('@/api/movie', async () => {
  const actual = await vi.importActual<typeof import('@/api/movie')>('@/api/movie')
  return {
    ...actual,
    fetchMovieFilterConfig: vi.fn().mockResolvedValue({ filters: {} }),
    fetchMovies: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, limit: 20, total_pages: 1 }),
    fetchFilters: vi.fn().mockResolvedValue([]),
    deleteMovies: vi.fn().mockResolvedValue({
      deleted_movies: 1,
      deleted_magnets: 0,
      updated_movies: 0,
      cloud_deleted_folders: [],
      cloud_missing_folders: [],
      cloud_failed_folders: [],
    }),
    syncMovieStorageStatus: vi.fn().mockResolvedValue({ total: 0, stored_count: 0, not_stored_count: 0, results: [] }),
  }
})

vi.mock('@/api/storage/storageTasks', () => ({
  getNextAlias: vi.fn().mockResolvedValue({ alias: '云存储_测试' }),
  createStoragePush: vi.fn(),
  createBatchStoragePush: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  subscribeRealtime: vi.fn().mockReturnValue(() => {}),
}))

function movieRow(id: string, code: string) {
  return {
    _id: id,
    id,
    code,
    source_url: '',
    source_name: code,
    cover: '',
    release_date: null,
    duration: 0,
    director: '',
    maker: '',
    series: '',
    rating: null,
    actors: [],
    tags: [],
    source_task_names: [],
    storage_locations: ['A'],
    marked: false,
    storage_status: 'stored' as const,
    storage_summary: {},
    raw_detail: {},
    created_at: null,
    updated_at: null,
  }
}

describe('MovieListPage delete', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('deletes a single movie with selected mode from confirmation modal', async () => {
    vi.mocked(fetchMovies).mockResolvedValue({
      items: [movieRow('movie-1', 'ABC-001')],
      total: 1,
      page: 1,
      limit: 20,
      total_pages: 1,
    })

    render(<MovieListPage />)

    expect(await screen.findByText('ABC-001')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    fireEvent.mouseDown(screen.getByLabelText('删除模式'))
    fireEvent.click(await screen.findByText('仅删除数据库'))
    fireEvent.click(screen.getByRole('button', { name: '删除' }))

    await waitFor(() => {
      expect(deleteMovies).toHaveBeenCalledWith({
        movie_ids: ['movie-1'],
        mode: 'database_only',
      })
    })
  })
})
```

- [ ] **Step 2: Run the UI test and verify it fails**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm test -- src/pages/content/movies/__tests__/movie-delete.test.tsx
```

Expected: FAIL because the movie list has no delete button.

- [ ] **Step 3: Add delete action to movie table**

In `frontend/src/pages/content/movies/components/MovieTable.tsx`, update `MovieColumnsOptions`:

```typescript
  onDelete?: (movie: Movie) => void
```

Change the function signature:

```typescript
export function createMovieColumns({ onViewDetail, onPush, onDelete }: MovieColumnsOptions): ColumnsType<Movie> {
```

Inside the operation column `Space`, add:

```tsx
          {onDelete && (
            <Button type="link" danger size="small" onClick={() => onDelete(record)}>
              删除
            </Button>
          )}
```

- [ ] **Step 4: Add delete modal and handlers to movie list**

In `frontend/src/pages/content/movies/MovieListPage.tsx`, update imports:

```typescript
import { Button, Modal, Select, Space, Typography, message } from 'antd'
import { deleteMovies } from '@/api/movie'
import type { MovieDeleteMode } from '@/api/movie/types'
```

Add delete mode options near `parseSortDefault()`:

```typescript
const movieDeleteModeOptions: Array<{ value: MovieDeleteMode; label: string }> = [
  { value: 'database_only', label: '仅删除数据库' },
  { value: 'cloud_only', label: '仅删除云存储' },
  { value: 'database_and_cloud', label: '同步删除数据库和云存储' },
]
```

Inside `MovieListPage()`, add this helper:

```typescript
  const confirmDeleteMovies = useCallback((movies: Movie[]) => {
    if (movies.length === 0) return
    let selectedMode: MovieDeleteMode = 'database_only'
    const title = movies.length === 1 ? `确认删除 ${movies[0].code}` : `确认批量删除 ${movies.length} 部影片`

    Modal.confirm({
      title,
      content: (
        <div>
          <p>请选择删除模式。删除操作不可撤销。</p>
          <div className={styles.deleteModeRow}>
            <Typography.Text className={styles.deleteModeLabel}>删除模式</Typography.Text>
            <Select<MovieDeleteMode>
              aria-label="删除模式"
              defaultValue="database_only"
              options={movieDeleteModeOptions}
              onChange={(value) => {
                selectedMode = value
              }}
              style={{ width: '100%' }}
            />
          </div>
          <Typography.Text type="danger" className={styles.deleteWarning}>
            删除云存储会删除影片对应的番号文件夹，不会只删除单个视频文件。
          </Typography.Text>
        </div>
      ),
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      width: 520,
      onOk: async () => {
        const result = await deleteMovies({
          movie_ids: movies.map((movie) => movie.id),
          mode: selectedMode,
        })
        message.success(`删除成功：数据库 ${result.deleted_movies} 部，云存储 ${result.cloud_deleted_folders.length} 个文件夹`)
        list.setSelectedRowKeys([])
        list.reload()
      },
    })
  }, [list])
```

Add:

```typescript
  const handleBatchDelete = useCallback(() => {
    const selectedIds = new Set(list.selectedRowKeys.map((key) => String(key)))
    const selectedMovies = list.data.items.filter((movie) => selectedIds.has(movie._id))
    confirmDeleteMovies(selectedMovies)
  }, [confirmDeleteMovies, list.data.items, list.selectedRowKeys])
```

Update columns:

```typescript
  const columns = useMemo(
    () => createMovieColumns({ onViewDetail: detail.showDetail, onPush: push.openSinglePush, onDelete: (movie) => confirmDeleteMovies([movie]) }),
    [detail.showDetail, push.openSinglePush, confirmDeleteMovies],
  )
```

In `toolbarLeft`, add a batch delete button next to batch push:

```tsx
              <Button danger size="small" onClick={handleBatchDelete}>
                批量删除
              </Button>
```

- [ ] **Step 5: Add modal styles**

In `frontend/src/pages/content/movies/MovieListPage.module.less`, add:

```less
.deleteModeRow {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 12px 0;
}

.deleteModeLabel {
  font-size: 13px;
}

.deleteWarning {
  display: block;
  font-size: 12px;
  line-height: 20px;
}
```

- [ ] **Step 6: Run the UI test and frontend build**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm test -- src/pages/content/movies/__tests__/movie-delete.test.tsx
npm run build
```

Expected: test passes and build succeeds.

- [ ] **Step 7: Commit movie delete UI**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add frontend/src/pages/content/movies/MovieListPage.tsx frontend/src/pages/content/movies/MovieListPage.module.less frontend/src/pages/content/movies/components/MovieTable.tsx frontend/src/pages/content/movies/__tests__/movie-delete.test.tsx
git commit -m "feat: add movie list delete actions"
```

Expected: commit succeeds.

## Task 6: Crawler Delete Frontend Result Display

**Files:**
- Modify: `frontend/src/api/crawlTask/types.ts`
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`

- [ ] **Step 1: Extend crawler delete result type**

In `frontend/src/api/crawlTask/types.ts`, add these fields to `DeleteTaskResult`:

```typescript
  cloud_deleted_folders: string[]
  cloud_missing_folders: string[]
  cloud_failed_folders: Array<Record<string, unknown>>
```

- [ ] **Step 2: Update crawler delete success message**

In `frontend/src/pages/crawler/tasks/TaskListPage.tsx`, replace:

```typescript
                    const msg = selectedMode === 'task_and_movies'
                        ? `，已删除 ${result?.deleted_movies ?? 0} 部关联影片`
                        : ''
                    message.success(`删除成功${msg}`)
```

with:

```typescript
                    const movieMsg = selectedMode !== 'task_only'
                        ? `，已删除 ${result?.deleted_movies ?? 0} 部关联影片`
                        : ''
                    const cloudMsg = selectedMode === 'task_movies_and_cloud'
                        ? `，已删除 ${result?.cloud_deleted_folders?.length ?? 0} 个云存储文件夹`
                        : ''
                    message.success(`删除成功${movieMsg}${cloudMsg}`)
```

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Commit crawler frontend update**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add frontend/src/api/crawlTask/types.ts frontend/src/pages/crawler/tasks/TaskListPage.tsx
git commit -m "feat: show crawler cloud delete result"
```

Expected: commit succeeds.

## Task 7: Full Verification

**Files:**
- Verify backend movie deletion, crawler deletion, and content movie APIs.
- Verify frontend movie list and crawler task delete flows.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_movie_delete_service.py \
  backend/tests/test_content_movies_api.py \
  backend/tests/test_task_delete_cascade.py \
  -q
```

Expected: all selected tests PASS.

- [ ] **Step 2: Run frontend focused tests**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm test -- src/pages/content/movies/__tests__/movie-delete.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Manual verification**

Start backend and frontend:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/backend
source ../.venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm run dev
```

Manual expected results:

```text
1. Movie row delete opens a confirmation modal with 删除模式 dropdown.
2. Batch delete appears only after selecting at least one movie.
3. 仅删除数据库 deletes movie rows and keeps CloudDrive untouched.
4. 仅删除云存储 deletes each target number folder and keeps movie rows with storage status 未存储.
5. 同步删除数据库和云存储 deletes cloud folders first, then deletes movie rows.
6. Crawler task mode 删除任务、关联影片和云存储 no longer returns 501.
7. Cloud deletion calls use folder paths such as /Movies/A/ABC-123, never /Movies/A/ABC-123/ABC-123.mp4.
```

- [ ] **Step 5: Commit verification fixes if source files changed**

Run this only if verification changes tracked source files:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/content/movies/delete_service.py backend/app/modules/content/movies/schemas.py backend/app/modules/content/movies/router.py backend/app/modules/crawler/tasks/delete_service.py backend/app/modules/crawler/tasks/router.py backend/tests/test_movie_delete_service.py backend/tests/test_content_movies_api.py backend/tests/test_task_delete_cascade.py frontend/src/api/movie/types.ts frontend/src/api/movie/index.ts frontend/src/api/crawlTask/types.ts frontend/src/pages/content/movies/MovieListPage.tsx frontend/src/pages/content/movies/MovieListPage.module.less frontend/src/pages/content/movies/components/MovieTable.tsx frontend/src/pages/content/movies/__tests__/movie-delete.test.tsx frontend/src/pages/crawler/tasks/TaskListPage.tsx
git commit -m "fix: verify movie and cloud deletion"
```

Expected: commit succeeds when verification required source changes.

## Self-Review

- Spec coverage: The plan adds single and batch movie deletion, all three requested deletion modes, folder-level CloudDrive deletion, and crawler task `task_movies_and_cloud` completion.
- Folder deletion rule: `collect_cloud_delete_folders()` converts file paths to parent folders and deduplicates paths before deletion.
- Crawler task integration: `task_movies_and_cloud` reuses the shared service and scopes cloud deletion by the task's `storage_location`.
- Frontend confirmation: Movie delete UI follows the crawler task delete modal pattern with a dropdown mode selector and destructive warning text.
- Safety: Batch delete requires explicit row selection. Database deletion is not performed when cloud deletion fails in combined mode.

## Execution Options

1. Subagent-Driven (recommended) - Use `superpowers:subagent-driven-development` to dispatch one fresh worker per task, then review between tasks.
2. Inline Execution - Use `superpowers:executing-plans` to execute this plan in the current session with checkpoints.
