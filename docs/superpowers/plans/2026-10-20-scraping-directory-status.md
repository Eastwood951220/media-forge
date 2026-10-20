# Scraping Directory Status and Scraping Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add scraping directory configuration, directory scanning with scraped/not-scraped movie status, metatube-style nfo/artwork generation, and persistent single/batch scraping tasks with list/detail pages.

**Architecture:** A new `scraping` data layer (movie columns + task tables), a filesystem scanner that judges `*.strm` + `movie.nfo` + image folders and maps them to stored movies via storage target folders and folder-name codes, a metadata source registry (javdb, javbus) used by a single-thread task worker that writes nfo/artwork into existing media folders, and React pages/actions that surface status and tasks.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0, Alembic, pytest (SQLite in-memory tests), React 19, TypeScript, Ant Design 6, TanStack Query, @dnd-kit, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-20-scraping-directory-status-design.md`

## Global Constraints

- Never create or use a Git worktree; work in this checkout.
- Stage intended files explicitly; never `git add .` or `git add -A`.
- Backend tests run against SQLite in-memory, so migrations and models must avoid PostgreSQL-only types/defaults; use `CompatibleJSON`, `String`, `Text`, `DateTime`, `Boolean`, `Integer`.
- Follow existing module conventions: task tables in `backend/app/models/`, services under `backend/app/modules/scraping/`, frontend page modules under `frontend/src/pages/scraping/`.
- All scraping writes go only into existing media folders; never create folders.
- `movies.scraping_status` is written only for movies whose normalized storage status is `stored`.
- Commands run from the repository root unless a step says otherwise.

---

## Task 1: Scraping data model and migration

**Files:**
- Create: `backend/app/models/scraping_task.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `shared/database/models/content.py`
- Create: `backend/alembic/versions/20261020_0001_add_scraping_status_and_tasks.py`
- Test: `backend/tests/test_scraping_models.py`

**Interfaces:**
- Produces: `ScrapingTask`, `ScrapingTaskItem` ORM classes; `Movie.scraping_status`, `Movie.scraping_folder`, `Movie.scraping_checked_at`.

- [ ] **Step 1: Write the failing model test**

```python
# backend/tests/test_scraping_models.py
from shared.database.models.base import Base
from shared.database.models.content import Movie
from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem


def test_movie_has_scraping_columns() -> None:
    columns = Movie.__table__.columns
    assert "scraping_status" in columns
    assert "scraping_folder" in columns
    assert "scraping_checked_at" in columns
    assert columns["scraping_status"].nullable is True


def test_scraping_tables_are_registered() -> None:
    assert ScrapingTask.__tablename__ == "scraping_tasks"
    assert ScrapingTaskItem.__tablename__ == "scraping_task_items"
    assert "scraping_tasks" in Base.metadata.tables
    assert "scraping_task_items" in Base.metadata.tables

    item_columns = ScrapingTaskItem.__table__.columns
    for name in ("task_id", "movie_id", "movie_code", "movie_title", "status", "source", "folder", "duration_ms", "error_message"):
        assert name in item_columns

    task_columns = ScrapingTask.__table__.columns
    for name in ("status", "total_count", "success_count", "failed_count", "skipped_count", "cancel_requested", "config_snapshot", "created_by"):
        assert name in task_columns
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest backend/tests/test_scraping_models.py -v`
Expected: FAIL with `ModuleNotFoundError: backend.app.models.scraping_task`.

- [ ] **Step 3: Create the task models**

```python
# backend/app/models/scraping_task.py
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from shared.database.types import CompatibleJSON


class ScrapingTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scraping_tasks"
    __table_args__ = (
        Index("idx_scraping_tasks_status_created", "status", "created_at"),
        Index("idx_scraping_tasks_created_by_status", "created_by", "status"),
    )

    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_snapshot: Mapped[dict] = mapped_column(CompatibleJSON, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    queued_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["ScrapingTaskItem"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="ScrapingTaskItem.created_at",
        lazy="selectin",
    )


class ScrapingTaskItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scraping_task_items"
    __table_args__ = (
        Index("idx_scraping_items_task_status", "task_id", "status"),
        Index("idx_scraping_items_created", "created_at"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scraping_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    movie_code: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    movie_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    folder: Mapped[str] = mapped_column(Text, nullable=False, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped[ScrapingTask] = relationship(back_populates="items")
```

- [ ] **Step 4: Register the models and add the movie columns**

In `backend/app/models/__init__.py`, add the import and exports:

```python
from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem
```

Add `"ScrapingTask", "ScrapingTaskItem"` to `__all__`.

In `shared/database/models/content.py`, add after `raw_detail`:

```python
    scraping_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    scraping_folder: Mapped[str | None] = mapped_column(Text, nullable=True)
    scraping_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 5: Run the model test to verify it passes**

Run: `python -m pytest backend/tests/test_scraping_models.py -v`
Expected: PASS.

- [ ] **Step 6: Write the Alembic migration**

Create `backend/alembic/versions/20261020_0001_add_scraping_status_and_tasks.py`:

```python
"""add scraping status and scraping tasks

Revision ID: 20261020_0001
Revises: 20260910_0002
Create Date: 2026-10-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20261020_0001"
down_revision = "20260910_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("movies", sa.Column("scraping_status", sa.String(length=20), nullable=True))
    op.add_column("movies", sa.Column("scraping_folder", sa.Text(), nullable=True))
    op.add_column("movies", sa.Column("scraping_checked_at", sa.DateTime(), nullable=True))

    op.create_table(
        "scraping_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("queued_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scraping_tasks_status"), "scraping_tasks", ["status"])
    op.create_index(op.f("ix_scraping_tasks_created_by"), "scraping_tasks", ["created_by"])
    op.create_index("idx_scraping_tasks_status_created", "scraping_tasks", ["status", "created_at"])
    op.create_index("idx_scraping_tasks_created_by_status", "scraping_tasks", ["created_by", "status"])

    op.create_table(
        "scraping_task_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("movie_id", sa.Uuid(), nullable=False),
        sa.Column("movie_code", sa.String(length=100), nullable=False),
        sa.Column("movie_title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("folder", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["scraping_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scraping_task_items_task_id"), "scraping_task_items", ["task_id"])
    op.create_index(op.f("ix_scraping_task_items_status"), "scraping_task_items", ["status"])
    op.create_index("idx_scraping_items_task_status", "scraping_task_items", ["task_id", "status"])
    op.create_index("idx_scraping_items_created", "scraping_task_items", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_scraping_items_created", table_name="scraping_task_items")
    op.drop_index("idx_scraping_items_task_status", table_name="scraping_task_items")
    op.drop_index(op.f("ix_scraping_task_items_status"), table_name="scraping_task_items")
    op.drop_index(op.f("ix_scraping_task_items_task_id"), table_name="scraping_task_items")
    op.drop_table("scraping_task_items")

    op.drop_index("idx_scraping_tasks_created_by_status", table_name="scraping_tasks")
    op.drop_index("idx_scraping_tasks_status_created", table_name="scraping_tasks")
    op.drop_index(op.f("ix_scraping_tasks_created_by"), table_name="scraping_tasks")
    op.drop_index(op.f("ix_scraping_tasks_status"), table_name="scraping_tasks")
    op.drop_table("scraping_tasks")

    op.drop_column("movies", "scraping_checked_at")
    op.drop_column("movies", "scraping_folder")
    op.drop_column("movies", "scraping_status")
```

- [ ] **Step 7: Verify the migration chain is consistent**

Run: `cd backend && python -c "import ast,pathlib; [ast.parse(pathlib.Path(p).read_text()) for p in pathlib.Path('alembic/versions').glob('20261020_*.py')]; print('ok')"`
Expected: `ok`.

- [ ] **Step 8: Run the backend suite for the model layer**

Run: `python -m pytest backend/tests/test_scraping_models.py backend/tests/test_content_models_metadata.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/scraping_task.py backend/app/models/__init__.py shared/database/models/content.py backend/alembic/versions/20261020_0001_add_scraping_status_and_tasks.py backend/tests/test_scraping_models.py
git commit -m "feat(scraping): add scraping status columns and task models"
```

---

## Task 2: Movie API exposes scraping status

**Files:**
- Modify: `backend/app/modules/content/movies/serializers.py`
- Test: `backend/tests/test_content_movie_serializers.py`
- Test: `backend/tests/test_content_movies_api.py`

**Interfaces:**
- Produces: `serialize_movie()` payload keys `scraping_status`, `scraping_folder`, `scraping_checked_at`.

- [ ] **Step 1: Write the failing serializer test**

Append to `backend/tests/test_content_movie_serializers.py`:

```python
def test_serialize_movie_includes_scraping_fields(admin_user) -> None:
    session = TestingSessionLocal()
    movie = Movie(
        code="BBB-002",
        source_url="https://javdb.com/v/bbb",
        source_name="刮削测试",
        storage_summary={"storage_status": "stored"},
        scraping_status="scraped",
        scraping_folder="/media/演员/BBB-002",
        scraping_checked_at=datetime(2026, 10, 20, 12, 0, 0),
    )
    session.add(movie)
    session.flush()

    payload = serialize_movie(movie, db=session)

    assert payload["scraping_status"] == "scraped"
    assert payload["scraping_folder"] == "/media/演员/BBB-002"
    assert payload["scraping_checked_at"] == "2026-10-20T12:00:00"
    session.close()


def test_serialize_movie_scraping_fields_default_to_none(admin_user) -> None:
    session = TestingSessionLocal()
    movie = Movie(code="CCC-003", source_url="https://javdb.com/v/ccc", source_name="默认")
    session.add(movie)
    session.flush()

    payload = serialize_movie(movie, db=session)

    assert payload["scraping_status"] is None
    assert payload["scraping_folder"] == ""
    assert payload["scraping_checked_at"] is None
    session.close()
```

Add `from datetime import datetime` to the test file's imports.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest backend/tests/test_content_movie_serializers.py -k scraping -v`
Expected: FAIL with `KeyError: 'scraping_status'`.

- [ ] **Step 3: Add the serializer fields**

In `serialize_movie()` payload (`backend/app/modules/content/movies/serializers.py`), after `"storage_summary": movie.storage_summary or {},` add:

```python
        "scraping_status": movie.scraping_status,
        "scraping_folder": movie.scraping_folder or "",
        "scraping_checked_at": movie.scraping_checked_at.isoformat() if movie.scraping_checked_at else None,
```

- [ ] **Step 4: Run the serializer tests to verify they pass**

Run: `python -m pytest backend/tests/test_content_movie_serializers.py -v`
Expected: PASS.

- [ ] **Step 5: Add an API-level assertion**

In `backend/tests/test_content_movies_api.py`, find the list-endpoint test helper (the function asserting `rows`) and add this assertion inside the first test that fetches rows:

```python
    assert "scraping_status" in rows[0]
    assert "scraping_folder" in rows[0]
    assert "scraping_checked_at" in rows[0]
```

- [ ] **Step 6: Run the movie API tests**

Run: `python -m pytest backend/tests/test_content_movies_api.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/content/movies/serializers.py backend/tests/test_content_movie_serializers.py backend/tests/test_content_movies_api.py
git commit -m "feat(scraping): expose scraping status on movie payloads"
```

---

## Task 3: Scraping config extension

**Files:**
- Modify: `backend/app/modules/scraping/schemas.py`
- Modify: `backend/app/modules/scraping/config.py`
- Test: `backend/tests/test_scraping_config_service.py`
- Test: `backend/tests/test_scraping_api.py`

**Interfaces:**
- Produces: `ScrapingConfig.metadata_sources: list[str]`, `scrape_root: str`, `media_root: str`; `ScrapingConfigService.get_public_config()` includes the three fields; `validate_scrape_root(config) -> str | None`.

- [ ] **Step 1: Write the failing config tests**

Append to `backend/tests/test_scraping_config_service.py`:

```python
def test_metadata_sources_round_trip_and_fallback(tmp_path: Path) -> None:
    service = _service(tmp_path)
    public = service.update_config(
        ScrapingConfigUpdate(
            scrape_root=str(tmp_path),
            media_root="/media/",
            metadata_sources=["javbus", "javdb"],
        )
    )

    assert public["scrape_root"] == str(tmp_path)
    assert public["media_root"] == "/media"
    assert public["metadata_sources"] == ["javbus", "javdb"]
    text = (tmp_path / "scraping.conf").read_text(encoding="utf-8")
    assert 'metadata_sources=["javbus", "javdb"]' in text


def test_invalid_metadata_sources_are_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(ValueError, match="元数据源"):
        service.update_config(ScrapingConfigUpdate(metadata_sources=["unknown"]))


def test_invalid_persisted_metadata_sources_fall_back(tmp_path: Path) -> None:
    (tmp_path / "scraping.conf").write_text(
        'metadata_sources=["unknown"]\nmedia_root=media\n',
        encoding="utf-8",
    )
    config = _service(tmp_path).get_public_config()
    assert config["metadata_sources"] == ["javdb", "javbus"]
    assert config["media_root"] == "/media"


def test_scrape_root_must_be_an_existing_directory(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(ValueError, match="刮削目录"):
        service.update_config(ScrapingConfigUpdate(scrape_root=str(tmp_path / "missing")))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest backend/tests/test_scraping_config_service.py -v`
Expected: FAIL (`ValidationError`/`AttributeError` for unknown fields).

- [ ] **Step 3: Extend the schemas**

Replace the contents of `backend/app/modules/scraping/schemas.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_BASE_URL = "http://192.168.0.36:12333"
DEFAULT_MEDIA_ROOT = "/media"
DEFAULT_METADATA_SOURCES = ["javdb", "javbus"]


class ScrapingConfig(BaseModel):
    """Persisted scraping settings."""

    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    directory_id: int | None = Field(default=None, ge=1)
    trigger_delay_seconds: int = Field(default=30, ge=10, le=3600)
    scrape_root: str = ""
    media_root: str = DEFAULT_MEDIA_ROOT
    metadata_sources: list[str] = Field(default_factory=lambda: list(DEFAULT_METADATA_SOURCES))


class ScrapingConfigUpdate(BaseModel):
    """Partial update; omitted fields keep their stored values."""

    base_url: str | None = None
    api_key: str | None = None
    directory_id: int | None = Field(default=None, ge=1)
    trigger_delay_seconds: int | None = Field(default=None, ge=10, le=3600)
    scrape_root: str | None = None
    media_root: str | None = None
    metadata_sources: list[str] | None = None


class ScrapingConfigResponse(ScrapingConfig):
    api_key: str = ""
    api_key_configured: bool = False
```

- [ ] **Step 4: Extend the config service**

In `backend/app/modules/scraping/config.py`:

Add imports and helpers near the top:

```python
from pathlib import Path

from backend.app.modules.scraping.schemas import (
    DEFAULT_MEDIA_ROOT,
    DEFAULT_METADATA_SOURCES,
    ScrapingConfig,
    ScrapingConfigResponse,
    ScrapingConfigUpdate,
)
from backend.app.modules.scraping.sources import SOURCE_REGISTRY
```

```python
def _normalize_media_root(value: str | None) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text.startswith("/") or text == "" or text == "/":
        raise ValueError("媒体库根路径必须是 / 开头的绝对路径")
    return text


def _normalize_scrape_root(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text)
    if not path.is_absolute():
        raise ValueError("刮削目录必须是绝对路径")
    if not path.is_dir():
        raise ValueError("刮削目录不存在或不是文件夹")
    return str(path)


def _parse_metadata_sources(raw: object) -> list[str]:
    try:
        parsed = json.loads(str(raw or ""))
    except (TypeError, ValueError):
        return list(DEFAULT_METADATA_SOURCES)
    if not isinstance(parsed, list):
        return list(DEFAULT_METADATA_SOURCES)
    sources = [str(item) for item in parsed if str(item) in SOURCE_REGISTRY]
    return sources or list(DEFAULT_METADATA_SOURCES)


def _safe_media_root(raw: object) -> str:
    text = str(raw or "").strip().rstrip("/")
    if not text.startswith("/") or text == "/":
        return DEFAULT_MEDIA_ROOT
    return text
```

In `get_raw_config()`, add after the `trigger_delay_seconds` line:

```python
        values["scrape_root"] = str(parsed.get("scrape_root") or "").strip()
        values["media_root"] = _safe_media_root(parsed.get("media_root"))
        values["metadata_sources"] = _parse_metadata_sources(parsed.get("metadata_sources"))
```

and wrap `ScrapingConfig(**values)` in a fallback that also normalizes an invalid persisted `media_root`:

```python
        try:
            return ScrapingConfig(**values).model_dump()
        except ValidationError:
            values["media_root"] = DEFAULT_MEDIA_ROOT
            values["metadata_sources"] = list(DEFAULT_METADATA_SOURCES)
            return ScrapingConfig(**values).model_dump()
```

In `update_config()`, after the `base_url` normalization block add:

```python
        if "scrape_root" in incoming:
            incoming["scrape_root"] = _normalize_scrape_root(incoming.get("scrape_root"))
        if "media_root" in incoming:
            incoming["media_root"] = _normalize_media_root(incoming.get("media_root"))
        if "metadata_sources" in incoming:
            sources = [str(item) for item in (incoming.get("metadata_sources") or [])]
            unknown = [item for item in sources if item not in SOURCE_REGISTRY]
            if unknown:
                raise ValueError(f"不支持的元数据源: {', '.join(unknown)}")
            if not sources:
                raise ValueError("元数据源不能为空")
            incoming["metadata_sources"] = sources
```

In `_write_config()`, serialize non-string values with JSON:

```python
    body = "".join(
        f"{key}={_serialize_value(value) if not isinstance(value, list) else json.dumps(value, ensure_ascii=False)}\n"
        for key, value in data.items()
    )
```

Note: `_serialize_value` quotes values containing spaces, so the list JSON must bypass it. This keeps the written line `metadata_sources=["javbus", "javdb"]` unquoted as required by the test.

Add at the end of the module:

```python
def validate_scrape_root(config: Mapping[str, Any]) -> str | None:
    """Return a human-readable reason when directory scanning is not runnable."""
    scrape_root = str(config.get("scrape_root") or "").strip()
    if not scrape_root:
        return "未配置刮削目录"
    if not Path(scrape_root).is_dir():
        return "刮削目录不存在或不是文件夹"
    return None
```

- [ ] **Step 5: Run the config tests**

Run: `python -m pytest backend/tests/test_scraping_config_service.py -v`
Expected: PASS.

- [ ] **Step 6: Update the API test expectations**

In `backend/tests/test_scraping_api.py`, add the new fields to both exact-dict assertions (`test_get_and_put_scraping_config`) and the `_write_config` fixture and any later expectations:

```python
        "scrape_root": "",
        "media_root": "/media",
        "metadata_sources": ["javdb", "javbus"],
```

Then extend `test_get_and_put_scraping_config` with a PUT that includes `scrape_root` set to a tmp directory and `metadata_sources` reordered:

```python
    reordered = client.put(
        "/api/scraping/config",
        headers=headers,
        json={"scrape_root": str(tmp_path), "metadata_sources": ["javbus", "javdb"]},
    )
    assert reordered.status_code == HTTPStatus.OK
    assert reordered.json()["data"]["metadata_sources"] == ["javbus", "javdb"]
    assert reordered.json()["data"]["scrape_root"] == str(tmp_path)
```

Also add:

```python
def test_put_rejects_unknown_metadata_source(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    headers = _auth_headers(client, admin_user)
    response = client.put(
        "/api/scraping/config",
        headers=headers,
        json={"metadata_sources": ["unknown"]},
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
```

- [ ] **Step 7: Run the API tests and any other 200-OK config tests**

Run: `python -m pytest backend/tests/test_scraping_api.py backend/tests/test_scraping_config_service.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/scraping/schemas.py backend/app/modules/scraping/config.py backend/tests/test_scraping_config_service.py backend/tests/test_scraping_api.py
git commit -m "feat(scraping): add directory and metadata source configuration"
```

---

## Task 4: Path mapping and code normalization

**Files:**
- Create: `backend/app/modules/scraping/paths.py`
- Test: `backend/tests/test_scraping_paths.py`

**Interfaces:**
- Produces: `normalize_code(value: str) -> str`, `code_from_folder_name(name: str) -> str | None`, `cloud_to_local(scrape_root: str, media_root: str, cloud_folder: str) -> Path | None`, `local_to_cloud(scrape_root: str, media_root: str, local_folder: str | Path) -> str | None`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_scraping_paths.py
from pathlib import Path

from backend.app.modules.scraping.paths import (
    cloud_to_local,
    code_from_folder_name,
    local_to_cloud,
    normalize_code,
)


def test_normalize_code_ignores_separators_and_case() -> None:
    assert normalize_code("abp-123") == "ABP123"
    assert normalize_code("ABP_123") == "ABP123"
    assert normalize_code(" ABP 123 ") == "ABP123"


def test_code_from_folder_name_supports_suffixes_and_titles() -> None:
    assert code_from_folder_name("ADN-784") == "ADN-784"
    assert code_from_folder_name("ADN-784 あなた、許して…。") == "ADN-784"
    assert code_from_folder_name("adn784") == "ADN-784"
    assert code_from_folder_name("ADN_784") == "ADN-784"
    assert code_from_folder_name("ADN-784-C") == "ADN-784-C"
    assert code_from_folder_name("ADN-784-CD1") == "ADN-784-CD1"
    assert code_from_folder_name("随机文件夹") is None
    assert code_from_folder_name("Movie 2023") is None
    assert code_from_folder_name("Part 01") is None
    assert code_from_folder_name("FHD 1080") is None
    assert code_from_folder_name("ABCDEFG-123") is None


def test_cloud_to_local_and_back(tmp_path: Path) -> None:
    scrape_root = str(tmp_path)
    assert cloud_to_local(scrape_root, "/media", "/media/演员/ADN-784") == tmp_path / "演员" / "ADN-784"
    assert local_to_cloud(scrape_root, "/media", tmp_path / "演员" / "ADN-784") == "/media/演员/ADN-784"


def test_cloud_to_local_rejects_paths_outside_media_root(tmp_path: Path) -> None:
    assert cloud_to_local(str(tmp_path), "/media", "/downloads/ADN-784") is None
    assert cloud_to_local(str(tmp_path), "/media", "/media") is None
    assert local_to_cloud(str(tmp_path), "/media", "/somewhere/else") is None


def test_cloud_to_local_rejects_escaping_paths(tmp_path: Path) -> None:
    assert cloud_to_local(str(tmp_path), "/media", "/media/../etc") is None


def test_path_mapping_rejects_invalid_roots(tmp_path: Path) -> None:
    assert cloud_to_local("", "/media", "/media/ADN-784") is None
    assert cloud_to_local(str(tmp_path), "media", "/media/ADN-784") is None
    assert cloud_to_local(str(tmp_path), "/", "/ADN-784") is None
    assert local_to_cloud(str(tmp_path), "/media", "/elsewhere/ADN-784") is None
    assert local_to_cloud("", "/media", str(tmp_path / "ADN-784")) is None


def test_path_mapping_normalizes_trailing_slashes(tmp_path: Path) -> None:
    assert cloud_to_local(str(tmp_path) + "/", "/media/", "/media/ADN-784/") == tmp_path / "ADN-784"
    assert local_to_cloud(str(tmp_path), "/media/", tmp_path / "ADN-784") == "/media/ADN-784"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest backend/tests/test_scraping_paths.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the paths module**

```python
# backend/app/modules/scraping/paths.py
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

CODE_PATTERN = re.compile(r"^([A-Za-z]{2,6})[-_]?(\d{2,6})(?:[-_]([A-Za-z0-9]{1,4}))?")


def normalize_code(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def code_from_folder_name(name: str) -> str | None:
    match = CODE_PATTERN.search(name or "")
    if match is None:
        return None
    code = f"{match.group(1)}-{match.group(2)}"
    if match.group(3):
        code = f"{code}-{match.group(3)}"
    return code.upper()


def _normalized_root(value: str) -> PurePosixPath | None:
    text = str(value or "").strip().rstrip("/")
    if not text.startswith("/"):
        return None
    root = PurePosixPath(text)
    if str(root) in ("", ".", "/"):
        return None
    return root


def cloud_to_local(scrape_root: str, media_root: str, cloud_folder: str) -> Path | None:
    if not str(scrape_root or "").strip():
        return None
    root = _normalized_root(media_root)
    folder = _normalized_root(cloud_folder)
    if root is None or folder is None:
        return None
    try:
        relative = folder.relative_to(root)
    except ValueError:
        return None
    if str(relative) == ".":
        return None
    base = Path(scrape_root)
    local = base / relative
    try:
        local.resolve().relative_to(base.resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    return local


def local_to_cloud(scrape_root: str, media_root: str, local_folder: str | Path) -> str | None:
    if not str(scrape_root or "").strip():
        return None
    root = _normalized_root(media_root)
    if root is None:
        return None
    base = Path(scrape_root)
    try:
        relative = Path(local_folder).resolve().relative_to(base.resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    return str(PurePosixPath(str(root)) / relative.as_posix())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest backend/tests/test_scraping_paths.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/scraping/paths.py backend/tests/test_scraping_paths.py
git commit -m "feat(scraping): add media path mapping and code normalization"
```

---

## Task 5: movie.nfo renderer

**Files:**
- Create: `backend/app/modules/scraping/nfo.py`
- Test: `backend/tests/test_scraping_nfo.py`

**Interfaces:**
- Produces: `render_movie_nfo(movie, *, cloud_folder: str, source_site: str | None = None, dateadded: datetime | None = None) -> str`, `write_movie_nfo(folder: Path, movie, *, cloud_folder: str, source_site: str | None = None) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_scraping_nfo.py
from datetime import date, datetime
from pathlib import Path

from backend.app.modules.scraping.nfo import render_movie_nfo, write_movie_nfo
from shared.database.models.content import Movie


def _movie(**overrides) -> Movie:
    values = dict(
        code="ADN-784",
        source_name="ADN-784 あなた、許して…。 心まで盗まれて",
        release_date=date(2026, 7, 3),
        maker="アタッカーズ",
        series="あなた、許して…。",
        tags=["ドラマ", "不倫"],
        actors=["北野未奈"],
    )
    values.update(overrides)
    return Movie(**values)


def test_render_movie_nfo_matches_metatube_shape() -> None:
    text = render_movie_nfo(
        _movie(),
        cloud_folder="/media/北野未奈/ADN-784",
        source_site="JavBus",
        dateadded=datetime(2026, 10, 20, 12, 0, 0),
    )

    assert text.startswith('<?xml version="1.0" encoding="utf-8" standalone="yes"?>')
    assert "<title>ADN-784 あなた、許して…。 心まで盗まれて</title>" in text
    assert "<originaltitle>あなた、許して…。 心まで盗まれて</originaltitle>" in text
    assert "<year>2026</year>" in text
    assert "<mpaa>JP-18+</mpaa>" in text
    assert "<premiered>2026-07-03</premiered>" in text
    assert "<releasedate>2026-07-03</releasedate>" in text
    assert "<tagline>配信開始日 2026-07-03</tagline>" in text
    assert "<genre>ドラマ</genre>" in text
    assert "<studio>アタッカーズ</studio>" in text
    assert "<metatubeid>JavBus:ADN-784</metatubeid>" in text
    assert "<poster>/media/北野未奈/ADN-784/folder.jpg</poster>" in text
    assert "<fanart>/media/北野未奈/ADN-784/backdrop.jpg</fanart>" in text
    assert "<name>あなた、許して…。</name>" in text


def test_render_movie_nfo_omits_metatubeid_without_source() -> None:
    text = render_movie_nfo(_movie(), cloud_folder="/media/ADN-784")
    assert "<metatubeid>" not in text


def test_render_movie_nfo_escapes_xml() -> None:
    text = render_movie_nfo(
        _movie(code="ADN-784", source_name='ADN-784 A & B <C>'),
        cloud_folder="/media/ADN-784",
    )
    assert "A &amp; B &lt;C&gt;" in text


def test_write_movie_nfo_is_atomic_and_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "movie.nfo"
    target.write_text("old", encoding="utf-8")

    write_movie_nfo(tmp_path, _movie(), cloud_folder="/media/ADN-784")

    assert "ADN-784" in target.read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.tmp"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest backend/tests/test_scraping_nfo.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the nfo module**

```python
# backend/app/modules/scraping/nfo.py
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from backend.app.modules.scraping.paths import normalize_code
from shared.database.models.content import Movie

XML_DECLARATION = '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n'


def _title(movie: Movie) -> str:
    name = str(movie.source_name or "").strip()
    code = str(movie.code or "").upper()
    if not name:
        return code
    if normalize_code(name).startswith(normalize_code(code)):
        return name
    return f"{code} {name}".strip()


def _original_title(movie: Movie) -> str:
    name = str(movie.source_name or "").strip()
    code = str(movie.code or "").strip()
    if not name or not code:
        return name
    stripped = re.sub(rf"^{re.escape(code)}[\s\-_ ]*", "", name, flags=re.IGNORECASE).strip()
    return stripped or name


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def render_movie_nfo(
    movie: Movie,
    *,
    cloud_folder: str,
    source_site: str | None = None,
    dateadded: datetime | None = None,
) -> str:
    root = ET.Element("movie")
    ET.SubElement(root, "plot")
    ET.SubElement(root, "lockdata").text = "false"
    ET.SubElement(root, "dateadded").text = (dateadded or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    ET.SubElement(root, "title").text = _title(movie)
    ET.SubElement(root, "originaltitle").text = _original_title(movie)

    release_date = movie.release_date
    if release_date is not None:
        ET.SubElement(root, "year").text = str(release_date.year)
    ET.SubElement(root, "mpaa").text = "JP-18+"
    if release_date is not None:
        premiered = release_date.isoformat()
        ET.SubElement(root, "premiered").text = premiered
        ET.SubElement(root, "releasedate").text = premiered
        ET.SubElement(root, "tagline").text = f"配信開始日 {premiered}"

    for genre in _dedupe(list(movie.tags or [])):
        ET.SubElement(root, "genre").text = genre

    maker = str(movie.maker or "").strip()
    if maker:
        ET.SubElement(root, "studio").text = maker

    for tag in _dedupe([maker, str(movie.series or ""), *list(movie.tags or [])]):
        ET.SubElement(root, "tag").text = tag

    if source_site:
        ET.SubElement(root, "metatubeid").text = f"{source_site}:{movie.code}"

    art = ET.SubElement(root, "art")
    folder = str(cloud_folder or "").rstrip("/")
    ET.SubElement(art, "poster").text = f"{folder}/folder.jpg"
    ET.SubElement(art, "fanart").text = f"{folder}/backdrop.jpg"

    series = str(movie.series or "").strip()
    if series:
        set_node = ET.SubElement(root, "set")
        ET.SubElement(set_node, "name").text = series

    fileinfo = ET.SubElement(root, "fileinfo")
    ET.SubElement(fileinfo, "streamdetails")

    ET.indent(root, space="  ")
    return XML_DECLARATION + ET.tostring(root, encoding="unicode") + "\n"


def write_movie_nfo(
    folder: Path,
    movie: Movie,
    *,
    cloud_folder: str,
    source_site: str | None = None,
) -> None:
    text = render_movie_nfo(movie, cloud_folder=cloud_folder, source_site=source_site)
    target = Path(folder) / "movie.nfo"
    temp = target.with_suffix(".nfo.tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(target)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest backend/tests/test_scraping_nfo.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/scraping/nfo.py backend/tests/test_scraping_nfo.py
git commit -m "feat(scraping): render metatube-style movie nfo"
```

---

## Task 6: Metadata source registry (javdb, javbus)

**Files:**
- Create: `backend/app/modules/scraping/sources.py`
- Test: `backend/tests/test_scraping_sources.py`

**Interfaces:**
- Produces: `SourceMetadata` dataclass, `SourceAdapter` protocol, `SOURCE_REGISTRY: dict[str, SourceAdapter]`, `SOURCE_LABELS: dict[str, str]`, `fetch_by_priority(code: str, sources: list[str]) -> SourceMetadata | None`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_scraping_sources.py
from backend.app.modules.scraping import sources
from backend.app.modules.scraping.sources import SOURCE_LABELS, SOURCE_REGISTRY, SourceMetadata


class _FakePage:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeFetcher:
    def __init__(self, pages: dict[str, object]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    def get(self, url: str, **_kwargs) -> object:
        self.requested.append(url)
        return self.pages[url]


def test_registry_contains_javdb_and_javbus() -> None:
    assert set(SOURCE_REGISTRY) == {"javdb", "javbus"}
    assert SOURCE_LABELS["javdb"]
    assert SOURCE_LABELS["javbus"]


def test_fetch_by_priority_uses_configured_order_and_stops_on_success(monkeypatch) -> None:
    calls: list[str] = []

    def fake_fetch(adapter, code):
        calls.append(adapter)
        if adapter == "javbus":
            return SourceMetadata(site_key="JavBus", title="ok")
        return None

    monkeypatch.setattr(sources, "fetch_with_source", fake_fetch)

    result = sources.fetch_by_priority("ADN-784", ["javdb", "javbus"])

    assert result is not None
    assert result.site_key == "JavBus"
    assert calls == ["javdb", "javbus"]


def test_fetch_by_priority_returns_none_when_all_sources_fail(monkeypatch) -> None:
    monkeypatch.setattr(sources, "fetch_with_source", lambda adapter, code: None)
    assert sources.fetch_by_priority("ADN-784", ["javdb", "javbus"]) is None


def test_javdb_adapter_parses_search_and_detail(monkeypatch) -> None:
    search_page = _FakePage("search")
    detail_page = _FakePage("detail")
    fetcher = _FakeFetcher({
        "https://javdb.com/search?q=ADN-784&f=all": search_page,
        "https://javdb.com/v/detail": detail_page,
    })

    monkeypatch.setattr(
        sources,
        "parse_javdb_search",
        lambda page, page_no: [
            {"url": "https://javdb.com/v/detail", "code": "ADN-784", "status": "pending", "name": "ADN-784"}
        ],
    )
    monkeypatch.setattr(
        sources,
        "parse_javdb_detail",
        lambda page: {
            "code": "ADN-784",
            "source_name": "ADN-784 タイトル",
            "cover": "https://javdb.com/cover.jpg",
            "release_date": "2026-07-03",
            "maker": "メーカー",
            "series": "シリーズ",
            "tags": ["タグ"],
            "actors": ["女優"],
        },
    )

    adapter = sources.JavdbAdapter(fetcher_factory=lambda source: fetcher, throttle=lambda: None)
    metadata = adapter.fetch_by_code("ADN-784")

    assert metadata is not None
    assert metadata.site_key == "JavDB"
    assert metadata.cover_url == "https://javdb.com/cover.jpg"
    assert metadata.premiered == "2026-07-03"
    assert metadata.studio == "メーカー"
    assert fetcher.requested[0].endswith("/search?q=ADN-784&f=all")


def test_javbus_adapter_parses_search_and_detail(monkeypatch) -> None:
    search_page = _FakePage("search")
    detail_page = _FakePage("detail")
    fetcher = _FakeFetcher({
        "https://www.javbus.com/search/ADN-784": search_page,
        "https://www.javbus.com/ADN-784": detail_page,
    })

    monkeypatch.setattr(
        sources,
        "parse_javbus_list",
        lambda page, source_url: ([{"url": "https://www.javbus.com/ADN-784", "code": "ADN-784"}], None),
    )
    monkeypatch.setattr(
        sources,
        "parse_javbus_detail",
        lambda page, source_url: {
            "code": "ADN-784",
            "source_name": "ADN-784 タイトル",
            "cover_url": "https://www.javbus.com/cover.jpg",
            "release_date": "2026-07-03",
            "maker": "メーカー",
            "series": "シリーズ",
            "tags": ["タグ"],
            "actors": ["女優"],
        },
    )

    adapter = sources.JavbusAdapter(fetcher_factory=lambda source: fetcher, throttle=lambda: None)
    metadata = adapter.fetch_by_code("ADN-784")

    assert metadata is not None
    assert metadata.site_key == "JavBus"
    assert metadata.cover_url == "https://www.javbus.com/cover.jpg"
    assert metadata.premiered == "2026-07-03"
    assert metadata.studio == "メーカー"
    assert fetcher.requested[1] == "https://www.javbus.com/ADN-784"


def test_adapters_return_none_when_fetch_raises() -> None:
    def failing_factory(source: str):
        raise RuntimeError("network down")

    adapter = sources.JavbusAdapter(fetcher_factory=failing_factory, throttle=lambda: None)

    assert adapter.fetch_by_code("ADN-784") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest backend/tests/test_scraping_sources.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the sources module**

```python
# backend/app/modules/scraping/sources.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Protocol
from urllib.parse import quote

from backend.app.modules.crawler.config.conf_reader import read_crawler_runtime_config
from scraper.config.sites import JAVBUS_SITE, JAVDB_SITE
from scraper.core.throttle import random_sleep
from scraper.fetchers.site_fetcher import build_site_fetcher
from scraper.spiders.javbus.javbus_parser import parse_detail_page as parse_javbus_detail
from scraper.spiders.javbus.javbus_parser import parse_list_page as parse_javbus_list
from scraper.spiders.javdb.javdb_parser import parse_detail_page as parse_javdb_detail
from scraper.spiders.javdb.javdb_parser import parse_search_page as parse_javdb_search

from backend.app.modules.scraping.paths import normalize_code

logger = logging.getLogger(__name__)


@dataclass
class SourceMetadata:
    site_key: str
    title: str | None = None
    original_title: str | None = None
    year: int | None = None
    premiered: str | None = None
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    studio: str | None = None
    series: str | None = None
    actors: list[str] = field(default_factory=list)
    cover_url: str | None = None
    backdrop_url: str | None = None
    landscape_url: str | None = None


class SourceAdapter(Protocol):
    key: str
    site_key: str

    def fetch_by_code(self, code: str) -> SourceMetadata | None: ...


def _clean(value: object) -> str:
    return str(value or "").strip()


def _throttle() -> None:
    try:
        config = read_crawler_runtime_config()
        random_sleep(config.DETAIL_PAGE_DELAY_MIN, config.DETAIL_PAGE_DELAY_MAX)
    except Exception:
        logger.warning("Metadata request throttle failed; continuing", exc_info=True)


class JavdbAdapter:
    key = "javdb"
    site_key = "JavDB"

    def __init__(
        self,
        fetcher_factory: Callable[[str], object] = build_site_fetcher,
        throttle: Callable[[], None] | None = None,
    ) -> None:
        self.fetcher_factory = fetcher_factory
        self.throttle = throttle or _throttle

    def fetch_by_code(self, code: str) -> SourceMetadata | None:
        try:
            fetcher = self.fetcher_factory("javdb")
            base = JAVDB_SITE["base_url"].rstrip("/")
            search_url = f"{base}/search?q={quote(code)}&f=all"
            self.throttle()
            search_page = fetcher.get(search_url)
            tasks = parse_javdb_search(search_page, 1)
            wanted = normalize_code(code)
            target = next(
                (task for task in tasks if normalize_code(task.get("code") or "") == wanted and task.get("status") != "skipped"),
                None,
            )
            if target is None or not target.get("url"):
                return None
            self.throttle()
            detail = parse_javdb_detail(fetcher.get(target["url"]))
            return SourceMetadata(
                site_key=self.site_key,
                title=_clean(detail.get("source_name")) or None,
                original_title=_clean(detail.get("source_name")) or None,
                premiered=_clean(detail.get("release_date")) or None,
                genres=list(detail.get("tags") or []),
                tags=list(detail.get("tags") or []),
                studio=_clean(detail.get("maker")) or None,
                series=_clean(detail.get("series")) or None,
                actors=list(detail.get("actors") or []),
                cover_url=_clean(detail.get("cover")) or None,
            )
        except Exception:
            logger.warning("javdb metadata fetch failed for %s", code, exc_info=True)
            return None


class JavbusAdapter:
    key = "javbus"
    site_key = "JavBus"

    def __init__(
        self,
        fetcher_factory: Callable[[str], object] = build_site_fetcher,
        throttle: Callable[[], None] | None = None,
    ) -> None:
        self.fetcher_factory = fetcher_factory
        self.throttle = throttle or _throttle

    def fetch_by_code(self, code: str) -> SourceMetadata | None:
        try:
            fetcher = self.fetcher_factory("javbus")
            base = JAVBUS_SITE["base_url"].rstrip("/")
            search_url = f"{base}/search/{quote(code)}"
            self.throttle()
            search_page = fetcher.get(search_url)
            movies, _page = parse_javbus_list(search_page, search_url)
            wanted = normalize_code(code)
            target = next((movie for movie in movies if normalize_code(movie.get("code") or "") == wanted), None)
            if target is None or not target.get("url"):
                return None
            self.throttle()
            detail = parse_javbus_detail(fetcher.get(target["url"]), target["url"])
            return SourceMetadata(
                site_key=self.site_key,
                title=_clean(detail.get("source_name")) or None,
                original_title=_clean(detail.get("source_name")) or None,
                premiered=_clean(detail.get("release_date")) or None,
                genres=list(detail.get("tags") or []),
                tags=list(detail.get("tags") or []),
                studio=_clean(detail.get("maker")) or None,
                series=_clean(detail.get("series")) or None,
                actors=list(detail.get("actors") or []),
                cover_url=_clean(detail.get("cover_url")) or None,
                backdrop_url=None,
            )
        except Exception:
            logger.warning("javbus metadata fetch failed for %s", code, exc_info=True)
            return None


SOURCE_REGISTRY: dict[str, SourceAdapter] = {
    "javdb": JavdbAdapter(),
    "javbus": JavbusAdapter(),
}
SOURCE_LABELS = {
    "javdb": "JavDB",
    "javbus": "JavBus",
}


def fetch_with_source(source: str, code: str) -> SourceMetadata | None:
    adapter = SOURCE_REGISTRY.get(source)
    if adapter is None:
        return None
    return adapter.fetch_by_code(code)


def fetch_by_priority(code: str, sources: list[str]) -> SourceMetadata | None:
    for source in sources:
        metadata = fetch_with_source(source, code)
        if metadata is not None:
            return metadata
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest backend/tests/test_scraping_sources.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/scraping/sources.py backend/tests/test_scraping_sources.py
git commit -m "feat(scraping): add javdb and javbus metadata sources"
```

---

## Task 7: Artwork downloader

**Files:**
- Create: `backend/app/modules/scraping/images.py`
- Test: `backend/tests/test_scraping_images.py`

**Interfaces:**
- Produces: `download_image(url: str, dest: Path, *, referer: str | None = None, transport: httpx.BaseTransport | None = None) -> bool`, `write_artwork(folder: Path, *, cover_url: str | None, backdrop_url: str | None, landscape_url: str | None, referer: str | None = None, transport=None) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_scraping_images.py
from pathlib import Path

import httpx

from backend.app.modules.scraping.images import download_image, write_artwork


def _transport(content: bytes, content_type: str, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=content, headers={"content-type": content_type})
    return httpx.MockTransport(handler)


def test_download_image_writes_the_file(tmp_path: Path) -> None:
    dest = tmp_path / "folder.jpg"
    ok = download_image("https://example.com/a.jpg", dest, transport=_transport(b"jpeg-bytes", "image/jpeg"))
    assert ok is True
    assert dest.read_bytes() == b"jpeg-bytes"
    assert not list(tmp_path.glob("*.tmp"))


def test_download_image_rejects_non_image_content(tmp_path: Path) -> None:
    dest = tmp_path / "folder.jpg"
    ok = download_image("https://example.com/a", dest, transport=_transport(b"<html>", "text/html"))
    assert ok is False
    assert not dest.exists()


def test_download_image_handles_http_errors(tmp_path: Path) -> None:
    dest = tmp_path / "folder.jpg"
    ok = download_image("https://example.com/a.jpg", dest, transport=_transport(b"", "image/jpeg", status=404))
    assert ok is False
    assert not dest.exists()


def test_download_image_rejects_oversized_content(tmp_path: Path, monkeypatch) -> None:
    from backend.app.modules.scraping import images

    monkeypatch.setattr(images, "MAX_IMAGE_BYTES", 4)
    dest = tmp_path / "folder.jpg"
    ok = download_image("https://example.com/a.jpg", dest, transport=_transport(b"12345", "image/jpeg"))
    assert ok is False
    assert not dest.exists()


def test_write_artwork_writes_available_images(tmp_path: Path) -> None:
    transport = _transport(b"img", "image/jpeg")
    count = write_artwork(
        tmp_path,
        cover_url="https://example.com/cover.jpg",
        backdrop_url="https://example.com/backdrop.jpg",
        landscape_url=None,
        transport=transport,
    )
    assert count == 2
    assert (tmp_path / "folder.jpg").exists()
    assert (tmp_path / "backdrop.jpg").exists()
    assert not (tmp_path / "landscape.jpg").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest backend/tests/test_scraping_images.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the images module**

```python
# backend/app/modules/scraping/images.py
from __future__ import annotations

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30.0
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def download_image(
    url: str,
    dest: Path,
    *,
    referer: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> bool:
    if not url:
        return False
    headers = {"User-Agent": "Mozilla/5.0"}
    if referer:
        headers["Referer"] = referer
    target = Path(dest)
    try:
        with httpx.Client(timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS), transport=transport) as client:
            with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if not content_type.lower().startswith("image/"):
                    logger.warning("Skipping non-image artwork: url=%s type=%s", url, content_type)
                    return False
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        logger.warning("Skipping oversized artwork: url=%s", url)
                        return False
                    chunks.append(chunk)
    except Exception:
        logger.warning("Artwork download failed: url=%s", url, exc_info=True)
        return False

    temp = target.with_suffix(target.suffix + ".tmp")
    try:
        temp.write_bytes(b"".join(chunks))
        temp.replace(target)
    except OSError:
        logger.warning("Artwork write failed: path=%s", target, exc_info=True)
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            logger.warning("Artwork temp cleanup failed: path=%s", temp, exc_info=True)
        return False
    return True


def write_artwork(
    folder: Path,
    *,
    cover_url: str | None,
    backdrop_url: str | None,
    landscape_url: str | None,
    referer: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> int:
    folder = Path(folder)
    written = 0
    mapping = (
        (cover_url, "folder.jpg"),
        (backdrop_url, "backdrop.jpg"),
        (landscape_url, "landscape.jpg"),
    )
    for url, filename in mapping:
        if not url:
            continue
        if download_image(url, folder / filename, referer=referer, transport=transport):
            written += 1
    return written
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest backend/tests/test_scraping_images.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/scraping/images.py backend/tests/test_scraping_images.py
git commit -m "feat(scraping): download artwork into media folders"
```

---

## Task 8: Directory scanner and status judgment

**Files:**
- Create: `backend/app/modules/scraping/scan.py`
- Test: `backend/tests/test_scraping_scan.py`

**Interfaces:**
- Produces: `ScanSummary` dataclass, `judge_folder(folder: Path) -> tuple[bool, bool, int]`, `scan_directory(db, config) -> ScanSummary`, `refresh_movie_status(db, movie, *, local_folder: Path | None = None, cloud_folder: str | None = None) -> str`, `schedule_scan_after_strm(config) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_scraping_scan.py
from datetime import datetime
from pathlib import Path

from backend.app.modules.content.movies.storage_status import STORAGE_STATUS_STORED, STORAGE_STATUS_NOT_STORED
from backend.app.modules.scraping.scan import (
    judge_folder,
    refresh_movie_status,
    scan_directory,
)
from shared.database.models.content import Movie


def _make_movie(db, code: str, *, stored: bool, target_folder: str = "") -> Movie:
    summary = {
        "storage_status": STORAGE_STATUS_STORED if stored else STORAGE_STATUS_NOT_STORED,
        "locations": [{"target_folder": target_folder, "path": target_folder}] if target_folder else [],
    }
    movie = Movie(code=code, source_name=f"{code} title", storage_summary=summary)
    db.add(movie)
    db.commit()
    db.refresh(movie)
    return movie


def _make_folder(root: Path, relative: str, *, strm=True, nfo=True, images=1) -> Path:
    folder = root / relative
    folder.mkdir(parents=True, exist_ok=True)
    if strm:
        (folder / f"{folder.name}.strm").write_text("http://example.com/v.mkv", encoding="utf-8")
    if nfo:
        (folder / "movie.nfo").write_text("<movie/>", encoding="utf-8")
    for index in range(images):
        (folder / f"image{index}.jpg").write_bytes(b"img")
    return folder


def _config(scrape_root: Path) -> dict:
    return {"scrape_root": str(scrape_root), "media_root": "/media", "metadata_sources": ["javdb", "javbus"]}


def test_judge_folder_requires_strm_nfo_and_image(tmp_path: Path) -> None:
    good = _make_folder(tmp_path, "ADN-784")
    no_nfo = _make_folder(tmp_path, "BBB-001", nfo=False)
    no_image = _make_folder(tmp_path, "CCC-002", images=0)

    assert judge_folder(good) == (True, True, 1)
    assert judge_folder(no_nfo) == (True, False, 1)
    assert judge_folder(no_image) == (True, True, 0)


def test_scan_directory_updates_stored_movies(tmp_path: Path, db_session, monkeypatch) -> None:
    stored = _make_movie(db_session, "ADN-784", stored=True, target_folder="/media/演员/ADN-784")
    missing = _make_movie(db_session, "BBB-001", stored=True, target_folder="/media/演员/BBB-001")
    not_stored = _make_movie(db_session, "CCC-002", stored=False)
    _make_folder(tmp_path, "演员/ADN-784")

    summary = scan_directory(db_session, _config(tmp_path))

    db_session.refresh(stored)
    db_session.refresh(missing)
    db_session.refresh(not_stored)
    assert stored.scraping_status == "scraped"
    assert stored.scraping_folder == "/media/演员/ADN-784"
    assert missing.scraping_status == "not_scraped"
    assert missing.scraping_folder is None
    assert not_stored.scraping_status is None
    assert summary.scraped_folders == 1
    assert summary.updated_movies >= 2


def test_scan_directory_matches_by_folder_name_when_location_does_not_map(tmp_path: Path, db_session) -> None:
    movie = _make_movie(db_session, "ADN-784", stored=True, target_folder="/other/ADN-784")
    _make_folder(tmp_path, "ADN-784")

    scan_directory(db_session, _config(tmp_path))

    db_session.refresh(movie)
    assert movie.scraping_status == "scraped"
    assert movie.scraping_folder == "/media/ADN-784"


def test_multi_location_movie_claims_only_one_deterministic_folder(tmp_path: Path, db_session) -> None:
    movie = Movie(
        code="ADN-784",
        source_name="ADN-784 title",
        storage_summary={
            "storage_status": "stored",
            "locations": [
                {"target_folder": "/media/z/ADN-784"},
                {"target_folder": "/media/a/ADN-784"},
            ],
        },
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    _make_folder(tmp_path, "z/ADN-784", nfo=False)
    _make_folder(tmp_path, "a/ADN-784")

    summary = scan_directory(db_session, _config(tmp_path))

    db_session.refresh(movie)
    assert movie.scraping_status == "scraped"
    assert movie.scraping_folder == "/media/a/ADN-784"
    assert summary.matched_movies == 1


def test_fallback_tie_break_is_lexicographic(tmp_path: Path, db_session) -> None:
    movie = _make_movie(db_session, "ADN-784", stored=True, target_folder="/other/ADN-784")
    _make_folder(tmp_path, "b/ADN-784", nfo=False)
    _make_folder(tmp_path, "a/ADN-784")

    scan_directory(db_session, _config(tmp_path))

    db_session.refresh(movie)
    assert movie.scraping_status == "scraped"
    assert movie.scraping_folder == "/media/a/ADN-784"


def test_refresh_movie_status_marks_missing_mapped_folder_not_scraped(tmp_path: Path, db_session, monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.modules.scraping.scan._current_scan_config",
        lambda: {"scrape_root": str(tmp_path), "media_root": "/media"},
    )
    movie = _make_movie(db_session, "ADN-784", stored=True, target_folder="/media/ADN-784")
    movie.scraping_status = "scraped"
    movie.scraping_folder = "/media/ADN-784"
    db_session.commit()

    status = refresh_movie_status(db_session, movie)

    db_session.refresh(movie)
    assert status == "not_scraped"
    assert movie.scraping_status == "not_scraped"
    assert movie.scraping_folder is None
    assert movie.scraping_checked_at is not None


def test_scan_preserves_status_for_unmapped_locations(tmp_path: Path, db_session) -> None:
    movie = _make_movie(db_session, "ADN-784", stored=True, target_folder="/other/ADN-784")
    movie.scraping_status = "scraped"
    movie.scraping_folder = "/other/ADN-784"
    db_session.commit()
    _make_folder(tmp_path, "ADN-999")

    scan_directory(db_session, _config(tmp_path))

    db_session.refresh(movie)
    assert movie.scraping_status == "scraped"
    assert movie.scraping_folder == "/other/ADN-784"


def test_refresh_movie_status_clears_when_not_stored(tmp_path: Path, db_session) -> None:
    movie = _make_movie(db_session, "ADN-784", stored=False, target_folder="/media/ADN-784")
    movie.scraping_status = "scraped"
    movie.scraping_folder = "/media/ADN-784"
    db_session.commit()

    status = refresh_movie_status(db_session, movie)

    db_session.refresh(movie)
    assert status == "not_stored"
    assert movie.scraping_status is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest backend/tests/test_scraping_scan.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the scanner**

```python
# backend/app/modules/scraping/scan.py
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy.orm import Session

from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
from backend.app.modules.scraping.paths import (
    cloud_to_local,
    code_from_folder_name,
    local_to_cloud,
    normalize_code,
)
from shared.database.models.content import Movie

logger = logging.getLogger(__name__)

MAX_DEPTH = 8
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SCRAPED = "scraped"
NOT_SCRAPED = "not_scraped"
UNMATCHED_LIMIT = 50


@dataclass
class ScanSummary:
    folders_scanned: int = 0
    folders_with_strm: int = 0
    scraped_folders: int = 0
    not_scraped_folders: int = 0
    matched_movies: int = 0
    updated_movies: int = 0
    unmatched_folders: list[str] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "folders_scanned": self.folders_scanned,
            "folders_with_strm": self.folders_with_strm,
            "scraped_folders": self.scraped_folders,
            "not_scraped_folders": self.not_scraped_folders,
            "matched_movies": self.matched_movies,
            "updated_movies": self.updated_movies,
            "unmatched_folders": self.unmatched_folders,
            "duration_ms": self.duration_ms,
        }


def judge_folder(folder: Path) -> tuple[bool, bool, int]:
    folder = Path(folder)
    has_strm = False
    has_nfo = False
    image_count = 0
    try:
        for entry in os.scandir(folder):
            if not entry.is_file():
                continue
            name = entry.name.lower()
            if name.endswith(".strm"):
                has_strm = True
            elif name == "movie.nfo":
                has_nfo = True
            elif Path(name).suffix in IMAGE_EXTENSIONS:
                image_count += 1
    except OSError:
        logger.warning("Cannot read scraping folder: %s", folder, exc_info=True)
        return False, False, 0
    return has_strm, has_nfo, image_count


def _judged_folder(path: Path) -> tuple[Path, bool, bool, int]:
    has_strm, has_nfo, image_count = judge_folder(path)
    return path, has_strm, has_nfo, image_count


def iter_movie_folders(scrape_root: Path) -> Iterator[tuple[Path, bool, bool, int]]:
    root = Path(scrape_root)
    root_depth = len(root.parts)
    for current, dirnames, _filenames in os.walk(root, followlinks=False):
        depth = len(Path(current).parts) - root_depth
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        if depth >= MAX_DEPTH:
            dirnames[:] = []
        path, has_strm, has_nfo, image_count = _judged_folder(Path(current))
        if has_strm:
            yield path, has_strm, has_nfo, image_count


def _stored_movies(db: Session) -> list[Movie]:
    movies = db.query(Movie).all()
    return [movie for movie in movies if normalized_movie_storage_status(movie) == "stored"]


def movie_target_folders(movie: Movie) -> list[str]:
    summary = dict(movie.storage_summary or {})
    result: list[str] = []
    for location in summary.get("locations") or []:
        if not isinstance(location, dict):
            continue
        target = str(location.get("target_folder") or "").strip()
        if target and target not in result:
            result.append(target)
    return result


def _apply_judgement(
    movie: Movie,
    *,
    has_strm: bool,
    has_nfo: bool,
    image_count: int,
    cloud_folder: str | None,
    checked_at: datetime,
) -> str:
    scraped = has_strm and has_nfo and image_count > 0
    movie.scraping_status = SCRAPED if scraped else NOT_SCRAPED
    movie.scraping_folder = cloud_folder
    movie.scraping_checked_at = checked_at
    return movie.scraping_status


def _select_folder(candidates: list[str]) -> str | None:
    if not candidates:
        return None
    return sorted(candidates)[0]


def scan_directory(db: Session, config: dict[str, Any]) -> ScanSummary:
    started = datetime.now(timezone.utc)
    scrape_root = str(config.get("scrape_root") or "").strip()
    media_root = str(config.get("media_root") or "/media")
    summary = ScanSummary()

    if not scrape_root or not Path(scrape_root).is_dir():
        return summary

    candidates = list(iter_movie_folders(Path(scrape_root)))
    candidates.sort(key=lambda item: str(item[0]))
    summary.folders_scanned = len(candidates)
    summary.folders_with_strm = len(candidates)

    judgements: dict[str, tuple[bool, bool, int]] = {}
    for path, has_strm, has_nfo, image_count in candidates:
        key = str(path.resolve())
        judgements[key] = (has_strm, has_nfo, image_count)
        if has_strm and has_nfo and image_count > 0:
            summary.scraped_folders += 1
        else:
            summary.not_scraped_folders += 1

    stored = sorted(_stored_movies(db), key=lambda movie: str(movie.id))
    stored_by_code: dict[str, Movie] = {}
    for movie in stored:
        code = normalize_code(movie.code or "")
        if code:
            stored_by_code.setdefault(code, movie)

    assigned: dict[str, str] = {}
    assigned_movies: dict[str, str] = {}

    # Exact pass: each stored movie claims at most one existing candidate folder
    # derived from its storage locations. Deterministic: lexicographically first.
    for movie in stored:
        candidates_for_movie: list[str] = []
        for target in movie_target_folders(movie):
            local = cloud_to_local(scrape_root, media_root, target)
            if local is None:
                continue
            key = str(local.resolve())
            if key in judgements and key not in candidates_for_movie:
                candidates_for_movie.append(key)
        key = _select_folder(candidates_for_movie)
        if key is None or key in assigned:
            continue
        assigned[key] = str(movie.id)
        assigned_movies[str(movie.id)] = key

    # Fallback pass: folder-name codes, again deterministic by sorted walk.
    for path, _has_strm, _has_nfo, _image_count in candidates:
        key = str(path.resolve())
        if key in assigned:
            continue
        code = code_from_folder_name(path.name)
        if not code:
            continue
        movie = stored_by_code.get(normalize_code(code))
        if movie is None:
            continue
        movie_id = str(movie.id)
        if movie_id in assigned_movies:
            continue
        assigned[key] = movie_id
        assigned_movies[movie_id] = key

    movie_by_id = {str(movie.id): movie for movie in stored}
    checked_at = datetime.now(timezone.utc)
    updated = 0
    for movie_id, key in assigned_movies.items():
        movie = movie_by_id.get(movie_id)
        if movie is None:
            continue
        has_strm, has_nfo, image_count = judgements[key]
        cloud = local_to_cloud(scrape_root, media_root, key)
        _apply_judgement(
            movie,
            has_strm=has_strm,
            has_nfo=has_nfo,
            image_count=image_count,
            cloud_folder=cloud,
            checked_at=checked_at,
        )
        updated += 1

    for movie in stored:
        if str(movie.id) in assigned_movies:
            continue
        mapped = any(
            cloud_to_local(scrape_root, media_root, target) is not None
            for target in movie_target_folders(movie)
        )
        if mapped:
            movie.scraping_status = NOT_SCRAPED
            movie.scraping_folder = None
            movie.scraping_checked_at = checked_at
            updated += 1

    for movie in db.query(Movie).all():
        if normalized_movie_storage_status(movie) != "not_stored":
            continue
        if movie.scraping_status is not None or movie.scraping_folder is not None or movie.scraping_checked_at is not None:
            movie.scraping_status = None
            movie.scraping_folder = None
            movie.scraping_checked_at = None
            updated += 1

    for path, _has_strm, _has_nfo, _image_count in candidates:
        if str(path.resolve()) in assigned:
            continue
        if len(summary.unmatched_folders) < UNMATCHED_LIMIT:
            summary.unmatched_folders.append(str(path))

    db.commit()
    summary.matched_movies = len(assigned_movies)
    summary.updated_movies = updated
    summary.duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    return summary


def refresh_movie_status(
    db: Session,
    movie: Movie,
    *,
    local_folder: Path | None = None,
    cloud_folder: str | None = None,
) -> str:
    status = normalized_movie_storage_status(movie)
    if status == "storing":
        return status
    if status != "stored":
        movie.scraping_status = None
        movie.scraping_folder = None
        movie.scraping_checked_at = None
        db.commit()
        return "not_stored"

    config = _current_scan_config()
    scrape_root = str(config.get("scrape_root") or "")
    media_root = str(config.get("media_root") or "/media")

    folder = local_folder
    cloud = cloud_folder or ""
    mapped_targets = [
        target
        for target in movie_target_folders(movie)
        if cloud_to_local(scrape_root, media_root, target) is not None
    ]
    if folder is None:
        for target in mapped_targets:
            candidate = cloud_to_local(scrape_root, media_root, target)
            if candidate is not None and candidate.is_dir():
                folder = candidate
                cloud = target
                break

    if folder is None:
        if mapped_targets:
            movie.scraping_status = NOT_SCRAPED
            movie.scraping_folder = None
            movie.scraping_checked_at = datetime.now(timezone.utc)
            db.commit()
        return "not_scraped"

    has_strm, has_nfo, image_count = judge_folder(folder)
    cloud = cloud or local_to_cloud(scrape_root, media_root, folder) or ""
    status = _apply_judgement(
        movie,
        has_strm=has_strm,
        has_nfo=has_nfo,
        image_count=image_count,
        cloud_folder=cloud or None,
        checked_at=datetime.now(timezone.utc),
    )
    db.commit()
    return status


def _current_scan_config() -> dict[str, Any]:
    from backend.app.modules.scraping.config import ScrapingConfigService

    return ScrapingConfigService().get_raw_config()


def schedule_scan_after_strm(config: dict[str, Any]) -> None:
    if not str(config.get("scrape_root") or "").strip():
        return

    def _run() -> None:
        try:
            from shared.database.session import get_session_factory

            factory = get_session_factory()
            with factory() as session:
                scan_directory(session, config)
        except Exception:
            logger.warning("Background scraping scan failed", exc_info=True)

    threading.Thread(target=_run, daemon=True, name="scraping-scan").start()
```

- [ ] **Step 4: Run the scan tests**

Run: `python -m pytest backend/tests/test_scraping_scan.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/scraping/scan.py backend/tests/test_scraping_scan.py
git commit -m "feat(scraping): scan media folders and persist scraping status"
```

---

## Task 9: Scan API and post-STRM refresh hook

**Files:**
- Modify: `backend/app/modules/scraping/router.py`
- Modify: `backend/app/modules/scraping/trigger.py`
- Create: `backend/tests/test_scraping_scan_api.py`
- Test: `backend/tests/test_scraping_strm_trigger.py`

**Interfaces:**
- Produces: `POST /api/scraping/scan` returning `ScanSummary.to_dict()`; trigger calls `schedule_scan_after_strm(config)` after a successful STRM request.

- [ ] **Step 1: Write the failing API test**

```python
# backend/tests/test_scraping_scan_api.py
from http import HTTPStatus

from backend.app.modules.scraping.scan import ScanSummary


def _auth_headers(client) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_scan_requires_scrape_root(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    headers = _auth_headers(client)

    response = client.post("/api/scraping/scan", headers=headers)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "刮削目录" in response.json()["detail"]


def test_scan_returns_summary(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    headers = _auth_headers(client)
    client.put("/api/scraping/config", headers=headers, json={"scrape_root": str(tmp_path), "media_root": "/media"})

    monkeypatch.setattr(
        "backend.app.modules.scraping.router.scan_directory",
        lambda db, config: ScanSummary(folders_scanned=3, folders_with_strm=1, scraped_folders=1, updated_movies=1),
    )

    response = client.post("/api/scraping/scan", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["scraped_folders"] == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest backend/tests/test_scraping_scan_api.py -v`
Expected: FAIL with 404 (route missing).

- [ ] **Step 3: Add the scan endpoint**

In `backend/app/modules/scraping/router.py`, add imports:

```python
from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_db
from backend.app.modules.scraping.config import validate_scrape_root
from backend.app.modules.scraping.scan import scan_directory
```

and the endpoint:

```python
@router.post("/scan")
def scan_scraping_directory(
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    config = ScrapingConfigService().get_raw_config()
    reason = validate_scrape_root(config)
    if reason is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
    return success(data=scan_directory(db, config).to_dict())
```

- [ ] **Step 4: Run the API tests**

Run: `python -m pytest backend/tests/test_scraping_scan_api.py -v`
Expected: PASS.

- [ ] **Step 4b: Schedule a scan after a successful manual STRM run**

The spec requires a refresh after the external STRM request succeeds on the
automatic **and manual** paths. The manual path lives in the same router, so
change `run_scraping_strm` to keep the result and schedule a scan on success:

```python
@router.post("/strm/run")
def run_scraping_strm(_current_user: CurrentUser) -> dict:
    config = ScrapingConfigService().get_raw_config()
    reason = validate_run_config(config)
    if reason is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
    result = run_strm_generation(config)
    if result.success:
        schedule_scan_after_strm(config)
    return success(data=asdict(result))
```

Add the import to the Step 3 import block:

```python
from backend.app.modules.scraping.scan import scan_directory, schedule_scan_after_strm
```

Then add this API test to `backend/tests/test_scraping_api.py`:

```python
def test_manual_strm_run_schedules_a_scan_on_success(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    _write_config(tmp_path)
    headers = _auth_headers(client, admin_user)
    scheduled: list[dict] = []

    monkeypatch.setattr(
        "backend.app.modules.scraping.router.run_strm_generation",
        lambda config: StrmRunResult(success=True, status_code=200, message="HTTP 200"),
    )
    monkeypatch.setattr(
        "backend.app.modules.scraping.router.schedule_scan_after_strm",
        lambda config: scheduled.append(config),
    )

    response = client.post("/api/scraping/strm/run", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert scheduled


def test_manual_strm_run_does_not_schedule_a_scan_on_failure(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    _write_config(tmp_path)
    headers = _auth_headers(client, admin_user)
    scheduled: list[dict] = []

    monkeypatch.setattr(
        "backend.app.modules.scraping.router.run_strm_generation",
        lambda config: StrmRunResult(success=False, status_code=500, message="HTTP 500"),
    )
    monkeypatch.setattr(
        "backend.app.modules.scraping.router.schedule_scan_after_strm",
        lambda config: scheduled.append(config),
    )

    response = client.post("/api/scraping/strm/run", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert scheduled == []
```

- [ ] **Step 5: Add the trigger hook test**

In `backend/tests/test_scraping_strm_trigger.py`, add:

```python
def test_successful_strm_generation_schedules_scan(monkeypatch) -> None:
    from backend.app.modules.scraping import trigger

    scheduled: list[dict] = []
    monkeypatch.setattr(
        "backend.app.modules.scraping.trigger.run_strm_generation",
        lambda config: type("R", (), {"success": True, "message": "ok"})(),
    )
    monkeypatch.setattr(
        "backend.app.modules.scraping.trigger.schedule_scan_after_strm",
        lambda config: scheduled.append(config),
    )
    monkeypatch.setattr(
        "backend.app.modules.scraping.trigger.ScrapingConfigService",
        lambda: type("S", (), {"get_raw_config": staticmethod(lambda: {"metadata_sources": ["javdb"]})})(),
    )
    monkeypatch.setattr(
        "backend.app.modules.scraping.trigger.validate_run_config",
        lambda config: None,
    )

    trigger._run_after_delay(
        generation=trigger._next_generation(),
        delay_seconds=0,
        runtime=type("Runtime", (), {"pending_main_task_count": lambda self: 0})(),
        is_worker_idle=lambda: True,
    )

    assert scheduled
```

If the existing test module already monkeypatches the config service and idle checks, match its fixtures; the assertion above must hold after the hook is added.

- [ ] **Step 6: Run the trigger test**

Run: `python -m pytest backend/tests/test_scraping_strm_trigger.py -v`
Expected: FAIL (hook missing).

- [ ] **Step 7: Wire the hook into the trigger**

In `backend/app/modules/scraping/trigger.py`, import:

```python
from backend.app.modules.scraping.scan import schedule_scan_after_strm
```

and after the successful branch:

```python
        result = run_strm_generation(config)
        if result.success:
            logger.info("STRM generation triggered: %s", result.message)
            schedule_scan_after_strm(config)
        else:
            logger.warning("STRM generation failed: %s", result.message)
```

- [ ] **Step 8: Run the trigger and scan API tests**

Run: `python -m pytest backend/tests/test_scraping_strm_trigger.py backend/tests/test_scraping_scan_api.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/scraping/router.py backend/app/modules/scraping/trigger.py backend/tests/test_scraping_scan_api.py backend/tests/test_scraping_strm_trigger.py
git commit -m "feat(scraping): expose directory scan and refresh after STRM"
```

---

## Task 10: Scraping task service and repository

**Files:**
- Create: `backend/app/modules/scraping/tasks/__init__.py`
- Create: `backend/app/modules/scraping/tasks/schemas.py`
- Create: `backend/app/modules/scraping/tasks/repository.py`
- Create: `backend/app/modules/scraping/tasks/serializers.py`
- Create: `backend/app/modules/scraping/tasks/service.py`
- Test: `backend/tests/test_scraping_task_service.py`

**Interfaces:**
- Produces: `ScrapingTaskCreate` pydantic schema; `ScrapingTaskRepository`; `ScrapingTaskService(db)` with `create_task(movie_ids, user_id)`, `list_tasks`, `count_tasks`, `get_task(task_id, user_id)`, `cancel_task(task_id, user_id)`, `retry_task(task_id, user_id)`; `task_to_dict(task)`, `item_to_dict(item)`.

- [ ] **Step 1: Write the failing service tests**

```python
# backend/tests/test_scraping_task_service.py
import uuid

import pytest

from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem
from backend.app.modules.scraping.tasks.service import ScrapingTaskService
from shared.database.models.content import Movie


def _movie(db, code: str, *, stored: bool = True) -> Movie:
    summary = {"storage_status": "stored" if stored else "not_stored", "locations": []}
    movie = Movie(code=code, source_name=code, storage_summary=summary)
    db.add(movie)
    db.commit()
    db.refresh(movie)
    return movie


def _config() -> dict:
    return {"scrape_root": "/tmp/media", "media_root": "/media", "metadata_sources": ["javdb", "javbus"]}


def test_create_task_dedupes_movies_and_starts_queued(db_session, admin_user) -> None:
    movie = _movie(db_session, "ADN-784")
    service = ScrapingTaskService(db_session)

    task = service.create_task([movie.id, movie.id], admin_user.id, config=_config())

    assert task.status == "queued"
    assert task.total_count == 1
    assert task.created_by == admin_user.id
    assert task.config_snapshot["metadata_sources"] == ["javdb", "javbus"]
    items = db_session.query(ScrapingTaskItem).filter_by(task_id=task.id).all()
    assert [item.status for item in items] == ["pending"]


def test_create_task_rejects_unknown_movie(db_session, admin_user) -> None:
    service = ScrapingTaskService(db_session)
    with pytest.raises(ValueError, match="电影不存在"):
        service.create_task([uuid.uuid4()], admin_user.id, config=_config())


def test_create_task_rejects_empty_and_oversized_lists(db_session, admin_user) -> None:
    service = ScrapingTaskService(db_session)
    with pytest.raises(ValueError, match="至少选择"):
        service.create_task([], admin_user.id, config=_config())

    movie = _movie(db_session, "ADN-784")
    with pytest.raises(ValueError, match="最多"):
        service.create_task([movie.id] * 501, admin_user.id, config=_config())


def test_cancel_queued_task_marks_pending_items_skipped(db_session, admin_user) -> None:
    movie = _movie(db_session, "ADN-784")
    service = ScrapingTaskService(db_session)
    task = service.create_task([movie.id], admin_user.id, config=_config())

    cancelled = service.cancel_task(task.id, admin_user.id)

    assert cancelled.status == "cancelled"
    item = db_session.query(ScrapingTaskItem).filter_by(task_id=task.id).one()
    assert item.status == "skipped"
    assert item.error_message == "任务已取消"


def test_retry_creates_a_task_from_failed_and_skipped_items(db_session, admin_user) -> None:
    movie = _movie(db_session, "ADN-784")
    service = ScrapingTaskService(db_session)
    task = service.create_task([movie.id], admin_user.id, config=_config())
    item = db_session.query(ScrapingTaskItem).filter_by(task_id=task.id).one()
    item.status = "failed"
    task.status = "failed"
    task.finished_at = None
    db_session.commit()

    retried = service.retry_task(task.id, admin_user.id, config=_config())

    assert retried.id != task.id
    assert retried.status == "queued"
    assert retried.total_count == 1


def test_get_task_is_owner_scoped(db_session, admin_user) -> None:
    movie = _movie(db_session, "ADN-784")
    service = ScrapingTaskService(db_session)
    task = service.create_task([movie.id], admin_user.id, config=_config())

    with pytest.raises(LookupError):
        service.get_task(task.id, uuid.uuid4())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest backend/tests/test_scraping_task_service.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement schemas, repository, serializers, service**

```python
# backend/app/modules/scraping/tasks/__init__.py
```

```python
# backend/app/modules/scraping/tasks/schemas.py
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ScrapingTaskCreate(BaseModel):
    movie_ids: list[UUID] = Field(min_length=1, max_length=500)
```

```python
# backend/app/modules/scraping/tasks/repository.py
from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session, noload

from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem


class ScrapingTaskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_task(self, task_id: uuid.UUID) -> ScrapingTask | None:
        return self.db.get(ScrapingTask, task_id)

    def get_item(self, item_id: uuid.UUID) -> ScrapingTaskItem | None:
        return self.db.get(ScrapingTaskItem, item_id)

    def list_items(self, task_id: uuid.UUID) -> list[ScrapingTaskItem]:
        return list(
            self.db.query(ScrapingTaskItem)
            .filter(ScrapingTaskItem.task_id == task_id)
            .order_by(ScrapingTaskItem.created_at.asc())
            .all()
        )

    def pending_items(self, task_id: uuid.UUID) -> list[ScrapingTaskItem]:
        return list(
            self.db.query(ScrapingTaskItem)
            .filter(ScrapingTaskItem.task_id == task_id, ScrapingTaskItem.status == "pending")
            .order_by(ScrapingTaskItem.created_at.asc())
            .all()
        )

    def _task_query(self, *, created_by: uuid.UUID, status: str | None):
        query = (
            self.db.query(ScrapingTask)
            .options(noload(ScrapingTask.items))
            .filter(ScrapingTask.created_by == created_by)
        )
        if status:
            query = query.filter(ScrapingTask.status == status)
        return query

    def list_tasks(self, *, created_by: uuid.UUID, page: int, size: int, status: str | None) -> list[ScrapingTask]:
        return list(
            self._task_query(created_by=created_by, status=status)
            .order_by(ScrapingTask.created_at.desc(), ScrapingTask.id.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

    def count_tasks(self, *, created_by: uuid.UUID, status: str | None) -> int:
        return int(
            self._task_query(created_by=created_by, status=status)
            .with_entities(func.count(ScrapingTask.id))
            .scalar()
            or 0
        )

    def recompute_counts(self, task: ScrapingTask) -> None:
        items = list(task.items or [])
        task.total_count = len(items)
        task.success_count = sum(1 for item in items if item.status == "success")
        task.failed_count = sum(1 for item in items if item.status == "failed")
        task.skipped_count = sum(1 for item in items if item.status == "skipped")
```

```python
# backend/app/modules/scraping/tasks/serializers.py
from __future__ import annotations

from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem


def task_to_dict(task: ScrapingTask) -> dict:
    return {
        "id": str(task.id),
        "status": task.status,
        "total_count": task.total_count,
        "success_count": task.success_count,
        "failed_count": task.failed_count,
        "skipped_count": task.skipped_count,
        "cancel_requested": bool(task.cancel_requested),
        "created_by": str(task.created_by),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "queued_at": task.queued_at.isoformat() if task.queued_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "error_message": task.error_message,
    }


def item_to_dict(item: ScrapingTaskItem) -> dict:
    return {
        "id": str(item.id),
        "task_id": str(item.task_id),
        "movie_id": str(item.movie_id),
        "movie_code": item.movie_code,
        "movie_title": item.movie_title,
        "status": item.status,
        "source": item.source,
        "folder": item.folder,
        "duration_ms": item.duration_ms,
        "error_message": item.error_message,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
```

```python
# backend/app/modules/scraping/tasks/service.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem
from backend.app.modules.scraping.tasks.repository import ScrapingTaskRepository
from shared.database.models.content import Movie

MAX_TASK_ITEMS = 500
TERMINAL_STATUSES = {"success", "partial_failed", "failed", "cancelled"}


class ScrapingTaskService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = ScrapingTaskRepository(db)

    def create_task(
        self,
        movie_ids: list[uuid.UUID],
        user_id: uuid.UUID,
        *,
        config: dict,
    ) -> ScrapingTask:
        deduped: list[uuid.UUID] = []
        for movie_id in movie_ids:
            if movie_id not in deduped:
                deduped.append(movie_id)
        if not deduped:
            raise ValueError("至少选择一部电影")
        if len(deduped) > MAX_TASK_ITEMS:
            raise ValueError(f"单个任务最多 {MAX_TASK_ITEMS} 部电影")

        movies = self.db.query(Movie).filter(Movie.id.in_(deduped)).all()
        by_id = {movie.id: movie for movie in movies}
        missing = [str(movie_id) for movie_id in deduped if movie_id not in by_id]
        if missing:
            raise ValueError(f"电影不存在: {', '.join(missing)}")

        now = datetime.now(timezone.utc)
        task = ScrapingTask(
            status="queued",
            total_count=len(deduped),
            created_by=user_id,
            queued_at=now,
            config_snapshot={
                "scrape_root": config.get("scrape_root", ""),
                "media_root": config.get("media_root", "/media"),
                "metadata_sources": list(config.get("metadata_sources") or []),
            },
        )
        self.db.add(task)
        self.db.flush()
        for movie_id in deduped:
            movie = by_id[movie_id]
            self.db.add(ScrapingTaskItem(
                task_id=task.id,
                movie_id=movie.id,
                movie_code=movie.code or "",
                movie_title=movie.source_name or "",
                status="pending",
            ))
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_task(self, task_id: uuid.UUID, user_id: uuid.UUID) -> ScrapingTask:
        task = self.repository.get_task(task_id)
        if task is None or task.created_by != user_id:
            raise LookupError("任务不存在")
        return task

    def list_tasks(self, *, user_id: uuid.UUID, page: int, size: int, status: str | None) -> list[ScrapingTask]:
        return self.repository.list_tasks(created_by=user_id, page=page, size=size, status=status)

    def count_tasks(self, *, user_id: uuid.UUID, status: str | None) -> int:
        return self.repository.count_tasks(created_by=user_id, status=status)

    def cancel_task(self, task_id: uuid.UUID, user_id: uuid.UUID) -> ScrapingTask:
        task = self.get_task(task_id, user_id)
        if task.status in TERMINAL_STATUSES:
            raise ValueError("当前状态不能取消")
        task.cancel_requested = True
        if task.status == "queued":
            for item in self.repository.pending_items(task.id):
                item.status = "skipped"
                item.error_message = "任务已取消"
            task.status = "cancelled"
            task.finished_at = datetime.now(timezone.utc)
            self.repository.recompute_counts(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def retry_task(self, task_id: uuid.UUID, user_id: uuid.UUID, *, config: dict) -> ScrapingTask:
        task = self.get_task(task_id, user_id)
        if task.status not in {"failed", "partial_failed", "cancelled"}:
            raise ValueError("只有失败、部分失败或已取消的任务可以重试")
        movie_ids = [
            item.movie_id
            for item in self.repository.list_items(task.id)
            if item.status in {"failed", "skipped"}
        ]
        if not movie_ids:
            raise ValueError("没有可重试的电影")
        return self.create_task(movie_ids, user_id, config=config)
```

- [ ] **Step 4: Run the service tests**

Run: `python -m pytest backend/tests/test_scraping_task_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/scraping/tasks/__init__.py backend/app/modules/scraping/tasks/schemas.py backend/app/modules/scraping/tasks/repository.py backend/app/modules/scraping/tasks/serializers.py backend/app/modules/scraping/tasks/service.py backend/tests/test_scraping_task_service.py
git commit -m "feat(scraping): add scraping task service and repository"
```

---

## Task 11: Task worker, item pipeline, events, startup cleanup

**Files:**
- Create: `backend/app/modules/scraping/tasks/events.py`
- Create: `backend/app/modules/scraping/tasks/item_runner.py`
- Create: `backend/app/modules/scraping/tasks/worker.py`
- Test: `backend/tests/test_scraping_task_worker.py`

**Interfaces:**
- Produces: `run_item(db, item, *, config, adapters=None, transport=None) -> None`; `run_task(task_id: uuid.UUID) -> None`; `ensure_scraping_worker_started() -> None`; `cleanup_interrupted_scraping_tasks(db) -> int`; `publish_scraping_task_updated(task)`, `publish_scraping_item_updated(owner_id, item)`, `publish_movie_scraping_updated(owner_id, movie_id)`.

- [ ] **Step 1: Write the failing worker tests**

```python
# backend/tests/test_scraping_task_worker.py
from datetime import datetime, timezone

from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem
from shared.database.models.content import Movie


def _seed_task(db, admin_user, status="queued"):
    movie = Movie(code="ADN-784", source_name="ADN-784", storage_summary={"storage_status": "stored", "locations": []})
    db.add(movie)
    db.flush()
    task = ScrapingTask(status=status, total_count=1, created_by=admin_user.id, queued_at=datetime.now(timezone.utc))
    db.add(task)
    db.flush()
    item = ScrapingTaskItem(task_id=task.id, movie_id=movie.id, movie_code="ADN-784", movie_title="ADN-784", status="pending")
    db.add(item)
    db.commit()
    return task, item


def test_run_task_success_transitions(db_session, admin_user, monkeypatch) -> None:
    task, item = _seed_task(db_session, admin_user)
    task_id = task.id

    def fake_run_item(db, item, *, config, **kwargs):
        item.status = "success"
        item.source = "javbus"
        item.duration_ms = 10

    monkeypatch.setattr("backend.app.modules.scraping.tasks.worker.run_item", fake_run_item)
    monkeypatch.setattr(worker, "_open_session", lambda: db_session)
    monkeypatch.setattr(worker, "get_scraping_config", lambda: {"metadata_sources": ["javdb", "javbus"]})
    monkeypatch.setattr(worker, "publish_scraping_task_updated", lambda task: None)
    monkeypatch.setattr(worker, "publish_scraping_item_updated", lambda owner_id, item: None)
    published: list[tuple] = []
    monkeypatch.setattr(worker, "publish_movie_scraping_updated", lambda *args: published.append(args))

    worker.run_task(task_id)

    db_session.expire_all()
    stored = db_session.get(ScrapingTask, task_id)
    assert stored.status == "success"
    assert stored.success_count == 1
    assert stored.finished_at is not None
    assert published and published[0][0] == str(admin_user.id)


def test_run_task_partial_failure_and_skips(db_session, admin_user, monkeypatch) -> None:
    task, _item = _seed_task(db_session, admin_user)
    task_id = task.id

    def fake_run_item(db, item, *, config, **kwargs):
        item.status = "failed"
        item.error_message = "boom"

    monkeypatch.setattr("backend.app.modules.scraping.tasks.worker.run_item", fake_run_item)
    monkeypatch.setattr(worker, "_open_session", lambda: db_session)
    monkeypatch.setattr(worker, "get_scraping_config", lambda: {"metadata_sources": ["javdb"]})
    monkeypatch.setattr(worker, "publish_scraping_task_updated", lambda task: None)
    monkeypatch.setattr(worker, "publish_scraping_item_updated", lambda owner_id, item: None)

    worker.run_task(task_id)

    db_session.expire_all()
    stored = db_session.get(ScrapingTask, task_id)
    assert stored.status == "failed"
    assert stored.failed_count == 1


def test_cancel_between_items_marks_pending_skipped(db_session, admin_user, monkeypatch) -> None:
    task, first = _seed_task(db_session, admin_user)
    extra = Movie(code="BBB-001", source_name="BBB-001", storage_summary={"storage_status": "stored", "locations": []})
    db_session.add(extra)
    db_session.flush()
    second = ScrapingTaskItem(task_id=task.id, movie_id=extra.id, movie_code="BBB-001", movie_title="BBB-001", status="pending")
    db_session.add(second)
    task.total_count = 2
    db_session.commit()
    task_id = task.id

    def fake_run_item(db, item, *, config, **kwargs):
        item.status = "success"
        task_row = db.get(ScrapingTask, task_id)
        task_row.cancel_requested = True
        db.commit()

    monkeypatch.setattr("backend.app.modules.scraping.tasks.worker.run_item", fake_run_item)
    monkeypatch.setattr(worker, "_open_session", lambda: db_session)
    monkeypatch.setattr(worker, "get_scraping_config", lambda: {"metadata_sources": ["javdb"]})
    monkeypatch.setattr(worker, "publish_scraping_task_updated", lambda task: None)
    monkeypatch.setattr(worker, "publish_scraping_item_updated", lambda owner_id, item: None)

    worker.run_task(task_id)

    db_session.expire_all()
    stored = db_session.get(ScrapingTask, task_id)
    assert stored.status == "cancelled"
    remaining = db_session.query(ScrapingTaskItem).filter_by(task_id=task_id, status="skipped").count()
    assert remaining == 1


def test_cleanup_marks_running_tasks_failed(db_session, admin_user) -> None:
    task, _item = _seed_task(db_session, admin_user, status="running")

    stopped = worker.cleanup_interrupted_scraping_tasks(db_session)

    db_session.expire_all()
    stored = db_session.get(ScrapingTask, task.id)
    assert stopped == 1
    assert stored.status == "failed"
    assert stored.error_message == "任务中断，需重试"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest backend/tests/test_scraping_task_worker.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement events**

```python
# backend/app/modules/scraping/tasks/events.py
from __future__ import annotations

from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem
from backend.app.modules.realtime.bus import event_bus
from backend.app.modules.realtime.schemas import make_realtime_event


def publish_scraping_task_updated(task: ScrapingTask) -> None:
    event_bus.publish(make_realtime_event(
        event="scraping.task.updated",
        scope="scraping.task",
        owner_id=str(task.created_by),
        resource_id=str(task.id),
        payload={
            "id": str(task.id),
            "status": task.status,
            "total_count": task.total_count,
            "success_count": task.success_count,
            "failed_count": task.failed_count,
            "skipped_count": task.skipped_count,
        },
    ))


def publish_scraping_item_updated(owner_id: str, item: ScrapingTaskItem) -> None:
    event_bus.publish(make_realtime_event(
        event="scraping.item.updated",
        scope="scraping.task",
        owner_id=str(owner_id),
        resource_id=str(item.id),
        payload={
            "id": str(item.id),
            "task_id": str(item.task_id),
            "status": item.status,
            "source": item.source,
            "error_message": item.error_message,
        },
    ))


def publish_movie_scraping_updated(owner_id: str, movie_id: str, status: str | None, checked_at: str | None) -> None:
    event_bus.publish(make_realtime_event(
        event="movie.scraping.updated",
        scope="movie",
        owner_id=str(owner_id),
        resource_id=str(movie_id),
        payload={"movie_id": str(movie_id), "scraping_status": status, "scraping_checked_at": checked_at},
    ))
```

- [ ] **Step 4: Implement the item runner**

```python
# backend/app/modules/scraping/tasks/item_runner.py
from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.models.scraping_task import ScrapingTaskItem
from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
from backend.app.modules.scraping.images import write_artwork
from backend.app.modules.scraping.nfo import write_movie_nfo
from backend.app.modules.scraping.paths import cloud_to_local
from backend.app.modules.scraping.scan import movie_target_folders, refresh_movie_status
from backend.app.modules.scraping.sources import fetch_by_priority
from shared.database.models.content import Movie


def _resolve_folder(movie: Movie, config: dict) -> tuple[Path | None, str]:
    scrape_root = str(config.get("scrape_root") or "")
    media_root = str(config.get("media_root") or "/media")
    for target in movie_target_folders(movie):
        local = cloud_to_local(scrape_root, media_root, target)
        if local is not None and local.is_dir():
            return local, target
    return None, ""


def run_item(
    db: Session,
    item: ScrapingTaskItem,
    *,
    config: dict,
    transport=None,
) -> None:
    started = time.monotonic()
    movie = db.get(Movie, item.movie_id)
    if movie is None:
        item.status = "failed"
        item.error_message = "电影不存在"
        return
    if normalized_movie_storage_status(movie) != "stored":
        item.status = "skipped"
        item.error_message = "未存储"
        return

    folder, cloud_folder = _resolve_folder(movie, config)
    if folder is None:
        item.status = "skipped"
        item.error_message = "目标文件夹不存在"
        return

    metadata = None
    missing = not (movie.cover and movie.actors and movie.release_date and movie.maker and movie.series)
    if missing:
        metadata = fetch_by_priority(movie.code or "", list(config.get("metadata_sources") or []))
        if metadata is not None:
            item.source = metadata.site_key.lower()
            if not movie.cover and metadata.cover_url:
                movie.cover = metadata.cover_url

    if not movie.cover:
        item.status = "failed"
        item.error_message = "缺少封面，无法生成图片"
        return

    write_movie_nfo(
        folder,
        movie,
        cloud_folder=cloud_folder,
        source_site=metadata.site_key if metadata is not None else None,
    )
    written = write_artwork(
        folder,
        cover_url=movie.cover,
        backdrop_url=metadata.backdrop_url if metadata is not None else None,
        landscape_url=metadata.landscape_url if metadata is not None else None,
        transport=transport,
    )
    if written == 0:
        item.status = "failed"
        item.error_message = "图片下载失败"
        return

    refresh_movie_status(db, movie, local_folder=folder, cloud_folder=cloud_folder)
    item.status = "success"
    item.folder = cloud_folder
    item.duration_ms = int((time.monotonic() - started) * 1000)
```

Note: `item.source` should be the source key; when no crawl was needed it stays `""`.

- [ ] **Step 5: Implement the worker**

```python
# backend/app/modules/scraping/tasks/worker.py
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone

from backend.app.models.scraping_task import ScrapingTask
from backend.app.modules.scraping.tasks.events import (
    publish_movie_scraping_updated,
    publish_scraping_item_updated,
    publish_scraping_task_updated,
)
from backend.app.modules.scraping.tasks.item_runner import run_item
from shared.database.models.content import Movie

logger = logging.getLogger(__name__)

_worker_lock = threading.Lock()
_worker_running = False


def get_scraping_config() -> dict:
    from backend.app.modules.scraping.config import ScrapingConfigService

    return ScrapingConfigService().get_raw_config()


def _open_session():
    from shared.database.session import get_session_factory

    return get_session_factory()()


def ensure_scraping_worker_started() -> None:
    global _worker_running
    with _worker_lock:
        if _worker_running:
            return
        _worker_running = True
    threading.Thread(target=_worker_loop, daemon=True, name="scraping-worker").start()


def _worker_loop() -> None:
    global _worker_running
    try:
        while True:
            db = _open_session()
            try:
                task = _claim_next_task(db)
            except Exception:
                logger.exception("Failed to claim a scraping task")
                task = None
            finally:
                db.close()
            if task is None:
                break
            try:
                run_task(task.id)
            except Exception:
                logger.exception("Scraping task failed: %s", task)
    finally:
        with _worker_lock:
            _worker_running = False


def _claim_next_task(db) -> ScrapingTask | None:
    task = (
        db.query(ScrapingTask)
        .filter(ScrapingTask.status == "queued")
        .order_by(ScrapingTask.created_at.asc(), ScrapingTask.id.asc())
        .first()
    )
    if task is None:
        return None
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return task


def run_task(task_id: uuid.UUID) -> None:
    db = _open_session()
    try:
        task = db.get(ScrapingTask, task_id)
        if task is None:
            return
        task.status = "running"
        if task.started_at is None:
            task.started_at = datetime.now(timezone.utc)
        db.commit()
        publish_scraping_task_updated(task)
        config = dict(task.config_snapshot or {}) or get_scraping_config()

        items = [item for item in task.items if item.status == "pending"]
        cancelled = False
        for item in items:
            db.refresh(task)
            if task.cancel_requested:
                cancelled = True
                break
            item.status = "running"
            db.commit()
            try:
                run_item(db, item, config=config)
            except Exception as exc:
                item.status = "failed"
                item.error_message = f"{type(exc).__name__}: {exc}"
            db.commit()
            _recompute(task, db)
            publish_scraping_item_updated(str(task.created_by), item)
            if item.status == "success" and item.movie_id is not None:
                movie = db.get(Movie, item.movie_id)
                if movie is not None:
                    publish_movie_scraping_updated(
                        str(task.created_by),
                        str(movie.id),
                        movie.scraping_status,
                        movie.scraping_checked_at.isoformat() if movie.scraping_checked_at else None,
                    )

        _recompute(task, db)
        if cancelled:
            for item in task.items:
                if item.status in {"pending", "running"}:
                    item.status = "skipped"
                    item.error_message = "任务已取消"
            task.status = "cancelled"
        elif task.success_count > 0 and task.failed_count + task.skipped_count > 0:
            task.status = "partial_failed"
        elif task.success_count > 0:
            task.status = "success"
        elif task.failed_count + task.skipped_count > 0:
            task.status = "failed"
        else:
            task.status = "failed"
            task.error_message = "没有可刮削的电影"
        task.finished_at = datetime.now(timezone.utc)
        db.commit()
        publish_scraping_task_updated(task)
    finally:
        db.close()


def _recompute(task: ScrapingTask, db) -> None:
    db.flush()
    items = list(task.items)
    task.total_count = len(items)
    task.success_count = sum(1 for item in items if item.status == "success")
    task.failed_count = sum(1 for item in items if item.status == "failed")
    task.skipped_count = sum(1 for item in items if item.status == "skipped")
    db.commit()


def cleanup_interrupted_scraping_tasks(db) -> int:
    rows = db.query(ScrapingTask).filter(ScrapingTask.status == "running").all()
    now = datetime.now(timezone.utc)
    for task in rows:
        task.status = "failed"
        task.finished_at = now
        task.error_message = "任务中断，需重试"
        for item in task.items:
            if item.status in {"pending", "running"}:
                item.status = "skipped"
                item.error_message = "任务中断，需重试"
    if rows:
        db.commit()
    return len(rows)
```

- [ ] **Step 6: Run the worker tests**

Run: `python -m pytest backend/tests/test_scraping_task_worker.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/scraping/tasks/events.py backend/app/modules/scraping/tasks/item_runner.py backend/app/modules/scraping/tasks/worker.py backend/tests/test_scraping_task_worker.py
git commit -m "feat(scraping): run scraping tasks in a background worker"
```

---

## Task 12: Scraping task API, worker start, and startup cleanup

**Files:**
- Modify: `backend/app/modules/scraping/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_scraping_tasks_api.py`

**Interfaces:**
- Produces: `POST /api/scraping/tasks`, `GET /api/scraping/tasks`, `GET /api/scraping/tasks/{id}`, `POST /api/scraping/tasks/{id}/cancel`, `POST /api/scraping/tasks/{id}/retry`.

- [ ] **Step 1: Write the failing API tests**

```python
# backend/tests/test_scraping_tasks_api.py
from http import HTTPStatus

from shared.database.models.content import Movie


def _auth_headers(client) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _movie(db, code="ADN-784") -> Movie:
    movie = Movie(code=code, source_name=code, storage_summary={"storage_status": "stored", "locations": []})
    db.add(movie)
    db.commit()
    db.refresh(movie)
    return movie


def test_create_and_list_scraping_tasks(client, admin_user, db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.modules.scraping.router.ensure_scraping_worker_started", lambda: None)
    headers = _auth_headers(client)
    movie = _movie(db_session)

    created = client.post("/api/scraping/tasks", headers=headers, json={"movie_ids": [str(movie.id)]})

    assert created.status_code == HTTPStatus.OK
    task = created.json()["data"]
    assert task["status"] == "queued"
    assert task["total_count"] == 1

    listed = client.get("/api/scraping/tasks", headers=headers)

    assert listed.status_code == HTTPStatus.OK
    assert listed.json()["data"]["total"] == 1

    detail = client.get(f"/api/scraping/tasks/{task['id']}", headers=headers)

    assert detail.status_code == HTTPStatus.OK
    assert len(detail.json()["data"]["items"]) == 1


def test_create_rejects_empty_and_unknown_movies(client, admin_user, db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.modules.scraping.router.ensure_scraping_worker_started", lambda: None)
    headers = _auth_headers(client)

    empty = client.post("/api/scraping/tasks", headers=headers, json={"movie_ids": []})

    assert empty.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    unknown = client.post("/api/scraping/tasks", headers=headers, json={"movie_ids": ["00000000-0000-0000-0000-000000000000"]})

    assert unknown.status_code == HTTPStatus.BAD_REQUEST


def test_cancel_and_retry_endpoints(client, admin_user, db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.modules.scraping.router.ensure_scraping_worker_started", lambda: None)
    headers = _auth_headers(client)
    movie = _movie(db_session)
    task = client.post("/api/scraping/tasks", headers=headers, json={"movie_ids": [str(movie.id)]}).json()["data"]

    cancelled = client.post(f"/api/scraping/tasks/{task['id']}/cancel", headers=headers)

    assert cancelled.status_code == HTTPStatus.OK
    assert cancelled.json()["data"]["status"] == "cancelled"

    retried = client.post(f"/api/scraping/tasks/{task['id']}/retry", headers=headers)

    assert retried.status_code == HTTPStatus.OK
    assert retried.json()["data"]["id"] != task["id"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest backend/tests/test_scraping_tasks_api.py -v`
Expected: FAIL with 404 (routes missing).

- [ ] **Step 3: Add the task endpoints**

In `backend/app/modules/scraping/router.py`, add imports:

```python
from backend.app.modules.scraping.tasks.schemas import ScrapingTaskCreate
from backend.app.modules.scraping.tasks.serializers import item_to_dict, task_to_dict
from backend.app.modules.scraping.tasks.service import ScrapingTaskService
from backend.app.modules.scraping.tasks.worker import ensure_scraping_worker_started
from shared.schemas.common import success as success_response
```

and the endpoints after the scan endpoint:

```python
@router.post("/tasks")
def create_scraping_task(
    body: ScrapingTaskCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    service = ScrapingTaskService(db)
    try:
        task = service.create_task(
            list(body.movie_ids),
            current_user.id,
            config=ScrapingConfigService().get_raw_config(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    ensure_scraping_worker_started()
    return success_response(data=task_to_dict(task))


@router.get("/tasks")
def list_scraping_tasks(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    page: int = 1,
    size: int = 20,
    status_filter: str | None = None,
) -> dict:
    service = ScrapingTaskService(db)
    rows = service.list_tasks(user_id=current_user.id, page=page, size=size, status=status_filter)
    total = service.count_tasks(user_id=current_user.id, status=status_filter)
    return success(data={"rows": [task_to_dict(row) for row in rows], "total": total, "page": page, "size": size})


@router.get("/tasks/{task_id}")
def get_scraping_task(
    task_id: str,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    import uuid as _uuid

    service = ScrapingTaskService(db)
    try:
        task = service.get_task(_uuid.UUID(task_id), current_user.id)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在") from exc
    payload = task_to_dict(task)
    payload["items"] = [item_to_dict(item) for item in task.items]
    return success(data=payload)


@router.post("/tasks/{task_id}/cancel")
def cancel_scraping_task(
    task_id: str,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    import uuid as _uuid

    service = ScrapingTaskService(db)
    try:
        task = service.cancel_task(_uuid.UUID(task_id), current_user.id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return success(data=task_to_dict(task))


@router.post("/tasks/{task_id}/retry")
def retry_scraping_task(
    task_id: str,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    import uuid as _uuid

    service = ScrapingTaskService(db)
    try:
        task = service.retry_task(
            _uuid.UUID(task_id),
            current_user.id,
            config=ScrapingConfigService().get_raw_config(),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    ensure_scraping_worker_started()
    return success(data=task_to_dict(task))
```

Note: keep `status` query name for the list endpoint consistent with storage (`status`), so rename `status_filter` to `status: str | None = None` and pass `status=status`.

- [ ] **Step 4: Run the API tests**

Run: `python -m pytest backend/tests/test_scraping_tasks_api.py -v`
Expected: PASS.

- [ ] **Step 5: Add startup cleanup**

In `backend/app/main.py`, import:

```python
from backend.app.modules.scraping.tasks.worker import cleanup_interrupted_scraping_tasks
```

after the storage cleanup block inside the lifespan `if` block add:

```python
            scraping_stopped = cleanup_interrupted_scraping_tasks(session)
            if scraping_stopped:
                logger.info("Failed %d interrupted scraping tasks.", scraping_stopped)
```

- [ ] **Step 6: Run the full scraping backend suite**

Run: `python -m pytest backend/tests/test_scraping_models.py backend/tests/test_scraping_config_service.py backend/tests/test_scraping_paths.py backend/tests/test_scraping_scan.py backend/tests/test_scraping_nfo.py backend/tests/test_scraping_sources.py backend/tests/test_scraping_images.py backend/tests/test_scraping_task_service.py backend/tests/test_scraping_task_worker.py backend/tests/test_scraping_tasks_api.py backend/tests/test_scraping_scan_api.py backend/tests/test_scraping_api.py backend/tests/test_scraping_strm_trigger.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/scraping/router.py backend/app/main.py backend/tests/test_scraping_tasks_api.py
git commit -m "feat(scraping): expose scraping task API and startup cleanup"
```

---

## Task 13: Frontend API modules, types, query keys, realtime events

**Files:**
- Modify: `frontend/src/api/scraping/scrapingConfig/types.ts`
- Modify: `frontend/src/api/scraping/scrapingConfig/index.ts`
- Create: `frontend/src/api/scraping/scrapingTasks/types.ts`
- Create: `frontend/src/api/scraping/scrapingTasks/index.ts`
- Modify: `frontend/src/api/queryKeys.ts`
- Modify: `frontend/src/realtime/types.ts`
- Test: `frontend/src/api/queryInvalidation.test.ts` (extend if present)

**Interfaces:**
- Produces: `runScrapingScan(): Promise<ScrapingScanSummary>`; `listScrapingTasks(params)`, `getScrapingTask(id)`, `createScrapingTask(movieIds)`, `cancelScrapingTask(id)`, `retryScrapingTask(id)`; `queryKeys.scrapingTasks.*`; realtime event names `scraping.task.updated`, `scraping.item.updated`, `movie.scraping.updated`.

- [ ] **Step 1: Extend scraping config types**

In `frontend/src/api/scraping/scrapingConfig/types.ts` add:

```ts
export interface ScrapingScanSummary {
  folders_scanned: number
  folders_with_strm: number
  scraped_folders: number
  not_scraped_folders: number
  matched_movies: number
  updated_movies: number
  unmatched_folders: string[]
  duration_ms: number
}
```

and add `scrape_root: string`, `media_root: string`, `metadata_sources: string[]` to `ScrapingConfig` and `ScrapingConfigUpdate`.

- [ ] **Step 2: Extend the scraping config API module**

In `frontend/src/api/scraping/scrapingConfig/index.ts`:

```ts
import type { ScrapingScanSummary } from './types.ts'

export function runScrapingScan(): Promise<ScrapingScanSummary> {
  return request.post<ScrapingScanSummary>(`${BASE_URL}/scan`)
}
```

and re-export `ScrapingScanSummary`.

- [ ] **Step 3: Create the scraping tasks API module**

```ts
// frontend/src/api/scraping/scrapingTasks/types.ts
export type ScrapingTaskStatus = 'queued' | 'running' | 'success' | 'partial_failed' | 'failed' | 'cancelled'
export type ScrapingItemStatus = 'pending' | 'running' | 'success' | 'failed' | 'skipped'

export interface ScrapingTask {
  id: string
  status: ScrapingTaskStatus
  total_count: number
  success_count: number
  failed_count: number
  skipped_count: number
  cancel_requested: boolean
  created_by: string
  created_at?: string | null
  queued_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  error_message?: string | null
}

export interface ScrapingTaskItem {
  id: string
  task_id: string
  movie_id: string
  movie_code: string
  movie_title: string
  status: ScrapingItemStatus
  source: string
  folder: string
  duration_ms: number
  error_message?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ScrapingTaskDetail extends ScrapingTask {
  items: ScrapingTaskItem[]
}

export interface ScrapingTaskListResponse {
  rows: ScrapingTask[]
  total: number
  page: number
  size: number
}
```

```ts
// frontend/src/api/scraping/scrapingTasks/index.ts
import { request } from '@/request'
import type { ScrapingTask, ScrapingTaskDetail, ScrapingTaskListResponse } from './types'

export type * from './types'

const BASE_URL = '/api/scraping/tasks'

export function listScrapingTasks(params: {
  page: number
  size: number
  status?: string
}): Promise<ScrapingTaskListResponse> {
  return request.get<ScrapingTaskListResponse>(BASE_URL, params)
}

export function getScrapingTask(id: string): Promise<ScrapingTaskDetail> {
  return request.get<ScrapingTaskDetail>(`${BASE_URL}/${id}`)
}

export function createScrapingTask(movieIds: string[]): Promise<ScrapingTask> {
  return request.post<ScrapingTask>(BASE_URL, { movie_ids: movieIds })
}

export function cancelScrapingTask(id: string): Promise<ScrapingTask> {
  return request.post<ScrapingTask>(`${BASE_URL}/${id}/cancel`)
}

export function retryScrapingTask(id: string): Promise<ScrapingTask> {
  return request.post<ScrapingTask>(`${BASE_URL}/${id}/retry`)
}
```

- [ ] **Step 4: Add query keys and realtime event names**

In `frontend/src/api/queryKeys.ts` add:

```ts
  scrapingTasks: {
    all: () => ['scrapingTasks'] as const,
    list: (params: { page: number; size: number; status?: string }) =>
      ['scrapingTasks', 'list', params] as const,
    detail: (id: string) => ['scrapingTasks', 'detail', id] as const,
  },
```

In `frontend/src/realtime/types.ts` add to `RealtimeEventName`:

```ts
  | 'scraping.task.updated'
  | 'scraping.item.updated'
  | 'movie.scraping.updated'
```

and add payload types:

```ts
export type ScrapingTaskUpdatedPayload = {
  id: string
  status: string
  total_count: number
  success_count: number
  failed_count: number
  skipped_count: number
}

export type MovieScrapingUpdatedPayload = {
  movie_id: string
  scraping_status: 'scraped' | 'not_scraped' | null
  scraping_checked_at: string | null
}
```

- [ ] **Step 5: Add a query-invalidation helper**

In `frontend/src/api/queryInvalidation.ts` add:

```ts
export function invalidateScrapingTaskLists(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.all() })
}
```

- [ ] **Step 6: Verify types compile**

Run: `cd frontend && pnpm build`
Expected: PASS (no type errors).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/scraping/scrapingConfig/types.ts frontend/src/api/scraping/scrapingConfig/index.ts frontend/src/api/scraping/scrapingTasks/types.ts frontend/src/api/scraping/scrapingTasks/index.ts frontend/src/api/queryKeys.ts frontend/src/api/queryInvalidation.ts frontend/src/realtime/types.ts
git commit -m "feat(scraping): add frontend scraping task API and types"
```

---

## Task 14: Scraping config page additions

**Files:**
- Create: `frontend/src/pages/scraping/config/components/SourcePriorityList.tsx`
- Modify: `frontend/src/pages/scraping/config/ScrapingConfigPage.tsx`
- Modify: `frontend/src/pages/scraping/config/ScrapingConfigPage.module.less`
- Modify: `frontend/src/pages/scraping/config/__tests__/ScrapingConfigPage.test.tsx`

**Interfaces:**
- Produces: config page fields `scrape_root`, `media_root`, ordered source switches, and a scan action rendering `ScrapingScanSummary`.

- [ ] **Step 1: Update the failing page test**

In `frontend/src/pages/scraping/config/__tests__/ScrapingConfigPage.test.tsx`:

- Extend `savedConfig` with `scrape_root: '/mnt/media'`, `media_root: '/media'`, `metadata_sources: ['javdb', 'javbus']`.
- Mock `runScrapingScan`.
- Add tests:

```tsx
it('loads scraping directory fields', async () => {
  renderPage()
  expect(await screen.findByDisplayValue('/mnt/media')).toBeInTheDocument()
  expect(screen.getByDisplayValue('/media')).toBeInTheDocument()
})

it('saves reordered metadata sources', async () => {
  renderPage()
  await screen.findByDisplayValue('/mnt/media')
  fireEvent.click(screen.getByRole('button', { name: '下移 JavDB' }))
  fireEvent.click(screen.getByRole('button', { name: '保存配置' }))
  await waitFor(() => expect(updateScrapingConfig).toHaveBeenCalled())
  const payload = vi.mocked(updateScrapingConfig).mock.calls[0][0]
  expect(payload.metadata_sources).toEqual(['javbus', 'javdb'])
})

it('runs a scan and shows the summary', async () => {
  vi.mocked(runScrapingScan).mockResolvedValue({
    folders_scanned: 10,
    folders_with_strm: 4,
    scraped_folders: 3,
    not_scraped_folders: 1,
    matched_movies: 3,
    updated_movies: 3,
    unmatched_folders: [],
    duration_ms: 12,
  })
  renderPage()
  await screen.findByDisplayValue('/mnt/media')
  fireEvent.click(screen.getByRole('button', { name: '扫描目录' }))
  expect(await screen.findByText(/已刮削 3/)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test -- src/pages/scraping/config`
Expected: FAIL (fields/buttons missing).

- [ ] **Step 3: Implement the source priority list**

```tsx
// frontend/src/pages/scraping/config/components/SourcePriorityList.tsx
import { Button, Space, Switch, Tag, Typography } from 'antd'
import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons'

export interface SourcePriorityListProps {
  sources: string[]
  labels: Record<string, string>
  onChange: (sources: string[]) => void
}

const ALL_SOURCES = ['javdb', 'javbus']

export default function SourcePriorityList({ sources, labels, onChange }: SourcePriorityListProps) {
  const move = (index: number, offset: number) => {
    const next = index + offset
    if (next < 0 || next >= sources.length) return
    const updated = [...sources]
    ;[updated[index], updated[next]] = [updated[next], updated[index]]
    onChange(updated)
  }

  const toggle = (source: string, enabled: boolean) => {
    if (enabled) {
      onChange([...sources, source])
      return
    }
    const remaining = sources.filter((item) => item !== source)
    if (remaining.length > 0) onChange(remaining)
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      {sources.map((source, index) => (
        <div key={source} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Tag color="blue">{index + 1}</Tag>
          <Typography.Text style={{ flex: 1 }}>{labels[source] ?? source}</Typography.Text>
          <Button
            size="small"
            icon={<ArrowUpOutlined />}
            aria-label={`上移 ${labels[source] ?? source}`}
            disabled={index === 0}
            onClick={() => move(index, -1)}
          />
          <Button
            size="small"
            icon={<ArrowDownOutlined />}
            aria-label={`下移 ${labels[source] ?? source}`}
            disabled={index === sources.length - 1}
            onClick={() => move(index, 1)}
          />
          <Switch
            checked
            aria-label={`启用 ${labels[source] ?? source}`}
            onChange={(value) => toggle(source, value)}
          />
        </div>
      ))}
      {ALL_SOURCES.filter((source) => !sources.includes(source)).map((source) => (
        <div key={source} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Tag color="default">-</Tag>
          <Typography.Text type="secondary" style={{ flex: 1 }}>{labels[source] ?? source}</Typography.Text>
          <Switch
            checked={false}
            aria-label={`启用 ${labels[source] ?? source}`}
            onChange={(value) => toggle(source, value)}
          />
        </div>
      ))}
    </Space>
  )
}
```

- [ ] **Step 4: Extend the config page**

In `ScrapingConfigPage.tsx`:

- Extend `FormValues` with `scrape_root: string`, `media_root: string`.
- Add state: `const [sources, setSources] = useState<string[]>(['javdb', 'javbus'])`, `const [scanning, setScanning] = useState(false)`, `const [scanSummary, setScanSummary] = useState<ScrapingScanSummary | null>(null)`.
- Import `runScrapingScan`, `ScrapingScanSummary`, `SourcePriorityList`, and `FolderOpenOutlined`, `ScanOutlined` icons.
- In `applyConfig`: set `scrape_root`, `media_root`, `setSources(config.metadata_sources ?? [])`.
- In `buildPayload`: add `scrape_root: values.scrape_root, media_root: values.media_root, metadata_sources: sources`.
- Add the scan handler:

```tsx
  const handleScan = async () => {
    setScanning(true)
    try {
      const summary = await runScrapingScan()
      setScanSummary(summary)
      message.success('扫描完成')
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setScanning(false)
    }
  }
```

- Add a new Card after the 自动触发 Card inside `mainPanel`:

```tsx
              <Card
                title={
                  <span className={styles.sectionTitle}>
                    <FolderOpenOutlined />
                    刮削目录
                  </span>
                }
                className={styles.formCard}
              >
                <div className={styles.fieldGrid}>
                  <Form.Item
                    name="scrape_root"
                    label="刮削目录（本地路径）"
                    rules={[{ required: true, message: '请输入刮削目录' }]}
                  >
                    <Input placeholder="/mnt/cd2/media" />
                  </Form.Item>
                  <Form.Item
                    name="media_root"
                    label="媒体库根路径（云端）"
                    rules={[{ required: true, message: '请输入媒体库根路径' }]}
                  >
                    <Input placeholder="/media" />
                  </Form.Item>
                </div>
                <div className={styles.fieldGrid}>
                  <Form.Item label="元数据源优先级" className={styles.fieldSpan2}>
                    <SourcePriorityList
                      sources={sources}
                      labels={{ javdb: 'JavDB', javbus: 'JavBus' }}
                      onChange={setSources}
                    />
                  </Form.Item>
                </div>
              </Card>
```

- Add a `扫描目录` button in the 操作 Card (next to 保存配置 / 立即生成):

```tsx
                  <Button
                    icon={<ScanOutlined />}
                    loading={scanning}
                    onClick={() => void handleScan()}
                  >
                    扫描目录
                  </Button>
                  {scanSummary && (
                    <Alert
                      type="success"
                      showIcon
                      message={(
                        <span>
                          扫描 {scanSummary.folders_scanned} 个文件夹，已刮削 {scanSummary.scraped_folders}，
                          未刮削 {scanSummary.not_scraped_folders}，匹配 {scanSummary.matched_movies} 部电影
                        </span>
                      )}
                    />
                  )}
```

- Add minimal styles to `ScrapingConfigPage.module.less` if needed (keep existing classes; no new required class beyond `fieldSpan2`, which exists).

- [ ] **Step 5: Run the config page tests**

Run: `cd frontend && pnpm test -- src/pages/scraping/config`
Expected: PASS.

- [ ] **Step 6: Run the build**

Run: `cd frontend && pnpm build`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/scraping/config/components/SourcePriorityList.tsx frontend/src/pages/scraping/config/ScrapingConfigPage.tsx frontend/src/pages/scraping/config/ScrapingConfigPage.module.less frontend/src/pages/scraping/config/__tests__/ScrapingConfigPage.test.tsx
git commit -m "feat(scraping): configure directory and metadata source priority"
```

---

## Task 15: Movie list scraping status and actions

**Files:**
- Modify: `frontend/src/api/movie/types.ts`
- Modify: `frontend/src/pages/content/movies/components/MovieTable.tsx`
- Modify: `frontend/src/pages/content/movies/MovieListPage.tsx`
- Create: `frontend/src/pages/content/movies/hooks/useMovieScraping.ts`
- Modify: `frontend/src/pages/content/movies/hooks/useMovieList.ts`
- Modify: `frontend/src/pages/content/movies/hooks/useMovieListRealtime.ts`
- Modify: `frontend/src/pages/content/movies/__tests__/movie-table-actions.test.tsx`

**Interfaces:**
- Produces: `Movie.scraping_status` etc.; column `刮削状态`; row action `刮削`; toolbar `批量刮削`; `useMovieScraping` returning `scrapeMovies(movies)`.

- [ ] **Step 1: Write failing frontend tests**

In `movie-table-actions.test.tsx` add:

```tsx
it('renders scraping status and a scrape action', () => {
  const onScrape = vi.fn()
  render(
    <Table
      rowKey="_id"
      dataSource={[{ ...movie, storage_status: 'stored', scraping_status: 'scraped' }]}
      columns={createMovieColumns({
        onViewDetail: vi.fn(),
        onPush: vi.fn(),
        onCd2Sync: vi.fn(),
        onRefreshMagnets: vi.fn(),
        onDelete: vi.fn(),
        onScrape,
      })}
      pagination={false}
    />,
  )

  expect(screen.getByText('已刮削')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '刮削' }))
  expect(onScrape).toHaveBeenCalled()
})

it('shows a dash for scraping status when the movie is not stored', () => {
  render(
    <Table
      rowKey="_id"
      dataSource={[{ ...movie, storage_status: 'not_stored', scraping_status: null }]}
      columns={createMovieColumns({ onViewDetail: vi.fn(), onScrape: vi.fn() })}
      pagination={false}
    />,
  )

  expect(screen.queryByText('已刮削')).not.toBeInTheDocument()
  expect(screen.queryByText('未刮削')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && pnpm test -- src/pages/content/movies/__tests__/movie-table-actions.test.tsx`
Expected: FAIL (`已刮削` not rendered, `刮削` button missing).

- [ ] **Step 3: Extend the movie type and table columns**

In `frontend/src/api/movie/types.ts` add to `Movie`:

```ts
  scraping_status?: 'scraped' | 'not_scraped' | null
  scraping_folder?: string
  scraping_checked_at?: string | null
```

In `MovieTable.tsx`, extend `MovieColumnsOptions` with `onScrape?: (movie: Movie) => void`, add the column after 存储状态:

```tsx
    {
      title: '刮削状态',
      key: 'scraping_status',
      width: 100,
      render: (_: unknown, record) => {
        if ((record.storage_status || record.storage_summary?.storage_status) !== 'stored') {
          return <span>-</span>
        }
        if (record.scraping_status === 'scraped') return <Tag color="success">已刮削</Tag>
        if (record.scraping_status === 'not_scraped') return <Tag>未刮削</Tag>
        return <span>-</span>
      },
    },
```

and add the action before `delete`:

```tsx
          ...(onScrape ? [{ key: 'scrape', label: '刮削', onClick: () => onScrape(record) }] : []),
```

- [ ] **Step 4: Add the scraping hook and list integration**

```ts
// frontend/src/pages/content/movies/hooks/useMovieScraping.ts
import { useCallback } from 'react'
import { App } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import { createScrapingTask } from '@/api/scraping/scrapingTasks'
import { queryKeys } from '@/api/queryKeys'
import type { Movie } from '@/api/movie/types'

export function useMovieScraping() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()

  const scrapeMovies = useCallback(async (movies: Movie[]) => {
    const movieIds = [...new Set(movies.map((movie) => movie._id))]
    if (movieIds.length === 0) return
    try {
      const task = await createScrapingTask(movieIds)
      void queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.all() })
      message.success(`已创建刮削任务，共 ${task.total_count} 部`)
    } catch {
      // error handled by request interceptor
    }
  }, [message, queryClient])

  return { scrapeMovies }
}
```

In `useMovieList.ts`, add a scraping update applier alongside `applyStorageUpdates`:

```ts
    const applyScrapingUpdates = useCallback(
        (updates: Array<{ movie_id: string; scraping_status: Movie['scraping_status']; scraping_checked_at?: string | null }>) => {
            if (updates.length === 0) return;
            const byId = new Map(updates.map((update) => [update.movie_id, update]));
            setData((current) => ({
                ...current,
                items: current.items.map((item) => {
                    const update = byId.get(item._id);
                    if (!update) return item;
                    return {
                        ...item,
                        scraping_status: update.scraping_status,
                        scraping_checked_at: update.scraping_checked_at ?? item.scraping_checked_at,
                    };
                }),
            }));
        },
        [],
    );
```

and return it from the hook (`applyScrapingUpdates`).

In `useMovieListRealtime.ts`, extend the signature and subscribe:

```ts
export function useMovieListRealtime(
  applyStorageUpdates: (updates: MovieStorageUpdate[]) => void,
  applyScrapingUpdates?: (updates: Array<{ movie_id: string; scraping_status: 'scraped' | 'not_scraped' | null; scraping_checked_at?: string | null }>) => void,
) {
```

inside the effect add:

```ts
    const unsubscribeScraping = subscribeRealtime<MovieScrapingUpdatedPayload>(
      'movie.scraping.updated',
      (event: RealtimeEvent<MovieScrapingUpdatedPayload>) => {
        applyScrapingUpdates?.([event.payload])
      },
    )
```

and call `unsubscribeScraping()` in the cleanup. Import `MovieScrapingUpdatedPayload`.

In `MovieListPage.tsx`:

```tsx
  const scraping = useMovieScraping()
```

pass to columns:

```tsx
      onScrape: (movie) => void scraping.scrapeMovies([movie]),
```

pass to realtime:

```tsx
  useMovieListRealtime(list.applyStorageUpdates, list.applyScrapingUpdates)
```

and add the toolbar button before 批量推送:

```tsx
            {list.selectedRowKeys.length > 0 && (
              <Button
                type="primary"
                size="small"
                onClick={() => void scraping.scrapeMovies(
                  list.data.items.filter((movie) => list.selectedRowKeys.includes(movie._id)),
                )}
              >
                批量刮削
              </Button>
            )}
```

- [ ] **Step 5: Run the movie list tests**

Run: `cd frontend && pnpm test -- src/pages/content/movies`
Expected: PASS.

- [ ] **Step 6: Run the build**

Run: `cd frontend && pnpm build`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/movie/types.ts frontend/src/pages/content/movies/components/MovieTable.tsx frontend/src/pages/content/movies/MovieListPage.tsx frontend/src/pages/content/movies/hooks/useMovieScraping.ts frontend/src/pages/content/movies/hooks/useMovieList.ts frontend/src/pages/content/movies/hooks/useMovieListRealtime.ts frontend/src/pages/content/movies/__tests__/movie-table-actions.test.tsx
git commit -m "feat(scraping): show scraping status and actions in the movie list"
```

---

## Task 16: Scraping task pages, routing, and sidebar

**Files:**
- Create: `frontend/src/pages/scraping/tasks/TaskListPage.tsx`
- Create: `frontend/src/pages/scraping/tasks/TaskDetailPage.tsx`
- Create: `frontend/src/pages/scraping/tasks/hooks/useScrapingTasks.ts`
- Create: `frontend/src/pages/scraping/tasks/utils/status.ts`
- Create: `frontend/src/pages/scraping/tasks/__tests__/task-pages.test.tsx`
- Modify: `frontend/src/routes/index.tsx`
- Modify: `frontend/src/routes/tags.ts`
- Modify: `frontend/src/layout/Sidebar/index.tsx`

**Interfaces:**
- Produces: routes `/scraping/tasks` and `/scraping/tasks/$id`; sidebar `刮削任务`; task list/detail pages.

- [ ] **Step 1: Write the failing page test**

```tsx
// frontend/src/pages/scraping/tasks/__tests__/task-pages.test.tsx
import { App as AntApp } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListPage from '../TaskListPage'
import TaskDetailPage from '../TaskDetailPage'
import * as api from '@/api/scraping/scrapingTasks'

vi.mock('@/api/scraping/scrapingTasks', () => ({
  listScrapingTasks: vi.fn(),
  getScrapingTask: vi.fn(),
  createScrapingTask: vi.fn(),
  cancelScrapingTask: vi.fn(),
  retryScrapingTask: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  subscribeRealtime: vi.fn(() => vi.fn()),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({ id: 'task-1' }),
}))

function renderPage(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AntApp>{ui}</AntApp>
    </QueryClientProvider>,
  )
}

describe('scraping task pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.listScrapingTasks).mockResolvedValue({
      rows: [{
        id: 'task-1',
        status: 'success',
        total_count: 2,
        success_count: 2,
        failed_count: 0,
        skipped_count: 0,
        cancel_requested: false,
        created_by: 'user-1',
      }],
      total: 1,
      page: 1,
      size: 20,
    })
    vi.mocked(api.getScrapingTask).mockResolvedValue({
      id: 'task-1',
      status: 'partial_failed',
      total_count: 2,
      success_count: 1,
      failed_count: 1,
      skipped_count: 0,
      cancel_requested: false,
      created_by: 'user-1',
      items: [{
        id: 'item-1',
        task_id: 'task-1',
        movie_id: 'movie-1',
        movie_code: 'ADN-784',
        movie_title: 'ADN-784',
        status: 'failed',
        source: '',
        folder: '',
        duration_ms: 10,
        error_message: 'boom',
      }],
    })
  })

  it('renders the task list with a status tag, title, and refresh button', async () => {
    renderPage(<TaskListPage />)
    expect(await screen.findByText('ADN-784')).toBeInTheDocument()
    expect(screen.getByText('成功')).toBeInTheDocument()
    expect(screen.getByText('刮削任务')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '刷新' }))

    await waitFor(() => expect(api.listScrapingTasks).toHaveBeenCalledTimes(2))
  })

  it('renders the task detail items', async () => {
    renderPage(<TaskDetailPage />)
    expect(await screen.findByText('ADN-784')).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()
  })
})
```

Keep the file name `task-pages.test.tsx`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test -- src/pages/scraping/tasks`
Expected: FAIL (modules missing).

- [ ] **Step 3: Implement status helpers and hooks**

```ts
// frontend/src/pages/scraping/tasks/utils/status.ts
export const TASK_STATUS_TEXT: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  success: '成功',
  partial_failed: '部分失败',
  failed: '失败',
  cancelled: '已取消',
}

export const TASK_STATUS_COLOR: Record<string, string> = {
  queued: 'default',
  running: 'processing',
  success: 'success',
  partial_failed: 'warning',
  failed: 'error',
  cancelled: 'default',
}

export const ITEM_STATUS_TEXT: Record<string, string> = {
  pending: '等待中',
  running: '刮削中',
  success: '成功',
  failed: '失败',
  skipped: '跳过',
}

export const ITEM_STATUS_COLOR: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  success: 'success',
  failed: 'error',
  skipped: 'warning',
}
```

```ts
// frontend/src/pages/scraping/tasks/hooks/useScrapingTasks.ts
import { useCallback, useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  cancelScrapingTask,
  getScrapingTask,
  listScrapingTasks,
  retryScrapingTask,
} from '@/api/scraping/scrapingTasks'
import { queryKeys } from '@/api/queryKeys'
import { subscribeRealtime } from '@/realtime/eventSourceClient'
import type { RealtimeEvent, ScrapingTaskUpdatedPayload } from '@/realtime/types'

export function useScrapingTaskList() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(20)
  const params = { page, size }

  const query = useQuery({
    queryKey: queryKeys.scrapingTasks.list(params),
    queryFn: () => listScrapingTasks(params),
    placeholderData: (previous) => previous,
  })

  useEffect(() => {
    const unsubscribe = subscribeRealtime<ScrapingTaskUpdatedPayload>(
      'scraping.task.updated',
      (_event: RealtimeEvent<ScrapingTaskUpdatedPayload>) => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.list(params) })
      },
    )
    return unsubscribe
  }, [params.page, params.size, queryClient])

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.list(params) })
  }, [params.page, params.size, queryClient])

  const cancel = useCallback(async (id: string) => {
    await cancelScrapingTask(id)
    refresh()
  }, [refresh])

  const retry = useCallback(async (id: string) => {
    await retryScrapingTask(id)
    refresh()
  }, [refresh])

  return {
    page,
    size,
    setPage,
    setSize,
    tasks: query.data?.rows ?? [],
    total: query.data?.total ?? 0,
    loading: query.isLoading,
    refresh,
    cancel,
    retry,
  }
}

export function useScrapingTaskDetail(id: string) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: queryKeys.scrapingTasks.detail(id),
    queryFn: () => getScrapingTask(id),
  })

  useEffect(() => {
    const refresh = () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.detail(id) })
    }
    const unsubscribeTask = subscribeRealtime<ScrapingTaskUpdatedPayload>(
      'scraping.task.updated',
      (_event: RealtimeEvent<ScrapingTaskUpdatedPayload>) => refresh(),
    )
    const unsubscribeItem = subscribeRealtime(
      'scraping.item.updated',
      (_event: RealtimeEvent) => refresh(),
    )
    return () => {
      unsubscribeTask()
      unsubscribeItem()
    }
  }, [id, queryClient])

  const cancel = useCallback(async () => {
    await cancelScrapingTask(id)
    void queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.detail(id) })
  }, [id, queryClient])

  const retry = useCallback(async () => {
    const created = await retryScrapingTask(id)
    void queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.detail(id) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.scrapingTasks.all() })
    return created
  }, [id, queryClient])

  return { task: query.data, loading: query.isLoading, cancel, retry }
}
```

- [ ] **Step 4: Implement the task list page**

```tsx
// frontend/src/pages/scraping/tasks/TaskListPage.tsx
import { ReloadOutlined } from '@ant-design/icons'
import { Button, Card, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useNavigate } from '@tanstack/react-router'
import type { ScrapingTask } from '@/api/scraping/scrapingTasks'
import { useScrapingTaskList } from './hooks/useScrapingTasks'
import { TASK_STATUS_COLOR, TASK_STATUS_TEXT } from './utils/status'

function formatTime(value?: string | null) {
  return value ? new Date(value).toLocaleString() : '-'
}

export default function TaskListPage() {
  const navigate = useNavigate()
  const list = useScrapingTaskList()

  const columns: ColumnsType<ScrapingTask> = [
    {
      title: '状态',
      key: 'status',
      width: 110,
      render: (_: unknown, record) => (
        <Tag color={TASK_STATUS_COLOR[record.status]}>{TASK_STATUS_TEXT[record.status] ?? record.status}</Tag>
      ),
    },
    {
      title: '进度',
      key: 'progress',
      width: 200,
      render: (_: unknown, record) => (
        <span>
          {record.success_count}/{record.total_count} 成功，失败 {record.failed_count}，跳过 {record.skipped_count}
        </span>
      ),
    },
    { title: '创建时间', key: 'created_at', width: 180, render: (_: unknown, record) => formatTime(record.created_at) },
    { title: '开始时间', key: 'started_at', width: 180, render: (_: unknown, record) => formatTime(record.started_at) },
    { title: '结束时间', key: 'finished_at', width: 180, render: (_: unknown, record) => formatTime(record.finished_at) },
    {
      title: '操作',
      key: 'action',
      width: 180,
      render: (_: unknown, record) => (
        <Space>
          <Button size="small" onClick={() => void navigate({ to: '/scraping/tasks/$id', params: { id: record.id } })}>
            详情
          </Button>
          {['queued', 'running'].includes(record.status) && (
            <Button size="small" danger onClick={() => void list.cancel(record.id)}>取消</Button>
          )}
          {['failed', 'partial_failed', 'cancelled'].includes(record.status) && (
            <Button size="small" onClick={() => void list.retry(record.id)}>重试</Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card
      title="刮削任务"
      extra={(
        <Button icon={<ReloadOutlined />} onClick={() => list.refresh()}>
          刷新
        </Button>
      )}
    >
      <Table<ScrapingTask>
        rowKey="id"
        loading={list.loading}
        dataSource={list.tasks}
        columns={columns}
        pagination={{
          current: list.page,
          pageSize: list.size,
          total: list.total,
          onChange: (page, size) => {
            list.setPage(page)
            list.setSize(size)
          },
        }}
      />
    </Card>
  )
}
```

- [ ] **Step 5: Implement the task detail page**

```tsx
// frontend/src/pages/scraping/tasks/TaskDetailPage.tsx
import { Button, Card, Descriptions, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useNavigate, useParams } from '@tanstack/react-router'
import type { ScrapingTaskItem } from '@/api/scraping/scrapingTasks'
import { useScrapingTaskDetail } from './hooks/useScrapingTasks'
import { ITEM_STATUS_COLOR, ITEM_STATUS_TEXT, TASK_STATUS_COLOR, TASK_STATUS_TEXT } from './utils/status'

export default function TaskDetailPage() {
  const navigate = useNavigate()
  const { id } = useParams({ strict: false }) as { id: string }
  const detail = useScrapingTaskDetail(id)
  const task = detail.task

  const handleRetry = async () => {
    const created = await detail.retry()
    void navigate({ to: '/scraping/tasks/$id', params: { id: created.id } })
  }

  const columns: ColumnsType<ScrapingTaskItem> = [
    { title: '番号', dataIndex: 'movie_code', key: 'movie_code', width: 140 },
    { title: '标题', dataIndex: 'movie_title', key: 'movie_title', ellipsis: true },
    {
      title: '结果',
      key: 'status',
      width: 100,
      render: (_: unknown, record) => (
        <Tag color={ITEM_STATUS_COLOR[record.status]}>{ITEM_STATUS_TEXT[record.status] ?? record.status}</Tag>
      ),
    },
    { title: '来源', dataIndex: 'source', key: 'source', width: 100 },
    { title: '文件夹', dataIndex: 'folder', key: 'folder', ellipsis: true },
    { title: '耗时', key: 'duration', width: 100, render: (_: unknown, record) => `${record.duration_ms} ms` },
    { title: '错误', dataIndex: 'error_message', key: 'error_message', ellipsis: true },
  ]

  if (!task) {
    return <Card loading={detail.loading} />
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Card
        title="刮削任务"
        extra={(
          <Space>
            {['queued', 'running'].includes(task.status) && (
              <Button danger onClick={() => void detail.cancel()}>取消任务</Button>
            )}
            {['failed', 'partial_failed', 'cancelled'].includes(task.status) && (
              <Button onClick={() => void handleRetry()}>重试失败项</Button>
            )}
          </Space>
        )}
      >
        <Descriptions column={4}>
          <Descriptions.Item label="状态">
            <Tag color={TASK_STATUS_COLOR[task.status]}>{TASK_STATUS_TEXT[task.status] ?? task.status}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="总数">{task.total_count}</Descriptions.Item>
          <Descriptions.Item label="成功">{task.success_count}</Descriptions.Item>
          <Descriptions.Item label="失败/跳过">{task.failed_count}/{task.skipped_count}</Descriptions.Item>
          {task.error_message && <Descriptions.Item label="错误">{task.error_message}</Descriptions.Item>}
        </Descriptions>
      </Card>
      <Table<ScrapingTaskItem>
        rowKey="id"
        loading={detail.loading}
        dataSource={task.items}
        columns={columns}
        pagination={false}
      />
    </Space>
  )
}
```

- [ ] **Step 6: Wire routes, tags, sidebar**

In `frontend/src/routes/index.tsx` add lazy imports:

```tsx
const ScrapingTaskListPage = lazyRouteComponent(() => import('@/pages/scraping/tasks/TaskListPage'))
const ScrapingTaskDetailPage = lazyRouteComponent(() => import('@/pages/scraping/tasks/TaskDetailPage'))
```

add routes:

```tsx
const scrapingTasksRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/scraping/tasks',
  component: ScrapingTaskListPage,
})

const scrapingTaskDetailRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/scraping/tasks/$id',
  component: ScrapingTaskDetailPage,
})
```

and add both to the children list next to `scrapingConfigRoute`.

In `frontend/src/routes/tags.ts` add:

```ts
  {
    pattern: /^\/scraping\/tasks$/,
    meta: { title: '刮削任务' },
  },
  {
    pattern: /^\/scraping\/tasks\/[^/]+$/,
    meta: { title: '刮削任务详情', activeMenu: '/scraping/tasks' },
  },
```

In `frontend/src/layout/Sidebar/index.tsx`, add to the `scraping` group children before `刮削配置`:

```tsx
      {
        key: '/scraping/tasks',
        icon: <HistoryOutlined />,
        label: '刮削任务',
      },
```

and extend the active-path resolution:

```tsx
            : pathname.startsWith('/scraping/tasks')
              ? '/scraping/tasks'
              : pathname.startsWith('/scraping/config')
                ? '/scraping/config'
```

- [ ] **Step 7: Run the task page tests and build**

Run: `cd frontend && pnpm test -- src/pages/scraping/tasks`
Expected: PASS.

Run: `cd frontend && pnpm build`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/scraping/tasks/TaskListPage.tsx frontend/src/pages/scraping/tasks/TaskDetailPage.tsx frontend/src/pages/scraping/tasks/hooks/useScrapingTasks.ts frontend/src/pages/scraping/tasks/utils/status.ts frontend/src/pages/scraping/tasks/__tests__/task-pages.test.tsx frontend/src/routes/index.tsx frontend/src/routes/tags.ts frontend/src/layout/Sidebar/index.tsx
git commit -m "feat(scraping): add scraping task list and detail pages"
```

---

## Task 17: Uncached list pages and list headers

**Files:**
- Modify: `frontend/src/layout/routeCacheControl.ts`
- Modify: `frontend/src/pages/crawler/runs/RunListPage.tsx`
- Test: `frontend/src/layout/__tests__/routeCacheControl.test.ts`
- Test: `frontend/src/pages/crawler/runs/__tests__/run-list-query.test.tsx`

**Interfaces:**
- Produces: `ROUTE_CACHE_EXCLUDE_PATHS` includes `/crawler/runs`, `/storage/tasks`, `/scraping/tasks`; the crawler run list renders a `运行记录` card with a `刷新` button.

- [ ] **Step 1: Write the failing route exclusion test**

```ts
// frontend/src/layout/__tests__/routeCacheControl.test.ts
import { describe, expect, it } from 'vitest'
import { isRouteCacheExcluded } from '../routeCacheControl'

describe('route cache exclusions', () => {
  it('excludes the three task list pages from keep-alive', () => {
    expect(isRouteCacheExcluded('/crawler/runs')).toBe(true)
    expect(isRouteCacheExcluded('/storage/tasks')).toBe(true)
    expect(isRouteCacheExcluded('/scraping/tasks')).toBe(true)
  })

  it('keeps detail routes cached', () => {
    expect(isRouteCacheExcluded('/crawler/runs/run-1')).toBe(false)
    expect(isRouteCacheExcluded('/storage/tasks/task-1')).toBe(false)
    expect(isRouteCacheExcluded('/scraping/tasks/task-1')).toBe(false)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test -- src/layout/__tests__/routeCacheControl.test.ts`
Expected: FAIL for the three list paths.

- [ ] **Step 3: Add the exclusions**

In `frontend/src/layout/routeCacheControl.ts`:

```ts
export const ROUTE_CACHE_EXCLUDE_PATHS = [
  '/login',
  '/init',
  '/crawler/runs',
  '/storage/tasks',
  '/scraping/tasks',
]
```

- [ ] **Step 4: Run the route test to verify it passes**

Run: `cd frontend && pnpm test -- src/layout/__tests__/routeCacheControl.test.ts`
Expected: PASS.

- [ ] **Step 5: Write the failing crawler run header test**

In `frontend/src/pages/crawler/runs/__tests__/run-list-query.test.tsx`, add:

```tsx
  it('renders the run list card title and refreshes from the header button', async () => {
    vi.mocked(getCrawlerRuns).mockResolvedValue({
      rows: [buildRun()],
      page: 1,
      size: 20,
      has_more: false,
    } as never)

    render(<RunListPage />, { wrapper })

    expect(await screen.findByText('运行记录')).toBeInTheDocument()
    await waitFor(() => expect(getCrawlerRuns).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('button', { name: '刷新' }))

    await waitFor(() => expect(getCrawlerRuns).toHaveBeenCalledTimes(2))
  })
```

- [ ] **Step 6: Run the crawler run tests to verify they fail**

Run: `cd frontend && pnpm test -- src/pages/crawler/runs/__tests__/run-list-query.test.tsx`
Expected: FAIL (`运行记录` and header refresh button missing).

- [ ] **Step 7: Add the card header to the crawler run list**

In `frontend/src/pages/crawler/runs/RunListPage.tsx`, replace:

```tsx
    <Card className={styles.runListCard}>
```

with:

```tsx
    <Card
      className={styles.runListCard}
      title="运行记录"
      extra={(
        <Button icon={<ReloadOutlined />} onClick={() => void refreshRuns()}>
          刷新
        </Button>
      )}
    >
```

and add `Button` to the existing `antd` import if it is not already there:

```tsx
import {Button, Card, message, Progress, Table, Tag} from 'antd'
```

- [ ] **Step 8: Run the crawler run tests**

Run: `cd frontend && pnpm test -- src/pages/crawler/runs/__tests__/run-list-query.test.tsx`
Expected: PASS.

- [ ] **Step 9: Confirm the storage list already matches the pattern**

`StorageMainTaskTable` already renders `Card title="任务列表"` with a `刷新`
button calling `onRefresh`; the only storage change is the route exclusion from
Step 3. Confirm the title/refresh still render by running:

Run: `cd frontend && pnpm test -- src/pages/storage/tasks`
Expected: PASS.

- [ ] **Step 10: Run the scraping task page tests again**

Run: `cd frontend && pnpm test -- src/pages/scraping/tasks`
Expected: PASS (the scraping list already has the `刮削任务` card header).

- [ ] **Step 11: Commit**

```bash
git add frontend/src/layout/routeCacheControl.ts frontend/src/layout/__tests__/routeCacheControl.test.ts frontend/src/pages/crawler/runs/RunListPage.tsx frontend/src/pages/crawler/runs/__tests__/run-list-query.test.tsx
git commit -m "feat(frontend): make task list pages uncached with refresh headers"
```

---

## Task 18: Documentation and full verification

**Files:**
- Modify: `frontend/README.md` (routes list)
- Verify: all tests/builds

- [ ] **Step 1: Update the frontend README routes**

In `frontend/README.md`, find the authenticated routes list and add:

```
  /scraping/config, /scraping/tasks, /scraping/tasks/$id,
```

If the README has no routes list, add a short `Scraping` section under the page modules:

```md
- `pages/scraping/` contains scraping configuration, directory scanning status
  display, and the scraping task list/detail pages.
```

- [ ] **Step 2: Run the full backend test suite**

Run: `python -m pytest backend/tests -v`
Expected: PASS (all tests, including the updated scraping config tests).

- [ ] **Step 3: Run the full frontend test suite and build**

Run: `cd frontend && pnpm test`
Expected: PASS.

Run: `cd frontend && pnpm build`
Expected: PASS.

- [ ] **Step 4: Run the scraper tests**

Run: `python -m pytest scraper/tests -v`
Expected: PASS (no scraper changes, but the source adapters import scraper parsers).

- [ ] **Step 5: Commit**

```bash
git add frontend/README.md
git commit -m "docs(scraping): document scraping task routes"
```

---

## Self-Review Notes

- Spec coverage: data model (Task 1), movie payload (Task 2), configuration and metadata sources (Tasks 3, 6), path mapping (Task 4), nfo/artwork (Tasks 5, 7), scanning and status judgment (Task 8), scan API and STRM refresh (Task 9), tasks with cancel/retry and progress (Tasks 10–12), frontend API/events (Task 13), config page (Task 14), movie list status/actions (Task 15), task pages/routing/sidebar (Task 16), uncached list pages and headers for crawler runs, storage tasks, and scraping tasks (Task 17), verification/docs (Task 18).
- Known deliberate simplifications: the scan API is synchronous (spec); `SourceMetadata.backdrop_url`/`landscape_url` are currently not populated by either adapter, so DB-complete movies write only `folder.jpg`; when no crawl is needed the nfo omits `metatubeid`; button hiding remains out of scope.
- Type consistency: `task_to_dict`/`item_to_dict` field names match the frontend `ScrapingTask`/`ScrapingTaskItem` types; `scan_directory` returns `ScanSummary` with `to_dict()` used by the API and matched by `ScrapingScanSummary`.
