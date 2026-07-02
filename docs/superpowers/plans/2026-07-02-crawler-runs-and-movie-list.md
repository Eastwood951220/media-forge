# Crawler Runs and Movie List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add manual incremental/full crawler runs with Redis-managed runtime progress, restartable run records, and a read-only content movie list.

**Architecture:** PostgreSQL stores durable run, subtask, movie, magnet, and filter records. Redis stores runtime queue, worker lock, stop signals, and volatile progress snapshots. The frontend adds run controls, run list/detail views, and read-only movie browsing while preserving the existing Media Forge task CRUD patterns.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, Alembic, Redis, pytest, React 19, Vite 8, TypeScript 6, Ant Design 6, TanStack Router 1.x, Vitest, React Testing Library.

## Global Constraints

- Keep scope anchored to migrating and stabilizing existing `jav-scrapling` crawler/content behavior.
- Do not add scheduled crawls, batch-run-all, single-page crawl, movie deletion, movie marking, storage push, magnet selection, or export.
- Startup must never auto-execute crawler work.
- Startup must mark interrupted `queued` and `running` crawler runs as `stopped`.
- Run creation and restart must fail before creating a stuck queued run if Redis is unavailable.
- The run UI button label for resuming unfinished stopped/failed work is `重启`.
- Restart creates a new run with `resumed_from` set to the old run id and copies unfinished subtasks; the old run remains inspectable.
- Lists should follow Media Forge response convention: `rows` and `total`.
- Use the existing `.venv/` for backend commands and `frontend/` npm scripts for frontend verification.

---

## File Structure

Backend durable models:

- Create `shared/database/models/content.py`: `Movie`, `MovieMagnet`, `MovieFilter`.
- Create `backend/app/models/crawl_run.py`: `CrawlRun`, `CrawlRunDetailTask`.
- Modify `shared/database/models/__init__.py`: export content models.
- Modify `backend/app/models/__init__.py`: import backend models for metadata registration.
- Create `backend/alembic/versions/20260702_0002_crawler_runs_and_content.py`: PostgreSQL migration.
- Modify `backend/app/modules/init/database_bootstrap.py`: include new model modules in bootstrap imports.

Backend runtime and APIs:

- Create `backend/app/modules/crawler/runtime/schemas.py`: runtime enums and dataclasses.
- Create `backend/app/modules/crawler/runtime/redis_state.py`: Redis key operations.
- Create `backend/app/modules/crawler/runtime/service.py`: run creation, stop, restart, cleanup, worker lifecycle.
- Create `backend/app/modules/crawler/runs/schemas.py`: API schemas.
- Create `backend/app/modules/crawler/runs/router.py`: run list/detail/stop/restart/queue status endpoints.
- Modify `backend/app/modules/crawler/tasks/router.py`: add `POST /{task_id}/run`.
- Modify `backend/app/main.py`: include run and movie routers; call startup/shutdown cleanup hooks.
- Create `backend/app/modules/content/movies/schemas.py`: movie API schemas.
- Create `backend/app/modules/content/movies/router.py`: read-only movie list/detail API.

Backend tests:

- Create `backend/tests/test_crawler_runtime_redis.py`.
- Create `backend/tests/test_crawler_runs_api.py`.
- Create `backend/tests/test_crawler_worker_service.py`.
- Create `backend/tests/test_content_movies_api.py`.
- Modify `backend/tests/conftest.py`: import new models before `Base.metadata.create_all`.

Frontend APIs and pages:

- Modify `frontend/src/api/crawlTask/index.ts`.
- Modify `frontend/src/api/crawlTask/types.ts`.
- Create `frontend/src/api/crawlerRun/index.ts`.
- Create `frontend/src/api/crawlerRun/types.ts`.
- Create `frontend/src/api/movie/index.ts`.
- Create `frontend/src/api/movie/types.ts`.
- Modify `frontend/src/pages/crawler/tasks/TaskListPage.tsx`.
- Modify `frontend/src/pages/crawler/tasks/components/TaskListTable.tsx`.
- Create `frontend/src/pages/crawler/runs/RunListPage.tsx`.
- Create `frontend/src/pages/crawler/runs/RunDetailPage.tsx`.
- Create `frontend/src/pages/crawler/runs/RunPages.module.less`.
- Create `frontend/src/pages/content/movies/MovieListPage.tsx`.
- Create `frontend/src/pages/content/movies/MovieListPage.module.less`.
- Modify `frontend/src/layout/Sidebar/index.tsx`.
- Modify `frontend/src/routes/index.tsx`.
- Modify `frontend/src/routes/tags.ts`.

Frontend tests:

- Create `frontend/tests/crawler-run-controls.ui.test.tsx`.
- Create `frontend/tests/crawler-runs.ui.test.tsx`.
- Create `frontend/tests/movie-list.ui.test.tsx`.

---

### Task 1: Add Durable Run and Content Models

**Files:**
- Create: `shared/database/models/content.py`
- Create: `backend/app/models/crawl_run.py`
- Modify: `shared/database/models/__init__.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260702_0002_crawler_runs_and_content.py`
- Modify: `backend/app/modules/init/database_bootstrap.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_content_models_metadata.py`

**Interfaces:**
- Produces: `Movie`, `MovieMagnet`, `MovieFilter`, `CrawlRun`, `CrawlRunDetailTask` SQLAlchemy classes.
- Produces: tables `movies`, `movie_magnets`, `movie_filters`, `crawl_runs`, `crawl_run_detail_tasks`.
- Consumes: `shared.database.models.base.Base`, `TimestampMixin`, `UUIDPrimaryKeyMixin`.

- [ ] **Step 1: Write the failing metadata test**

Create `backend/tests/test_content_models_metadata.py`:

```python
from shared.database.models.base import Base


def test_crawler_run_and_content_tables_registered() -> None:
    expected = {
        "crawl_runs",
        "crawl_run_detail_tasks",
        "movies",
        "movie_magnets",
        "movie_filters",
    }
    assert expected.issubset(set(Base.metadata.tables))
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_models_metadata.py -v
```

Expected: FAIL because the new tables are not registered.

- [ ] **Step 3: Add `backend/app/models/crawl_run.py`**

Implement:

```python
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CrawlRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawl_runs"
    __table_args__ = (
        Index("idx_crawl_runs_task_status", "task_id", "status"),
        Index("idx_crawl_runs_queued_at", "queued_at"),
        Index("idx_crawl_runs_resumed_from", "resumed_from"),
    )

    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    crawl_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="incremental")
    queued_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    resumed_from: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    detail_tasks: Mapped[list["CrawlRunDetailTask"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="CrawlRunDetailTask.created_at",
        lazy="selectin",
    )


class CrawlRunDetailTask(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "crawl_run_detail_tasks"
    __table_args__ = (
        Index("idx_crawl_detail_run_status", "run_id", "status"),
        Index("idx_crawl_detail_run_source", "run_id", "source_url"),
        Index("idx_crawl_detail_created_at", "created_at"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    crawled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    saved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    run: Mapped[CrawlRun] = relationship(back_populates="detail_tasks")
```

- [ ] **Step 4: Add `shared/database/models/content.py`**

Implement the PostgreSQL model from `jav-scrapling`, adapted to current base classes:

```python
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Movie(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "movies"
    __table_args__ = (
        Index("idx_movies_code", "code"),
        Index("idx_movies_source_url", "source_url"),
        Index("idx_movies_created_at", "created_at"),
        Index("idx_movies_updated_at", "updated_at"),
        Index("idx_movies_release_date", "release_date"),
        Index("idx_movies_rating", "rating"),
        Index("idx_movies_actors_gin", "actors", postgresql_using="gin"),
        Index("idx_movies_tags_gin", "tags", postgresql_using="gin"),
        Index("idx_movies_source_task_names_gin", "source_task_names", postgresql_using="gin"),
        Index("idx_movies_storage_summary_gin", "storage_summary", postgresql_using="gin"),
        UniqueConstraint("code", name="uq_movies_code"),
        UniqueConstraint("source_url", name="uq_movies_source_url"),
    )

    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    duration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    director: Mapped[str] = mapped_column(Text, nullable=False, default="")
    maker: Mapped[str] = mapped_column(Text, nullable=False, default="")
    series: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 1), nullable=True)
    actors: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    source_task_names: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    cover: Mapped[str] = mapped_column(Text, nullable=False, default="")
    marked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    storage_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    raw_detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    magnets: Mapped[list["MovieMagnet"]] = relationship(
        back_populates="movie",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class MovieMagnet(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "movie_magnets"
    __table_args__ = (
        UniqueConstraint("movie_id", "dedupe_key", name="uq_movie_magnets_movie_dedupe"),
        Index("idx_movie_magnets_movie_id", "movie_id"),
        Index("idx_movie_magnets_info_hash", "info_hash"),
        Index("idx_movie_magnets_quality", "has_chinese_sub", "size_mb"),
    )

    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    magnet_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    info_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    size_mb: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    size_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    has_chinese_sub: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    date: Mapped[str] = mapped_column(Text, nullable=False, default="")
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    movie: Mapped[Movie] = relationship(back_populates="magnets")


class MovieFilter(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "movie_filters"
    __table_args__ = (
        UniqueConstraint("type", "name", name="uq_movie_filters_type_name"),
        Index("idx_movie_filters_type", "type"),
    )

    type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

- [ ] **Step 5: Register models for metadata**

Modify `shared/database/models/__init__.py`:

```python
"""SQLAlchemy models shared across backend and other packages."""

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from shared.database.models.content import Movie, MovieFilter, MovieMagnet

__all__ = [
    "Base",
    "UUIDPrimaryKeyMixin",
    "TimestampMixin",
    "Movie",
    "MovieMagnet",
    "MovieFilter",
]
```

Modify `backend/app/models/__init__.py`:

```python
"""Backend SQLAlchemy models."""

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.models.user import User

__all__ = [
    "User",
    "CrawlTask",
    "CrawlTaskUrl",
    "CrawlRun",
    "CrawlRunDetailTask",
]
```

- [ ] **Step 6: Ensure test metadata imports new models**

Modify `backend/tests/conftest.py` near imports:

```python
import backend.app.models  # noqa: F401
import shared.database.models.content  # noqa: F401
```

- [ ] **Step 7: Add the Alembic migration**

Create `backend/alembic/versions/20260702_0002_crawler_runs_and_content.py` with explicit `op.create_table`, indexes, unique constraints, and downgrade drops. Use PostgreSQL `sa.dialects.postgresql.JSONB` and `ARRAY(sa.Text())` for the real migration. Do not optimize for SQLite inside Alembic.

- [ ] **Step 8: Update init bootstrap imports**

Modify `backend/app/modules/init/database_bootstrap.py` model import list to include:

```python
"backend.app.models.crawl_run",
"shared.database.models.content",
```

- [ ] **Step 9: Run the model tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_models_metadata.py -v
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add shared/database/models/content.py backend/app/models/crawl_run.py shared/database/models/__init__.py backend/app/models/__init__.py backend/alembic/versions/20260702_0002_crawler_runs_and_content.py backend/app/modules/init/database_bootstrap.py backend/tests/conftest.py backend/tests/test_content_models_metadata.py
git commit -m "feat: add crawler run and content models"
```

---

### Task 2: Add Redis Runtime State Layer

**Files:**
- Create: `backend/app/modules/crawler/runtime/__init__.py`
- Create: `backend/app/modules/crawler/runtime/schemas.py`
- Create: `backend/app/modules/crawler/runtime/redis_state.py`
- Test: `backend/tests/test_crawler_runtime_redis.py`

**Interfaces:**
- Produces: `CrawlerRuntimeState(redis_client: redis.Redis)`.
- Produces: `enqueue_run(run_id: str) -> None`, `claim_next_run() -> str | None`, `set_current_run(run_id: str | None) -> None`, `request_stop(run_id: str) -> None`, `is_stop_requested(run_id: str) -> bool`, `write_progress(run_id: str, progress: dict) -> None`, `read_progress(run_id: str) -> dict`, `cleanup_runtime() -> None`, `queue_status() -> dict`.
- Consumes: Redis client from `backend.app.core.dependencies.get_redis`.

- [ ] **Step 1: Write runtime tests with fake Redis**

Create `backend/tests/test_crawler_runtime_redis.py`:

```python
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState


class FakeRedis:
    def __init__(self) -> None:
        self.values = {}
        self.lists = {}

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def lpop(self, key):
        values = self.lists.get(key, [])
        return values.pop(0) if values else None

    def llen(self, key):
        return len(self.lists.get(key, []))

    def set(self, key, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.lists.pop(key, None)

    def keys(self, pattern):
        prefix = pattern.removesuffix("*")
        return [key for key in [*self.values, *self.lists] if key.startswith(prefix)]


def test_enqueue_claim_and_queue_status() -> None:
    runtime = CrawlerRuntimeState(FakeRedis())

    runtime.enqueue_run("run-1")

    assert runtime.queue_status()["queue_size"] == 1
    assert runtime.claim_next_run() == "run-1"
    assert runtime.queue_status()["queue_size"] == 0


def test_stop_signal_and_cleanup() -> None:
    redis = FakeRedis()
    runtime = CrawlerRuntimeState(redis)

    runtime.set_current_run("run-1")
    runtime.request_stop("run-1")
    runtime.write_progress("run-1", {"total": 3, "finished": 1})

    assert runtime.is_stop_requested("run-1") is True
    assert runtime.read_progress("run-1") == {"total": 3, "finished": 1}

    runtime.cleanup_runtime()

    assert runtime.queue_status() == {
        "queue_size": 0,
        "is_running": False,
        "current_run_id": None,
        "stop_requested": False,
    }
```

- [ ] **Step 2: Run failing runtime tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runtime_redis.py -v
```

Expected: FAIL because runtime files do not exist.

- [ ] **Step 3: Add runtime schemas**

Create `backend/app/modules/crawler/runtime/schemas.py`:

```python
from enum import StrEnum


class CrawlRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class CrawlMode(StrEnum):
    INCREMENTAL = "incremental"
    FULL = "full"


class DetailTaskStatus(StrEnum):
    PENDING_CRAWL = "pending_crawl"
    CRAWLED = "crawled"
    CRAWL_FAILED = "crawl_failed"
    SAVED = "saved"
    SAVE_FAILED = "save_failed"
    SKIPPED = "skipped"
```

- [ ] **Step 4: Add Redis key operations**

Create `backend/app/modules/crawler/runtime/redis_state.py`:

```python
import json
from typing import Any


class CrawlerRuntimeState:
    PREFIX = "media-forge:crawler:"
    QUEUE_KEY = f"{PREFIX}queue"
    CURRENT_KEY = f"{PREFIX}current_run_id"

    def __init__(self, redis_client) -> None:
        self.redis = redis_client

    def _stop_key(self, run_id: str) -> str:
        return f"{self.PREFIX}stop:{run_id}"

    def _progress_key(self, run_id: str) -> str:
        return f"{self.PREFIX}progress:{run_id}"

    def enqueue_run(self, run_id: str) -> None:
        self.redis.rpush(self.QUEUE_KEY, run_id)

    def claim_next_run(self) -> str | None:
        value = self.redis.lpop(self.QUEUE_KEY)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    def set_current_run(self, run_id: str | None) -> None:
        if run_id is None:
            self.redis.delete(self.CURRENT_KEY)
            return
        self.redis.set(self.CURRENT_KEY, run_id)

    def request_stop(self, run_id: str) -> None:
        self.redis.set(self._stop_key(run_id), "1")

    def is_stop_requested(self, run_id: str) -> bool:
        return self.redis.get(self._stop_key(run_id)) is not None

    def write_progress(self, run_id: str, progress: dict[str, Any]) -> None:
        self.redis.set(self._progress_key(run_id), json.dumps(progress))

    def read_progress(self, run_id: str) -> dict[str, Any]:
        raw = self.redis.get(self._progress_key(run_id))
        if raw is None:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)

    def cleanup_runtime(self) -> None:
        keys = list(self.redis.keys(f"{self.PREFIX}*"))
        if keys:
            self.redis.delete(*keys)

    def queue_status(self) -> dict[str, Any]:
        current = self.redis.get(self.CURRENT_KEY)
        current_run_id = current.decode() if isinstance(current, bytes) else current
        return {
            "queue_size": self.redis.llen(self.QUEUE_KEY),
            "is_running": current_run_id is not None,
            "current_run_id": current_run_id,
            "stop_requested": bool(current_run_id and self.is_stop_requested(str(current_run_id))),
        }
```

- [ ] **Step 5: Run runtime tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runtime_redis.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/crawler/runtime backend/tests/test_crawler_runtime_redis.py
git commit -m "feat: add crawler redis runtime state"
```

---

### Task 3: Add Run Service Skeleton and Startup Cleanup

**Files:**
- Create: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_crawler_runs_api.py`

**Interfaces:**
- Produces: `CrawlerRunService(db: Session, runtime: CrawlerRuntimeState)`.
- Produces: `create_run(task: CrawlTask, crawl_mode: str) -> CrawlRun`.
- Produces: `cleanup_interrupted_runs(db: Session, runtime: CrawlerRuntimeState) -> int`.
- Produces: `get_runtime_state() -> CrawlerRuntimeState`.

- [ ] **Step 1: Write failing startup cleanup test**

Create `backend/tests/test_crawler_runs_api.py`:

```python
from datetime import datetime
from http import HTTPStatus

from fastapi.testclient import TestClient

from backend.app.models.crawl_run import CrawlRun
from backend.tests.conftest import TestingSessionLocal


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


class FakeRuntime:
    def __init__(self) -> None:
        self.cleaned = False

    def cleanup_runtime(self) -> None:
        self.cleaned = True


def test_cleanup_interrupted_runs_marks_queued_and_running_stopped() -> None:
    from backend.app.modules.crawler.runtime.service import cleanup_interrupted_runs

    session = TestingSessionLocal()
    queued = CrawlRun(task_name="queued task", status="queued", crawl_mode="incremental", queued_at=datetime.now())
    running = CrawlRun(task_name="running task", status="running", crawl_mode="full", queued_at=datetime.now())
    completed = CrawlRun(task_name="done task", status="completed", crawl_mode="full", queued_at=datetime.now())
    session.add_all([queued, running, completed])
    session.commit()

    runtime = FakeRuntime()
    count = cleanup_interrupted_runs(session, runtime)

    assert count == 2
    assert runtime.cleaned is True
    assert queued.status == "stopped"
    assert running.status == "stopped"
    assert completed.status == "completed"
    assert "服务重启" in (queued.error or "")


def test_queue_status_endpoint_returns_runtime_state(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)

    class Runtime:
        def queue_status(self):
            return {"queue_size": 0, "is_running": False, "current_run_id": None, "stop_requested": False}

    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: Runtime())

    response = client.get("/api/crawler/runs/queue-status", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["queue_size"] == 0
```

- [ ] **Step 2: Run failing tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py -v
```

Expected: FAIL because service/router do not exist.

- [ ] **Step 3: Implement service skeleton**

Create `backend/app/modules/crawler/runtime/service.py`:

```python
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_redis
from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState

logger = logging.getLogger(__name__)


def get_runtime_state() -> CrawlerRuntimeState:
    return CrawlerRuntimeState(get_redis())


def cleanup_interrupted_runs(db: Session, runtime: CrawlerRuntimeState) -> int:
    runtime.cleanup_runtime()
    rows = db.query(CrawlRun).filter(CrawlRun.status.in_(["queued", "running"])).all()
    now = datetime.now()
    for run in rows:
        run.status = "stopped"
        run.finished_at = run.finished_at or now
        run.error = "服务重启，任务已停止，需手动重启"
    db.commit()
    return len(rows)


class CrawlerRunService:
    def __init__(self, db: Session, runtime: CrawlerRuntimeState) -> None:
        self.db = db
        self.runtime = runtime

    def create_run(self, task: CrawlTask, crawl_mode: str) -> CrawlRun:
        if crawl_mode not in {"incremental", "full"}:
            raise ValueError("crawl_mode must be incremental or full")
        run = CrawlRun(
            task_id=task.id,
            task_name=task.name,
            status="queued",
            crawl_mode=crawl_mode,
            queued_at=datetime.now(),
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        self.runtime.enqueue_run(str(run.id))
        return run
```

- [ ] **Step 4: Add minimal runs router for queue status**

Create `backend/app/modules/crawler/runs/router.py`:

```python
from fastapi import APIRouter

from backend.app.core.dependencies import CurrentUser
from backend.app.modules.crawler.runtime.service import get_runtime_state
from shared.schemas.common import success

router = APIRouter(prefix="/api/crawler/runs", tags=["crawler-runs"])


@router.get("/queue-status")
def queue_status(_current_user: CurrentUser) -> dict:
    return success(data=get_runtime_state().queue_status())
```

- [ ] **Step 5: Register router and startup cleanup hook**

Modify `backend/app/main.py`:

```python
from backend.app.modules.crawler.runs.router import router as crawler_runs_router
from backend.app.modules.crawler.runtime.service import cleanup_interrupted_runs, get_runtime_state
from shared.database.session import close_postgres, connect_postgres, get_session_factory
```

Inside lifespan after `connect_postgres()`:

```python
        factory = get_session_factory()
        with factory() as session:
            stopped = cleanup_interrupted_runs(session, get_runtime_state())
            if stopped:
                logger.info("Stopped %d interrupted crawler runs.", stopped)
```

Include router:

```python
app.include_router(crawler_runs_router)
```

- [ ] **Step 6: Run tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/runtime/service.py backend/app/modules/crawler/runs/router.py backend/app/main.py backend/tests/test_crawler_runs_api.py
git commit -m "feat: add crawler run service cleanup"
```

---

### Task 4: Add Run Creation and Run Listing APIs

**Files:**
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Create: `backend/app/modules/crawler/runs/schemas.py`
- Modify: `backend/app/modules/crawler/runs/router.py`
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Test: `backend/tests/test_crawler_runs_api.py`

**Interfaces:**
- Produces: `POST /api/crawler/tasks/{task_id}/run`.
- Produces: `GET /api/crawler/runs`.
- Produces: `GET /api/crawler/runs/{run_id}`.
- Produces: `GET /api/crawler/runs/{run_id}/tasks`.

- [ ] **Step 1: Add API tests**

Append to `backend/tests/test_crawler_runs_api.py`:

```python
from backend.tests.test_crawl_tasks_api import task_payload


class RuntimeForRun:
    def __init__(self) -> None:
        self.enqueued = []

    def enqueue_run(self, run_id: str) -> None:
        self.enqueued.append(run_id)

    def queue_status(self):
        return {"queue_size": len(self.enqueued), "is_running": False, "current_run_id": None, "stop_requested": False}


def test_task_run_endpoint_creates_queued_run(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = task_response.json()["data"]["id"]
    runtime = RuntimeForRun()
    monkeypatch.setattr("backend.app.modules.crawler.tasks.router.get_runtime_state", lambda: runtime)

    response = client.post(
        f"/api/crawler/tasks/{task_id}/run",
        json={"crawl_mode": "incremental"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["task_id"] == task_id
    assert body["status"] == "queued"
    assert body["crawl_mode"] == "incremental"
    assert runtime.enqueued == [body["id"]]


def test_run_list_and_detail_endpoints(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = task_response.json()["data"]["id"]
    monkeypatch.setattr("backend.app.modules.crawler.tasks.router.get_runtime_state", lambda: RuntimeForRun())

    run_response = client.post(f"/api/crawler/tasks/{task_id}/run", json={"crawl_mode": "full"}, headers=headers)
    run_id = run_response.json()["data"]["id"]

    list_response = client.get("/api/crawler/runs", headers=headers)
    detail_response = client.get(f"/api/crawler/runs/{run_id}", headers=headers)
    tasks_response = client.get(f"/api/crawler/runs/{run_id}/tasks", headers=headers)

    assert list_response.status_code == HTTPStatus.OK
    assert list_response.json()["total"] == 1
    assert detail_response.json()["data"]["id"] == run_id
    assert tasks_response.json()["rows"] == []
```

- [ ] **Step 2: Run failing tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py -v
```

Expected: FAIL because endpoints/schemas are incomplete.

- [ ] **Step 3: Add run schemas**

Create `backend/app/modules/crawler/runs/schemas.py`:

```python
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class RunCreateRequest(BaseModel):
    crawl_mode: Literal["incremental", "full"]


class CrawlRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID | None
    task_name: str
    status: str
    crawl_mode: str
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    result: dict[str, Any] | None
    error: str | None
    resumed_from: uuid.UUID | None
    created_at: datetime
    updated_at: datetime | None


class CrawlRunDetailTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    task_name: str
    code: str | None
    source_url: str
    source_name: str
    status: str
    error: str | None
    item_data: dict[str, Any] | None
    created_at: datetime
    crawled_at: datetime | None
    saved_at: datetime | None
```

- [ ] **Step 4: Add task run endpoint**

Modify `backend/app/modules/crawler/tasks/router.py` imports:

```python
from backend.app.modules.crawler.runs.schemas import CrawlRunRead, RunCreateRequest
from backend.app.modules.crawler.runtime.service import CrawlerRunService, get_runtime_state
```

Add before `@router.get("/{task_id}")` so static paths remain safe:

```python
@router.post("/{task_id}/run", status_code=status.HTTP_201_CREATED)
def run_task(
    task_id: uuid.UUID,
    data: RunCreateRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.is_skip:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="禁用任务不能执行")
    try:
        run = CrawlerRunService(db, get_runtime_state()).create_run(task, data.crawl_mode)
    except Exception as exc:
        db.rollback()
        logger.exception("Create crawler run failed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"任务运行时不可用: {exc}") from exc
    return success(data=CrawlRunRead.model_validate(run).model_dump(mode="json"))
```

- [ ] **Step 5: Expand runs router**

Modify `backend/app/modules/crawler/runs/router.py` with list/detail/task endpoints using `paginated` and `success`. Use `selectinload(CrawlRun.detail_tasks)` for detail. Filter detail tasks by optional `status` and `keyword`.

- [ ] **Step 6: Run tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py backend/tests/test_crawl_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/tasks/router.py backend/app/modules/crawler/runs backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_runs_api.py
git commit -m "feat: add crawler run APIs"
```

---

### Task 5: Add Stop and Restart APIs

**Files:**
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/app/modules/crawler/runs/router.py`
- Test: `backend/tests/test_crawler_runs_api.py`

**Interfaces:**
- Produces: `CrawlerRunService.stop_run(run_id: uuid.UUID) -> CrawlRun`.
- Produces: `CrawlerRunService.restart_run(run_id: uuid.UUID) -> CrawlRun`.
- Produces: `POST /api/crawler/runs/{run_id}/stop`.
- Produces: `POST /api/crawler/runs/{run_id}/restart`.

- [ ] **Step 1: Add stop and restart tests**

Append:

```python
from backend.app.models.crawl_run import CrawlRunDetailTask


class RuntimeForStopRestart(RuntimeForRun):
    def __init__(self) -> None:
        super().__init__()
        self.stopped = []

    def request_stop(self, run_id: str) -> None:
        self.stopped.append(run_id)


def test_stop_running_run_sets_stop_signal(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="running", crawl_mode="incremental")
    session.add(run)
    session.commit()
    run_id = str(run.id)
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(f"/api/crawler/runs/{run_id}/stop", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert runtime.stopped == [run_id]
    assert response.json()["data"]["status"] == "stopped"


def test_restart_copies_unfinished_subtasks(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="stopped", crawl_mode="incremental")
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="A", source_url="https://a", source_name="A", status="saved", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="B", source_url="https://b", source_name="B", status="crawl_failed", created_at=datetime.now()),
    ])
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(f"/api/crawler/runs/{run.id}/restart", headers=headers)

    assert response.status_code == HTTPStatus.CREATED
    new_run = response.json()["data"]
    assert new_run["resumed_from"] == str(run.id)
    assert runtime.enqueued == [new_run["id"]]

    tasks_response = client.get(f"/api/crawler/runs/{new_run['id']}/tasks", headers=headers)
    assert [row["code"] for row in tasks_response.json()["rows"]] == ["B"]
```

- [ ] **Step 2: Run failing tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py -v
```

Expected: FAIL until stop/restart logic exists.

- [ ] **Step 3: Implement service methods**

Add to `CrawlerRunService`:

```python
import uuid

from backend.app.models.crawl_run import CrawlRunDetailTask

UNFINISHED_DETAIL_STATUSES = {"pending_crawl", "crawl_failed", "save_failed"}


def stop_run(self, run_id: uuid.UUID) -> CrawlRun:
    run = self.db.get(CrawlRun, run_id)
    if run is None:
        raise ValueError("运行记录不存在")
    if run.status not in {"queued", "running"}:
        raise ValueError("任务当前未在运行中")
    self.runtime.request_stop(str(run.id))
    run.status = "stopped"
    run.finished_at = datetime.now()
    self.db.commit()
    self.db.refresh(run)
    return run


def restart_run(self, run_id: uuid.UUID) -> CrawlRun:
    old_run = self.db.get(CrawlRun, run_id)
    if old_run is None:
        raise ValueError("运行记录不存在")
    if old_run.status not in {"stopped", "failed"}:
        raise ValueError("只能重启已停止或失败的运行")
    details = (
        self.db.query(CrawlRunDetailTask)
        .filter(
            CrawlRunDetailTask.run_id == old_run.id,
            CrawlRunDetailTask.status.in_(UNFINISHED_DETAIL_STATUSES),
        )
        .order_by(CrawlRunDetailTask.created_at.asc())
        .all()
    )
    if not details:
        raise ValueError("没有未完成的子任务")
    new_run = CrawlRun(
        task_id=old_run.task_id,
        task_name=old_run.task_name,
        status="queued",
        crawl_mode=old_run.crawl_mode,
        queued_at=datetime.now(),
        resumed_from=old_run.id,
    )
    self.db.add(new_run)
    self.db.flush()
    for detail in details:
        self.db.add(CrawlRunDetailTask(
            run_id=new_run.id,
            task_name=detail.task_name,
            code=detail.code,
            source_url=detail.source_url,
            source_name=detail.source_name,
            status=detail.status,
            error=None,
            item_data=detail.item_data,
            created_at=datetime.now(),
            crawled_at=None,
            saved_at=None,
        ))
    self.db.commit()
    self.db.refresh(new_run)
    self.runtime.enqueue_run(str(new_run.id))
    return new_run
```

- [ ] **Step 4: Add router endpoints**

Add to `backend/app/modules/crawler/runs/router.py`:

```python
@router.post("/{run_id}/stop")
def stop_run(run_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    try:
        run = CrawlerRunService(db, get_runtime_state()).stop_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return success(data=CrawlRunRead.model_validate(run).model_dump(mode="json"))


@router.post("/{run_id}/restart", status_code=status.HTTP_201_CREATED)
def restart_run(run_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    try:
        run = CrawlerRunService(db, get_runtime_state()).restart_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"任务运行时不可用: {exc}") from exc
    return success(data=CrawlRunRead.model_validate(run).model_dump(mode="json"))
```

- [ ] **Step 5: Run tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/crawler/runtime/service.py backend/app/modules/crawler/runs/router.py backend/tests/test_crawler_runs_api.py
git commit -m "feat: add crawler run stop and restart"
```

---

### Task 6: Add Worker Processing Against MovieService

**Files:**
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Test: `backend/tests/test_crawler_worker_service.py`

**Interfaces:**
- Produces: `process_next_run(db_factory: sessionmaker, runtime: CrawlerRuntimeState) -> bool`.
- Produces: worker thread start from `create_run` and `restart_run`.
- Consumes: `scraper.services.movie_service.MovieService`.

- [ ] **Step 1: Write worker tests with mocked MovieService**

Create `backend/tests/test_crawler_worker_service.py`:

```python
from datetime import datetime

from backend.app.core.security import get_password_hash
from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.models.user import User
from backend.app.modules.crawler.runtime.service import process_next_run
from backend.tests.conftest import TestingSessionLocal


class Runtime:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.current = None
        self.progress = {}

    def claim_next_run(self):
        run_id, self.run_id = self.run_id, None
        return run_id

    def set_current_run(self, run_id):
        self.current = run_id

    def is_stop_requested(self, run_id):
        return False

    def write_progress(self, run_id, progress):
        self.progress = progress


class MovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        kwargs["on_tasks_batch_created"]([
            {"code": "AAA-001", "url": "https://javdb.com/v/aaa", "name": "AAA"}
        ])
        kwargs["on_item_saved"](
            {"code": "AAA-001", "url": "https://javdb.com/v/aaa", "name": "AAA"},
            {"code": "AAA-001", "source_url": "https://javdb.com/v/aaa", "source_name": "AAA", "source_task_name": [task.name]},
        )
        return {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}


def test_process_next_run_marks_saved(monkeypatch) -> None:
    session = TestingSessionLocal()
    user = User(username="worker-user", hashed_password=get_password_hash("pw"), role="admin")
    session.add(user)
    session.flush()
    task = CrawlTask(name="任务", owner_id=user.id, is_skip=False)
    task.urls = [CrawlTaskUrl(position=0, url="https://javdb.com/actors/a", url_type="actors", final_url="https://javdb.com/actors/a?page=1", source="javdb")]
    session.add(task)
    session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="queued", crawl_mode="incremental", queued_at=datetime.now())
    session.add(run)
    session.commit()
    runtime = Runtime(str(run.id))
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.MovieService", lambda: MovieServiceStub())

    processed = process_next_run(TestingSessionLocal, runtime)

    assert processed is True
    refreshed = session.get(CrawlRun, run.id)
    assert refreshed.status == "completed"
    detail = session.query(CrawlRunDetailTask).one()
    assert detail.status == "saved"
```

- [ ] **Step 2: Run failing worker test**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py -v
```

Expected: FAIL because `process_next_run` does not exist.

- [ ] **Step 3: Implement worker processing**

In `backend/app/modules/crawler/runtime/service.py`:

- Add `process_next_run`.
- Claim one run from Redis.
- Mark run `running`.
- If `resumed_from` exists, load existing copied detail rows and call `MovieService()._build_spider().run_detail_tasks(...)`.
- If new run, build scraper task from `CrawlTask` + `CrawlTaskUrl` rows using `scraper.tasks.task_utils.build_crawl_task_from_doc`.
- Wire callbacks:
  - `on_tasks_batch_created`: insert `CrawlRunDetailTask(status="pending_crawl")`.
  - `on_detail_failed`: upsert detail as `crawl_failed`.
  - `on_item_saved`: upsert detail as `saved`.
  - persistence exceptions: `save_failed`.
- Write progress after each callback using counts from PostgreSQL.
- Mark final status `completed`, `failed`, or `stopped`.
- Always clear current run in `finally`.

- [ ] **Step 4: Start worker from enqueue methods**

Add a module-level worker lock and daemon thread starter. `create_run` and `restart_run` should enqueue then call `ensure_worker_started()`. The worker loop should exit when `claim_next_run()` returns `None`.

- [ ] **Step 5: Run worker and API tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py backend/tests/test_crawler_runs_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_worker_service.py
git commit -m "feat: process crawler runs with worker"
```

---

### Task 7: Add Read-Only Movie API

**Files:**
- Create: `backend/app/modules/content/__init__.py`
- Create: `backend/app/modules/content/movies/__init__.py`
- Create: `backend/app/modules/content/movies/schemas.py`
- Create: `backend/app/modules/content/movies/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_content_movies_api.py`

**Interfaces:**
- Produces: `GET /api/content/movies`.
- Produces: `GET /api/content/movies/{movie_id}`.

- [ ] **Step 1: Write movie API tests**

Create `backend/tests/test_content_movies_api.py`:

```python
from datetime import date
from decimal import Decimal
from http import HTTPStatus

from fastapi.testclient import TestClient

from shared.database.models.content import Movie, MovieMagnet
from backend.tests.conftest import TestingSessionLocal
from backend.tests.test_crawl_tasks_api import auth_headers


def seed_movie() -> str:
    session = TestingSessionLocal()
    movie = Movie(
        code="AAA-001",
        source_url="https://javdb.com/v/aaa",
        source_name="测试电影",
        release_date=date(2026, 1, 1),
        duration=120,
        rating=Decimal("4.5"),
        actors=["演员A"],
        tags=["标签A"],
        source_task_names=["任务A"],
        cover="https://example.com/cover.jpg",
    )
    session.add(movie)
    session.flush()
    session.add(MovieMagnet(movie_id=movie.id, magnet_url="magnet:?xt=urn:btih:abc", dedupe_key="abc", name="磁力A"))
    session.commit()
    movie_id = str(movie.id)
    session.close()
    return movie_id


def test_list_movies_search_and_source_task(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    seed_movie()

    response = client.get("/api/content/movies?keyword=AAA&source_task_name=任务A", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["code"] == "AAA-001"
    assert body["rows"][0]["source_task_names"] == ["任务A"]


def test_get_movie_detail_includes_magnets(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    movie_id = seed_movie()

    response = client.get(f"/api/content/movies/{movie_id}", headers=headers)

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert data["id"] == movie_id
    assert data["magnets"][0]["magnet_url"].startswith("magnet:")
```

- [ ] **Step 2: Run failing movie API tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py -v
```

Expected: FAIL because movie router does not exist.

- [ ] **Step 3: Add schemas and serializer helpers**

Create `backend/app/modules/content/movies/schemas.py` with `MovieRead`, `MovieMagnetRead`.

- [ ] **Step 4: Add router**

Create `backend/app/modules/content/movies/router.py`:

- List query params: `skip`, `limit`, `keyword`, `source_task_name`, `sort_by`, `sort_order`.
- Allowed sort fields: `created_at`, `updated_at`, `code`, `source_name`, `release_date`, `rating`.
- Use SQLAlchemy filters for keyword against `code`, `source_name`, `director`, `maker`, `series`.
- For PostgreSQL ARRAY `source_task_names`, use `.contains([source_task_name])`; for SQLite tests, fall back to Python filtering when dialect is sqlite.
- Return `paginated(rows=[...], total=total)`.
- Detail loads magnets with `selectinload`.

- [ ] **Step 5: Register router**

Modify `backend/app/main.py`:

```python
from backend.app.modules.content.movies.router import router as content_movies_router

app.include_router(content_movies_router)
```

- [ ] **Step 6: Run movie API tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/content backend/app/main.py backend/tests/test_content_movies_api.py
git commit -m "feat: add read-only movie API"
```

---

### Task 8: Add Frontend API Clients and Types

**Files:**
- Modify: `frontend/src/api/crawlTask/index.ts`
- Modify: `frontend/src/api/crawlTask/types.ts`
- Create: `frontend/src/api/crawlerRun/index.ts`
- Create: `frontend/src/api/crawlerRun/types.ts`
- Create: `frontend/src/api/movie/index.ts`
- Create: `frontend/src/api/movie/types.ts`
- Test: `frontend/tests/crawler-run-controls.ui.test.tsx`

**Interfaces:**
- Produces: `runCrawlTask(taskId: string, crawlMode: CrawlMode): Promise<CrawlRun>`.
- Produces: `getCrawlerRuns`, `getCrawlerRun`, `getCrawlerRunTasks`, `stopCrawlerRun`, `restartCrawlerRun`, `getCrawlerQueueStatus`.
- Produces: `getMovies`, `getMovie`.

- [ ] **Step 1: Create API type files**

Create `frontend/src/api/crawlerRun/types.ts`:

```ts
export type CrawlMode = 'incremental' | 'full'
export type CrawlRunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'stopped'
export type DetailTaskStatus = 'pending_crawl' | 'crawled' | 'crawl_failed' | 'saved' | 'save_failed' | 'skipped'

export interface CrawlRun {
  id: string
  task_id: string | null
  task_name: string
  status: CrawlRunStatus
  crawl_mode: CrawlMode
  queued_at: string | null
  started_at: string | null
  finished_at: string | null
  result: Record<string, unknown> | null
  error: string | null
  resumed_from: string | null
  created_at: string
  updated_at: string | null
}

export interface CrawlRunDetailTask {
  id: string
  run_id: string
  task_name: string
  code: string | null
  source_url: string
  source_name: string
  status: DetailTaskStatus
  error: string | null
  item_data: Record<string, unknown> | null
  created_at: string
  crawled_at: string | null
  saved_at: string | null
}

export interface QueueStatus {
  queue_size: number
  is_running: boolean
  current_run_id: string | null
  stop_requested: boolean
}
```

Create `frontend/src/api/movie/types.ts`:

```ts
export interface MovieMagnet {
  id: string
  magnet_url: string
  name: string
  size_text: string
  has_chinese_sub: boolean
  date: string
  selected: boolean
}

export interface Movie {
  id: string
  code: string | null
  source_url: string | null
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
  source_task_names: string[]
  storage_summary: Record<string, unknown>
  raw_detail: Record<string, unknown>
  magnets?: MovieMagnet[]
  created_at: string
  updated_at: string | null
}
```

- [ ] **Step 2: Add API clients**

Implement `frontend/src/api/crawlerRun/index.ts` and `frontend/src/api/movie/index.ts` using `request.get/post` and the existing `PaginatedResponse<T>`.

- [ ] **Step 3: Extend crawl task client**

Add to `frontend/src/api/crawlTask/index.ts`:

```ts
import type { CrawlMode, CrawlRun } from '@/api/crawlerRun/types'

export function runCrawlTask(taskId: string, crawlMode: CrawlMode): Promise<CrawlRun> {
  return request.post<CrawlRun>(`${BASE_URL}/${taskId}/run`, {
    crawl_mode: crawlMode,
  })
}
```

- [ ] **Step 4: Run typecheck build**

```bash
cd frontend
npm run build
```

Expected: PASS or only existing unrelated failures. Fix new type errors before continuing.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/crawlTask frontend/src/api/crawlerRun frontend/src/api/movie
git commit -m "feat: add crawler run and movie API clients"
```

---

### Task 9: Add Task List Run Controls

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/src/pages/crawler/tasks/components/TaskListTable.tsx`
- Modify: `frontend/src/pages/crawler/tasks/TaskPages.module.less`
- Test: `frontend/tests/crawler-run-controls.ui.test.tsx`

**Interfaces:**
- Consumes: `runCrawlTask(taskId, crawlMode)`.
- Produces: task row buttons `增量爬取` and `全量爬取`.

- [ ] **Step 1: Write UI test**

Create `frontend/tests/crawler-run-controls.ui.test.tsx`:

```tsx
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListPage from '../src/pages/crawler/tasks/TaskListPage'
import { getCrawlTasks, runCrawlTask } from '../src/api/crawlTask'

vi.mock('../src/api/crawlTask', () => ({
  getCrawlTasks: vi.fn(),
  deleteCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
  runCrawlTask: vi.fn(),
}))

function renderPage() {
  const rootRoute = createRootRoute({ component: () => <TaskListPage /> })
  const router = createRouter({
    routeTree: rootRoute.addChildren([
      createRoute({ getParentRoute: () => rootRoute, path: '/crawler/runs', component: () => <div>runs page</div> }),
    ]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(<RouterProvider router={router} />)
}

describe('crawler task run controls', () => {
  beforeEach(() => {
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [{
        id: 'task-1',
        name: '任务A',
        urls: [],
        is_skip: false,
        status: 'pending',
        task_id: null,
        error_message: null,
        total_found: 0,
        total_qualified: 0,
        owner_id: 'user-1',
        created_at: '2026-07-02T00:00:00',
        updated_at: null,
      }],
      total: 1,
    })
    vi.mocked(runCrawlTask).mockResolvedValue({ id: 'run-1' } as never)
  })

  it('starts an incremental run from a task row', async () => {
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: '增量爬取' }))

    await waitFor(() => {
      expect(runCrawlTask).toHaveBeenCalledWith('task-1', 'incremental')
    })
  })
})
```

- [ ] **Step 2: Run failing frontend test**

```bash
cd frontend
npm test -- crawler-run-controls.ui.test.tsx
```

Expected: FAIL because buttons do not exist.

- [ ] **Step 3: Add props and buttons**

Modify `TaskListTable` props:

```ts
onRun: (task: CrawlTask, mode: 'incremental' | 'full') => void
```

Add action buttons with `PlayCircleOutlined`:

```tsx
<Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => onRun(record, 'incremental')}>
  增量爬取
</Button>
<Button size="small" icon={<PlayCircleOutlined />} onClick={() => onRun(record, 'full')}>
  全量爬取
</Button>
```

- [ ] **Step 4: Wire page handler**

In `TaskListPage.tsx`, import `runCrawlTask`, call it, show Ant Design message, and navigate to `/crawler/runs`.

- [ ] **Step 5: Run tests**

```bash
cd frontend
npm test -- crawler-run-controls.ui.test.tsx task-list-query-state.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/crawler/tasks frontend/tests/crawler-run-controls.ui.test.tsx
git commit -m "feat: add crawler task run controls"
```

---

### Task 10: Add Run List and Detail Pages

**Files:**
- Create: `frontend/src/pages/crawler/runs/RunListPage.tsx`
- Create: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- Create: `frontend/src/pages/crawler/runs/RunPages.module.less`
- Modify: `frontend/src/routes/index.tsx`
- Modify: `frontend/src/routes/tags.ts`
- Modify: `frontend/src/layout/Sidebar/index.tsx`
- Test: `frontend/tests/crawler-runs.ui.test.tsx`

**Interfaces:**
- Consumes: crawler run API client from Task 8.
- Produces: `/crawler/runs` and `/crawler/runs/$id`.

- [ ] **Step 1: Write run UI test**

Create `frontend/tests/crawler-runs.ui.test.tsx` with mocks for `getCrawlerRuns`, `restartCrawlerRun`, `stopCrawlerRun`, `getCrawlerRun`, and `getCrawlerRunTasks`. Assert:

- `任务A` row renders on `/crawler/runs`.
- `stopped` row renders `重启`.
- clicking `重启` calls `restartCrawlerRun('run-1')`.
- detail route renders subtask code `AAA-001`.

- [ ] **Step 2: Run failing run UI test**

```bash
cd frontend
npm test -- crawler-runs.ui.test.tsx
```

Expected: FAIL because pages/routes do not exist.

- [ ] **Step 3: Build `RunListPage`**

Use `Table`, `Tag`, `Progress`, `Button`, `Select`, and `Space`.

Status labels:

```ts
const statusLabels = {
  queued: '排队中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  stopped: '已停止',
} as const
```

Progress uses `result.total_tasks`, `result.saved`, `result.save_failed`, and `result.crawl_failed` when available.

- [ ] **Step 4: Build `RunDetailPage`**

Load run detail and subtasks. Provide status filter, keyword search, summary panel, and subtask table.

- [ ] **Step 5: Add routes, tags, and menu**

Add:

- `/crawler/runs`
- `/crawler/runs/$id`
- tag title `运行记录`
- sidebar item under `爬虫`.

- [ ] **Step 6: Run frontend tests**

```bash
cd frontend
npm test -- crawler-runs.ui.test.tsx
npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/crawler/runs frontend/src/routes/index.tsx frontend/src/routes/tags.ts frontend/src/layout/Sidebar/index.tsx frontend/tests/crawler-runs.ui.test.tsx
git commit -m "feat: add crawler run pages"
```

---

### Task 11: Add Read-Only Movie List Page

**Files:**
- Create: `frontend/src/pages/content/movies/MovieListPage.tsx`
- Create: `frontend/src/pages/content/movies/MovieListPage.module.less`
- Modify: `frontend/src/routes/index.tsx`
- Modify: `frontend/src/routes/tags.ts`
- Modify: `frontend/src/layout/Sidebar/index.tsx`
- Test: `frontend/tests/movie-list.ui.test.tsx`

**Interfaces:**
- Consumes: `getMovies`, `getMovie`.
- Produces: `/content/movies`.

- [ ] **Step 1: Write movie list UI test**

Create `frontend/tests/movie-list.ui.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MovieListPage from '../src/pages/content/movies/MovieListPage'
import { getMovie, getMovies } from '../src/api/movie'

vi.mock('../src/api/movie', () => ({
  getMovies: vi.fn(),
  getMovie: vi.fn(),
}))

describe('MovieListPage', () => {
  beforeEach(() => {
    vi.mocked(getMovies).mockResolvedValue({
      rows: [{
        id: 'movie-1',
        code: 'AAA-001',
        source_url: 'https://javdb.com/v/aaa',
        source_name: '测试电影',
        cover: '',
        release_date: '2026-01-01',
        duration: 120,
        director: '',
        maker: '',
        series: '',
        rating: 4.5,
        actors: ['演员A'],
        tags: ['标签A'],
        source_task_names: ['任务A'],
        storage_summary: {},
        raw_detail: {},
        created_at: '2026-07-02T00:00:00',
        updated_at: null,
      }],
      total: 1,
    })
    vi.mocked(getMovie).mockResolvedValue({
      id: 'movie-1',
      code: 'AAA-001',
      source_url: 'https://javdb.com/v/aaa',
      source_name: '测试电影',
      cover: '',
      release_date: '2026-01-01',
      duration: 120,
      director: '',
      maker: '',
      series: '',
      rating: 4.5,
      actors: ['演员A'],
      tags: ['标签A'],
      source_task_names: ['任务A'],
      storage_summary: {},
      raw_detail: {},
      created_at: '2026-07-02T00:00:00',
      updated_at: null,
      magnets: [{ id: 'm-1', magnet_url: 'magnet:?x', name: '磁力A', size_text: '', has_chinese_sub: false, date: '', selected: false }],
    })
  })

  it('renders movies and opens read-only detail', async () => {
    render(<MovieListPage />)

    expect(await screen.findByText('AAA-001')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '详情' }))
    expect(await screen.findByText('磁力A')).toBeInTheDocument()
    expect(screen.queryByText('删除')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run failing movie UI test**

```bash
cd frontend
npm test -- movie-list.ui.test.tsx
```

Expected: FAIL because page does not exist.

- [ ] **Step 3: Build read-only movie page**

Use a quiet data table layout with:

- search input
- source task filter input/select
- table columns: cover, code, title, rating, release date, duration, actors, tags, source task names, created time, action `详情`
- drawer for detail and magnets

Do not add mutation controls.

- [ ] **Step 4: Add route and sidebar**

Add content management parent menu and `/content/movies` route/tag.

- [ ] **Step 5: Run tests and build**

```bash
cd frontend
npm test -- movie-list.ui.test.tsx
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/content/movies frontend/src/routes/index.tsx frontend/src/routes/tags.ts frontend/src/layout/Sidebar/index.tsx frontend/tests/movie-list.ui.test.tsx
git commit -m "feat: add read-only movie list"
```

---

### Task 12: Final Verification and Integration Pass

**Files:**
- Modify only files required to fix integration failures found by verification.

**Interfaces:**
- Consumes all previous tasks.
- Produces a verified implementation ready for review.

- [ ] **Step 1: Run backend tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/ -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests**

```bash
cd frontend
npm test
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Run lint**

```bash
cd frontend
npm run lint
```

Expected: PASS.

- [ ] **Step 5: Manual API smoke test**

Start backend:

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

Start frontend:

```bash
cd frontend
npm run dev
```

Verify in browser:

- task list displays `增量爬取` and `全量爬取`
- run list opens
- movie list opens
- no task auto-runs on backend restart

- [ ] **Step 6: Commit fixes**

```bash
git status --short
git add backend/app/modules/crawler/runtime/service.py backend/app/modules/crawler/runs/router.py backend/app/modules/content/movies/router.py frontend/src/pages/crawler/runs/RunListPage.tsx frontend/src/pages/crawler/runs/RunDetailPage.tsx frontend/src/pages/content/movies/MovieListPage.tsx
git commit -m "fix: stabilize crawler runs integration"
```

If verification changed different files, stage only the exact changed files that belong to this feature. Do not stage unrelated pre-existing worktree changes.
