# Crawler Task Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the crawler task backend API, task list, and new/edit task workflow from `/Users/eastwood/Code/PycharmProjects/jav-scrapling` into Media Forge with cleaner boundaries, tests, and Media Forge route/sidebar styling.

**Architecture:** Add a PostgreSQL-backed FastAPI crawler task module that owns task persistence, validation, server-side final URL generation, and the `/api/crawler/tasks` contract. Keep Media Forge's current `pages` + `api` frontend organization instead of importing the source project's `features` layout; put crawler task API wrappers under `frontend/src/api/crawler/tasks`, task pages under `frontend/src/pages/crawler/tasks`, and URL detection/final URL generation in a pure frontend utility so behavior is testable without rendering Ant Design forms.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pytest, React 19, TypeScript 6, Vite 8, TanStack Router, Ant Design 6, Less modules, Vitest, React Testing Library.

---

## Source And Target Context

Source files to port from:
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/crawler/tasks/router.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/crawler/tasks/schemas.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/repositories/task_repository.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/shared/database/models/crawler.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/crawler/tasks/TaskList.tsx`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/crawler/tasks/TaskForm.tsx`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/crawler/tasks/api.ts`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/crawler/tasks/types.ts`

Media Forge currently has:
- Backend routers in `backend/app/main.py`
- Backend models in `backend/app/models/*`
- Backend repositories in `backend/app/repositories/*`
- Backend tests in `backend/tests/*`
- Alembic migrations in `backend/alembic/versions/*`
- Manual routes in `frontend/src/routes/index.tsx`
- Navigation items in `frontend/src/layout/Sidebar/index.tsx`
- API wrappers under `frontend/src/api/*`
- Request wrapper exported from `frontend/src/request/index.ts`
- UI tests under `frontend/tests/*`

Backend crawler endpoints are not present in Media Forge yet, so this plan adds the concrete `/api/crawler/tasks` backend before wiring the frontend to it. The backend contract is:
- `GET /api/crawler/tasks` -> `CrawlTask[]`
- `GET /api/crawler/tasks/{id}` -> `CrawlTask`
- `POST /api/crawler/tasks` with `TaskPayload` -> `CrawlTask`
- `PUT /api/crawler/tasks/{id}` with `TaskPayload` -> `CrawlTask`
- `PATCH /api/crawler/tasks/{id}/skip` with `{ is_skip: boolean }` -> `CrawlTask`
- `DELETE /api/crawler/tasks/{id}` -> `{ deleted: boolean }`
- `POST /api/crawler/tasks/extract-name` with `{ url: string; url_type: UrlType }` -> `{ name: string }`

## File Structure

- Create `backend/app/models/crawler.py` for the `crawl_tasks` SQLAlchemy model.
- Create `backend/app/repositories/task.py` for task lookup and persistence operations.
- Create `backend/app/modules/crawler/__init__.py` for the crawler module package.
- Create `backend/app/modules/crawler/tasks/__init__.py` for the tasks package.
- Create `backend/app/modules/crawler/tasks/schemas.py` for Pydantic request/response contracts.
- Create `backend/app/modules/crawler/tasks/url_utils.py` for server-side URL finalization and name extraction fallback.
- Create `backend/app/modules/crawler/tasks/router.py` for `/api/crawler/tasks` endpoints.
- Create `backend/alembic/versions/b17e4f6d9c01_add_crawler_tasks.py` for the `crawl_tasks` table.
- Create `backend/tests/test_crawler_tasks.py` for backend API behavior.
- Modify `backend/app/main.py` to include the crawler task router.
- Modify `backend/app/models/__init__.py` and `backend/alembic/env.py` to register the crawler model.
- Create `frontend/src/api/crawler/tasks/types.ts` for task, URL entry, payload, and delete response types.
- Create `frontend/src/api/crawler/tasks/index.ts` for Media Forge request-wrapper based API functions.
- Create `frontend/src/pages/crawler/tasks/task-url-utils.ts` for `detectUrlType`, `buildFinalUrl`, labels, and select options.
- Create `frontend/src/pages/crawler/tasks/components/UrlEntryCard.tsx` for one URL card in the task form.
- Create `frontend/src/pages/crawler/tasks/TaskFormPage.tsx` for new/edit task submission.
- Create `frontend/src/pages/crawler/tasks/TaskListPage.tsx` for task table, status toggle, delete, and navigation to new/edit.
- Create `frontend/src/pages/crawler/tasks/TaskPages.module.less` for task list and form layout styling.
- Modify `frontend/src/routes/index.tsx` to add `/crawler/tasks`, `/crawler/tasks/new`, and `/crawler/tasks/$id/edit`.
- Modify `frontend/src/layout/Sidebar/index.tsx` to add the crawler task navigation item.
- Create `frontend/tests/crawler-task-url-utils.test.ts` for pure URL behavior.
- Create `frontend/tests/crawler-tasks-api.test.ts` for API wrapper contracts.
- Create `frontend/tests/crawler-task-pages.ui.test.tsx` for list/form rendering and submit behavior.
- Modify `frontend/tests/layout.ui.test.tsx` to expect the new sidebar item.

---

### Task 1: Backend Crawler Task API

**Files:**
- Create: `backend/app/models/crawler.py`
- Create: `backend/app/repositories/task.py`
- Create: `backend/app/modules/crawler/__init__.py`
- Create: `backend/app/modules/crawler/tasks/__init__.py`
- Create: `backend/app/modules/crawler/tasks/schemas.py`
- Create: `backend/app/modules/crawler/tasks/url_utils.py`
- Create: `backend/app/modules/crawler/tasks/router.py`
- Create: `backend/alembic/versions/b17e4f6d9c01_add_crawler_tasks.py`
- Create: `backend/tests/test_crawler_tasks.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/alembic/env.py`

- [ ] **Step 1: Write backend API tests**

Create `backend/tests/test_crawler_tasks.py`:

```python
from http import HTTPStatus

from fastapi.testclient import TestClient


def task_payload(name: str = "Actor A") -> dict:
    return {
        "name": name,
        "is_skip": False,
        "urls": [
            {
                "url": "https://javdb.com/actors/a?t=d&page=2&keep=1",
                "url_type": "actors",
                "has_magnet": True,
                "has_chinese_sub": True,
                "sort_type": 5,
                "url_name": "Actor A",
            }
        ],
    }


class TestCrawlerTasks:
    def test_list_tasks_returns_empty_list(self, client: TestClient) -> None:
        response = client.get("/api/crawler/tasks")

        assert response.status_code == HTTPStatus.OK
        assert response.json() == []

    def test_create_list_and_get_task(self, client: TestClient) -> None:
        create_response = client.post("/api/crawler/tasks", json=task_payload())

        assert create_response.status_code == HTTPStatus.CREATED
        created = create_response.json()
        assert created["_id"]
        assert created["name"] == "Actor A"
        assert created["is_skip"] is False
        assert created["urls"][0]["source"] == "javdb.com"
        assert created["urls"][0]["final_url"] == (
            "https://javdb.com/actors/a?keep=1&t=c%2Cd&sort=5"
        )

        list_response = client.get("/api/crawler/tasks")
        assert list_response.status_code == HTTPStatus.OK
        assert [item["name"] for item in list_response.json()] == ["Actor A"]

        get_response = client.get(f"/api/crawler/tasks/{created['_id']}")
        assert get_response.status_code == HTTPStatus.OK
        assert get_response.json()["name"] == "Actor A"

    def test_create_rejects_duplicate_task_name(self, client: TestClient) -> None:
        assert client.post("/api/crawler/tasks", json=task_payload()).status_code == HTTPStatus.CREATED

        response = client.post("/api/crawler/tasks", json=task_payload())

        assert response.status_code == HTTPStatus.CONFLICT
        assert "already exists" in response.json()["detail"]

    def test_create_rejects_duplicate_urls(self, client: TestClient) -> None:
        payload = task_payload()
        payload["urls"].append(payload["urls"][0].copy())

        response = client.post("/api/crawler/tasks", json=payload)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "Duplicate URL" in response.json()["detail"]

    def test_update_task_recalculates_final_url(self, client: TestClient) -> None:
        created = client.post("/api/crawler/tasks", json=task_payload()).json()
        update_payload = {
            "name": "Search A",
            "is_skip": True,
            "urls": [
                {
                    "url": "https://javdb.com/search?q=test&page=3&f=cnsub",
                    "url_type": "search",
                    "has_magnet": True,
                    "has_chinese_sub": True,
                    "sort_type": 1,
                    "url_name": "test",
                }
            ],
        }

        response = client.put(f"/api/crawler/tasks/{created['_id']}", json=update_payload)

        assert response.status_code == HTTPStatus.OK
        body = response.json()
        assert body["name"] == "Search A"
        assert body["is_skip"] is True
        assert body["urls"][0]["final_url"] == "https://javdb.com/search?q=test&f=download&sb=1"

    def test_toggle_skip_updates_only_skip_state(self, client: TestClient) -> None:
        created = client.post("/api/crawler/tasks", json=task_payload()).json()

        response = client.patch(
            f"/api/crawler/tasks/{created['_id']}/skip",
            json={"is_skip": True},
        )

        assert response.status_code == HTTPStatus.OK
        assert response.json()["is_skip"] is True

    def test_delete_task_removes_task(self, client: TestClient) -> None:
        created = client.post("/api/crawler/tasks", json=task_payload()).json()

        delete_response = client.delete(f"/api/crawler/tasks/{created['_id']}")

        assert delete_response.status_code == HTTPStatus.OK
        assert delete_response.json() == {"deleted": True}
        assert client.get(f"/api/crawler/tasks/{created['_id']}").status_code == HTTPStatus.NOT_FOUND

    def test_extract_name_from_search_query(self, client: TestClient) -> None:
        response = client.post(
            "/api/crawler/tasks/extract-name",
            json={"url": "https://javdb.com/search?q=actor%20name", "url_type": "search"},
        )

        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"name": "actor name"}

    def test_extract_name_from_url_slug_without_scraper_dependency(self, client: TestClient) -> None:
        response = client.post(
            "/api/crawler/tasks/extract-name",
            json={"url": "https://javdb.com/actors/actor-name", "url_type": "actors"},
        )

        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"name": "actor name"}
```

- [ ] **Step 2: Run backend API tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_tasks.py -v
```

Expected: FAIL with 404 responses for `/api/crawler/tasks` because the router is not registered yet.

- [ ] **Step 3: Implement crawler task model**

Create `backend/app/models/crawler.py`:

```python
from sqlalchemy import Boolean, Index, JSON, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CrawlTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawl_tasks"
    __table_args__ = (
        UniqueConstraint("name", name="uq_crawl_tasks_name"),
        Index("idx_crawl_tasks_created_at", "created_at"),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    urls: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    is_skip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
```

- [ ] **Step 4: Register model exports**

Modify `backend/app/models/__init__.py`:

```python
from backend.app.models.crawler import CrawlTask
from backend.app.models.user import User

__all__ = ["CrawlTask", "User"]
```

- [ ] **Step 5: Add task repository**

Create `backend/app/repositories/task.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.crawler import CrawlTask


class TaskRepository:
    """Repository for crawler task persistence."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[CrawlTask]:
        stmt = select(CrawlTask).order_by(CrawlTask.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def get(self, task_id: uuid.UUID) -> CrawlTask | None:
        return self.session.get(CrawlTask, task_id)

    def get_by_name(self, name: str) -> CrawlTask | None:
        stmt = select(CrawlTask).where(CrawlTask.name == name)
        return self.session.scalar(stmt)

    def name_exists(self, name: str, *, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = select(CrawlTask).where(CrawlTask.name == name)
        if exclude_id is not None:
            stmt = stmt.where(CrawlTask.id != exclude_id)
        return self.session.scalar(stmt) is not None

    def create(self, task: CrawlTask) -> CrawlTask:
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def save(self, task: CrawlTask) -> CrawlTask:
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def delete(self, task: CrawlTask) -> None:
        self.session.delete(task)
        self.session.commit()
```

- [ ] **Step 6: Add backend schemas**

Create `backend/app/modules/crawler/__init__.py`:

```python
"""Crawler backend module."""
```

Create `backend/app/modules/crawler/tasks/__init__.py`:

```python
"""Crawler task API module."""
```

Create `backend/app/modules/crawler/tasks/schemas.py`:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


UrlType = Literal[
    "actors",
    "series",
    "makers",
    "directors",
    "video_codes",
    "lists",
    "tags",
    "search",
]


class TaskUrlEntry(BaseModel):
    url: str = Field(..., min_length=1)
    url_type: UrlType
    has_magnet: bool = False
    has_chinese_sub: bool = False
    sort_type: int = 0
    source: str | None = None
    final_url: str | None = None
    url_name: str | None = None


class TaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    urls: list[TaskUrlEntry] = Field(..., min_length=1)
    is_skip: bool = False


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    urls: list[TaskUrlEntry] | None = Field(default=None, min_length=1)
    is_skip: bool | None = None


class TaskSkipUpdate(BaseModel):
    is_skip: bool


class ExtractNameRequest(BaseModel):
    url: str = Field(..., min_length=1)
    url_type: UrlType


class ExtractNameResponse(BaseModel):
    name: str


class TaskDeleteResponse(BaseModel):
    deleted: bool


class CrawlTaskResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    name: str
    urls: list[TaskUrlEntry]
    is_skip: bool
    config: dict = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None
```

- [ ] **Step 7: Add server-side URL utilities**

Create `backend/app/modules/crawler/tasks/url_utils.py`:

```python
from __future__ import annotations

from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse, urlunparse

from backend.app.modules.crawler.tasks.schemas import TaskUrlEntry, UrlType


PARAM_KEYS = {"t", "f", "c10", "sort", "page", "sb"}

URL_TYPE_PARAMS: dict[UrlType, dict[str, str]] = {
    "actors": {"magnet": "t=d", "sub": "t=c", "both": "t=c,d"},
    "series": {"magnet": "f=download", "sub": "f=cnsub", "both": "f=cnsub"},
    "makers": {"magnet": "f=download", "sub": "f=cnsub", "both": "f=cnsub"},
    "directors": {"magnet": "f=download", "sub": "f=cnsub", "both": "f=cnsub"},
    "video_codes": {"magnet": "f=download", "sub": "f=cnsub", "both": "f=cnsub"},
    "lists": {"magnet": "f=download", "sub": "f=cnsub", "both": "f=cnsub"},
    "tags": {"magnet": "c10=1", "sub": "c10=2", "both": "c10=1,2"},
    "search": {"magnet": "f=download", "sub": "f=cnsub", "both": "f=cnsub"},
}


def determine_source(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    return parsed.netloc.lower()


def _without_managed_params(raw_url: str) -> tuple:
    parsed = urlparse(raw_url)
    params = [
        (key, value)
        for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
        if key not in PARAM_KEYS
        for value in values
    ]
    return parsed, params


def _with_parts(raw_url: str, parts: list[str]) -> str:
    parsed, params = _without_managed_params(raw_url)
    next_params = list(params)
    for part in parts:
        key, value = part.split("=", 1)
        next_params.append((key, value))
    query = urlencode(next_params)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", query, ""))


def build_final_url(
    *,
    url: str,
    url_type: UrlType,
    has_magnet: bool,
    has_chinese_sub: bool,
    sort_type: int,
) -> str:
    parts: list[str] = []

    if url_type == "search":
        if has_magnet:
            parts.append("f=download")
        elif has_chinese_sub:
            parts.append("f=cnsub")
        parts.append(f"sb={sort_type}")
        return _with_parts(url, parts)

    config = URL_TYPE_PARAMS[url_type]
    if has_magnet and has_chinese_sub:
        parts.append(config["both"])
    elif has_magnet:
        parts.append(config["magnet"])
    elif has_chinese_sub:
        parts.append(config["sub"])

    if url_type in {"actors", "video_codes"} and sort_type != 0:
        parts.append(f"sort={sort_type}")

    if not parts:
        return _with_parts(url, [])

    return _with_parts(url, parts)


def normalize_url_entry(entry: TaskUrlEntry) -> dict:
    source = determine_source(entry.url)
    final_url = build_final_url(
        url=entry.url,
        url_type=entry.url_type,
        has_magnet=entry.has_magnet,
        has_chinese_sub=entry.has_chinese_sub,
        sort_type=entry.sort_type,
    )
    return {
        "url": entry.url,
        "url_type": entry.url_type,
        "has_magnet": entry.has_magnet,
        "has_chinese_sub": entry.has_chinese_sub,
        "sort_type": entry.sort_type,
        "source": source,
        "final_url": final_url,
        "url_name": entry.url_name or "",
    }


def extract_name_from_url(raw_url: str, url_type: UrlType) -> str:
    parsed = urlparse(raw_url)
    if url_type == "search":
        q_values = parse_qs(parsed.query).get("q", [])
        return unquote(q_values[0]).strip() if q_values else ""

    slug = parsed.path.rstrip("/").split("/")[-1]
    return unquote(quote(slug, safe="%")).replace("-", " ").replace("_", " ").strip()
```

- [ ] **Step 8: Add crawler task router**

Create `backend/app/modules/crawler/tasks/router.py`:

```python
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_db
from backend.app.models.crawler import CrawlTask
from backend.app.modules.crawler.tasks.schemas import (
    CrawlTaskResponse,
    ExtractNameRequest,
    ExtractNameResponse,
    TaskCreate,
    TaskDeleteResponse,
    TaskSkipUpdate,
    TaskUpdate,
    TaskUrlEntry,
)
from backend.app.modules.crawler.tasks.url_utils import (
    extract_name_from_url,
    normalize_url_entry,
)
from backend.app.repositories.task import TaskRepository

router = APIRouter(prefix="/api/crawler/tasks", tags=["crawler-tasks"])


def parse_task_id(task_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(task_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid task ID",
        ) from exc


def task_to_response(task: CrawlTask) -> dict:
    return {
        "_id": str(task.id),
        "name": task.name,
        "urls": task.urls or [],
        "is_skip": task.is_skip,
        "config": task.config or {},
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def ensure_unique_urls(urls: list[TaskUrlEntry]) -> None:
    seen: set[str] = set()
    for entry in urls:
        normalized = entry.url.strip()
        if normalized in seen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate URL: {normalized}",
            )
        seen.add(normalized)


def normalize_entries(urls: list[TaskUrlEntry]) -> list[dict]:
    ensure_unique_urls(urls)
    return [normalize_url_entry(entry) for entry in urls]


DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[CrawlTaskResponse])
def list_tasks(db: DbSession) -> list[dict]:
    repository = TaskRepository(db)
    return [task_to_response(task) for task in repository.list()]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CrawlTaskResponse)
def create_task(body: TaskCreate, db: DbSession) -> dict:
    repository = TaskRepository(db)
    name = body.name.strip()

    if repository.name_exists(name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task name already exists: {name}",
        )

    task = CrawlTask(
        name=name,
        urls=normalize_entries(body.urls),
        is_skip=body.is_skip,
        config={},
    )
    return task_to_response(repository.create(task))


@router.get("/{task_id}", response_model=CrawlTaskResponse)
def get_task(task_id: str, db: DbSession) -> dict:
    repository = TaskRepository(db)
    task = repository.get(parse_task_id(task_id))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task_to_response(task)


@router.put("/{task_id}", response_model=CrawlTaskResponse)
def update_task(task_id: str, body: TaskUpdate, db: DbSession) -> dict:
    repository = TaskRepository(db)
    parsed_id = parse_task_id(task_id)
    task = repository.get(parsed_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    update_data = body.model_dump(exclude_unset=True)
    if "name" in update_data and body.name is not None:
        name = body.name.strip()
        if repository.name_exists(name, exclude_id=parsed_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Task name already exists: {name}",
            )
        task.name = name

    if body.urls is not None:
        task.urls = normalize_entries(body.urls)

    if body.is_skip is not None:
        task.is_skip = body.is_skip

    return task_to_response(repository.save(task))


@router.patch("/{task_id}/skip", response_model=CrawlTaskResponse)
def toggle_task_skip(task_id: str, body: TaskSkipUpdate, db: DbSession) -> dict:
    repository = TaskRepository(db)
    task = repository.get(parse_task_id(task_id))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    task.is_skip = body.is_skip
    return task_to_response(repository.save(task))


@router.delete("/{task_id}", response_model=TaskDeleteResponse)
def delete_task(task_id: str, db: DbSession) -> TaskDeleteResponse:
    repository = TaskRepository(db)
    task = repository.get(parse_task_id(task_id))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    repository.delete(task)
    return TaskDeleteResponse(deleted=True)


@router.post("/extract-name", response_model=ExtractNameResponse)
def extract_name(body: ExtractNameRequest) -> ExtractNameResponse:
    return ExtractNameResponse(name=extract_name_from_url(body.url, body.url_type))
```

- [ ] **Step 9: Register router and model metadata**

Modify `backend/app/main.py`:

```python
import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import get_settings
from backend.app.core.dependencies import close_redis
from backend.app.modules.auth.router import router as auth_router
from backend.app.modules.crawler.tasks.router import router as crawler_tasks_router
from backend.app.modules.health.router import router as health_router
from backend.app.modules.init.router import router as init_router
from shared.database.session import close_postgres, connect_postgres
from shared.logging.file_log import ensure_log_dir
from shared.runtime_config import load_runtime_config, runtime_config_exists

settings = get_settings()

logger = logging.getLogger()
logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

console_handler = logging.StreamHandler(sys.stderr)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

ensure_log_dir(settings.log_dir)
file_handler = logging.FileHandler(
    f"{settings.log_dir}/backend.log", encoding="utf-8"
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle."""
    logger.info("Starting Media Forge backend v%s", settings.app_version)

    load_runtime_config()

    if runtime_config_exists():
        connect_postgres()
        logger.info("PostgreSQL connected.")
    else:
        logger.warning("Backend not initialized — only init endpoints available.")

    yield

    close_redis()
    if runtime_config_exists():
        close_postgres()
    logger.info("Media Forge backend shut down.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(init_router)
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(crawler_tasks_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} API", "version": settings.app_version}
```

Modify `backend/alembic/env.py`:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.app.models.crawler import CrawlTask  # noqa: F401
from backend.app.models.user import User  # noqa: F401
from shared.database.models.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 10: Add Alembic migration**

Create `backend/alembic/versions/b17e4f6d9c01_add_crawler_tasks.py`:

```python
"""add_crawler_tasks

Revision ID: b17e4f6d9c01
Revises: a04675645d56
Create Date: 2026-07-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b17e4f6d9c01"
down_revision: Union[str, None] = "a04675645d56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crawl_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("urls", sa.JSON(), nullable=False),
        sa.Column("is_skip", sa.Boolean(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crawl_tasks")),
        sa.UniqueConstraint("name", name="uq_crawl_tasks_name"),
    )
    op.create_index("idx_crawl_tasks_created_at", "crawl_tasks", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_crawl_tasks_created_at", table_name="crawl_tasks")
    op.drop_table("crawl_tasks")
```

- [ ] **Step 11: Run backend task tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_tasks.py -v
```

Expected: PASS for all tests in `backend/tests/test_crawler_tasks.py`.

- [ ] **Step 12: Run all backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/ -v
```

Expected: PASS for auth, health, and crawler task tests.

- [ ] **Step 13: Commit Task 1**

Run:

```bash
git add backend/app/models/crawler.py backend/app/models/__init__.py backend/app/repositories/task.py backend/app/modules/crawler backend/app/main.py backend/alembic/env.py backend/alembic/versions/b17e4f6d9c01_add_crawler_tasks.py backend/tests/test_crawler_tasks.py
git commit -m "feat: add crawler task backend API"
```

Expected: Commit succeeds.

---

### Task 2: Extract Frontend Task Types, API Client, And URL Utilities

**Files:**
- Create: `frontend/src/api/crawler/tasks/types.ts`
- Create: `frontend/src/api/crawler/tasks/index.ts`
- Create: `frontend/src/pages/crawler/tasks/task-url-utils.ts`
- Test: `frontend/tests/crawler-task-url-utils.test.ts`
- Test: `frontend/tests/crawler-tasks-api.test.ts`

- [ ] **Step 1: Write URL utility tests**

Create `frontend/tests/crawler-task-url-utils.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { buildFinalUrl, detectUrlType } from '../src/pages/crawler/tasks/task-url-utils'

describe('crawler task URL utilities', () => {
  it('detects supported JavDB URL types', () => {
    expect(detectUrlType('https://javdb.com/actors/abc')).toBe('actors')
    expect(detectUrlType('https://javdb.com/series/abc')).toBe('series')
    expect(detectUrlType('https://javdb.com/makers/abc')).toBe('makers')
    expect(detectUrlType('https://javdb.com/directors/abc')).toBe('directors')
    expect(detectUrlType('https://javdb.com/video_codes/abc')).toBe('video_codes')
    expect(detectUrlType('https://javdb.com/lists/abc')).toBe('lists')
    expect(detectUrlType('https://javdb.com/tags')).toBe('tags')
    expect(detectUrlType('https://javdb.com/tags/abc')).toBe('tags')
    expect(detectUrlType('https://javdb.com/search?q=abc')).toBe('search')
  })

  it('returns null for invalid or unsupported URLs', () => {
    expect(detectUrlType('not-a-url')).toBeNull()
    expect(detectUrlType('https://javdb.com/unknown/abc')).toBeNull()
  })

  it('builds actor final URLs with magnet, subtitle, and sort parameters', () => {
    expect(buildFinalUrl({
      baseUrl: 'https://javdb.com/actors/abc?t=d&page=2&keep=1',
      urlType: 'actors',
      hasMagnet: true,
      hasChineseSub: true,
      sortType: 5,
    })).toBe('https://javdb.com/actors/abc?keep=1&t=c%2Cd&sort=5')
  })

  it('builds search final URLs with sb ordering and download filter', () => {
    expect(buildFinalUrl({
      baseUrl: 'https://javdb.com/search?q=test&f=cnsub&page=3',
      urlType: 'search',
      hasMagnet: true,
      hasChineseSub: true,
      sortType: 1,
    })).toBe('https://javdb.com/search?q=test&f=download&sb=1')
  })

  it('preserves unknown extra query parameters', () => {
    expect(buildFinalUrl({
      baseUrl: 'https://javdb.com/tags?c7=212&c10=1',
      urlType: 'tags',
      hasMagnet: false,
      hasChineseSub: true,
      sortType: 0,
    })).toBe('https://javdb.com/tags?c7=212&c10=2')
  })
})
```

- [ ] **Step 2: Run URL utility tests to verify they fail**

Run:

```bash
cd frontend && npm test -- crawler-task-url-utils.test.ts
```

Expected: FAIL with a module resolution error for `../src/pages/crawler/tasks/task-url-utils`.

- [ ] **Step 3: Write API wrapper tests**

Create `frontend/tests/crawler-tasks-api.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createTask,
  deleteTask,
  extractTaskName,
  fetchTask,
  fetchTasks,
  toggleTaskSkip,
  updateTask,
} from '../src/api/crawler/tasks'
import { request } from '@/request'
import type { TaskPayload } from '../src/api/crawler/tasks/types'

vi.mock('@/request', () => ({
  request: vi.fn(),
}))

const mockedRequest = vi.mocked(request)

describe('crawler tasks API', () => {
  beforeEach(() => {
    mockedRequest.mockReset()
  })

  it('fetches the task list from the Media Forge API prefix', async () => {
    mockedRequest.mockResolvedValueOnce([])

    await fetchTasks()

    expect(mockedRequest).toHaveBeenCalledWith({
      url: '/api/crawler/tasks',
      method: 'get',
    })
  })

  it('fetches one task by id', async () => {
    mockedRequest.mockResolvedValueOnce({ _id: 'task-1' })

    await fetchTask('task-1')

    expect(mockedRequest).toHaveBeenCalledWith({
      url: '/api/crawler/tasks/task-1',
      method: 'get',
    })
  })

  it('creates a task payload', async () => {
    const payload: TaskPayload = {
      name: 'Actor A',
      is_skip: false,
      urls: [{
        url: 'https://javdb.com/actors/a',
        url_type: 'actors',
        has_magnet: true,
        has_chinese_sub: false,
        sort_type: 0,
        url_name: 'Actor A',
      }],
    }
    mockedRequest.mockResolvedValueOnce({ _id: 'task-1' })

    await createTask(payload)

    expect(mockedRequest).toHaveBeenCalledWith({
      url: '/api/crawler/tasks',
      method: 'post',
      data: payload,
      isRepeatSubmit: true,
    })
  })

  it('updates a task payload', async () => {
    const payload: TaskPayload = {
      name: 'Actor B',
      is_skip: false,
      urls: [],
    }
    mockedRequest.mockResolvedValueOnce({ _id: 'task-1' })

    await updateTask('task-1', payload)

    expect(mockedRequest).toHaveBeenCalledWith({
      url: '/api/crawler/tasks/task-1',
      method: 'put',
      data: payload,
      isRepeatSubmit: true,
    })
  })

  it('toggles task skip state through a narrow patch endpoint', async () => {
    mockedRequest.mockResolvedValueOnce({ _id: 'task-1', is_skip: true })

    await toggleTaskSkip('task-1', true)

    expect(mockedRequest).toHaveBeenCalledWith({
      url: '/api/crawler/tasks/task-1/skip',
      method: 'patch',
      data: { is_skip: true },
      isRepeatSubmit: true,
    })
  })

  it('deletes a task by id', async () => {
    mockedRequest.mockResolvedValueOnce({ deleted: true })

    await deleteTask('task-1')

    expect(mockedRequest).toHaveBeenCalledWith({
      url: '/api/crawler/tasks/task-1',
      method: 'delete',
    })
  })

  it('extracts a display name for a URL entry', async () => {
    mockedRequest.mockResolvedValueOnce({ name: 'Actor A' })

    await extractTaskName('https://javdb.com/actors/a', 'actors')

    expect(mockedRequest).toHaveBeenCalledWith({
      url: '/api/crawler/tasks/extract-name',
      method: 'post',
      data: {
        url: 'https://javdb.com/actors/a',
        url_type: 'actors',
      },
      isRepeatSubmit: true,
    })
  })
})
```

- [ ] **Step 4: Run API tests to verify they fail**

Run:

```bash
cd frontend && npm test -- crawler-tasks-api.test.ts
```

Expected: FAIL with a module resolution error for `../src/api/crawler/tasks`.

- [ ] **Step 5: Implement task types**

Create `frontend/src/api/crawler/tasks/types.ts`:

```ts
export type UrlType =
  | 'actors'
  | 'series'
  | 'makers'
  | 'directors'
  | 'video_codes'
  | 'lists'
  | 'tags'
  | 'search'

export interface TaskUrlEntry {
  url: string
  url_type: UrlType
  has_magnet: boolean
  has_chinese_sub: boolean
  sort_type: number
  source?: string
  final_url?: string
  url_name?: string
}

export interface CrawlTask {
  _id: string
  name: string
  urls: TaskUrlEntry[]
  is_skip: boolean
  created_at?: string
  updated_at?: string
}

export interface TaskPayload {
  name: string
  urls: TaskUrlEntry[]
  is_skip: boolean
}

export interface TaskDeleteResult {
  deleted: boolean
}

export interface ExtractNameResult {
  name: string
}
```

- [ ] **Step 6: Implement task API client**

Create `frontend/src/api/crawler/tasks/index.ts`:

```ts
import { request } from '@/request'
import type {
  CrawlTask,
  ExtractNameResult,
  TaskDeleteResult,
  TaskPayload,
  UrlType,
} from './types'

const BASE_URL = '/api/crawler/tasks'

export function fetchTasks(): Promise<CrawlTask[]> {
  return request<CrawlTask[]>({
    url: BASE_URL,
    method: 'get',
  })
}

export function fetchTask(id: string): Promise<CrawlTask> {
  return request<CrawlTask>({
    url: `${BASE_URL}/${id}`,
    method: 'get',
  })
}

export function createTask(data: TaskPayload): Promise<CrawlTask> {
  return request<CrawlTask>({
    url: BASE_URL,
    method: 'post',
    data,
    isRepeatSubmit: true,
  })
}

export function updateTask(id: string, data: TaskPayload): Promise<CrawlTask> {
  return request<CrawlTask>({
    url: `${BASE_URL}/${id}`,
    method: 'put',
    data,
    isRepeatSubmit: true,
  })
}

export function toggleTaskSkip(id: string, isSkip: boolean): Promise<CrawlTask> {
  return request<CrawlTask>({
    url: `${BASE_URL}/${id}/skip`,
    method: 'patch',
    data: { is_skip: isSkip },
    isRepeatSubmit: true,
  })
}

export function deleteTask(id: string): Promise<TaskDeleteResult> {
  return request<TaskDeleteResult>({
    url: `${BASE_URL}/${id}`,
    method: 'delete',
  })
}

export function extractTaskName(url: string, urlType: UrlType): Promise<ExtractNameResult> {
  return request<ExtractNameResult>({
    url: `${BASE_URL}/extract-name`,
    method: 'post',
    data: {
      url,
      url_type: urlType,
    },
    isRepeatSubmit: true,
  })
}

export type {
  CrawlTask,
  ExtractNameResult,
  TaskDeleteResult,
  TaskPayload,
  TaskUrlEntry,
  UrlType,
} from './types'
```

- [ ] **Step 7: Implement URL utility module**

Create `frontend/src/pages/crawler/tasks/task-url-utils.ts`:

```ts
import type { UrlType } from '@/api/crawler/tasks/types'

type CondParamConfig = {
  magnet: string
  sub: string
  both: string
}

export const URL_TYPE_LABELS: Record<UrlType, string> = {
  actors: '演员',
  series: '系列',
  makers: '片商',
  directors: '导演',
  video_codes: '番号',
  lists: '列表',
  tags: '标签',
  search: '搜索',
}

export const URL_TYPE_HINTS: Record<UrlType, string> = {
  actors: 'actors',
  series: 'series',
  makers: 'makers',
  directors: 'directors',
  video_codes: 'video_codes',
  lists: 'lists',
  tags: 'tags',
  search: 'search',
}

export const SORT_OPTIONS = [
  { value: 0, label: '日期降序' },
  { value: 5, label: '番号降序' },
]

export const SEARCH_SORT_OPTIONS = [
  { value: 0, label: '按相关度' },
  { value: 1, label: '按发布日期' },
]

const URL_TYPE_PARAMS: Record<UrlType, CondParamConfig> = {
  actors: { magnet: 't=d', sub: 't=c', both: 't=c,d' },
  series: { magnet: 'f=download', sub: 'f=cnsub', both: 'f=cnsub' },
  makers: { magnet: 'f=download', sub: 'f=cnsub', both: 'f=cnsub' },
  directors: { magnet: 'f=download', sub: 'f=cnsub', both: 'f=cnsub' },
  video_codes: { magnet: 'f=download', sub: 'f=cnsub', both: 'f=cnsub' },
  lists: { magnet: 'f=download', sub: 'f=cnsub', both: 'f=cnsub' },
  tags: { magnet: 'c10=1', sub: 'c10=2', both: 'c10=1,2' },
  search: { magnet: 'f=download', sub: 'f=cnsub', both: 'f=cnsub' },
}

const PARAM_KEYS = ['t', 'f', 'c10', 'sort', 'page', 'sb'] as const

export type BuildFinalUrlInput = {
  baseUrl: string
  urlType: UrlType | null | undefined
  hasMagnet: boolean
  hasChineseSub: boolean
  sortType: number
}

export function detectUrlType(rawUrl: string): UrlType | null {
  try {
    const url = new URL(rawUrl)
    const path = url.pathname

    if (path.startsWith('/search')) return 'search'
    if (path.startsWith('/actors/')) return 'actors'
    if (path.startsWith('/series/')) return 'series'
    if (path.startsWith('/makers/')) return 'makers'
    if (path.startsWith('/directors/')) return 'directors'
    if (path.startsWith('/video_codes/')) return 'video_codes'
    if (path.startsWith('/lists/')) return 'lists'
    if (path === '/tags' || path.startsWith('/tags/')) return 'tags'

    return null
  } catch {
    return null
  }
}

function strippedUrl(rawUrl: string): URL | null {
  try {
    const url = new URL(rawUrl)
    PARAM_KEYS.forEach((key) => url.searchParams.delete(key))
    return url
  } catch {
    return null
  }
}

function appendParamParts(url: URL, parts: string[]): string {
  const nextUrl = new URL(url.toString())
  for (const part of parts) {
    const [key, value] = part.split('=')
    nextUrl.searchParams.set(key, value)
  }
  return nextUrl.toString()
}

export function buildFinalUrl({
  baseUrl,
  urlType,
  hasMagnet,
  hasChineseSub,
  sortType,
}: BuildFinalUrlInput): string {
  if (!baseUrl || !urlType) return baseUrl

  const url = strippedUrl(baseUrl)
  if (!url) return baseUrl

  const parts: string[] = []

  if (urlType === 'search') {
    if (hasMagnet) {
      parts.push('f=download')
    } else if (hasChineseSub) {
      parts.push('f=cnsub')
    }
    parts.push(`sb=${sortType}`)
    return appendParamParts(url, parts)
  }

  const config = URL_TYPE_PARAMS[urlType]
  if (hasMagnet && hasChineseSub) {
    parts.push(config.both)
  } else if (hasMagnet) {
    parts.push(config.magnet)
  } else if (hasChineseSub) {
    parts.push(config.sub)
  }

  if ((urlType === 'actors' || urlType === 'video_codes') && sortType !== 0) {
    parts.push(`sort=${sortType}`)
  }

  if (parts.length === 0) return url.toString()

  return appendParamParts(url, parts)
}

export function formatUrlTypeLabel(urlType: UrlType | null): string {
  if (!urlType) return '无法识别'
  return `${URL_TYPE_LABELS[urlType]} (${URL_TYPE_HINTS[urlType]})`
}

export function canShowSort(urlType: UrlType | null | undefined): boolean {
  return urlType === 'video_codes' || urlType === 'search'
}
```

- [ ] **Step 8: Run Task 2 tests**

Run:

```bash
cd frontend && npm test -- crawler-task-url-utils.test.ts crawler-tasks-api.test.ts
```

Expected: PASS for both test files.

- [ ] **Step 9: Commit Task 2**

Run:

```bash
git add frontend/src/api/crawler/tasks frontend/src/pages/crawler/tasks/task-url-utils.ts frontend/tests/crawler-task-url-utils.test.ts frontend/tests/crawler-tasks-api.test.ts
git commit -m "feat: add crawler task API and URL utilities"
```

Expected: Commit succeeds.

---

### Task 3: Build The New/Edit Task Form Page

**Files:**
- Create: `frontend/src/pages/crawler/tasks/components/UrlEntryCard.tsx`
- Create: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
- Create: `frontend/src/pages/crawler/tasks/TaskPages.module.less`
- Test: `frontend/tests/crawler-task-pages.ui.test.tsx`

- [ ] **Step 1: Write form UI tests**

Create `frontend/tests/crawler-task-pages.ui.test.tsx`:

```tsx
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import TaskFormPage from '../src/pages/crawler/tasks/TaskFormPage'
import TaskListPage from '../src/pages/crawler/tasks/TaskListPage'

const navigateMock = vi.fn()

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    useNavigate: () => navigateMock,
    useParams: () => ({}),
  }
})

vi.mock('../src/api/crawler/tasks', () => ({
  createTask: vi.fn().mockResolvedValue({ _id: 'task-1' }),
  deleteTask: vi.fn().mockResolvedValue({ deleted: true }),
  extractTaskName: vi.fn().mockResolvedValue({ name: 'Actor A' }),
  fetchTask: vi.fn(),
  fetchTasks: vi.fn().mockResolvedValue([
    {
      _id: 'task-1',
      name: 'Actor A',
      is_skip: false,
      urls: [{
        url: 'https://javdb.com/actors/a',
        url_type: 'actors',
        has_magnet: true,
        has_chinese_sub: false,
        sort_type: 0,
        url_name: 'Actor A',
      }],
    },
  ]),
  toggleTaskSkip: vi.fn().mockResolvedValue({ _id: 'task-1', is_skip: true }),
  updateTask: vi.fn().mockResolvedValue({ _id: 'task-1' }),
}))

function renderWithAntApp(ui: React.ReactElement) {
  return render(<AntApp>{ui}</AntApp>)
}

function renderRoute(ui: React.ReactElement) {
  const rootRoute = createRootRoute({ component: () => <AntApp>{ui}</AntApp> })
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })

  return render(<RouterProvider router={router} />)
}

describe('crawler task pages', () => {
  beforeEach(() => {
    navigateMock.mockReset()
  })

  it('renders the new task form with URL preview controls', async () => {
    renderWithAntApp(<TaskFormPage />)

    expect(screen.getByRole('heading', { name: '新建爬取任务' })).toBeInTheDocument()
    expect(screen.getByLabelText('任务名称')).toBeInTheDocument()
    expect(screen.getByLabelText('URL')).toBeInTheDocument()
    expect(screen.getByText('最终 URL 预览')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('URL'), 'https://javdb.com/actors/a')

    expect(await screen.findByDisplayValue('演员 (actors)')).toBeInTheDocument()
  })

  it('submits a valid new task and returns to the task list', async () => {
    const api = await import('../src/api/crawler/tasks')
    const createTask = vi.mocked(api.createTask)

    renderWithAntApp(<TaskFormPage />)

    await userEvent.type(screen.getByLabelText('任务名称'), 'Actor A')
    await userEvent.clear(screen.getByLabelText('URL'))
    await userEvent.type(screen.getByLabelText('URL'), 'https://javdb.com/actors/a')
    await userEvent.click(screen.getByRole('button', { name: '创建任务' }))

    await waitFor(() => {
      expect(createTask).toHaveBeenCalledWith({
        name: 'Actor A',
        is_skip: false,
        urls: [{
          url: 'https://javdb.com/actors/a',
          url_type: 'actors',
          has_magnet: true,
          has_chinese_sub: false,
          sort_type: 0,
          url_name: '',
          final_url: 'https://javdb.com/actors/a?t=d',
        }],
      })
      expect(navigateMock).toHaveBeenCalledWith({ to: '/crawler/tasks' })
    })
  })

  it('renders the task list with fetched rows', async () => {
    renderRoute(<TaskListPage />)

    expect(await screen.findByRole('heading', { name: '爬取任务' })).toBeInTheDocument()
    expect(await screen.findByText('Actor A')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '新建任务' })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run form UI tests to verify they fail**

Run:

```bash
cd frontend && npm test -- crawler-task-pages.ui.test.tsx
```

Expected: FAIL with module resolution errors for `TaskFormPage` and `TaskListPage`.

- [ ] **Step 3: Implement shared task page styles**

Create `frontend/src/pages/crawler/tasks/TaskPages.module.less`:

```less
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.pageHeader {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.titleBlock {
  min-width: 0;
}

.eyebrow {
  display: block;
  margin-bottom: 4px;
  color: rgba(15, 23, 42, 0.56);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.title {
  margin: 0;
  color: #111827;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.25;
}

.summary {
  margin: 6px 0 0;
  color: rgba(15, 23, 42, 0.64);
  font-size: 14px;
  line-height: 1.5;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 8px;
  background: #fff;
}

.tablePanel,
.formPanel {
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 8px;
  background: #fff;
}

.formPanel {
  padding: 18px;
}

.urlGrid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.urlCard {
  height: 100%;
}

.addUrlButton {
  min-height: 216px;
  width: 100%;
}

.formActions {
  display: flex;
  gap: 8px;
  margin-top: 24px;
}

.finalUrlInput input {
  color: rgba(15, 23, 42, 0.72) !important;
}

@media (max-width: 768px) {
  .pageHeader,
  .toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .urlGrid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 4: Implement URL entry card component**

Create `frontend/src/pages/crawler/tasks/components/UrlEntryCard.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react'
import { MinusCircleOutlined, SearchOutlined } from '@ant-design/icons'
import { App, Button, Card, Form, Input, Select, Switch } from 'antd'
import { extractTaskName } from '@/api/crawler/tasks'
import type { UrlType } from '@/api/crawler/tasks/types'
import {
  buildFinalUrl,
  canShowSort,
  detectUrlType,
  formatUrlTypeLabel,
  SEARCH_SORT_OPTIONS,
  SORT_OPTIONS,
} from '../task-url-utils'
import styles from '../TaskPages.module.less'

type UrlEntryCardProps = {
  index: number
  remove?: () => void
  onNameExtracted: (index: number, name: string) => void
  onUrlTypeDetected: (index: number, urlType: UrlType) => void
}

type FieldValue = string | number | boolean | undefined

function readField(getFieldValue: (name: (string | number)[]) => FieldValue, index: number, field: string): FieldValue {
  return getFieldValue(['urls', index, field])
}

export function UrlEntryCard({
  index,
  remove,
  onNameExtracted,
  onUrlTypeDetected,
}: UrlEntryCardProps) {
  const { message } = App.useApp()
  const [extracting, setExtracting] = useState(false)
  const form = Form.useFormInstance()
  const url = Form.useWatch(['urls', index, 'url'], form) as string | undefined
  const urlType = Form.useWatch(['urls', index, 'url_type'], form) as UrlType | undefined

  const detectedType = useMemo(() => (url ? detectUrlType(url) : null), [url])

  useEffect(() => {
    if (detectedType && detectedType !== urlType) {
      onUrlTypeDetected(index, detectedType)
    }
  }, [detectedType, index, onUrlTypeDetected, urlType])

  const handleExtractName = async () => {
    if (!url || !urlType) {
      message.warning('请输入可识别的 URL')
      return
    }

    setExtracting(true)
    try {
      const result = await extractTaskName(url, urlType)
      if (result.name) {
        onNameExtracted(index, result.name)
      } else {
        message.warning('未能提取到名称')
      }
    } catch {
      message.error('名称提取失败')
    } finally {
      setExtracting(false)
    }
  }

  return (
    <Card
      className={styles.urlCard}
      size="small"
      title={`URL ${index + 1}`}
      extra={remove ? (
        <Button
          aria-label={`删除 URL ${index + 1}`}
          danger
          icon={<MinusCircleOutlined />}
          onClick={remove}
          shape="circle"
          size="small"
          type="text"
        />
      ) : null}
    >
      <Form.Item
        name={[index, 'url']}
        label="URL"
        rules={[
          { required: true, message: '请输入 URL' },
          { type: 'url', message: '请输入完整 URL，例如 https://javdb.com/actors/abc' },
        ]}
      >
        <Input placeholder="https://javdb.com/actors/..." />
      </Form.Item>

      <Form.Item label="URL 类型">
        <Input value={url ? formatUrlTypeLabel(detectedType) : '请输入 URL'} disabled />
      </Form.Item>

      <Form.Item name={[index, 'url_type']} hidden>
        <Input />
      </Form.Item>

      <Form.Item name={[index, 'has_magnet']} label="含磁力链接" valuePropName="checked">
        <Switch />
      </Form.Item>

      <Form.Item name={[index, 'has_chinese_sub']} label="含中文字幕" valuePropName="checked">
        <Switch />
      </Form.Item>

      {canShowSort(urlType) && (
        <Form.Item name={[index, 'sort_type']} label="排序方式">
          <Select options={urlType === 'search' ? SEARCH_SORT_OPTIONS : SORT_OPTIONS} />
        </Form.Item>
      )}

      <Form.Item noStyle shouldUpdate>
        {({ getFieldValue }) => {
          const currentUrl = String(readField(getFieldValue, index, 'url') ?? '')
          const currentType = readField(getFieldValue, index, 'url_type') as UrlType | undefined
          const hasMagnet = Boolean(readField(getFieldValue, index, 'has_magnet'))
          const hasChineseSub = Boolean(readField(getFieldValue, index, 'has_chinese_sub'))
          const sortType = Number(readField(getFieldValue, index, 'sort_type') ?? 0)
          const finalUrl = buildFinalUrl({
            baseUrl: currentUrl,
            urlType: currentType,
            hasMagnet,
            hasChineseSub,
            sortType,
          })

          return (
            <Form.Item label="最终 URL 预览">
              <Input className={styles.finalUrlInput} value={finalUrl} disabled />
            </Form.Item>
          )
        }}
      </Form.Item>

      <Form.Item noStyle shouldUpdate>
        {({ getFieldValue }) => {
          const urlName = readField(getFieldValue, index, 'url_name')
          if (!urlName) return null

          return (
            <Form.Item label="URL 名称">
              <Input value={String(urlName)} disabled />
            </Form.Item>
          )
        }}
      </Form.Item>

      <Button
        disabled={!url || !urlType}
        icon={<SearchOutlined />}
        loading={extracting}
        onClick={handleExtractName}
      >
        获取名称
      </Button>
    </Card>
  )
}
```

- [ ] **Step 5: Implement task form page**

Create `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useState } from 'react'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate, useParams } from '@tanstack/react-router'
import { App, Button, Col, Form, Input, Row, Spin, Switch } from 'antd'
import {
  createTask,
  extractTaskName,
  fetchTask,
  updateTask,
} from '@/api/crawler/tasks'
import type { TaskPayload, TaskUrlEntry, UrlType } from '@/api/crawler/tasks/types'
import { buildFinalUrl, detectUrlType } from './task-url-utils'
import { UrlEntryCard } from './components/UrlEntryCard'
import styles from './TaskPages.module.less'

type TaskFormValues = {
  name?: string
  is_skip?: boolean
  urls?: Array<Partial<TaskUrlEntry>>
}

const initialUrlEntry: Partial<TaskUrlEntry> = {
  has_magnet: true,
  has_chinese_sub: false,
  sort_type: 0,
  url_name: '',
}

function normalizeUrlEntry(entry: Partial<TaskUrlEntry>): TaskUrlEntry {
  const url = String(entry.url ?? '').trim()
  const detectedType = detectUrlType(url)
  const urlType = (entry.url_type || detectedType) as UrlType
  const hasMagnet = Boolean(entry.has_magnet)
  const hasChineseSub = Boolean(entry.has_chinese_sub)
  const sortType = Number(entry.sort_type ?? 0)

  return {
    url,
    url_type: urlType,
    has_magnet: hasMagnet,
    has_chinese_sub: hasChineseSub,
    sort_type: sortType,
    url_name: String(entry.url_name ?? ''),
    final_url: buildFinalUrl({
      baseUrl: url,
      urlType,
      hasMagnet,
      hasChineseSub,
      sortType,
    }),
  }
}

function findDuplicateUrl(entries: Array<Partial<TaskUrlEntry>>): string | null {
  const seen = new Set<string>()

  for (const entry of entries) {
    const url = String(entry.url ?? '').trim()
    if (!url) continue
    if (seen.has(url)) return url
    seen.add(url)
  }

  return null
}

async function enrichMissingNames(entries: TaskUrlEntry[]): Promise<TaskUrlEntry[]> {
  const enriched: TaskUrlEntry[] = []

  for (const entry of entries) {
    if (entry.url_name) {
      enriched.push(entry)
      continue
    }

    try {
      const result = await extractTaskName(entry.url, entry.url_type)
      enriched.push({ ...entry, url_name: result.name || '' })
    } catch {
      enriched.push(entry)
    }
  }

  return enriched
}

export default function TaskFormPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const params = useParams({ strict: false }) as { id?: string }
  const taskId = params.id
  const isEdit = Boolean(taskId)
  const [form] = Form.useForm<TaskFormValues>()
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!taskId) return

    setLoading(true)
    fetchTask(taskId)
      .then((task) => {
        form.setFieldsValue({
          name: task.name,
          is_skip: task.is_skip,
          urls: task.urls.map((entry) => ({
            url: entry.url,
            url_type: entry.url_type,
            has_magnet: entry.has_magnet,
            has_chinese_sub: entry.has_chinese_sub,
            sort_type: entry.sort_type,
            url_name: entry.url_name ?? '',
          })),
        })
      })
      .catch(() => {
        message.error('任务详情加载失败')
      })
      .finally(() => setLoading(false))
  }, [form, message, taskId])

  const pageTitle = useMemo(() => (isEdit ? '编辑爬取任务' : '新建爬取任务'), [isEdit])

  const updateUrlEntry = useCallback((index: number, patch: Partial<TaskUrlEntry>) => {
    const urls = form.getFieldValue('urls') ?? []
    const nextUrls = urls.map((entry, entryIndex) => (
      entryIndex === index ? { ...entry, ...patch } : entry
    ))
    form.setFieldsValue({ urls: nextUrls })
  }, [form])

  const handleSubmit = async (values: TaskFormValues) => {
    const rawEntries = values.urls ?? []
    const duplicateUrl = findDuplicateUrl(rawEntries)

    if (duplicateUrl) {
      message.error(`URL 重复: ${duplicateUrl}`)
      return
    }

    const entries = rawEntries.map(normalizeUrlEntry)
    const invalidEntry = entries.find((entry) => !entry.url_type)
    if (invalidEntry) {
      message.error(`无法识别 URL 类型: ${invalidEntry.url}`)
      return
    }

    setSubmitting(true)
    try {
      const payload: TaskPayload = {
        name: String(values.name ?? '').trim(),
        is_skip: Boolean(values.is_skip),
        urls: await enrichMissingNames(entries),
      }

      if (isEdit && taskId) {
        await updateTask(taskId, payload)
        message.success('任务已更新')
      } else {
        await createTask(payload)
        message.success('任务已创建')
      }

      void navigate({ to: '/crawler/tasks' })
    } catch {
      message.error(isEdit ? '任务更新失败' : '任务创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className={styles.page}>
        <Spin />
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div className={styles.titleBlock}>
          <span className={styles.eyebrow}>Crawler setup</span>
          <h1 className={styles.title}>{pageTitle}</h1>
          <p className={styles.summary}>配置可重复执行的媒体来源 URL、过滤条件和任务名称。</p>
        </div>
      </header>

      <section className={styles.formPanel}>
        <Form<TaskFormValues>
          form={form}
          layout="vertical"
          onFinish={(values) => { void handleSubmit(values) }}
          initialValues={{
            urls: [initialUrlEntry],
            is_skip: false,
          }}
        >
          <Row gutter={16}>
            <Col xs={24} lg={18}>
              <Form.Item
                name="name"
                label="任务名称"
                rules={[{ required: true, message: '请输入任务名称' }]}
              >
                <Input placeholder="例如：演员、系列或列表名称" />
              </Form.Item>
            </Col>
            <Col xs={24} lg={6}>
              <Form.Item name="is_skip" label="禁用任务" valuePropName="checked">
                <Switch checkedChildren="禁用" unCheckedChildren="启用" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item label="URL 列表" required>
            <Form.List name="urls">
              {(fields, { add, remove }) => (
                <div className={styles.urlGrid}>
                  {fields.map((field) => (
                    <UrlEntryCard
                      key={field.key}
                      index={field.name}
                      remove={fields.length > 1 ? () => remove(field.name) : undefined}
                      onNameExtracted={(index, name) => {
                        updateUrlEntry(index, { url_name: name })
                        if (!form.getFieldValue('name')) {
                          form.setFieldsValue({ name })
                        }
                      }}
                      onUrlTypeDetected={(index, urlType) => {
                        updateUrlEntry(index, { url_type: urlType })
                      }}
                    />
                  ))}
                  <Button
                    className={styles.addUrlButton}
                    icon={<PlusOutlined />}
                    onClick={() => add(initialUrlEntry)}
                    type="dashed"
                  >
                    添加 URL
                  </Button>
                </div>
              )}
            </Form.List>
          </Form.Item>

          <div className={styles.formActions}>
            <Button type="primary" htmlType="submit" loading={submitting}>
              {isEdit ? '更新任务' : '创建任务'}
            </Button>
            <Button onClick={() => navigate({ to: '/crawler/tasks' })}>
              取消
            </Button>
          </div>
        </Form>
      </section>
    </div>
  )
}
```

- [ ] **Step 6: Run form UI tests**

Run:

```bash
cd frontend && npm test -- crawler-task-pages.ui.test.tsx
```

Expected: FAIL only because `TaskListPage` has not been created yet. There should be no `TaskFormPage` module resolution error.

- [ ] **Step 7: Commit Task 3**

Run:

```bash
git add frontend/src/pages/crawler/tasks/components/UrlEntryCard.tsx frontend/src/pages/crawler/tasks/TaskFormPage.tsx frontend/src/pages/crawler/tasks/TaskPages.module.less frontend/tests/crawler-task-pages.ui.test.tsx
git commit -m "feat: add crawler task form page"
```

Expected: Commit succeeds.

---

### Task 4: Build The Task List Page

**Files:**
- Create: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/tests/crawler-task-pages.ui.test.tsx`

- [ ] **Step 1: Add list-specific interaction test**

Append this test inside the existing `describe('crawler task pages', () => { ... })` block in `frontend/tests/crawler-task-pages.ui.test.tsx`:

```tsx
  it('navigates from the task list to the new task form', async () => {
    renderRoute(<TaskListPage />)

    await userEvent.click(await screen.findByRole('button', { name: '新建任务' }))

    expect(navigateMock).toHaveBeenCalledWith({ to: '/crawler/tasks/new' })
  })
```

- [ ] **Step 2: Run list UI tests to verify they fail**

Run:

```bash
cd frontend && npm test -- crawler-task-pages.ui.test.tsx
```

Expected: FAIL with a module resolution error for `TaskListPage`.

- [ ] **Step 3: Implement task list page**

Create `frontend/src/pages/crawler/tasks/TaskListPage.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { useNavigate } from '@tanstack/react-router'
import { App, Button, Space, Switch, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  deleteTask,
  fetchTasks,
  toggleTaskSkip,
} from '@/api/crawler/tasks'
import type { CrawlTask } from '@/api/crawler/tasks/types'
import styles from './TaskPages.module.less'

function formatDate(value?: string): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

export default function TaskListPage() {
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<CrawlTask[]>([])
  const [loading, setLoading] = useState(false)

  const loadTasks = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchTasks()
      setTasks(data)
    } catch {
      message.error('任务列表加载失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    void loadTasks()
  }, [loadTasks])

  const handleToggle = async (task: CrawlTask) => {
    try {
      const nextSkip = !task.is_skip
      await toggleTaskSkip(task._id, nextSkip)
      message.success(nextSkip ? '任务已禁用' : '任务已启用')
      await loadTasks()
    } catch {
      message.error('任务状态更新失败')
    }
  }

  const handleDelete = (task: CrawlTask) => {
    modal.confirm({
      title: '删除任务',
      content: `确认删除“${task.name}”？任务配置会被移除。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteTask(task._id)
          message.success('任务已删除')
          await loadTasks()
        } catch {
          message.error('任务删除失败')
        }
      },
    })
  }

  const columns = useMemo<ColumnsType<CrawlTask>>(() => [
    {
      title: '任务名称',
      dataIndex: 'name',
      key: 'name',
      width: 220,
      render: (name: string) => <Typography.Text strong>{name}</Typography.Text>,
    },
    {
      title: 'URL',
      key: 'urls',
      width: 280,
      render: (_value, record) => (
        <Space size={4} wrap>
          <Tag>{record.urls.length} 个 URL</Tag>
          {record.urls.slice(0, 3).map((entry, index) => (
            <Tag key={`${entry.url}-${index}`}>{entry.url_name || entry.url_type}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_skip',
      key: 'is_skip',
      width: 120,
      render: (_value, record) => (
        <Switch
          checked={!record.is_skip}
          checkedChildren="启用"
          unCheckedChildren="禁用"
          onChange={() => { void handleToggle(record) }}
        />
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (value?: string) => formatDate(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_value, record) => (
        <Space>
          <Button
            icon={<EditOutlined />}
            onClick={() => navigate({ to: '/crawler/tasks/$id/edit', params: { id: record._id } })}
            size="small"
          >
            编辑
          </Button>
          <Button
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record)}
            size="small"
          >
            删除
          </Button>
        </Space>
      ),
    },
  ], [navigate])

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div className={styles.titleBlock}>
          <span className={styles.eyebrow}>Crawler tasks</span>
          <h1 className={styles.title}>爬取任务</h1>
          <p className={styles.summary}>管理可复用的媒体来源任务、URL 条件和启用状态。</p>
        </div>
      </header>

      <div className={styles.toolbar}>
        <Space>
          <Button
            icon={<PlusOutlined />}
            onClick={() => navigate({ to: '/crawler/tasks/new' })}
            type="primary"
          >
            新建任务
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => { void loadTasks() }}>
            刷新
          </Button>
        </Space>
        <Typography.Text type="secondary">
          共 {tasks.length} 个任务
        </Typography.Text>
      </div>

      <section className={styles.tablePanel}>
        <Table<CrawlTask>
          columns={columns}
          dataSource={tasks}
          loading={loading}
          pagination={{ pageSize: 20 }}
          rowKey="_id"
          scroll={{ x: 860 }}
        />
      </section>
    </div>
  )
}
```

- [ ] **Step 4: Run crawler page UI tests**

Run:

```bash
cd frontend && npm test -- crawler-task-pages.ui.test.tsx
```

Expected: PASS for `crawler-task-pages.ui.test.tsx`.

- [ ] **Step 5: Run all crawler-related frontend tests**

Run:

```bash
cd frontend && npm test -- crawler
```

Expected: PASS for `crawler-task-url-utils.test.ts`, `crawler-tasks-api.test.ts`, and `crawler-task-pages.ui.test.tsx`.

- [ ] **Step 6: Commit Task 4**

Run:

```bash
git add frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/tests/crawler-task-pages.ui.test.tsx
git commit -m "feat: add crawler task list page"
```

Expected: Commit succeeds.

---

### Task 5: Register Routes And Sidebar Navigation

**Files:**
- Modify: `frontend/src/routes/index.tsx`
- Modify: `frontend/src/layout/Sidebar/index.tsx`
- Modify: `frontend/tests/layout.ui.test.tsx`
- Modify: `frontend/tests/App.test.tsx`

- [ ] **Step 1: Update route and layout tests**

Modify `frontend/tests/layout.ui.test.tsx` so the first test includes the crawler menu assertion:

```tsx
  it('renders console shell landmarks and dashboard navigation', async () => {
    renderLayout()

    expect(await screen.findByText('Media Forge')).toBeInTheDocument()
    expect(screen.getByText('Operations Console')).toBeInTheDocument()
    expect(screen.getByRole('menu')).toBeInTheDocument()
    expect(screen.getAllByText('仪表盘').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('爬取任务')).toBeInTheDocument()
    expect(screen.getByText('console outlet')).toBeInTheDocument()
    expect(screen.queryByLabelText('Open settings')).not.toBeInTheDocument()
  })
```

Modify the authenticated route test in `frontend/tests/App.test.tsx` so it matches the current dashboard content and add a crawler route test:

```tsx
  it('shows dashboard for authenticated user', async () => {
    useAuthStore.setState({ token: 'test-token', isAuthenticated: true })

    renderApp('/')

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Operations Console' })).toBeInTheDocument()
      expect(screen.getByText('Media pipeline health')).toBeInTheDocument()
    })
  })

  it('shows crawler task page for authenticated user', async () => {
    useAuthStore.setState({ token: 'test-token', isAuthenticated: true })

    renderApp('/crawler/tasks')

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '爬取任务' })).toBeInTheDocument()
    })
  })
```

- [ ] **Step 2: Run route/layout tests to verify they fail**

Run:

```bash
cd frontend && npm test -- layout.ui.test.tsx App.test.tsx
```

Expected: FAIL because the sidebar item and `/crawler/tasks` route are not registered.

- [ ] **Step 3: Register crawler task routes**

Modify `frontend/src/routes/index.tsx`:

```tsx
import { createRootRoute, createRoute, createRouter, Outlet } from '@tanstack/react-router'
import { ConfigProvider, App as AntApp, theme } from 'antd'
import { useThemeStore } from '@/stores/useThemeStore'
import { redirectIfAuthenticated, requireAuth, requireInit } from './-guards'
import LoginPage from '@/pages/login/LoginPage'
import DashboardPage from '@/pages/dashboard/DashboardPage'
import InitPage from '@/pages/init/InitPage'
import TaskListPage from '@/pages/crawler/tasks/TaskListPage'
import TaskFormPage from '@/pages/crawler/tasks/TaskFormPage'
import AppLayout from '@/layout'

const rootRoute = createRootRoute({
  component: function RootLayout() {
    const darkMode = useThemeStore((state) => state.darkMode)
    const primaryColor = useThemeStore((state) => state.primaryColor)

    return (
      <ConfigProvider
        theme={{
          algorithm: darkMode ? theme.darkAlgorithm : theme.defaultAlgorithm,
          token: {
            colorPrimary: primaryColor,
            borderRadius: 8,
          },
        }}
      >
        <AntApp>
          <Outlet />
        </AntApp>
      </ConfigProvider>
    )
  },
})

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  beforeLoad: redirectIfAuthenticated,
  component: LoginPage,
  validateSearch: (search: Record<string, unknown>) => ({
    redirect: typeof search.redirect === 'string' ? search.redirect : undefined,
  }),
})

const initRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/init',
  component: InitPage,
})

const layoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'layout',
  beforeLoad: async () => {
    await requireInit()
    requireAuth()
  },
  component: AppLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/',
  component: DashboardPage,
})

const crawlerTasksRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/tasks',
  component: TaskListPage,
})

const crawlerTaskNewRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/tasks/new',
  component: TaskFormPage,
})

const crawlerTaskEditRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/tasks/$id/edit',
  component: TaskFormPage,
})

const routeTree = rootRoute.addChildren([
  initRoute,
  loginRoute,
  layoutRoute.addChildren([
    indexRoute,
    crawlerTasksRoute,
    crawlerTaskNewRoute,
    crawlerTaskEditRoute,
  ]),
])

export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
})
```

- [ ] **Step 4: Add sidebar navigation**

Modify `frontend/src/layout/Sidebar/index.tsx`:

```tsx
import { useMemo } from 'react'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import { DashboardOutlined, UnorderedListOutlined } from '@ant-design/icons'
import { Layout, Menu } from 'antd'
import type { MenuProps } from 'antd'
import { useThemeStore } from '@/stores/useThemeStore'
import styles from './Sidebar.module.less'

const { Sider } = Layout

const menuItems: MenuProps['items'] = [
  {
    key: '/',
    icon: <DashboardOutlined />,
    label: '仪表盘',
  },
  {
    key: '/crawler/tasks',
    icon: <UnorderedListOutlined />,
    label: '爬取任务',
  },
]

type SideMenuProps = {
  collapsed: boolean
}

export function SideMenu({ collapsed }: SideMenuProps) {
  const navigate = useNavigate()
  const darkMode = useThemeStore((state) => state.darkMode)
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const selectedKey = pathname.startsWith('/crawler/tasks') ? '/crawler/tasks' : pathname
  const selectedKeys = useMemo(() => [selectedKey === '/' ? '/' : selectedKey], [selectedKey])

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    const nextPath = String(key)
    if (nextPath !== pathname) {
      void navigate({ to: nextPath })
    }
  }

  return (
    <Sider
      collapsed={collapsed}
      width={232}
      collapsedWidth={80}
      collapsible={false}
      className={[
        styles.sider,
        darkMode ? styles.dark : '',
        collapsed ? styles.collapsed : '',
      ].filter(Boolean).join(' ')}
    >
      <div className={styles.logo}>
        <span className={styles.logoMark}>MF</span>
        {!collapsed && <span className={styles.logoText}>Media Forge</span>}
      </div>

      <div className={styles.menuWrapper}>
        <Menu
          className={styles.menu}
          mode="inline"
          theme={darkMode ? 'dark' : 'light'}
          inlineCollapsed={collapsed}
          selectedKeys={selectedKeys}
          items={menuItems}
          onClick={handleMenuClick}
        />
      </div>
    </Sider>
  )
}
```

- [ ] **Step 5: Run route/layout tests**

Run:

```bash
cd frontend && npm test -- layout.ui.test.tsx App.test.tsx
```

Expected: PASS for both test files.

- [ ] **Step 6: Commit Task 5**

Run:

```bash
git add frontend/src/routes/index.tsx frontend/src/layout/Sidebar/index.tsx frontend/tests/layout.ui.test.tsx frontend/tests/App.test.tsx
git commit -m "feat: register crawler task routes"
```

Expected: Commit succeeds.

---

### Task 6: Final Verification And Build

**Files:**
- Verify only.

- [ ] **Step 1: Run the focused backend crawler tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_tasks.py -v
```

Expected: PASS for all crawler task backend tests.

- [ ] **Step 2: Run all backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/ -v
```

Expected: PASS for auth, health, and crawler task tests.

- [ ] **Step 3: Verify Alembic can see the migration**

Run:

```bash
source .venv/bin/activate
cd backend
alembic history --verbose | grep b17e4f6d9c01
```

Expected: Output includes `b17e4f6d9c01 -> add_crawler_tasks`.

- [ ] **Step 4: Run the focused frontend crawler test suite**

Run:

```bash
cd frontend && npm test -- crawler
```

Expected: PASS for crawler task utility, API, and UI tests.

- [ ] **Step 5: Run all frontend tests**

Run:

```bash
cd frontend && npm test
```

Expected: PASS for all frontend tests.

- [ ] **Step 6: Run frontend lint**

Run:

```bash
cd frontend && npm run lint
```

Expected: PASS with no ESLint errors.

- [ ] **Step 7: Run frontend production build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS with TypeScript compilation and Vite production build completed.

- [ ] **Step 8: Commit verification fixes if any files changed**

If verification required code changes, run:

```bash
git status --short
git add backend frontend/src frontend/tests
git commit -m "fix: stabilize crawler task pages"
```

Expected: Commit succeeds when files changed. If `git status --short` is empty, no commit is created.

---

## Self-Review

**Spec coverage:** The plan ports the source crawler task backend CRUD contract, task list, new/edit form, URL type detection, final URL preview, task status toggle, deletion, route registration, sidebar navigation, and tests. Source-only queue status, run task actions, and single-page crawl modal are intentionally excluded because Media Forge has no crawler run worker or queue module yet.

**Placeholder scan:** No placeholder markers or incomplete implementation steps remain. Every new file has concrete content, and every changed file has concrete replacement or insertion code.

**Type consistency:** `UrlType`, `TaskUrlEntry`, `CrawlTask`, `TaskPayload`, API function names, route paths, and test imports are consistent across tasks.
