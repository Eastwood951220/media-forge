# Movie Delete Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add single and batch deletion to `/content/movies` with three modes: database only, cloud storage only, and synchronized database plus cloud deletion.

**Architecture:** Keep the public contract compatible with the original `jav-scrapling` movies feature while fitting the current `media-forge` response envelope and `BaseListPage` layout. Backend deletion is centralized in a small service that validates the mode, collects target folders from `Movie.storage_summary.locations[].target_folder`, deletes CloudDrive2 folders when requested, and deletes database rows only for `db_only` and `both`. Frontend deletion is a focused API + hook layer used by `MovieListPage` and the table action column.

**Tech Stack:** FastAPI, SQLAlchemy 2, Pydantic 2, pytest, React 19, TypeScript, Ant Design 6, Vitest, React Testing Library, CloudDrive2 gRPC integration migrated from `/Users/eastwood/Code/PycharmProjects/jav-scrapling`.

---

## File Structure

- Create: `backend/app/modules/content/movies/delete_service.py`
  - Owns delete mode validation, result counting, database row deletion, cloud target folder collection, and CloudDrive2 deletion orchestration.
- Modify: `backend/app/modules/content/movies/schemas.py`
  - Adds request/response schemas for movie deletion.
- Modify: `backend/app/modules/content/movies/router.py`
  - Adds `DELETE /api/content/movies/batch` and `DELETE /api/content/movies/{movie_id}` before the existing `GET /{movie_id}` route.
- Modify: `backend/tests/test_content_movies_api.py`
  - Adds backend coverage for all three modes, invalid modes, missing IDs, and batch deletion.
- Create by copying from reference: `shared/integrations/base/*`
  - Brings over base integration exceptions used by CloudDrive2 mapper code.
- Create by copying from reference: `shared/integrations/storage_providers/clouddrive2/*`
  - Brings over the existing CloudDrive2 client, factory, gateway, mapper, models, proto files, and exceptions needed for folder deletion.
- Modify: `backend/requirements.txt`
  - Adds `grpcio` and `grpcio-tools`, matching the original CloudDrive2 integration requirements.
- Modify: `frontend/src/api/movie/types.ts`
  - Adds `DeleteMode` and `MovieDeleteResult`.
- Modify: `frontend/src/api/movie/index.ts`
  - Adds `deleteMovie()` and `deleteMovies()`.
- Create: `frontend/src/pages/content/movies/hooks/useMovieDelete.tsx`
  - Owns confirm modals, mode selector, API calls, success/warning messages, reloads, and selection clearing.
- Modify: `frontend/src/pages/content/movies/components/MovieTable.tsx`
  - Adds a row delete action and removes stale Ant Design column sorters so the existing query-form sort test passes.
- Modify: `frontend/src/pages/content/movies/MovieListPage.tsx`
  - Wires `useMovieDelete`, batch delete toolbar button, selected-row clearing, and row delete handler.
- Modify: `frontend/tests/movie-table.test.tsx`
  - Adds assertion for the delete action while preserving existing sorter expectations.
- Modify: `frontend/tests/movie-list.ui.test.tsx`
  - Adds API mocks and UI coverage for single and batch delete modal flows.

## Behavioral Contract

- `DeleteMode` values:
  - `db_only`: delete movie rows and related `MovieMagnet` rows through existing ORM cascade; do not call CloudDrive2.
  - `cloud_only`: delete CloudDrive2 target folders; keep database rows.
  - `both`: delete CloudDrive2 target folders first, then delete database rows.
- Backend response body is wrapped by `success()` and transformed on the frontend into:

```json
{
  "deleted": 1,
  "cloud_deleted": 0,
  "cloud_errors": 0,
  "cloud_skipped": 0
}
```

- Batch delete uses `DELETE /api/content/movies/batch` with JSON body:

```json
{
  "ids": ["movie-id-1", "movie-id-2"],
  "mode": "db_only"
}
```

- Single delete uses `DELETE /api/content/movies/{movie_id}?mode=db_only`.
- Cloud target folders come from each movie's `storage_summary.locations` list. Every unique non-empty `target_folder` is deleted at most once per request.
- If cloud deletion is requested and a movie has no target folder, count one `cloud_skipped`.
- If CloudDrive2 is not configured or a CloudDrive2 call fails for a folder, count `cloud_errors`; do not delete database rows for `both` until cloud deletion attempts complete. Match the old `jav-scrapling` behavior by allowing partial cloud failure and still applying database deletion in `both`, while surfacing warning counts to the UI.
- Invalid modes return HTTP 400.
- Missing single movie returns HTTP 404.
- Batch with an empty `ids` list returns HTTP 400.
- Batch with invalid UUID strings skips those strings, matching the reference backend's batch behavior.

## Task 1: Backend Delete Service Tests

**Files:**
- Modify: `backend/tests/test_content_movies_api.py`
- Create later: `backend/app/modules/content/movies/delete_service.py`
- Modify later: `backend/app/modules/content/movies/router.py`

- [ ] **Step 1: Add backend tests for database-only single and batch deletion**

Append these tests to `backend/tests/test_content_movies_api.py`:

```python
def seed_movie_with_storage(code: str, target_folder: str | None = None) -> str:
    session = TestingSessionLocal()
    storage_summary = {}
    if target_folder:
        storage_summary = {
            "last_status": "completed",
            "locations": [
                {
                    "path": f"{target_folder}/{code}.mp4",
                    "target_folder": target_folder,
                    "exists": True,
                }
            ],
        }
    movie = Movie(
        code=code,
        source_url=f"https://javdb.com/v/{code.lower()}",
        source_name=f"测试电影 {code}",
        source_task_ids=[TASK_ID_A],
        storage_summary=storage_summary,
    )
    session.add(movie)
    session.flush()
    session.add(MovieMagnet(movie_id=movie.id, magnet_url=f"magnet:?xt=urn:btih:{code}", dedupe_key=code, name=f"磁力 {code}"))
    session.commit()
    movie_id = str(movie.id)
    session.close()
    return movie_id


def test_delete_movie_db_only_removes_movie_and_magnets(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    movie_id = seed_movie_with_storage("DEL-001", "/Movies/任务A/DEL-001")

    response = client.delete(f"/api/content/movies/{movie_id}?mode=db_only", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"] == {
        "deleted": 1,
        "cloud_deleted": 0,
        "cloud_errors": 0,
        "cloud_skipped": 0,
    }

    session = TestingSessionLocal()
    assert session.get(Movie, uuid.UUID(movie_id)) is None
    assert session.query(MovieMagnet).filter(MovieMagnet.movie_id == uuid.UUID(movie_id)).count() == 0
    session.close()


def test_delete_movies_batch_db_only_removes_multiple_movies(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    first_id = seed_movie_with_storage("DEL-002")
    second_id = seed_movie_with_storage("DEL-003")

    response = client.request(
        "DELETE",
        "/api/content/movies/batch",
        json={"ids": [first_id, second_id], "mode": "db_only"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"] == {
        "deleted": 2,
        "cloud_deleted": 0,
        "cloud_errors": 0,
        "cloud_skipped": 0,
    }

    session = TestingSessionLocal()
    assert session.get(Movie, uuid.UUID(first_id)) is None
    assert session.get(Movie, uuid.UUID(second_id)) is None
    session.close()
```

- [ ] **Step 2: Run tests to verify they fail because routes are missing**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_delete_movie_db_only_removes_movie_and_magnets backend/tests/test_content_movies_api.py::test_delete_movies_batch_db_only_removes_multiple_movies -v
```

Expected: FAIL with HTTP 405 or HTTP 404 because the delete endpoints do not exist yet.

- [ ] **Step 3: Add backend tests for cloud-only and synchronized deletion**

Append these tests to `backend/tests/test_content_movies_api.py`:

```python
class FakeCloudDeleteResult:
    def __init__(self, success: bool = True, error_message: str | None = None) -> None:
        self.success = success
        self.error_message = error_message


class FakeCloudDeleteGateway:
    def __init__(self, existing_paths: set[str], failing_paths: set[str] | None = None) -> None:
        self.existing_paths = existing_paths
        self.failing_paths = failing_paths or set()
        self.deleted_paths: list[str] = []
        self.client = self

    def find_file(self, path: str) -> object | None:
        return object() if path in self.existing_paths else None

    def delete_file(self, path: str) -> FakeCloudDeleteResult:
        if path in self.failing_paths:
            return FakeCloudDeleteResult(False, "delete failed")
        self.deleted_paths.append(path)
        return FakeCloudDeleteResult(True)

    def close(self) -> None:
        return None


def test_delete_movie_cloud_only_deletes_cloud_folder_and_keeps_db(client: TestClient, admin_user, monkeypatch) -> None:
    from backend.app.modules.content.movies import delete_service

    headers = auth_headers(client, admin_user)
    movie_id = seed_movie_with_storage("DEL-004", "/Movies/任务A/DEL-004")
    gateway = FakeCloudDeleteGateway(existing_paths={"/Movies/任务A/DEL-004"})
    monkeypatch.setattr(delete_service, "build_cloud_delete_gateway", lambda: gateway)

    response = client.delete(f"/api/content/movies/{movie_id}?mode=cloud_only", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"] == {
        "deleted": 0,
        "cloud_deleted": 1,
        "cloud_errors": 0,
        "cloud_skipped": 0,
    }
    assert gateway.deleted_paths == ["/Movies/任务A/DEL-004"]

    session = TestingSessionLocal()
    assert session.get(Movie, uuid.UUID(movie_id)) is not None
    session.close()


def test_delete_movies_both_deletes_cloud_once_and_database_rows(client: TestClient, admin_user, monkeypatch) -> None:
    from backend.app.modules.content.movies import delete_service

    headers = auth_headers(client, admin_user)
    first_id = seed_movie_with_storage("DEL-005", "/Movies/任务A/DEL-005")
    second_id = seed_movie_with_storage("DEL-006", "/Movies/任务A/DEL-006")
    gateway = FakeCloudDeleteGateway(existing_paths={"/Movies/任务A/DEL-005", "/Movies/任务A/DEL-006"})
    monkeypatch.setattr(delete_service, "build_cloud_delete_gateway", lambda: gateway)

    response = client.request(
        "DELETE",
        "/api/content/movies/batch",
        json={"ids": [first_id, second_id], "mode": "both"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"] == {
        "deleted": 2,
        "cloud_deleted": 2,
        "cloud_errors": 0,
        "cloud_skipped": 0,
    }
    assert sorted(gateway.deleted_paths) == ["/Movies/任务A/DEL-005", "/Movies/任务A/DEL-006"]

    session = TestingSessionLocal()
    assert session.get(Movie, uuid.UUID(first_id)) is None
    assert session.get(Movie, uuid.UUID(second_id)) is None
    session.close()


def test_delete_movie_cloud_only_counts_missing_target_as_skipped(client: TestClient, admin_user, monkeypatch) -> None:
    from backend.app.modules.content.movies import delete_service

    headers = auth_headers(client, admin_user)
    movie_id = seed_movie_with_storage("DEL-007", "/Movies/任务A/DEL-007")
    gateway = FakeCloudDeleteGateway(existing_paths=set())
    monkeypatch.setattr(delete_service, "build_cloud_delete_gateway", lambda: gateway)

    response = client.delete(f"/api/content/movies/{movie_id}?mode=cloud_only", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"] == {
        "deleted": 0,
        "cloud_deleted": 0,
        "cloud_errors": 0,
        "cloud_skipped": 1,
    }


def test_delete_movie_rejects_invalid_mode(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    movie_id = seed_movie_with_storage("DEL-008")

    response = client.delete(f"/api/content/movies/{movie_id}?mode=bad", headers=headers)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"] == "mode must be 'both', 'cloud_only', or 'db_only'"


def test_delete_movies_batch_requires_ids(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)

    response = client.request(
        "DELETE",
        "/api/content/movies/batch",
        json={"ids": [], "mode": "db_only"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"] == "ids 不能为空"
```

- [ ] **Step 4: Run tests to verify cloud-mode tests fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py -k "delete_movie or delete_movies" -v
```

Expected: FAIL because `backend.app.modules.content.movies.delete_service` and delete routes do not exist.

- [ ] **Step 5: Commit backend failing tests**

```bash
git add backend/tests/test_content_movies_api.py
git commit -m "test: cover movie delete modes"
```

## Task 2: Backend Delete Schemas and Service

**Files:**
- Modify: `backend/app/modules/content/movies/schemas.py`
- Create: `backend/app/modules/content/movies/delete_service.py`
- Modify later: `backend/requirements.txt`
- Create later by copying: `shared/integrations/base/*`
- Create later by copying: `shared/integrations/storage_providers/clouddrive2/*`

- [ ] **Step 1: Add delete schemas**

Modify `backend/app/modules/content/movies/schemas.py` to include these imports and classes:

```python
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DeleteMode = Literal["both", "cloud_only", "db_only"]


class DeleteMoviesRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)
    mode: DeleteMode = "db_only"


class MovieDeleteResult(BaseModel):
    deleted: int = 0
    cloud_deleted: int = 0
    cloud_errors: int = 0
    cloud_skipped: int = 0
```

Keep the existing `MovieMagnetRead`, `MovieRead`, and `MovieDetailRead` classes unchanged below these additions.

- [ ] **Step 2: Create the delete service**

Create `backend/app/modules/content/movies/delete_service.py` with:

```python
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from shared.database.models.content import Movie

DeleteMode = str
VALID_DELETE_MODES = {"both", "cloud_only", "db_only"}

logger = logging.getLogger(__name__)


class RemoteOperationResult(Protocol):
    success: bool
    error_message: str | None


class CloudDeleteGateway(Protocol):
    client: object

    def find_file(self, path: str) -> object | None:
        raise NotImplementedError

    def delete_file(self, path: str) -> RemoteOperationResult:
        raise NotImplementedError


class CloudDeleteConfigurationError(RuntimeError):
    pass


@dataclass
class MovieDeleteResult:
    deleted: int = 0
    cloud_deleted: int = 0
    cloud_errors: int = 0
    cloud_skipped: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "deleted": self.deleted,
            "cloud_deleted": self.cloud_deleted,
            "cloud_errors": self.cloud_errors,
            "cloud_skipped": self.cloud_skipped,
        }


def validate_delete_mode(mode: str | None) -> str:
    effective_mode = mode or "db_only"
    if effective_mode not in VALID_DELETE_MODES:
        raise ValueError("mode must be 'both', 'cloud_only', or 'db_only'")
    return effective_mode


def build_cloud_delete_gateway() -> CloudDeleteGateway:
    from shared.integrations.storage_providers.clouddrive2.factory import CloudDriveClientFactory
    from shared.integrations.storage_providers.clouddrive2.gateway import CloudDrive2Gateway

    api_token = os.getenv("CLOUDDRIVE2_API_TOKEN", "").strip()
    if not api_token:
        raise CloudDeleteConfigurationError("CLOUDDRIVE2_API_TOKEN is not configured")

    config = {
        "grpc_host": os.getenv("CLOUDDRIVE2_GRPC_HOST", "localhost:9798"),
        "api_token": api_token,
        "request_timeout_seconds": int(os.getenv("CLOUDDRIVE2_REQUEST_TIMEOUT_SECONDS", "60")),
        "connect_timeout_seconds": int(os.getenv("CLOUDDRIVE2_CONNECT_TIMEOUT_SECONDS", "10")),
    }
    client = CloudDriveClientFactory().create(config)
    return CloudDrive2Gateway(client)


def _close_gateway(gateway: CloudDeleteGateway) -> None:
    client = getattr(gateway, "client", None)
    close = getattr(client, "close", None)
    if callable(close):
        close()


def _target_folders_for_movie(movie: Movie) -> set[str]:
    folders: set[str] = set()
    storage_summary = movie.storage_summary or {}
    locations = storage_summary.get("locations", [])
    if isinstance(locations, list):
        for location in locations:
            if not isinstance(location, dict):
                continue
            target_folder = str(location.get("target_folder") or "").strip()
            if target_folder:
                folders.add(target_folder)
    return folders


def _delete_cloud_folders(movies: list[Movie]) -> MovieDeleteResult:
    result = MovieDeleteResult()
    folders: set[str] = set()

    for movie in movies:
        movie_folders = _target_folders_for_movie(movie)
        if movie_folders:
            folders.update(movie_folders)
        else:
            result.cloud_skipped += 1

    if not folders:
        return result

    try:
        gateway = build_cloud_delete_gateway()
    except Exception as exc:
        logger.warning("CloudDrive2 delete gateway is unavailable: %s", exc)
        result.cloud_errors += len(folders)
        return result

    try:
        for folder in sorted(folders):
            try:
                existing = gateway.find_file(folder)
                if existing is None:
                    result.cloud_skipped += 1
                    continue
                operation = gateway.delete_file(folder)
                if operation.success:
                    result.cloud_deleted += 1
                else:
                    result.cloud_errors += 1
                    logger.warning("Failed to delete cloud folder %s: %s", folder, operation.error_message)
            except Exception as exc:
                result.cloud_errors += 1
                logger.warning("Error deleting cloud folder %s: %s", folder, exc)
    finally:
        _close_gateway(gateway)

    return result


def _normalize_movie_ids(raw_ids: list[str | uuid.UUID]) -> list[uuid.UUID]:
    movie_ids: list[uuid.UUID] = []
    for raw_id in raw_ids:
        try:
            movie_ids.append(raw_id if isinstance(raw_id, uuid.UUID) else uuid.UUID(str(raw_id)))
        except ValueError:
            continue
    return movie_ids


def delete_movies(db: Session, ids: list[str | uuid.UUID], mode: str | None = "db_only") -> MovieDeleteResult:
    effective_mode = validate_delete_mode(mode)
    movie_ids = _normalize_movie_ids(ids)
    if not movie_ids:
        return MovieDeleteResult()

    movies = list(
        db.scalars(
            select(Movie)
            .options(selectinload(Movie.magnets))
            .where(Movie.id.in_(movie_ids))
        ).all()
    )

    result = MovieDeleteResult()

    if effective_mode in {"both", "cloud_only"}:
        cloud_result = _delete_cloud_folders(movies)
        result.cloud_deleted = cloud_result.cloud_deleted
        result.cloud_errors = cloud_result.cloud_errors
        result.cloud_skipped = cloud_result.cloud_skipped

    if effective_mode in {"both", "db_only"}:
        for movie in movies:
            db.delete(movie)
            result.deleted += 1
        db.commit()

    return result
```

- [ ] **Step 3: Add CloudDrive2 Python dependencies**

Modify `backend/requirements.txt` by adding:

```text
grpcio>=1.60.0
grpcio-tools>=1.60.0
```

- [ ] **Step 4: Copy the existing CloudDrive2 integration from `jav-scrapling`**

Run:

```bash
mkdir -p shared/integrations
cp -R /Users/eastwood/Code/PycharmProjects/jav-scrapling/shared/integrations/base shared/integrations/
mkdir -p shared/integrations/storage_providers
cp -R /Users/eastwood/Code/PycharmProjects/jav-scrapling/shared/integrations/storage_providers/clouddrive2 shared/integrations/storage_providers/
touch shared/integrations/__init__.py
touch shared/integrations/storage_providers/__init__.py
```

Expected: `shared/integrations/storage_providers/clouddrive2/gateway.py` exists and exposes `CloudDrive2Gateway.delete_file()`.

- [ ] **Step 5: Run backend service tests before router wiring**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py -k "delete_movie or delete_movies" -v
```

Expected: FAIL because the service exists but the FastAPI delete routes are not wired.

- [ ] **Step 6: Commit service and integration migration**

```bash
git add backend/app/modules/content/movies/schemas.py backend/app/modules/content/movies/delete_service.py backend/requirements.txt shared/integrations
git commit -m "feat: add movie delete service"
```

## Task 3: Backend Delete Routes

**Files:**
- Modify: `backend/app/modules/content/movies/router.py`
- Test: `backend/tests/test_content_movies_api.py`

- [ ] **Step 1: Import delete schemas and service**

Modify the imports near the top of `backend/app/modules/content/movies/router.py`:

```python
from backend.app.modules.content.movies.delete_service import delete_movies, validate_delete_mode
from backend.app.modules.content.movies.schemas import DeleteMoviesRequest
```

- [ ] **Step 2: Add batch and single delete routes before `@router.get("/{movie_id}")`**

Insert this code after `update_filter_config()` and before the existing `get_movie()` route:

```python
@router.delete("/batch")
def delete_movies_batch(
    body: DeleteMoviesRequest,
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    if not body.ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ids 不能为空")

    try:
        result = delete_movies(db, body.ids, mode=body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return success(data=result.to_dict())


@router.delete("/{movie_id}")
def delete_movie(
    movie_id: uuid.UUID,
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
    mode: str | None = Query(default=None, description="Delete mode: 'both', 'cloud_only', 'db_only'"),
    delete_storage: bool = Query(default=False, description="Backward-compatible alias for mode=both"),
) -> dict:
    if mode is None and delete_storage:
        mode = "both"
    try:
        effective_mode = validate_delete_mode(mode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    movie = db.get(Movie, movie_id)
    if movie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")

    result = delete_movies(db, [movie_id], mode=effective_mode)
    return success(data=result.to_dict())
```

- [ ] **Step 3: Run backend delete tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py -k "delete_movie or delete_movies" -v
```

Expected: PASS for all delete-related tests.

- [ ] **Step 4: Run full content movies backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit routes**

```bash
git add backend/app/modules/content/movies/router.py backend/tests/test_content_movies_api.py
git commit -m "feat: expose movie delete endpoints"
```

## Task 4: Frontend API Contract Tests and Client

**Files:**
- Modify: `frontend/src/api/movie/types.ts`
- Modify: `frontend/src/api/movie/index.ts`
- Test by TypeScript build and UI tests in later tasks.

- [ ] **Step 1: Add frontend delete types**

Append to `frontend/src/api/movie/types.ts`:

```ts
export type DeleteMode = 'both' | 'cloud_only' | 'db_only'

export interface MovieDeleteResult {
  deleted: number
  cloud_deleted: number
  cloud_errors: number
  cloud_skipped: number
}
```

- [ ] **Step 2: Add delete API functions**

Modify `frontend/src/api/movie/index.ts` imports and exports:

```ts
import { request } from '@/request'
import type { DeleteMode, Movie, MovieDeleteResult, MovieListResponse } from './types'

export type { DeleteMode, Movie, MovieDeleteResult, MovieListResponse, StorageLocation } from './types'
```

Add these functions after `fetchMovie()`:

```ts
export function deleteMovie(id: string, mode: DeleteMode = 'db_only'): Promise<MovieDeleteResult> {
  return request.delete<MovieDeleteResult>(`${BASE_URL}/${id}`, { mode })
}

export function deleteMovies(ids: string[], mode: DeleteMode = 'db_only'): Promise<MovieDeleteResult> {
  return request<MovieDeleteResult>({
    url: `${BASE_URL}/batch`,
    method: 'delete',
    data: { ids, mode },
  })
}
```

- [ ] **Step 3: Type-check frontend API**

Run:

```bash
cd frontend
npm run build
```

Expected: FAIL until UI mocks/tests import the new functions or PASS if no test compile blockers exist.

- [ ] **Step 4: Commit frontend API contract**

```bash
git add frontend/src/api/movie/types.ts frontend/src/api/movie/index.ts
git commit -m "feat: add movie delete API client"
```

## Task 5: Frontend Delete Hook

**Files:**
- Create: `frontend/src/pages/content/movies/hooks/useMovieDelete.tsx`
- Modify later: `frontend/tests/movie-list.ui.test.tsx`

- [ ] **Step 1: Create the delete hook**

Create `frontend/src/pages/content/movies/hooks/useMovieDelete.tsx` with:

```tsx
import type React from 'react'
import { useCallback } from 'react'
import { App, Select } from 'antd'
import { deleteMovie, deleteMovies, type DeleteMode, type MovieDeleteResult } from '@/api/movie'

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '请求失败'
}

function formatDeleteResult(mode: DeleteMode, result: MovieDeleteResult): string {
  const parts: string[] = []
  if (mode !== 'cloud_only' && result.deleted > 0) {
    parts.push(`删除 ${result.deleted} 条记录`)
  }
  if (mode !== 'db_only') {
    if (result.cloud_deleted > 0) parts.push(`云存储删除成功 ${result.cloud_deleted}`)
    if (result.cloud_errors > 0) parts.push(`云存储删除失败 ${result.cloud_errors}`)
    if (result.cloud_skipped > 0) parts.push(`云存储跳过 ${result.cloud_skipped}`)
  }
  return parts.join('，') || '无操作'
}

export interface UseMovieDeleteOptions {
  selectedRowKeys: React.Key[]
  reload: () => void
  clearSelection: () => void
}

export function useMovieDelete({ selectedRowKeys, reload, clearSelection }: UseMovieDeleteOptions) {
  const { modal, message } = App.useApp()

  const showResult = useCallback((mode: DeleteMode, result: MovieDeleteResult) => {
    const summary = formatDeleteResult(mode, result)
    if (result.cloud_errors > 0) {
      void message.warning(summary)
    } else {
      void message.success(summary)
    }
  }, [message])

  const handleDelete = useCallback(async (id: string, mode: DeleteMode) => {
    try {
      const result = await deleteMovie(id, mode)
      showResult(mode, result)
      clearSelection()
      reload()
    } catch (error: unknown) {
      void message.error(getErrorMessage(error))
    }
  }, [clearSelection, reload, showResult, message])

  const showDeleteConfirm = useCallback((id: string, code: string) => {
    let selectedMode: DeleteMode = 'db_only'
    modal.confirm({
      title: `确认删除影片 ${code}？`,
      content: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div>删除后不可恢复，请选择删除模式：</div>
          <Select
            defaultValue="db_only"
            style={{ width: '100%' }}
            onChange={(value) => { selectedMode = value as DeleteMode }}
            options={[
              { value: 'db_only', label: '仅删除数据库' },
              { value: 'cloud_only', label: '仅删除云存储' },
              { value: 'both', label: '同步删除（数据库 + 云存储）' },
            ]}
          />
        </div>
      ),
      okText: '确认删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => handleDelete(id, selectedMode),
    })
  }, [handleDelete, modal])

  const handleBatchDelete = useCallback(async (mode: DeleteMode) => {
    if (selectedRowKeys.length === 0) return
    try {
      const result = await deleteMovies(selectedRowKeys.map(String), mode)
      showResult(mode, result)
      clearSelection()
      reload()
    } catch (error: unknown) {
      void message.error(getErrorMessage(error))
    }
  }, [selectedRowKeys, clearSelection, reload, showResult, message])

  const showBatchDeleteConfirm = useCallback(() => {
    if (selectedRowKeys.length === 0) return
    let selectedMode: DeleteMode = 'db_only'
    modal.confirm({
      title: `确认删除选中的 ${selectedRowKeys.length} 条影片？`,
      content: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div>删除后不可恢复，请选择删除模式：</div>
          <Select
            defaultValue="db_only"
            style={{ width: '100%' }}
            onChange={(value) => { selectedMode = value as DeleteMode }}
            options={[
              { value: 'db_only', label: '仅删除数据库' },
              { value: 'cloud_only', label: '仅删除云存储' },
              { value: 'both', label: '同步删除（数据库 + 云存储）' },
            ]}
          />
        </div>
      ),
      okText: '确认删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => handleBatchDelete(selectedMode),
    })
  }, [selectedRowKeys, handleBatchDelete, modal])

  return {
    showDeleteConfirm,
    showBatchDeleteConfirm,
  }
}
```

- [ ] **Step 2: Run TypeScript build to verify hook imports**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS if API types compile; otherwise fix the exact TypeScript error before continuing.

- [ ] **Step 3: Commit hook**

```bash
git add frontend/src/pages/content/movies/hooks/useMovieDelete.tsx
git commit -m "feat: add movie delete hook"
```

## Task 6: Frontend Table and Page Wiring

**Files:**
- Modify: `frontend/src/pages/content/movies/components/MovieTable.tsx`
- Modify: `frontend/src/pages/content/movies/MovieListPage.tsx`
- Test: `frontend/tests/movie-table.test.tsx`
- Test: `frontend/tests/movie-list.ui.test.tsx`

- [ ] **Step 1: Update the movie table columns**

Modify `frontend/src/pages/content/movies/components/MovieTable.tsx`:

```tsx
import { Button, Space, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { Movie } from '@/api/movie/types'

export interface MovieColumnsOptions {
  onViewDetail: (id: string) => void
  onDelete: (id: string, code: string) => void
}
```

Change the function signature and remove `sorter` / `defaultSortOrder` from rating and release date columns:

```tsx
export function createMovieColumns({ onViewDetail, onDelete }: MovieColumnsOptions): ColumnsType<Movie> {
```

Use this operation column:

```tsx
{
  title: '操作',
  key: 'action',
  fixed: 'right',
  width: 140,
  render: (_: unknown, record) => (
    <Space size={4}>
      <Button type="link" size="small" onClick={() => onViewDetail(record._id)}>
        详情
      </Button>
      <Button type="link" size="small" danger onClick={() => onDelete(record._id, record.code || record.source_name || record._id)}>
        删除
      </Button>
    </Space>
  ),
}
```

- [ ] **Step 2: Wire the delete hook into `MovieListPage`**

Modify imports in `frontend/src/pages/content/movies/MovieListPage.tsx`:

```tsx
import { Button } from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import { useMovieDelete } from './hooks/useMovieDelete'
```

After `const configHook = useMovieFilterConfig()`, add:

```tsx
const deleteHook = useMovieDelete({
  selectedRowKeys: list.selectedRowKeys,
  reload: list.reload,
  clearSelection: () => list.setSelectedRowKeys([]),
})
```

Change the columns memo:

```tsx
const columns = useMemo(
  () => createMovieColumns({
    onViewDetail: detail.showDetail,
    onDelete: deleteHook.showDeleteConfirm,
  }),
  [detail.showDetail, deleteHook.showDeleteConfirm],
)
```

Add `toolbarLeft` to `BaseListPage`:

```tsx
toolbarLeft={(
  <Button
    danger
    icon={<DeleteOutlined />}
    disabled={list.selectedRowKeys.length === 0}
    onClick={deleteHook.showBatchDeleteConfirm}
  >
    批量删除{list.selectedRowKeys.length > 0 ? ` (${list.selectedRowKeys.length})` : ''}
  </Button>
)}
```

- [ ] **Step 3: Update table tests**

Modify `frontend/tests/movie-table.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { createMovieColumns } from '../src/pages/content/movies/components/MovieTable'

describe('MovieTable columns', () => {
  it('keeps rating and release date sorting controlled by the query form only', () => {
    const columns = createMovieColumns({ onViewDetail: vi.fn(), onDelete: vi.fn() })
    const ratingColumn = columns.find((column) => column.key === 'rating')
    const releaseDateColumn = columns.find((column) => column.key === 'release_date')

    expect(ratingColumn).toMatchObject({ key: 'rating' })
    expect(releaseDateColumn).toMatchObject({ key: 'release_date' })
    expect(ratingColumn).not.toHaveProperty('sorter')
    expect(ratingColumn).not.toHaveProperty('defaultSortOrder')
    expect(releaseDateColumn).not.toHaveProperty('sorter')
    expect(releaseDateColumn).not.toHaveProperty('defaultSortOrder')
  })

  it('renders a delete action for each row', () => {
    const onDelete = vi.fn()
    const columns = createMovieColumns({ onViewDetail: vi.fn(), onDelete })
    const actionColumn = columns.find((column) => column.key === 'action')
    const element = actionColumn?.render?.(null, {
      _id: 'movie-1',
      id: 'movie-1',
      code: 'AAA-001',
      source_url: '',
      source_name: '测试电影',
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
      marked: false,
      storage_summary: {},
      raw_detail: {},
      created_at: null,
      updated_at: null,
    }, 0)

    render(<>{element}</>)
    screen.getByRole('button', { name: '删除' }).click()

    expect(onDelete).toHaveBeenCalledWith('movie-1', 'AAA-001')
  })
})
```

- [ ] **Step 4: Run table tests**

Run:

```bash
cd frontend
npm test -- movie-table.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit table and page wiring**

```bash
git add frontend/src/pages/content/movies/components/MovieTable.tsx frontend/src/pages/content/movies/MovieListPage.tsx frontend/tests/movie-table.test.tsx
git commit -m "feat: wire movie delete actions"
```

## Task 7: Frontend Movie List Delete Flow Tests

**Files:**
- Modify: `frontend/tests/movie-list.ui.test.tsx`

- [ ] **Step 1: Add delete API mocks**

Modify imports in `frontend/tests/movie-list.ui.test.tsx`:

```tsx
import {
  deleteMovie,
  deleteMovies,
  fetchFilters,
  fetchMovie,
  fetchMovieFilterConfig,
  fetchMovies,
  fetchTaskNames,
  updateMovieFilterConfig,
} from '../src/api/movie'
```

Modify `vi.mock('../src/api/movie', ...)`:

```tsx
vi.mock('../src/api/movie', () => ({
  fetchMovies: vi.fn(),
  fetchMovie: vi.fn(),
  fetchTaskNames: vi.fn(),
  fetchFilters: vi.fn(),
  fetchMovieFilterConfig: vi.fn(),
  updateMovieFilterConfig: vi.fn(),
  deleteMovie: vi.fn(),
  deleteMovies: vi.fn(),
}))
```

Add to `beforeEach()`:

```tsx
vi.mocked(deleteMovie).mockResolvedValue({
  deleted: 1,
  cloud_deleted: 0,
  cloud_errors: 0,
  cloud_skipped: 0,
})
vi.mocked(deleteMovies).mockResolvedValue({
  deleted: 1,
  cloud_deleted: 0,
  cloud_errors: 0,
  cloud_skipped: 0,
})
```

- [ ] **Step 2: Update the read-only detail assertion**

The existing detail test currently asserts no `删除` text exists. Replace:

```tsx
expect(screen.queryByText('删除')).not.toBeInTheDocument()
```

with:

```tsx
expect(screen.getByRole('button', { name: '删除' })).toBeInTheDocument()
expect(screen.queryByText('推送存储')).not.toBeInTheDocument()
expect(screen.queryByText('标记')).not.toBeInTheDocument()
```

- [ ] **Step 3: Add single delete UI test**

Append this test inside `describe('MovieListPage', ...)`:

```tsx
it('deletes a single movie with the default database-only mode', async () => {
  renderPage()

  await screen.findByText('AAA-001')
  await userEvent.click(screen.getByRole('button', { name: '删除' }))
  expect(await screen.findByText('确认删除影片 AAA-001？')).toBeInTheDocument()
  expect(screen.getByText('仅删除数据库')).toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: '确认删除' }))

  await waitFor(() => {
    expect(deleteMovie).toHaveBeenCalledWith('movie-1', 'db_only')
  })
})
```

- [ ] **Step 4: Add batch delete UI test**

Append this test inside `describe('MovieListPage', ...)`:

```tsx
it('deletes selected movies in batch with the default database-only mode', async () => {
  renderPage()

  await screen.findByText('AAA-001')
  await userEvent.click(screen.getByRole('checkbox', { name: /select row/i }))
  await userEvent.click(screen.getByRole('button', { name: /批量删除 \(1\)/ }))

  expect(await screen.findByText('确认删除选中的 1 条影片？')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: '确认删除' }))

  await waitFor(() => {
    expect(deleteMovies).toHaveBeenCalledWith(['movie-1'], 'db_only')
  })
})
```

If Ant Design renders the row selection checkbox without an accessible `select row` name in this environment, use this replacement inside the test after `await screen.findByText('AAA-001')`:

```tsx
const checkboxes = screen.getAllByRole('checkbox')
await userEvent.click(checkboxes[1])
```

- [ ] **Step 5: Run movie list UI tests**

Run:

```bash
cd frontend
npm test -- movie-list.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit UI tests**

```bash
git add frontend/tests/movie-list.ui.test.tsx
git commit -m "test: cover movie delete UI flows"
```

## Task 8: Final Verification

**Files:**
- All files touched above.

- [ ] **Step 1: Run backend content movie tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run targeted frontend tests**

Run:

```bash
cd frontend
npm test -- movie-table.test.tsx movie-list.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Run backend import smoke test for CloudDrive2 integration**

Run:

```bash
source .venv/bin/activate
python - <<'PY'
from shared.integrations.storage_providers.clouddrive2.factory import CloudDriveClientFactory
from shared.integrations.storage_providers.clouddrive2.gateway import CloudDrive2Gateway
print(CloudDriveClientFactory.__name__, CloudDrive2Gateway.__name__)
PY
```

Expected output:

```text
CloudDriveClientFactory CloudDrive2Gateway
```

- [ ] **Step 5: Run full changed test set**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py backend/tests/test_task_delete_cascade.py -v
cd frontend
npm test -- movie-table.test.tsx movie-list.ui.test.tsx request-error-envelope.test.ts
npm run build
```

Expected: PASS for all commands.

- [ ] **Step 6: Inspect git diff**

Run:

```bash
git diff --stat
git diff -- backend/app/modules/content/movies frontend/src/pages/content/movies frontend/src/api/movie frontend/tests/movie-list.ui.test.tsx frontend/tests/movie-table.test.tsx
```

Expected: Diff is limited to movie delete API/service/UI/tests, CloudDrive2 integration copy, and `backend/requirements.txt`.

- [ ] **Step 7: Commit final verification fixes if any were needed**

If verification required small fixes, commit them:

```bash
git add backend frontend shared backend/requirements.txt
git commit -m "fix: stabilize movie delete modes"
```

If no fixes were needed, do not create an empty commit.

## Self-Review

- Spec coverage: The plan covers single delete, batch delete, three delete modes, frontend `/content/movies` page wiring, backend API routes, database deletion, cloud storage deletion, and reference compatibility with `jav-scrapling` mode names and response counters.
- Red-flag scan: No deferred implementation language and no unspecified test behavior remains. The CloudDrive2 integration is copied from exact reference paths and used by concrete service code.
- Type consistency: Backend mode strings are `both | cloud_only | db_only`; frontend `DeleteMode` uses the same union. Backend response fields are `deleted`, `cloud_deleted`, `cloud_errors`, and `cloud_skipped`; frontend hook uses the same names.
