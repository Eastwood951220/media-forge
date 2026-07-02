# Task Delete And Movie Source Task IDs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add task deletion modes, require task `storage_location`, and replace movie source-task name storage with task IDs.

**Architecture:** Backend schema and models switch from `movies.source_task_names` to `movies.source_task_ids`, while `crawl_tasks.storage_location` becomes a required immutable creation field. Task deletion is handled by a focused service that owns transactional cleanup for `task_only` and `task_and_movies`; frontend adds a mode selector to the delete confirmation and uses `/api/crawler/tasks/dict` to map movie source task IDs to names.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Pytest, React 19, TypeScript 6, Ant Design 6, Vitest.

---

## File Structure

- Create `backend/alembic/versions/20260702_0003_task_delete_source_task_ids.py`: schema migration for `crawl_tasks.storage_location`, `movies.source_task_ids`, and dropping `movies.source_task_names`.
- Modify `shared/database/types.py`: make SQLite JSON serialization of array values tolerate UUID objects.
- Modify `backend/app/models/crawl_task.py`: add `storage_location`.
- Modify `shared/database/models/content.py`: replace `source_task_names` with `source_task_ids`.
- Modify `backend/app/modules/init/database_bootstrap.py`: ensure init-time table creation and empty legacy-table repair handle the new crawler task and movie schemas.
- Modify `backend/app/schemas/crawl_task.py`: add `storage_location` to create/read, reject update.
- Modify `backend/app/repositories/crawl_task.py`: persist `storage_location` and add task dictionary query.
- Modify `backend/app/modules/crawler/tasks/router.py`: add `/dict`, delete mode parsing, and immutable storage-location behavior.
- Create `backend/app/modules/crawler/tasks/delete_service.py`: implement task delete modes and result counts.
- Modify `scraper/database/repositories/movie_repository.py`: persist and append `source_task_ids`.
- Modify `backend/app/modules/crawler/runtime/source_task_names.py`: convert helper behavior from names to IDs.
- Modify `backend/app/modules/crawler/runtime/service.py`: pass current task ID through movie persistence and existing-movie association paths.
- Modify `backend/app/modules/content/movies/router.py`: return/filter `source_task_ids` and remove `task-names`.
- Modify `backend/app/modules/content/movies/schemas.py`: expose `source_task_ids`, remove `source_task_names`.
- Modify backend tests in `backend/tests/test_crawler_tasks_api.py`, `backend/tests/test_crawler_worker_service.py`, `backend/tests/test_content_movies_api.py`, `backend/tests/test_crawler_source_task_names.py`, and metadata tests.
- Modify `frontend/src/api/crawlTask/index.ts` and `frontend/src/api/crawlTask/types.ts`: add storage location, task dict, delete modes/results.
- Modify `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`: add create-only `storage_location` behavior.
- Modify `frontend/src/pages/crawler/tasks/TaskListPage.tsx`: add delete mode selector in confirmation.
- Modify `frontend/src/api/movie/index.ts`, `frontend/src/api/movie/types.ts`, and movie list components/hooks: use task dict, `source_task_id`, and `source_task_ids`.
- Modify frontend tests for task form, task list deletion, and movie list.

---

### Task 1: Database Models And Schemas

**Files:**
- Create: `backend/alembic/versions/20260702_0003_task_delete_source_task_ids.py`
- Modify: `shared/database/types.py`
- Modify: `backend/app/models/crawl_task.py`
- Modify: `shared/database/models/content.py`
- Modify: `backend/app/modules/init/database_bootstrap.py`
- Modify: `backend/app/schemas/crawl_task.py`
- Modify: `backend/tests/test_content_models_metadata.py`
- Modify: `backend/tests/test_init_database_bootstrap.py`

- [ ] **Step 1: Write failing metadata tests**

Modify `backend/tests/test_content_models_metadata.py` to assert the new columns and removed column:

```python
def test_crawler_run_and_content_tables_registered() -> None:
    from shared.database.models.base import Base

    tables = Base.metadata.tables
    assert "crawl_tasks" in tables
    assert "crawl_runs" in tables
    assert "crawl_run_detail_tasks" in tables
    assert "movies" in tables
    assert "movie_magnets" in tables

    assert "storage_location" in tables["crawl_tasks"].columns
    assert "source_task_ids" in tables["movies"].columns
    assert "source_task_names" not in tables["movies"].columns
```

- [ ] **Step 2: Run metadata test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_models_metadata.py -v
```

Expected: FAIL because `storage_location` and `source_task_ids` do not exist yet, and `source_task_names` still exists.

- [ ] **Step 3: Add Alembic migration**

Create `backend/alembic/versions/20260702_0003_task_delete_source_task_ids.py`:

```python
"""add task storage location and movie source task ids

Revision ID: 20260702_0003
Revises: 20260702_0002
Create Date: 2026-07-02 16:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260702_0003"
down_revision = "20260702_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crawl_tasks",
        sa.Column("storage_location", sa.String(length=10), nullable=False, server_default=""),
    )
    op.add_column(
        "movies",
        sa.Column(
            "source_task_ids",
            postgresql.ARRAY(sa.Uuid()),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
    )
    op.drop_index("idx_movies_source_task_names_gin", table_name="movies")
    op.drop_column("movies", "source_task_names")
    op.create_index(
        "idx_movies_source_task_ids_gin",
        "movies",
        ["source_task_ids"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("idx_movies_source_task_ids_gin", table_name="movies")
    op.add_column(
        "movies",
        sa.Column(
            "source_task_names",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.create_index(
        "idx_movies_source_task_names_gin",
        "movies",
        ["source_task_names"],
        postgresql_using="gin",
    )
    op.drop_column("movies", "source_task_ids")
    op.drop_column("crawl_tasks", "storage_location")
```

- [ ] **Step 4: Make compatible array JSON serialization UUID-safe**

Modify `shared/database/types.py`, changing `CompatibleARRAY.process_bind_param` to:

```python
    def process_bind_param(self, value: Any, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return json.dumps(value, default=str)
```

- [ ] **Step 5: Update SQLAlchemy models**

Modify `backend/app/models/crawl_task.py`.

Add `storage_location` after `name`:

```python
    storage_location: Mapped[str] = mapped_column(String(10), nullable=False, default="")
```

Modify `shared/database/models/content.py`.

1. Add `Uuid` to imports:

```python
from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint, Uuid
```

2. Replace the index:

```python
        Index("idx_movies_source_task_ids_gin", "source_task_ids", postgresql_using="gin"),
```

3. Replace the field:

```python
    source_task_ids: Mapped[list[uuid.UUID]] = mapped_column(CompatibleARRAY(Uuid), nullable=False, default=list)
```

- [ ] **Step 6: Update crawl task schemas**

Modify `backend/app/schemas/crawl_task.py`.

Add to `CrawlTaskCreate`:

```python
    storage_location: str = Field(..., min_length=1, max_length=10)
```

Do not add `storage_location` to `CrawlTaskUpdate`.

Add to `CrawlTaskRead` after `name`:

```python
    storage_location: str
```

- [ ] **Step 7: Run metadata test and verify it passes**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_models_metadata.py -v
```

Expected: PASS.

- [ ] **Step 8: Add init bootstrap coverage for new schemas**

Modify `backend/tests/test_init_database_bootstrap.py`.

Extend `test_create_application_tables_uses_shared_metadata` so init-time table creation verifies the new columns:

```python
    inspector = inspect(engine)
    crawl_task_columns = {column["name"] for column in inspector.get_columns("crawl_tasks")}
    movie_columns = {column["name"] for column in inspector.get_columns("movies")}

    assert "storage_location" in crawl_task_columns
    assert "source_task_ids" in movie_columns
    assert "source_task_names" not in movie_columns
```

Add a test for empty legacy movie tables:

```python
def test_create_application_tables_repairs_empty_legacy_movie_tables() -> None:
    engine = sqlite_engine()
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE movies (
                id VARCHAR PRIMARY KEY,
                code VARCHAR NOT NULL,
                source_url TEXT NOT NULL,
                source_task_names TEXT NOT NULL
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE movie_magnets (
                id VARCHAR PRIMARY KEY,
                movie_id VARCHAR NOT NULL,
                magnet_url TEXT NOT NULL
            )
            """
        ))

    create_application_tables(engine)

    inspector = inspect(engine)
    movie_columns = {column["name"] for column in inspector.get_columns("movies")}

    assert "source_task_ids" in movie_columns
    assert "source_task_names" not in movie_columns
```

- [ ] **Step 9: Update init bootstrap repair logic**

Modify `backend/app/modules/init/database_bootstrap.py`.

Keep `create_application_tables()` backed by `Base.metadata.create_all(bind=engine)` for clean database initialization. Add a movie-table repair path for empty incompatible legacy tables, mirroring `repair_empty_crawler_task_tables`:

```python
CONTENT_TABLE_NAMES = ("movie_magnets", "movies")


def repair_empty_content_tables(engine: Engine) -> bool:
    from shared.database.models.content import Movie, MovieMagnet

    expected = {
        "movies": {column.name for column in Movie.__table__.columns},
        "movie_magnets": {column.name for column in MovieMagnet.__table__.columns},
    }

    incompatible = [
        table_name
        for table_name, expected_columns in expected.items()
        if _is_incompatible_table(engine, table_name, expected_columns)
    ]
    if not incompatible:
        return False

    non_empty = [
        table_name
        for table_name in CONTENT_TABLE_NAMES
        if inspect(engine).has_table(table_name) and _table_row_count(engine, table_name) > 0
    ]
    if non_empty:
        names = ", ".join(non_empty)
        raise RuntimeError(f"影片表结构不兼容且已有数据，无法自动重建: {names}")

    logger.warning("Rebuilding empty incompatible content tables: %s", ", ".join(incompatible))
    MovieMagnet.__table__.drop(bind=engine, checkfirst=True)
    Movie.__table__.drop(bind=engine, checkfirst=True)
    Base.metadata.create_all(bind=engine)
    return True
```

Call it from `create_application_tables()` before the final `Base.metadata.create_all(bind=engine)`:

```python
def create_application_tables(engine: Engine) -> None:
    import_application_models()
    repair_empty_crawler_task_tables(engine)
    repair_empty_content_tables(engine)
    Base.metadata.create_all(bind=engine)
```

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_init_database_bootstrap.py backend/tests/test_content_models_metadata.py -v
```

Expected: PASS. This confirms both init-after-config table creation and empty legacy-table repair use the new schema.

- [ ] **Step 10: Commit**

```bash
git add backend/alembic/versions/20260702_0003_task_delete_source_task_ids.py shared/database/types.py backend/app/models/crawl_task.py shared/database/models/content.py backend/app/modules/init/database_bootstrap.py backend/app/schemas/crawl_task.py backend/tests/test_content_models_metadata.py backend/tests/test_init_database_bootstrap.py
git commit -m "feat: add task storage location and source task ids"
```

---

### Task 2: Task Create, Update Immutability, And Dictionary API

**Files:**
- Modify: `backend/app/repositories/crawl_task.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Modify: `backend/tests/test_crawler_tasks_api.py`

- [ ] **Step 1: Write failing API tests**

Create or modify `backend/tests/test_crawler_tasks_api.py` with these tests:

```python
from http import HTTPStatus

from fastapi.testclient import TestClient

from backend.app.models.user import User
from backend.tests.conftest import TestingSessionLocal


def auth_headers(client: TestClient, admin_user: User) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def task_payload(name: str = "任务A", storage_location: str = "任务A") -> dict:
    return {
        "name": name,
        "storage_location": storage_location,
        "is_skip": False,
        "urls": [{"url": "https://javdb.com/actors/a", "url_type": "actors"}],
    }


def test_create_task_requires_storage_location(client: TestClient, admin_user: User) -> None:
    headers = auth_headers(client, admin_user)
    payload = task_payload()
    payload.pop("storage_location")

    response = client.post("/api/crawler/tasks", json=payload, headers=headers)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_create_task_returns_storage_location(client: TestClient, admin_user: User) -> None:
    headers = auth_headers(client, admin_user)

    response = client.post("/api/crawler/tasks", json=task_payload(storage_location="VR"), headers=headers)

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["data"]["storage_location"] == "VR"


def test_update_task_cannot_change_storage_location(client: TestClient, admin_user: User) -> None:
    headers = auth_headers(client, admin_user)
    created = client.post("/api/crawler/tasks", json=task_payload(storage_location="VR"), headers=headers).json()["data"]

    response = client.put(
        f"/api/crawler/tasks/{created['id']}",
        json={
            "name": "任务A改名",
            "storage_location": "NEW",
            "urls": [{"url": "https://javdb.com/actors/a", "url_type": "actors"}],
        },
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["name"] == "任务A改名"
    assert response.json()["data"]["storage_location"] == "VR"


def test_task_dict_returns_only_id_and_name(client: TestClient, admin_user: User) -> None:
    headers = auth_headers(client, admin_user)
    created = client.post("/api/crawler/tasks", json=task_payload(storage_location="VR"), headers=headers).json()["data"]

    response = client.get("/api/crawler/tasks/dict", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"] == [{"id": created["id"], "name": "任务A"}]
```

- [ ] **Step 2: Run task API tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_tasks_api.py -v
```

Expected: FAIL because repository creation does not persist `storage_location` and `/dict` does not exist.

- [ ] **Step 3: Update repository creation and dictionary query**

Modify `backend/app/repositories/crawl_task.py`.

Change `create_with_urls` signature to:

```python
    def create_with_urls(
        self,
        *,
        owner_id: uuid.UUID,
        name: str,
        storage_location: str,
        is_skip: bool,
        urls: list[TaskUrlEntryCreate],
    ) -> CrawlTask:
```

Change task creation line to:

```python
        task = CrawlTask(name=name, storage_location=storage_location, is_skip=is_skip, owner_id=owner_id)
```

Add this method:

```python
    def get_dict_by_owner(self, owner_id: uuid.UUID) -> list[dict[str, str]]:
        rows = (
            self.session.query(CrawlTask.id, CrawlTask.name)
            .filter(CrawlTask.owner_id == owner_id)
            .order_by(CrawlTask.name.asc())
            .all()
        )
        return [{"id": str(row.id), "name": row.name} for row in rows]
```

- [ ] **Step 4: Update task router**

Modify `backend/app/modules/crawler/tasks/router.py`.

Add this route before `@router.get("/{task_id}")`:

```python
@router.get("/dict")
def task_dict(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    return success(data=CrawlTaskRepository(db).get_dict_by_owner(current_user.id))
```

Update `create_task`, adding `storage_location=data.storage_location`:

```python
        created = repo.create_with_urls(
            owner_id=current_user.id,
            name=data.name,
            storage_location=data.storage_location,
            is_skip=data.is_skip,
            urls=data.urls,
        )
```

Update `update_task` to ignore incoming `storage_location` by keeping:

```python
    update_data = data.model_dump(exclude_unset=True, exclude={"urls"})
```

No schema field exists on `CrawlTaskUpdate`, so Pydantic ignores the extra field in the test payload and the persisted value remains unchanged.

- [ ] **Step 5: Run task API tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/repositories/crawl_task.py backend/app/modules/crawler/tasks/router.py backend/tests/test_crawler_tasks_api.py
git commit -m "feat: add task storage location api"
```

---

### Task 3: Task Delete Service And API Modes

**Files:**
- Create: `backend/app/modules/crawler/tasks/delete_service.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Modify: `backend/tests/test_crawler_tasks_api.py`

- [ ] **Step 1: Add failing delete mode tests**

Append these imports to `backend/tests/test_crawler_tasks_api.py`:

```python
from datetime import datetime

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from shared.database.models.content import Movie, MovieMagnet
```

Append these helpers and tests:

```python
def seed_run_and_detail(task_id: str) -> None:
    session = TestingSessionLocal()
    task = session.get(CrawlTask, task_id)
    run = CrawlRun(task_id=task.id, task_name=task.name, status="completed", crawl_mode="incremental", queued_at=datetime.now())
    session.add(run)
    session.flush()
    session.add(CrawlRunDetailTask(run_id=run.id, task_name=task.name, code="AAA-001", source_url="https://javdb.com/v/aaa", source_name="AAA", status="saved", created_at=datetime.now()))
    session.commit()
    session.close()


def seed_movie_with_tasks(task_ids: list[str], code: str = "AAA-001") -> str:
    session = TestingSessionLocal()
    movie = Movie(code=code, source_url=f"https://javdb.com/v/{code.lower()}", source_name=code, source_task_ids=task_ids)
    session.add(movie)
    session.flush()
    session.add(MovieMagnet(movie_id=movie.id, magnet_url=f"magnet:?xt=urn:btih:{code}", dedupe_key=code, name=code))
    session.commit()
    movie_id = str(movie.id)
    session.close()
    return movie_id


def test_delete_task_only_removes_task_runs_and_details_but_keeps_movies(client: TestClient, admin_user: User) -> None:
    headers = auth_headers(client, admin_user)
    task = client.post("/api/crawler/tasks", json=task_payload(storage_location="VR"), headers=headers).json()["data"]
    seed_run_and_detail(task["id"])
    movie_id = seed_movie_with_tasks([task["id"]])

    response = client.delete(f"/api/crawler/tasks/{task['id']}?mode=task_only", headers=headers)

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert data["deleted_task"] is True
    assert data["deleted_runs"] == 1
    assert data["deleted_detail_tasks"] == 1
    assert data["deleted_movies"] == 0
    session = TestingSessionLocal()
    assert session.get(CrawlTask, task["id"]) is None
    assert session.get(Movie, movie_id) is not None
    session.close()


def test_delete_task_and_movies_removes_task_id_from_shared_movie(client: TestClient, admin_user: User) -> None:
    headers = auth_headers(client, admin_user)
    task_a = client.post("/api/crawler/tasks", json=task_payload("任务A", "A"), headers=headers).json()["data"]
    task_b = client.post("/api/crawler/tasks", json=task_payload("任务B", "B"), headers=headers).json()["data"]
    movie_id = seed_movie_with_tasks([task_a["id"], task_b["id"]])

    response = client.delete(f"/api/crawler/tasks/{task_a['id']}?mode=task_and_movies", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["updated_movies"] == 1
    session = TestingSessionLocal()
    movie = session.get(Movie, movie_id)
    assert [str(value) for value in movie.source_task_ids] == [task_b["id"]]
    session.close()


def test_delete_task_and_movies_deletes_single_source_movie_and_magnets(client: TestClient, admin_user: User) -> None:
    headers = auth_headers(client, admin_user)
    task = client.post("/api/crawler/tasks", json=task_payload(storage_location="VR"), headers=headers).json()["data"]
    movie_id = seed_movie_with_tasks([task["id"]])

    response = client.delete(f"/api/crawler/tasks/{task['id']}?mode=task_and_movies", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["deleted_movies"] == 1
    assert response.json()["data"]["deleted_magnets"] == 1
    session = TestingSessionLocal()
    assert session.get(Movie, movie_id) is None
    assert session.query(MovieMagnet).count() == 0
    session.close()


def test_delete_task_cloud_mode_is_not_implemented_and_mutates_nothing(client: TestClient, admin_user: User) -> None:
    headers = auth_headers(client, admin_user)
    task = client.post("/api/crawler/tasks", json=task_payload(storage_location="VR"), headers=headers).json()["data"]

    response = client.delete(f"/api/crawler/tasks/{task['id']}?mode=task_movies_and_cloud", headers=headers)

    assert response.status_code == HTTPStatus.NOT_IMPLEMENTED
    session = TestingSessionLocal()
    assert session.get(CrawlTask, task["id"]) is not None
    session.close()
```

- [ ] **Step 2: Run delete tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_tasks_api.py::test_delete_task_only_removes_task_runs_and_details_but_keeps_movies backend/tests/test_crawler_tasks_api.py::test_delete_task_and_movies_removes_task_id_from_shared_movie backend/tests/test_crawler_tasks_api.py::test_delete_task_and_movies_deletes_single_source_movie_and_magnets backend/tests/test_crawler_tasks_api.py::test_delete_task_cloud_mode_is_not_implemented_and_mutates_nothing -v
```

Expected: FAIL because delete modes are not implemented.

- [ ] **Step 3: Implement delete service**

Create `backend/app/modules/crawler/tasks/delete_service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from shared.database.models.content import Movie

DeleteMode = Literal["task_only", "task_and_movies", "task_movies_and_cloud"]
VALID_DELETE_MODES = {"task_only", "task_and_movies", "task_movies_and_cloud"}


class UnsupportedDeleteMode(ValueError):
    pass


class CloudDeleteNotImplemented(RuntimeError):
    pass


@dataclass
class DeleteTaskResult:
    deleted_task: bool
    deleted_runs: int
    deleted_detail_tasks: int
    updated_movies: int
    deleted_movies: int
    deleted_magnets: int
    cloud_delete: str

    def to_dict(self) -> dict:
        return {
            "deleted_task": self.deleted_task,
            "deleted_runs": self.deleted_runs,
            "deleted_detail_tasks": self.deleted_detail_tasks,
            "updated_movies": self.updated_movies,
            "deleted_movies": self.deleted_movies,
            "deleted_magnets": self.deleted_magnets,
            "cloud_delete": self.cloud_delete,
        }


def _contains_task_id(values: list, task_id: str) -> bool:
    return task_id in {str(value) for value in (values or [])}


def _remove_task_id(values: list, task_id: str) -> list:
    return [value for value in (values or []) if str(value) != task_id]


def delete_crawl_task(db: Session, task: CrawlTask, mode: str) -> DeleteTaskResult:
    if mode not in VALID_DELETE_MODES:
        raise UnsupportedDeleteMode(f"未知删除模式: {mode}")
    if mode == "task_movies_and_cloud":
        raise CloudDeleteNotImplemented("云存储删除暂未实现")

    task_id = str(task.id)
    runs = db.query(CrawlRun).filter(CrawlRun.task_id == task.id).all()
    run_ids = [run.id for run in runs]
    deleted_detail_tasks = 0
    if run_ids:
        deleted_detail_tasks = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id.in_(run_ids)).count()
    deleted_runs = len(runs)

    updated_movies = 0
    deleted_movies = 0
    deleted_magnets = 0

    if mode == "task_and_movies":
        movies = db.query(Movie).all()
        for movie in movies:
            if not _contains_task_id(movie.source_task_ids, task_id):
                continue
            remaining_ids = _remove_task_id(movie.source_task_ids, task_id)
            if remaining_ids:
                movie.source_task_ids = remaining_ids
                updated_movies += 1
            else:
                deleted_magnets += len(movie.magnets or [])
                db.delete(movie)
                deleted_movies += 1

    for run in runs:
        db.delete(run)
    db.delete(task)
    db.commit()

    return DeleteTaskResult(
        deleted_task=True,
        deleted_runs=deleted_runs,
        deleted_detail_tasks=deleted_detail_tasks,
        updated_movies=updated_movies,
        deleted_movies=deleted_movies,
        deleted_magnets=deleted_magnets,
        cloud_delete="not_requested",
    )
```

- [ ] **Step 4: Wire delete service into router**

Modify `backend/app/modules/crawler/tasks/router.py`.

Add imports:

```python
from backend.app.modules.crawler.tasks.delete_service import (
    CloudDeleteNotImplemented,
    UnsupportedDeleteMode,
    delete_crawl_task,
)
```

Replace `delete_task` with:

```python
@router.delete("/{task_id}")
def delete_task(
    task_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    mode: str = Query(default="task_only"),
) -> dict:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    try:
        result = delete_crawl_task(db, task, mode)
    except UnsupportedDeleteMode as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CloudDeleteNotImplemented as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Delete crawler task failed: %s", task_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除任务失败: {exc}") from exc
    return success(data=result.to_dict(), msg="删除成功")
```

- [ ] **Step 5: Run delete tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/crawler/tasks/delete_service.py backend/app/modules/crawler/tasks/router.py backend/tests/test_crawler_tasks_api.py
git commit -m "feat: add crawler task delete modes"
```

---

### Task 4: Movie Persistence Uses Source Task IDs

**Files:**
- Modify: `scraper/database/repositories/movie_repository.py`
- Modify: `backend/app/modules/crawler/runtime/source_task_names.py`
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/tests/test_crawler_source_task_names.py`
- Modify: `backend/tests/test_crawler_worker_service.py`

- [ ] **Step 1: Replace source task helper tests**

Replace `backend/tests/test_crawler_source_task_names.py` with:

```python
from backend.app.modules.crawler.runtime.source_task_names import (
    add_source_task_id_for_code,
    find_existing_movie_codes,
    movie_code_exists,
)
from backend.tests.conftest import TestingSessionLocal
from shared.database.models.content import Movie


def test_find_existing_movie_codes_returns_only_existing_codes() -> None:
    session = TestingSessionLocal()
    session.add(Movie(code="AAA-001", source_url="https://example.test/aaa", source_task_ids=[]))
    session.add(Movie(code="BBB-002", source_url="https://example.test/bbb", source_task_ids=[]))
    session.commit()

    existing = find_existing_movie_codes(session, ["AAA-001", "AAA-001", "CCC-003", None, ""])

    assert existing == {"AAA-001"}
    assert movie_code_exists(session, "BBB-002") is True
    assert movie_code_exists(session, "CCC-003") is False
    assert movie_code_exists(session, None) is False


def test_add_source_task_id_for_code_appends_once() -> None:
    session = TestingSessionLocal()
    movie = Movie(code="AAA-010", source_url="https://example.test/aaa010", source_task_ids=["task-old"])
    session.add(movie)
    session.commit()

    assert add_source_task_id_for_code(session, "AAA-010", "task-new") is True
    assert add_source_task_id_for_code(session, "AAA-010", "task-new") is False
    assert add_source_task_id_for_code(session, "MISSING", "task-new") is False
    session.commit()

    session.refresh(movie)
    assert [str(value) for value in movie.source_task_ids] == ["task-old", "task-new"]
```

- [ ] **Step 2: Update worker persistence tests to expect IDs**

Modify `backend/tests/test_crawler_worker_service.py`.

Where stubs currently pass `source_task_name`, replace it with `source_task_id`:

```python
"source_task_id": str(task.id),
```

Replace assertions such as:

```python
assert movie.source_task_names == [run.task_name]
```

with:

```python
assert [str(value) for value in movie.source_task_ids] == [str(run.task_id)]
```

In list/detail dedupe tests, replace `source_task_names=["旧任务"]` with `source_task_ids=["old-task"]`, and assert IDs update:

```python
assert [str(value) for value in movie.source_task_ids] == ["old-task", str(run.task_id)]
```

- [ ] **Step 3: Run movie persistence tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_source_task_names.py backend/tests/test_crawler_worker_service.py -v
```

Expected: FAIL because repository/runtime still uses `source_task_names`.

- [ ] **Step 4: Update movie repository**

Modify `scraper/database/repositories/movie_repository.py`.

Replace the movie creation field:

```python
                source_task_ids=document.get("source_task_ids", []),
```

Replace `add_source_task_name` method with:

```python
    def add_source_task_id(self, code: str, task_id: str) -> tuple[bool, list[str]]:
        """Add a task id to an existing movie's source_task_ids list."""
        if not self.available or not code or not task_id:
            return False, []

        close_session = self._session is None
        session = self._session_scope()
        try:
            movie = session.scalar(select(Movie).where(Movie.code == code))
            if not movie:
                return False, []

            previous_ids = [str(value) for value in (movie.source_task_ids or [])]
            if task_id not in previous_ids:
                movie.source_task_ids = previous_ids + [task_id]
                session.commit()
                return True, previous_ids
            return False, previous_ids
        except Exception as exc:
            session.rollback()
            self.logger.warning("Failed to add source_task_id: %s", exc)
            return False, []
        finally:
            if close_session:
                session.close()
```

- [ ] **Step 5: Update runtime source task helper**

Replace `backend/app/modules/crawler/runtime/source_task_names.py` with:

```python
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.database.models.content import Movie


def _clean_codes(codes: Iterable[str | None]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for code in codes:
        normalized = str(code or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            cleaned.append(normalized)
    return cleaned


def find_existing_movie_codes(db: Session, codes: Iterable[str | None]) -> set[str]:
    cleaned = _clean_codes(codes)
    if not cleaned:
        return set()
    rows = db.scalars(select(Movie.code).where(Movie.code.in_(cleaned))).all()
    return {code for code in rows if code}


def movie_code_exists(db: Session, code: str | None) -> bool:
    normalized = str(code or "").strip()
    if not normalized:
        return False
    return db.scalar(select(Movie.id).where(Movie.code == normalized)) is not None


def add_source_task_id_for_code(db: Session, code: str | None, task_id: str) -> bool:
    normalized = str(code or "").strip()
    if not normalized or not task_id:
        return False

    movie = db.scalar(select(Movie).where(Movie.code == normalized))
    if movie is None:
        return False

    current_ids = [str(value) for value in (movie.source_task_ids or [])]
    if task_id in current_ids:
        return False

    movie.source_task_ids = current_ids + [task_id]
    db.flush()
    return True
```

- [ ] **Step 6: Update runtime service to pass task IDs**

Modify `backend/app/modules/crawler/runtime/service.py`.

1. Replace import:

```python
from backend.app.modules.crawler.runtime.source_task_names import (
    add_source_task_id_for_code,
    find_existing_movie_codes,
    movie_code_exists,
)
```

2. Change `_persist_crawled_item` to preserve `source_task_ids`:

```python
def _persist_crawled_item(db: Session, item_data: dict[str, Any]) -> uuid.UUID:
```

Keep current body, but ensure movie document contains `source_task_ids` by callers.

3. In `on_tasks_batch_created`, replace:

```python
                if add_source_task_name_for_code(db, item.get("code"), task.name):
```

with:

```python
                if add_source_task_id_for_code(db, item.get("code"), str(task.id)):
```

4. In `on_item_saved`, before `_persist_crawled_item`, build item data with the task id:

```python
            item_data = {
                **item_data,
                "source_task_ids": [str(task.id)],
            }
            movie_id = _persist_crawled_item(db, item_data)
```

5. In `on_item_already_exists`, replace:

```python
        add_source_task_name_for_code(db, code, task.name)
```

with:

```python
        add_source_task_id_for_code(db, code, str(task.id))
```

- [ ] **Step 7: Run movie persistence tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_source_task_names.py backend/tests/test_crawler_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add scraper/database/repositories/movie_repository.py backend/app/modules/crawler/runtime/source_task_names.py backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_source_task_names.py backend/tests/test_crawler_worker_service.py
git commit -m "feat: persist movie source task ids"
```

---

### Task 5: Movie API Uses Source Task IDs

**Files:**
- Modify: `backend/app/modules/content/movies/router.py`
- Modify: `backend/app/modules/content/movies/schemas.py`
- Modify: `backend/tests/test_content_movies_api.py`

- [ ] **Step 1: Update failing movie API tests**

Modify `backend/tests/test_content_movies_api.py`.

1. Update every `Movie(...)` test seed to use `source_task_ids=[task_id]` instead of `source_task_names`.

2. Add a task creation helper:

```python
from backend.app.models.crawl_task import CrawlTask
from backend.app.models.user import User


def seed_task_for_movie(name: str = "任务A", storage_location: str = "任务A") -> str:
    session = TestingSessionLocal()
    user = session.query(User).filter(User.username == "admin").one()
    task = CrawlTask(name=name, storage_location=storage_location, owner_id=user.id, is_skip=False)
    session.add(task)
    session.commit()
    task_id = str(task.id)
    session.close()
    return task_id
```

3. Update `seed_movie`:

```python
def seed_movie() -> tuple[str, str]:
    task_id = seed_task_for_movie()
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
        source_task_ids=[task_id],
        cover="https://example.com/cover.jpg",
    )
    session.add(movie)
    session.flush()
    session.add(MovieMagnet(movie_id=movie.id, magnet_url="magnet:?xt=urn:btih:abc", dedupe_key="abc", name="磁力A"))
    session.commit()
    movie_id = str(movie.id)
    session.close()
    return movie_id, task_id
```

4. Replace list source filter assertion test:

```python
def test_list_movies_search_and_source_task_id(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    _movie_id, task_id = seed_movie()

    response = client.get(f"/api/content/movies?keyword=AAA&source_task_id={task_id}", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["code"] == "AAA-001"
    assert body["rows"][0]["source_task_ids"] == [task_id]
    assert "source_task_names" not in body["rows"][0]
```

5. Update detail test:

```python
def test_get_movie_detail_includes_magnets_and_source_task_ids(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    movie_id, task_id = seed_movie()

    response = client.get(f"/api/content/movies/{movie_id}", headers=headers)

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert data["id"] == movie_id
    assert data["source_task_ids"] == [task_id]
    assert "source_task_names" not in data
    assert data["magnets"][0]["magnet_url"].startswith("magnet:")
```

- [ ] **Step 2: Run movie API tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py -v
```

Expected: FAIL because router and schemas still read `source_task_names`.

- [ ] **Step 3: Update router payload and filters**

Modify `backend/app/modules/content/movies/router.py`.

1. In `_movie_payload`, remove all `source_task_names` logic and add:

```python
        "source_task_ids": [str(value) for value in (movie.source_task_ids or [])],
```

2. Remove route `@router.get("/task-names")`.

3. Change `_movie_matches_python` parameter from `source_task_name` to `source_task_id`:

```python
    source_task_id: str | None,
```

Replace check with:

```python
    if source_task_id and source_task_id not in {str(value) for value in (movie.source_task_ids or [])}:
        return False
```

4. Change `list_movies` query param:

```python
    source_task_id: str | None = Query(default=None, max_length=100),
```

5. Pass `source_task_id=source_task_id` into `_movie_matches_python`.

- [ ] **Step 4: Update schemas**

Modify `backend/app/modules/content/movies/schemas.py`.

Replace:

```python
    source_task_names: list[str]
```

with:

```python
    source_task_ids: list[uuid.UUID]
```

- [ ] **Step 5: Run movie API tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/content/movies/router.py backend/app/modules/content/movies/schemas.py backend/tests/test_content_movies_api.py
git commit -m "feat: filter movies by source task id"
```

---

### Task 6: Frontend Task Form Storage Location

**Files:**
- Modify: `frontend/src/api/crawlTask/types.ts`
- Modify: `frontend/src/api/crawlTask/index.ts`
- Modify: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
- Modify: `frontend/tests/task-form-restore.ui.test.tsx`

- [ ] **Step 1: Write frontend form tests**

Modify `frontend/tests/task-form-restore.ui.test.tsx` to add tests for storage location:

```tsx
it('syncs storage location from task name until manually edited', async () => {
  renderTaskForm('/crawler/tasks/new')

  await userEvent.type(await screen.findByLabelText('任务名称'), 'JavDBVR女优列表')

  expect(screen.getByLabelText('存储位置')).toHaveValue('JavDBVR女优')

  await userEvent.clear(screen.getByLabelText('存储位置'))
  await userEvent.type(screen.getByLabelText('存储位置'), 'VR')
  await userEvent.type(screen.getByLabelText('任务名称'), '追加')

  expect(screen.getByLabelText('存储位置')).toHaveValue('VR')
})


it('disables storage location in edit mode', async () => {
  vi.mocked(getCrawlTask).mockResolvedValue({
    id: 'task-1',
    name: '任务A',
    storage_location: 'VR',
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
  })

  renderTaskForm('/crawler/tasks/task-1/edit')

  expect(await screen.findByLabelText('存储位置')).toBeDisabled()
  expect(screen.getByLabelText('存储位置')).toHaveValue('VR')
})
```

If the existing file uses different helper names, keep its helper style and add equivalent assertions.

- [ ] **Step 2: Run form tests and verify they fail**

Run:

```bash
cd frontend
npm test -- task-form-restore.ui.test.tsx
```

Expected: FAIL because `storage_location` is not in the form or API types.

- [ ] **Step 3: Update crawl task frontend types**

Modify `frontend/src/api/crawlTask/types.ts`.

Add to `CrawlTask`:

```ts
  storage_location: string
```

Add to `CrawlTaskCreateParams`:

```ts
  storage_location: string
```

Do not add `storage_location` to `CrawlTaskUpdateParams`.

Add delete mode/result types for later tasks:

```ts
export type CrawlTaskDeleteMode = 'task_only' | 'task_and_movies' | 'task_movies_and_cloud'

export interface CrawlTaskDeleteResult {
  deleted_task: boolean
  deleted_runs: number
  deleted_detail_tasks: number
  updated_movies: number
  deleted_movies: number
  deleted_magnets: number
  cloud_delete: string
}

export interface CrawlTaskDictItem {
  id: string
  name: string
}
```

- [ ] **Step 4: Update TaskFormPage form behavior**

Modify `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`.

1. Add state:

```tsx
  const [storageLocationTouched, setStorageLocationTouched] = useState(false)
```

2. Add watcher after form setup:

```tsx
  const taskName = Form.useWatch('name', form)

  useEffect(() => {
    if (isEdit || storageLocationTouched) return
    const nextValue = typeof taskName === 'string' ? taskName.slice(0, 10) : ''
    form.setFieldValue('storage_location', nextValue)
  }, [form, isEdit, storageLocationTouched, taskName])
```

3. In edit load `form.setFieldsValue`, add:

```tsx
          storage_location: task.storage_location,
```

4. In `payload`, include storage only on create:

```tsx
      const payload: CrawlTaskCreateParams = {
        name: values.name,
        storage_location: values.storage_location,
        is_skip: values.is_skip ?? false,
        urls: enrichedEntries,
      }
```

Before `updateCrawlTask`, build an update payload without storage:

```tsx
        await updateCrawlTask(taskId, {
          name: payload.name,
          is_skip: payload.is_skip,
          urls: payload.urls,
        })
```

5. In form JSX, add `storage_location` next to task name:

```tsx
            <Col flex="160px">
              <Form.Item
                name="storage_location"
                label="存储位置"
                rules={[
                  { required: true, message: '请输入存储位置' },
                  { max: 10, message: '最多 10 个字符' },
                ]}
              >
                <Input
                  placeholder="最多10字符"
                  disabled={isEdit}
                  maxLength={10}
                  onChange={() => setStorageLocationTouched(true)}
                />
              </Form.Item>
            </Col>
```

- [ ] **Step 5: Run form tests and verify they pass**

Run:

```bash
cd frontend
npm test -- task-form-restore.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/crawlTask/types.ts frontend/src/pages/crawler/tasks/TaskFormPage.tsx frontend/tests/task-form-restore.ui.test.tsx
git commit -m "feat: add task storage location form"
```

---

### Task 7: Frontend Task Delete Mode Selector

**Files:**
- Modify: `frontend/src/api/crawlTask/index.ts`
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/tests/crawler-run-controls.ui.test.tsx` or create `frontend/tests/crawler-task-delete.ui.test.tsx`

- [ ] **Step 1: Write delete modal test**

Create `frontend/tests/crawler-task-delete.ui.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListPage from '../src/pages/crawler/tasks/TaskListPage'
import { deleteCrawlTask, getCrawlTasks } from '../src/api/crawlTask'

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('../src/api/crawlTask', () => ({
  getCrawlTasks: vi.fn(),
  deleteCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

vi.mock('../src/api/crawlerRun', () => ({
  runCrawlTask: vi.fn(),
}))

describe('crawler task delete modes', () => {
  beforeEach(() => {
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [{
        id: 'task-1',
        name: '任务A',
        storage_location: 'VR',
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
    vi.mocked(deleteCrawlTask).mockResolvedValue({
      deleted_task: true,
      deleted_runs: 0,
      deleted_detail_tasks: 0,
      updated_movies: 0,
      deleted_movies: 0,
      deleted_magnets: 0,
      cloud_delete: 'not_requested',
    })
  })

  it('deletes with selected mode and disables cloud mode', async () => {
    render(<TaskListPage />)

    await userEvent.click(await screen.findByLabelText('删除'))

    expect(await screen.findByText('删除任务「任务A」')).toBeInTheDocument()
    expect(screen.getByLabelText('删除任务、电影与云存储（暂未实现）')).toBeDisabled()
    await userEvent.click(screen.getByLabelText('删除任务、运行记录与关联电影'))
    await userEvent.click(screen.getByRole('button', { name: '删除' }))

    await waitFor(() => {
      expect(deleteCrawlTask).toHaveBeenCalledWith('task-1', 'task_and_movies')
    })
  })
})
```

- [ ] **Step 2: Run delete modal test and verify it fails**

Run:

```bash
cd frontend
npm test -- crawler-task-delete.ui.test.tsx
```

Expected: FAIL because API signature and modal content do not exist.

- [ ] **Step 3: Update delete API**

Modify `frontend/src/api/crawlTask/index.ts`.

Add imports:

```ts
  CrawlTaskDeleteMode,
  CrawlTaskDeleteResult,
  CrawlTaskDictItem,
```

Replace `deleteCrawlTask`:

```ts
export function deleteCrawlTask(
  taskId: string,
  mode: CrawlTaskDeleteMode = 'task_only',
): Promise<CrawlTaskDeleteResult> {
  return request.delete<CrawlTaskDeleteResult>(`${BASE_URL}/${taskId}`, { mode })
}
```

Add task dict API:

```ts
export function getCrawlTaskDict(): Promise<CrawlTaskDictItem[]> {
  return request.get<CrawlTaskDictItem[]>(`${BASE_URL}/dict`)
}
```

- [ ] **Step 4: Update TaskListPage delete modal**

Modify `frontend/src/pages/crawler/tasks/TaskListPage.tsx`.

1. Add import:

```tsx
import { Radio, Typography } from 'antd'
import type { CrawlTaskDeleteMode } from '@/api/crawlTask/types'
```

Merge with existing Ant Design import.

2. Replace `handleDelete` modal content with a stateful confirm component:

```tsx
  const handleDelete = useCallback(
    (task: CrawlTask) => {
      let selectedMode: CrawlTaskDeleteMode = 'task_only'
      Modal.confirm({
        title: `删除任务「${task.name}」`,
        content: (
          <Radio.Group
            defaultValue="task_only"
            onChange={(event) => {
              selectedMode = event.target.value as CrawlTaskDeleteMode
            }}
          >
            <Space direction="vertical">
              <Radio value="task_only">仅删除任务与运行记录</Radio>
              <Radio value="task_and_movies">删除任务、运行记录与关联电影</Radio>
              <Radio value="task_movies_and_cloud" disabled>
                删除任务、电影与云存储（暂未实现）
              </Radio>
              <Typography.Text type="secondary">
                删除后不可恢复，请确认删除范围。
              </Typography.Text>
            </Space>
          </Radio.Group>
        ),
        okText: '删除',
        okType: 'danger',
        cancelText: '取消',
        onOk: async () => {
          const result = await deleteCrawlTask(task.id, selectedMode)
          message.success(`删除成功：运行 ${result.deleted_runs} 条，明细 ${result.deleted_detail_tasks} 条`)
          void fetchTasks(current, keyword)
        },
      })
    },
    [current, fetchTasks, keyword],
  )
```

- [ ] **Step 5: Run delete modal test and verify it passes**

Run:

```bash
cd frontend
npm test -- crawler-task-delete.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/crawlTask/index.ts frontend/src/api/crawlTask/types.ts frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/tests/crawler-task-delete.ui.test.tsx
git commit -m "feat: add task delete mode selector"
```

---

### Task 8: Frontend Movie Source Task ID Mapping

**Files:**
- Modify: `frontend/src/api/movie/index.ts`
- Modify: `frontend/src/api/movie/types.ts`
- Modify: `frontend/src/pages/content/movies/hooks/useMovieFilters.ts`
- Modify: `frontend/src/pages/content/movies/utils/movieFilter.ts`
- Modify: `frontend/src/pages/content/movies/components/MovieFilterBar.tsx`
- Modify: `frontend/src/pages/content/movies/components/MovieTable.tsx`
- Modify: `frontend/src/pages/content/movies/components/MovieDetailDrawer.tsx`
- Modify: `frontend/src/pages/content/movies/MovieListPage.tsx`
- Modify: `frontend/tests/movie-list.ui.test.tsx`

- [ ] **Step 1: Update movie UI tests**

Modify `frontend/tests/movie-list.ui.test.tsx`.

1. Mock `getCrawlTaskDict` from `../src/api/crawlTask`.

2. Replace movie fixture `source_task_names` with:

```ts
  source_task_ids: ['task-1'],
```

3. Add setup:

```ts
vi.mock('../src/api/crawlTask', () => ({
  getCrawlTaskDict: vi.fn(),
}))

vi.mocked(getCrawlTaskDict).mockResolvedValue([{ id: 'task-1', name: '任务A' }])
```

4. Add assertions:

```tsx
expect(await screen.findByText('任务A')).toBeInTheDocument()
```

5. In filter search assertion, expect:

```ts
source_task_id: 'task-1'
```

- [ ] **Step 2: Run movie UI test and verify it fails**

Run:

```bash
cd frontend
npm test -- movie-list.ui.test.tsx
```

Expected: FAIL because movie UI still expects `source_task_names` or task name filter.

- [ ] **Step 3: Update movie frontend types and API params**

Modify `frontend/src/api/movie/types.ts`.

Replace `source_task_name` and `source_task_names` with:

```ts
  source_task_ids: string[]
```

Modify `frontend/src/api/movie/index.ts`.

Replace `source_task_name?: string` with:

```ts
  source_task_id?: string
```

Remove `fetchTaskNames` export or stop using it.

- [ ] **Step 4: Update movie filter state and params**

Modify `frontend/src/pages/content/movies/utils/movieFilter.ts`.

Rename params:

```ts
    source_task_id?: string;
```

Change build params:

```ts
        source_task_id: state.selectedTask,
```

Modify `frontend/src/pages/content/movies/hooks/useMovieFilters.ts`.

Replace `fetchTaskNames` import with:

```ts
import { getCrawlTaskDict } from '@/api/crawlTask'
```

Replace tasks load:

```ts
                getCrawlTaskDict(),
```

Keep:

```ts
            setTaskOptions(tasks.map((t) => ({value: t.id, label: t.name})));
```

- [ ] **Step 5: Pass task dictionary into movie table and detail drawer**

Modify `frontend/src/pages/content/movies/MovieListPage.tsx`.

Create task dictionary map:

```tsx
  const taskNameById = useMemo(
    () => Object.fromEntries(filters.taskOptions.map((option) => [String(option.value), option.label])),
    [filters.taskOptions],
  )
```

Pass to table and drawer:

```tsx
          taskNameById={taskNameById}
```

```tsx
        taskNameById={taskNameById}
```

Modify `MovieTableProps`:

```tsx
  taskNameById: Record<string, string>
```

Add a source task column or replace old source task display with:

```tsx
    {
      title: '来源任务',
      dataIndex: 'source_task_ids',
      key: 'source_task_ids',
      width: 180,
      render: (ids: string[]) => (
        <Space size={[0, 4]} wrap>
          {(ids || []).map((id) => <Tag key={id}>{taskNameById[id] || '未知任务'}</Tag>)}
        </Space>
      ),
    },
```

Modify `MovieDetailDrawerProps`:

```tsx
    taskNameById?: Record<string, string>;
```

Add a descriptions item:

```tsx
                    <Descriptions.Item label="来源任务">
                        {Array.isArray(detail.source_task_ids) && detail.source_task_ids.length > 0
                            ? (detail.source_task_ids as string[]).map((id) => <Tag key={id}>{taskNameById?.[id] || "未知任务"}</Tag>)
                            : "-"}
                    </Descriptions.Item>
```

- [ ] **Step 6: Run movie UI test and verify it passes**

Run:

```bash
cd frontend
npm test -- movie-list.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/movie frontend/src/pages/content/movies frontend/tests/movie-list.ui.test.tsx
git commit -m "feat: map movie source task ids in UI"
```

---

### Task 9: Full Verification

**Files:**
- No planned code changes.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_models_metadata.py backend/tests/test_crawler_tasks_api.py backend/tests/test_crawler_source_task_names.py backend/tests/test_crawler_worker_service.py backend/tests/test_content_movies_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend focused tests**

Run:

```bash
cd frontend
npm test -- task-form-restore.ui.test.tsx crawler-task-delete.ui.test.tsx movie-list.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Run Alembic upgrade on a clean dev database**

Run:

```bash
source .venv/bin/activate
cd backend
alembic upgrade head
```

Expected: PASS. The migration is not old-data-compatible by design; use a clean or disposable database.

- [ ] **Step 5: Manual UI check**

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

Expected:

- New crawler task form requires `storage_location`.
- `storage_location` auto-fills from task name until manually edited.
- Edit task form shows `storage_location` disabled.
- Delete task modal offers two enabled modes and one disabled cloud mode.
- `task_only` removes the task and run data, leaving movies.
- `task_and_movies` removes source task IDs or deletes single-source movies.
- Movie list displays task names by mapping `source_task_ids` through `/api/crawler/tasks/dict`.

---

## Self-Review

- Spec coverage:
  - Task 1 covers schema changes for `storage_location`, `source_task_ids`, and removing `source_task_names`.
  - Task 2 covers required creation, update immutability, and `/api/crawler/tasks/dict`.
  - Task 3 covers all delete modes and not-implemented cloud behavior.
  - Task 4 covers movie persistence and existing-movie association by task ID.
  - Task 5 covers movie API filtering and payload changes.
  - Tasks 6-8 cover frontend form, delete modal, and movie task-name display mapping.
- Placeholder scan:
  - No forbidden placeholder terms are present.
  - Cloud deletion is explicitly represented as “暂未实现” behavior with tests.
- Type consistency:
  - Delete modes use `task_only`, `task_and_movies`, and `task_movies_and_cloud` in backend and frontend.
  - Movie association uses `source_task_ids` everywhere after migration.
  - Frontend display names are mapped via `/api/crawler/tasks/dict`, not backend movie payloads.
