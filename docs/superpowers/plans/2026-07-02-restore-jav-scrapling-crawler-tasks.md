# Restore Jav-Scrapling Crawler Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the `jav-scrapling` crawler task list and new-task behavior in Media Forge, add the crawler task schema to the unified init bootstrap flow, and store task URLs in a normalized child table.

**Architecture:** Replace Media Forge’s temporary generic task shape (`keywords`, `target_websites`) with the original task model (`name`, `is_skip`, `urls`, URL filters, derived `final_url`, `url_name`). Store URLs in `crawl_task_urls` instead of a JSON column because each URL has ordering, uniqueness, derived fields, source metadata, and future run/report relationships. Database creation and default data seeding are owned by `docs/superpowers/plans/2026-07-02-init-database-bootstrap.md`; this plan only adds crawler task models/migrations and registers the model module with that bootstrap.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, Alembic, PostgreSQL 18, Pytest, React 19, Vite 8, TypeScript 6, Ant Design 6, TanStack Router 1.x, Vitest, React Testing Library.

---

## Source Context

- Original task backend:
  - `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/crawler/tasks/router.py`
  - `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/crawler/tasks/schemas.py`
  - `/Users/eastwood/Code/PycharmProjects/jav-scrapling/shared/database/models/crawler.py`
- Original task frontend:
  - `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/crawler/tasks/TaskList.tsx`
  - `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/crawler/tasks/TaskForm.tsx`
  - `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/crawler/tasks/api.ts`
  - `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/crawler/tasks/types.ts`
- Existing reusable Media Forge scraper helpers:
  - `scraper/tasks/task_utils.py` already provides `determine_source()` and `build_final_url()`.
  - `scraper/spiders/javdb/javdb_parser.py` already provides `parse_page_section_name()`.
  - `scraper/core/security.py` already provides `is_security_check_page()`.

## Prerequisite

Complete `docs/superpowers/plans/2026-07-02-init-database-bootstrap.md` before executing this plan. The crawler task tables must be created through the unified init bootstrap by registering `backend.app.models.crawl_task` in `APPLICATION_MODEL_MODULES`; this plan must not add separate init table-creation code.

## Design Decision: URL Child Table

Yes, store the original `urls` array in a child table.

Use:

- `crawl_tasks`: one row per task, user-owned, unique task name per owner.
- `crawl_task_urls`: one row per URL entry with `position`, `url`, `url_type`, `has_magnet`, `has_chinese_sub`, `sort_type`, `source`, `final_url`, `url_name`.

Reasons:

- Duplicate URL validation becomes a database constraint: `UNIQUE(task_id, url)`.
- Ordered URL cards can be preserved with `position`.
- Search and future run detail links can target one URL row.
- Derived `final_url` and `source` can be recalculated consistently on create/update.
- The scraper still receives a list of URL dicts, so this does not require a scraper rewrite.

## File Structure

- Modify: `backend/app/models/crawl_task.py`
  - Replace the temporary generic task fields with original task fields and add `CrawlTaskUrl`.
- Modify: `backend/alembic/env.py`
  - Ensure the new model is imported for autogeneration/manual migration metadata.
- Create: `backend/alembic/versions/20260702_0001_restore_crawler_tasks.py`
  - Create `crawl_tasks` and `crawl_task_urls` for a fresh database.
- Modify: `backend/app/schemas/crawl_task.py`
  - Add original-compatible URL entry schemas and task read/create/update schemas.
- Modify: `backend/app/repositories/crawl_task.py`
  - Add name uniqueness, URL child loading, task list, and update helpers.
- Modify: `backend/app/modules/crawler/tasks/router.py`
  - Restore list/create/get/update/delete and `extract-name`.
- Modify: `backend/app/modules/crawl_tasks/router.py`
  - Keep legacy `/api/crawl-tasks` compatibility routes aligned with canonical API.
- Modify: `backend/tests/test_crawl_tasks_api.py`
  - Replace temporary keyword/target-site expectations with original URL-entry behavior.
- Modify: `frontend/src/api/crawlTask/types.ts`
  - Restore original task URL entry types.
- Modify: `frontend/src/api/crawlTask/index.ts`
  - Add `extractTaskName()` and use original-compatible payload names.
- Create: `frontend/src/pages/crawler/tasks/taskUrlUtils.ts`
  - Move URL type detection/final URL preview helpers out of the page for tests.
- Modify: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
  - Restore original-style URL card form.
- Modify: `frontend/src/pages/crawlTasks/components/TaskListTable.tsx`
  - Restore original-style task list columns.
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
  - Use restored list actions and display shape.
- Modify: `frontend/tests/App.test.tsx`
  - Update crawl task API mocks to the restored response shape.
- Create: `frontend/tests/task-url-utils.test.ts`
  - Test URL detection and final URL preview helpers.
- Create: `frontend/tests/task-form-restore.ui.test.tsx`
  - Test new-task form payload with URL entries.

---

### Task 1: Backend Database Schema With `crawl_task_urls`

**Files:**
- Modify: `backend/app/models/crawl_task.py`
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/20260702_0001_restore_crawler_tasks.py`
- Test: `backend/tests/test_crawl_tasks_api.py`

- [ ] **Step 1: Write the failing API schema test**

Replace `task_payload()` in `backend/tests/test_crawl_tasks_api.py` with:

```python
def task_payload() -> dict:
    return {
        "name": "每日演员任务",
        "is_skip": False,
        "urls": [
            {
                "url": "https://javdb.com/actors/abc",
                "url_type": "actors",
                "has_magnet": True,
                "has_chinese_sub": False,
                "sort_type": 0,
                "url_name": "演员 A",
            }
        ],
    }
```

Replace `test_canonical_route_creates_and_lists_task` with:

```python
    def test_canonical_route_creates_and_lists_task_with_url_entries(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)

        created_response = client.post(
            "/api/crawler/tasks",
            json=task_payload(),
            headers=headers,
        )

        assert created_response.status_code == HTTPStatus.CREATED
        created = created_response.json()["data"]
        assert created["name"] == "每日演员任务"
        assert created["owner_id"] == str(admin_user.id)
        assert created["is_skip"] is False
        assert created["urls"][0]["url"] == "https://javdb.com/actors/abc"
        assert created["urls"][0]["url_type"] == "actors"
        assert created["urls"][0]["source"] == "javdb"
        assert "page=1" in created["urls"][0]["final_url"]
        assert created["urls"][0]["url_name"] == "演员 A"

        list_response = client.get("/api/crawler/tasks", headers=headers)
        assert list_response.status_code == HTTPStatus.OK
        body = list_response.json()
        assert body["total"] == 1
        assert [item["name"] for item in body["rows"]] == ["每日演员任务"]
        assert body["rows"][0]["urls"][0]["url_name"] == "演员 A"
```

Append this duplicate URL test inside `class TestCrawlTasksApi`:

```python
    def test_create_task_rejects_duplicate_urls(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        payload = task_payload()
        payload["urls"].append(payload["urls"][0].copy())

        response = client.post("/api/crawler/tasks", json=payload, headers=headers)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "URL 重复" in response.json()["detail"]
```

- [ ] **Step 2: Run the failing backend task tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_canonical_route_creates_and_lists_task_with_url_entries backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_create_task_rejects_duplicate_urls -v
```

Expected: FAIL because the current API requires `keywords` and `target_websites`, and there is no `urls` relationship.

- [ ] **Step 3: Replace the crawl task models**

Replace `backend/app/models/crawl_task.py` with:

```python
import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CrawlTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawl_tasks"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_crawl_tasks_owner_name"),
        Index("idx_crawl_tasks_owner_created_at", "owner_id", "created_at"),
        Index("idx_crawl_tasks_owner_skip", "owner_id", "is_skip"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_skip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    task_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    celery_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_qualified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    urls: Mapped[list["CrawlTaskUrl"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="CrawlTaskUrl.position",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<CrawlTask(id={self.id}, name={self.name}, urls={len(self.urls)})>"


class CrawlTaskUrl(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawl_task_urls"
    __table_args__ = (
        UniqueConstraint("task_id", "url", name="uq_crawl_task_urls_task_url"),
        Index("idx_crawl_task_urls_task_position", "task_id", "position"),
        Index("idx_crawl_task_urls_source", "source"),
        Index("idx_crawl_task_urls_url_type", "url_type"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_type: Mapped[str] = mapped_column(String(50), nullable=False)
    has_magnet: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_chinese_sub: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_type: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    final_url: Mapped[str] = mapped_column(Text, nullable=False)
    url_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    task: Mapped[CrawlTask] = relationship(back_populates="urls")
```

- [ ] **Step 4: Update Alembic model imports**

Ensure `backend/alembic/env.py` imports the new classes with:

```python
from app.models.crawl_task import CrawlTask, CrawlTaskUrl  # noqa: F401
```

- [ ] **Step 5: Create the fresh-database Alembic revision**

Create `backend/alembic/versions/20260702_0001_restore_crawler_tasks.py`:

```python
"""restore crawler task url schema

Revision ID: 20260702_0001
Revises:
Create Date: 2026-07-02 00:01:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260702_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawl_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_skip", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("task_id", sa.String(length=100), nullable=True),
        sa.Column("celery_id", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("total_found", sa.Integer(), nullable=False),
        sa.Column("total_qualified", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_crawl_tasks_owner_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_crawl_tasks"),
        sa.UniqueConstraint("owner_id", "name", name="uq_crawl_tasks_owner_name"),
        sa.UniqueConstraint("task_id", name="uq_crawl_tasks_task_id"),
    )
    op.create_index("ix_crawl_tasks_owner_id", "crawl_tasks", ["owner_id"])
    op.create_index("ix_crawl_tasks_status", "crawl_tasks", ["status"])
    op.create_index("idx_crawl_tasks_owner_created_at", "crawl_tasks", ["owner_id", "created_at"])
    op.create_index("idx_crawl_tasks_owner_skip", "crawl_tasks", ["owner_id", "is_skip"])

    op.create_table(
        "crawl_task_urls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_type", sa.String(length=50), nullable=False),
        sa.Column("has_magnet", sa.Boolean(), nullable=False),
        sa.Column("has_chinese_sub", sa.Boolean(), nullable=False),
        sa.Column("sort_type", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("final_url", sa.Text(), nullable=False),
        sa.Column("url_name", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["crawl_tasks.id"], name="fk_crawl_task_urls_task_id_crawl_tasks", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_crawl_task_urls"),
        sa.UniqueConstraint("task_id", "url", name="uq_crawl_task_urls_task_url"),
    )
    op.create_index("ix_crawl_task_urls_task_id", "crawl_task_urls", ["task_id"])
    op.create_index("idx_crawl_task_urls_task_position", "crawl_task_urls", ["task_id", "position"])
    op.create_index("idx_crawl_task_urls_source", "crawl_task_urls", ["source"])
    op.create_index("idx_crawl_task_urls_url_type", "crawl_task_urls", ["url_type"])


def downgrade() -> None:
    op.drop_index("idx_crawl_task_urls_url_type", table_name="crawl_task_urls")
    op.drop_index("idx_crawl_task_urls_source", table_name="crawl_task_urls")
    op.drop_index("idx_crawl_task_urls_task_position", table_name="crawl_task_urls")
    op.drop_index("ix_crawl_task_urls_task_id", table_name="crawl_task_urls")
    op.drop_table("crawl_task_urls")
    op.drop_index("idx_crawl_tasks_owner_skip", table_name="crawl_tasks")
    op.drop_index("idx_crawl_tasks_owner_created_at", table_name="crawl_tasks")
    op.drop_index("ix_crawl_tasks_status", table_name="crawl_tasks")
    op.drop_index("ix_crawl_tasks_owner_id", table_name="crawl_tasks")
    op.drop_table("crawl_tasks")
```

- [ ] **Step 6: Run the failing tests again**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_canonical_route_creates_and_lists_task_with_url_entries backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_create_task_rejects_duplicate_urls -v
```

Expected: still FAIL because schemas/router still use the old temporary fields. The model and migration are now ready for the next task.

- [ ] **Step 7: Commit schema work**

Run:

```bash
git add backend/app/models/crawl_task.py backend/alembic/env.py backend/alembic/versions/20260702_0001_restore_crawler_tasks.py backend/tests/test_crawl_tasks_api.py
git commit -m "feat(backend): normalize crawler task urls"
```

Expected: one commit with model, migration, and failing tests.

---

### Task 2: Backend Schemas, Repository, and Task API

**Files:**
- Modify: `backend/app/schemas/crawl_task.py`
- Modify: `backend/app/repositories/crawl_task.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Modify: `backend/app/modules/crawl_tasks/router.py`
- Test: `backend/tests/test_crawl_tasks_api.py`

- [ ] **Step 1: Replace the crawl task schemas**

Replace `backend/app/schemas/crawl_task.py` with:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TaskUrlEntryBase(BaseModel):
    url: str = Field(..., min_length=1)
    url_type: str = Field(..., min_length=1, max_length=50)
    has_magnet: bool = False
    has_chinese_sub: bool = False
    sort_type: int = Field(default=0, ge=0)
    final_url: str | None = None
    source: str | None = None
    url_name: str | None = Field(default=None, max_length=200)


class TaskUrlEntryCreate(TaskUrlEntryBase):
    pass


class TaskUrlEntryRead(TaskUrlEntryBase):
    id: uuid.UUID
    position: int
    source: str
    final_url: str
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CrawlTaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    urls: list[TaskUrlEntryCreate] = Field(..., min_length=1)
    is_skip: bool = False


class CrawlTaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    urls: list[TaskUrlEntryCreate] | None = None
    is_skip: bool | None = None


class CrawlTaskRead(BaseModel):
    id: uuid.UUID
    _id: uuid.UUID
    name: str
    urls: list[TaskUrlEntryRead]
    is_skip: bool
    status: str
    task_id: str | None = None
    error_message: str | None = None
    total_found: int
    total_qualified: int
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ExtractNameRequest(BaseModel):
    url: str = Field(..., min_length=1)
    url_type: str = Field(..., min_length=1)


class ExtractNameResponse(BaseModel):
    name: str
```

- [ ] **Step 2: Replace the repository**

Replace `backend/app/repositories/crawl_task.py` with:

```python
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.repositories.base import BaseRepository
from backend.app.schemas.crawl_task import TaskUrlEntryCreate
from scraper.tasks.task_utils import build_final_url, determine_source


class CrawlTaskRepository(BaseRepository):
    """Repository for CrawlTask model operations."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, CrawlTask)

    def _owner_query(self, owner_id: uuid.UUID, keyword: str | None = None):
        query = (
            self.session.query(CrawlTask)
            .options(selectinload(CrawlTask.urls))
            .filter(CrawlTask.owner_id == owner_id)
        )
        normalized_keyword = keyword.strip() if keyword else ""
        if normalized_keyword:
            query = query.filter(CrawlTask.name.ilike(f"%{normalized_keyword}%"))
        return query

    def get_by_owner(
        self,
        owner_id: uuid.UUID,
        *,
        skip: int = 0,
        limit: int = 20,
        keyword: str | None = None,
    ) -> list[CrawlTask]:
        return (
            self._owner_query(owner_id, keyword)
            .order_by(CrawlTask.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_owner(self, owner_id: uuid.UUID, keyword: str | None = None) -> int:
        query = self.session.query(CrawlTask).filter(CrawlTask.owner_id == owner_id)
        normalized_keyword = keyword.strip() if keyword else ""
        if normalized_keyword:
            query = query.filter(CrawlTask.name.ilike(f"%{normalized_keyword}%"))
        return query.with_entities(func.count(CrawlTask.id)).scalar() or 0

    def get_owned(self, task_id: uuid.UUID, owner_id: uuid.UUID) -> CrawlTask | None:
        return (
            self.session.query(CrawlTask)
            .options(selectinload(CrawlTask.urls))
            .filter(CrawlTask.id == task_id, CrawlTask.owner_id == owner_id)
            .first()
        )

    def get_by_name(self, owner_id: uuid.UUID, name: str) -> CrawlTask | None:
        return (
            self.session.query(CrawlTask)
            .filter(CrawlTask.owner_id == owner_id, CrawlTask.name == name)
            .first()
        )

    def build_url_rows(self, entries: list[TaskUrlEntryCreate]) -> list[CrawlTaskUrl]:
        rows: list[CrawlTaskUrl] = []
        for position, entry in enumerate(entries):
            source = determine_source(entry.url)
            final_url = build_final_url(
                url=entry.url,
                url_type=entry.url_type,
                has_magnet=entry.has_magnet,
                has_chinese_sub=entry.has_chinese_sub,
                sort_type=entry.sort_type,
                source=source,
            )
            rows.append(
                CrawlTaskUrl(
                    position=position,
                    url=entry.url,
                    url_type=entry.url_type,
                    has_magnet=entry.has_magnet,
                    has_chinese_sub=entry.has_chinese_sub,
                    sort_type=entry.sort_type,
                    source=source,
                    final_url=entry.final_url or final_url,
                    url_name=entry.url_name,
                )
            )
        return rows

    def create_with_urls(
        self,
        *,
        owner_id: uuid.UUID,
        name: str,
        is_skip: bool,
        urls: list[TaskUrlEntryCreate],
    ) -> CrawlTask:
        task = CrawlTask(name=name, is_skip=is_skip, owner_id=owner_id)
        task.urls = self.build_url_rows(urls)
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return self.get_owned(task.id, owner_id) or task

    def replace_urls(self, task: CrawlTask, urls: list[TaskUrlEntryCreate]) -> None:
        task.urls.clear()
        task.urls.extend(self.build_url_rows(urls))
```

- [ ] **Step 3: Replace the task router**

Replace `backend/app/modules/crawler/tasks/router.py` with:

```python
import logging
import uuid
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.repositories.crawl_task import CrawlTaskRepository
from backend.app.schemas.crawl_task import (
    CrawlTaskCreate,
    CrawlTaskRead,
    CrawlTaskUpdate,
    ExtractNameRequest,
)
from scraper.config.settings import REQUEST_TIMEOUT
from scraper.config.sites import JAVDB_SITE
from scraper.cookies.cookie_manager import CookieManager
from scraper.core.security import is_security_check_page
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher
from scraper.spiders.javdb.javdb_parser import parse_page_section_name
from shared.schemas.common import paginated, success

router = APIRouter(prefix="/api/crawler/tasks", tags=["crawler-tasks"])
logger = logging.getLogger(__name__)


def _check_urls_unique(urls) -> None:
    seen: set[str] = set()
    for entry in urls:
        if entry.url in seen:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"URL 重复: {entry.url}")
        seen.add(entry.url)


def _serialize(task) -> CrawlTaskRead:
    data = CrawlTaskRead.model_validate(task)
    data._id = data.id
    return data


@router.get("")
def list_tasks(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, max_length=200),
) -> dict:
    repo = CrawlTaskRepository(db)
    rows = repo.get_by_owner(current_user.id, skip=skip, limit=limit, keyword=keyword)
    total = repo.count_by_owner(current_user.id, keyword=keyword)
    return paginated(rows=[_serialize(row).model_dump(mode="json") for row in rows], total=total)


@router.get("/stats")
def get_stats(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    repo = CrawlTaskRepository(db)
    return success(data={"total": repo.count_by_owner(current_user.id)})


@router.post("/extract-name")
def extract_name(body: ExtractNameRequest, _current_user: CurrentUser) -> dict:
    if body.url_type == "search":
        parsed = urlparse(body.url)
        q_values = parse_qs(parsed.query).get("q", [])
        return success(data={"name": q_values[0].strip() if q_values else ""})

    try:
        cookie_manager = CookieManager(JAVDB_SITE["cookie_file"])
        fetcher = ScraplingFetcher(
            headers=JAVDB_SITE["headers"],
            cookies=cookie_manager.load(),
            timeout=REQUEST_TIMEOUT,
        )
        page = fetcher.get(body.url)
        if is_security_check_page(page):
            raise HTTPException(status_code=429, detail="触发安全验证，请稍后重试")
        return success(data={"name": parse_page_section_name(page, body.url_type)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Extract task URL name failed: %s", body.url)
        raise HTTPException(status_code=500, detail=f"提取名称失败: {exc}") from exc


@router.get("/{task_id}")
def get_task(task_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return success(data=_serialize(task).model_dump(mode="json"))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(data: CrawlTaskCreate, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    repo = CrawlTaskRepository(db)
    if repo.get_by_name(current_user.id, data.name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"任务名称 '{data.name}' 已存在")
    _check_urls_unique(data.urls)
    try:
        created = repo.create_with_urls(
            owner_id=current_user.id,
            name=data.name,
            is_skip=data.is_skip,
            urls=data.urls,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务 URL 或名称重复") from exc
    return success(data=_serialize(created).model_dump(mode="json"))


@router.put("/{task_id}")
def update_task(
    task_id: uuid.UUID,
    data: CrawlTaskUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    update_data = data.model_dump(exclude_unset=True, exclude={"urls"})
    if "name" in update_data:
        duplicate = repo.get_by_name(current_user.id, update_data["name"])
        if duplicate and duplicate.id != task.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"任务名称 '{update_data['name']}' 已存在")

    for field, value in update_data.items():
        setattr(task, field, value)

    if data.urls is not None:
        _check_urls_unique(data.urls)
        repo.replace_urls(task, data.urls)

    try:
        updated = repo.update(task)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务 URL 或名称重复") from exc
    return success(data=_serialize(updated).model_dump(mode="json"))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> None:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    repo.delete(task)
```

- [ ] **Step 4: Keep legacy route compatibility**

Modify `backend/app/modules/crawl_tasks/router.py` so the top docstring says:

```python
"""Compatibility routes for the old /api/crawl-tasks prefix.

The restored crawler task API uses /api/crawler/tasks. Keep this prefix for
stale browser bundles and existing bookmarks.
"""
```

Keep the existing `add_api_route` mapping to canonical functions unchanged.

- [ ] **Step 5: Run backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py -v
```

Expected: PASS after updating any old assertions in the file from raw lists to the canonical paginated wrapper.

- [ ] **Step 6: Commit backend API restoration**

Run:

```bash
git add backend/app/schemas/crawl_task.py backend/app/repositories/crawl_task.py backend/app/modules/crawler/tasks/router.py backend/app/modules/crawl_tasks/router.py backend/tests/test_crawl_tasks_api.py
git commit -m "feat(backend): restore crawler task url api"
```

Expected: one commit with backend restored task API.

---

### Task 3: Register Crawler Models With Init Bootstrap

**Files:**
- Modify: `backend/app/modules/init/database_bootstrap.py`
- Test: `backend/tests/test_init_database_bootstrap.py`
- Verify: `backend/alembic/versions/20260702_0001_restore_crawler_tasks.py`

- [ ] **Step 1: Add crawler task URL table coverage to bootstrap tests**

In `backend/tests/test_init_database_bootstrap.py`, update `test_import_application_models_registers_known_tables` to:

```python
def test_import_application_models_registers_known_tables() -> None:
    import_application_models()

    assert "users" in Base.metadata.tables
    assert "crawl_tasks" in Base.metadata.tables
    assert "crawl_task_urls" in Base.metadata.tables
```

Update `test_create_application_tables_uses_shared_metadata` to:

```python
def test_create_application_tables_uses_shared_metadata() -> None:
    engine = sqlite_engine()

    create_application_tables(engine)

    table_names = set(inspect(engine).get_table_names())
    assert "users" in table_names
    assert "crawl_tasks" in table_names
    assert "crawl_task_urls" in table_names
```

- [ ] **Step 2: Run the failing bootstrap table test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_init_database_bootstrap.py::test_create_application_tables_uses_shared_metadata -v
```

Expected: FAIL until `CrawlTaskUrl` exists and `backend.app.models.crawl_task` is registered in `APPLICATION_MODEL_MODULES`.

- [ ] **Step 3: Register crawler model module in the bootstrap service**

In `backend/app/modules/init/database_bootstrap.py`, ensure `APPLICATION_MODEL_MODULES` includes:

```python
APPLICATION_MODEL_MODULES = (
    "backend.app.models.user",
    "backend.app.models.crawl_task",
)
```

Do not add table creation logic to `backend/app/modules/init/router.py`; the router must continue to call `bootstrap_application_database()`.

- [ ] **Step 4: Verify init bootstrap creates crawler tables**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_init_database_bootstrap.py -v
```

Expected: PASS. `create_application_tables(engine)` creates `users`, `crawl_tasks`, and `crawl_task_urls` from `Base.metadata`.

- [ ] **Step 5: Verify Alembic can create the same schema**

Run:

```bash
source .venv/bin/activate
cd backend
alembic upgrade head
```

Expected: PASS on a fresh database. `crawl_tasks` and `crawl_task_urls` exist.

- [ ] **Step 6: Commit bootstrap registration**

Run:

```bash
git add backend/app/modules/init/database_bootstrap.py backend/tests/test_init_database_bootstrap.py
git commit -m "feat(init): register crawler task tables"
```

Expected: one commit registering crawler task models with unified init bootstrap.

---

### Task 4: Frontend API Types and URL Utilities

**Files:**
- Modify: `frontend/src/api/crawlTask/types.ts`
- Modify: `frontend/src/api/crawlTask/index.ts`
- Create: `frontend/src/pages/crawler/tasks/taskUrlUtils.ts`
- Create: `frontend/tests/task-url-utils.test.ts`

- [ ] **Step 1: Add URL utility tests**

Create `frontend/tests/task-url-utils.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { buildFinalUrlPreview, detectUrlType } from '../src/pages/crawler/tasks/taskUrlUtils'

describe('taskUrlUtils', () => {
  it('detects restored javdb URL types', () => {
    expect(detectUrlType('https://javdb.com/actors/abc')).toBe('actors')
    expect(detectUrlType('https://javdb.com/series/abc')).toBe('series')
    expect(detectUrlType('https://javdb.com/makers/abc')).toBe('makers')
    expect(detectUrlType('https://javdb.com/directors/abc')).toBe('directors')
    expect(detectUrlType('https://javdb.com/video_codes/abc')).toBe('video_codes')
    expect(detectUrlType('https://javdb.com/lists/abc')).toBe('lists')
    expect(detectUrlType('https://javdb.com/tags?c7=212')).toBe('tags')
    expect(detectUrlType('https://javdb.com/search?q=test')).toBe('search')
    expect(detectUrlType('not-a-url')).toBeNull()
  })

  it('builds search final url preview with subtitle and date sort', () => {
    expect(buildFinalUrlPreview('https://javdb.com/search?q=abc', 'search', false, true, 1)).toContain('f=cnsub')
    expect(buildFinalUrlPreview('https://javdb.com/search?q=abc', 'search', false, true, 1)).toContain('sb=1')
  })
})
```

- [ ] **Step 2: Run the failing utility tests**

Run:

```bash
cd frontend
npm test -- tests/task-url-utils.test.ts -- --run
```

Expected: FAIL because `taskUrlUtils.ts` does not exist.

- [ ] **Step 3: Replace task API types**

Replace `frontend/src/api/crawlTask/types.ts` with:

```ts
export interface TaskUrlEntry {
  id?: string
  position?: number
  url: string
  url_type: string
  has_magnet?: boolean
  has_chinese_sub?: boolean
  sort_type?: number
  source?: string
  final_url?: string
  url_name?: string | null
}

export interface CrawlTask {
  id: string
  _id?: string
  name: string
  urls: TaskUrlEntry[]
  is_skip: boolean
  status: string
  task_id: string | null
  error_message: string | null
  total_found: number
  total_qualified: number
  owner_id: string
  created_at: string
  updated_at: string | null
}

export interface PaginatedResponse<T> {
  rows: T[]
  total: number
  page?: number
  page_size?: number
  code?: number
  msg?: string
}

export interface CrawlTaskCreateParams {
  name: string
  urls: TaskUrlEntry[]
  is_skip?: boolean
}

export interface CrawlTaskUpdateParams {
  name?: string
  urls?: TaskUrlEntry[]
  is_skip?: boolean
}

export interface CrawlTaskStats {
  total: number
}
```

- [ ] **Step 4: Add extract-name API helper**

Modify `frontend/src/api/crawlTask/index.ts` to include:

```ts
export function extractTaskName(url: string, urlType: string): Promise<{ name: string }> {
  return request.post<{ name: string }>(`${BASE_URL}/extract-name`, {
    url,
    url_type: urlType,
  })
}
```

Keep the existing `getCrawlTasks`, `getCrawlTask`, `createCrawlTask`, `updateCrawlTask`, and `deleteCrawlTask` exports.

- [ ] **Step 5: Create URL utility module**

Create `frontend/src/pages/crawler/tasks/taskUrlUtils.ts`:

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

type CondParamConfig = {
  magnet: string
  sub: string
  both: string
}

const URL_TYPE_PARAMS: Record<string, CondParamConfig> = {
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

export const URL_TYPE_LABELS: Record<UrlType, string> = {
  actors: '演员 (actors)',
  series: '系列 (series)',
  makers: '片商 (makers)',
  directors: '导演 (directors)',
  video_codes: '番号 (video_codes)',
  lists: '列表 (lists)',
  tags: '标签 (tags)',
  search: '搜索 (search)',
}

export const SORT_OPTIONS = [
  { value: 0, label: '日期降序' },
  { value: 5, label: '番号降序' },
]

export const SEARCH_SORT_OPTIONS = [
  { value: 0, label: '按相关度' },
  { value: 1, label: '按发布日期' },
]

export function detectUrlType(url: string): UrlType | null {
  try {
    const parsed = new URL(url)
    const path = parsed.pathname
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

function stripQueryParams(rawUrl: string): string {
  try {
    const parsed = new URL(rawUrl)
    PARAM_KEYS.forEach((key) => parsed.searchParams.delete(key))
    const query = parsed.searchParams.toString()
    return parsed.pathname + (query ? `?${query}` : '')
  } catch {
    return rawUrl
  }
}

export function buildFinalUrlPreview(
  baseUrl: string,
  urlType: UrlType,
  hasMagnet: boolean,
  hasSub: boolean,
  sortType: number,
): string {
  if (!baseUrl) return baseUrl

  const stripped = stripQueryParams(baseUrl)
  const parts: string[] = []

  if (urlType === 'search') {
    if (hasMagnet) parts.push('f=download')
    else if (hasSub) parts.push('f=cnsub')
    parts.push(`sb=${sortType}`)
  } else {
    const cfg = URL_TYPE_PARAMS[urlType]
    if (hasMagnet && hasSub && cfg.both) parts.push(cfg.both)
    else if (hasMagnet) parts.push(cfg.magnet)
    else if (hasSub) parts.push(cfg.sub)
    if ((urlType === 'actors' || urlType === 'video_codes') && sortType !== 0) {
      parts.push(`sort=${sortType}`)
    }
  }

  if (parts.length === 0) return stripped

  try {
    const parsed = new URL(baseUrl)
    const base = parsed.origin + stripped
    return base + (stripped.includes('?') ? '&' : '?') + parts.join('&')
  } catch {
    return stripped + (stripped.includes('?') ? '&' : '?') + parts.join('&')
  }
}
```

- [ ] **Step 6: Run utility tests**

Run:

```bash
cd frontend
npm test -- tests/task-url-utils.test.ts -- --run
```

Expected: PASS.

- [ ] **Step 7: Commit frontend API and utilities**

Run:

```bash
git add frontend/src/api/crawlTask/types.ts frontend/src/api/crawlTask/index.ts frontend/src/pages/crawler/tasks/taskUrlUtils.ts frontend/tests/task-url-utils.test.ts
git commit -m "feat(frontend): restore crawler task url types"
```

Expected: one commit with frontend types and URL utilities.

---

### Task 5: Restore New Task Form

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
- Modify: `frontend/src/pages/crawler/tasks/TaskPages.module.less`
- Create: `frontend/tests/task-form-restore.ui.test.tsx`

- [ ] **Step 1: Write the failing form test**

Create `frontend/tests/task-form-restore.ui.test.tsx`:

```tsx
import { App as AntApp } from 'antd'
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskFormPage from '../src/pages/crawler/tasks/TaskFormPage'
import { createCrawlTask, extractTaskName, getCrawlTask, updateCrawlTask } from '../src/api/crawlTask'

vi.mock('../src/api/crawlTask', () => ({
  createCrawlTask: vi.fn(),
  extractTaskName: vi.fn(),
  getCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

function renderForm() {
  const rootRoute = createRootRoute({
    component: () => (
      <AntApp>
        <TaskFormPage />
      </AntApp>
    ),
  })
  const formRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks/new',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([formRoute]),
    history: createMemoryHistory({ initialEntries: ['/crawler/tasks/new'] }),
  })
  return render(<RouterProvider router={router} />)
}

describe('TaskFormPage restored crawler task form', () => {
  beforeEach(() => {
    vi.mocked(createCrawlTask).mockResolvedValue({} as never)
    vi.mocked(updateCrawlTask).mockResolvedValue({} as never)
    vi.mocked(getCrawlTask).mockResolvedValue({} as never)
    vi.mocked(extractTaskName).mockResolvedValue({ name: '演员 A' })
  })

  it('creates a task with restored url entry payload', async () => {
    renderForm()

    await userEvent.type(await screen.findByLabelText('任务名称'), '每日演员任务')
    await userEvent.type(screen.getByLabelText('URL'), 'https://javdb.com/actors/abc')
    await userEvent.click(screen.getByRole('switch', { name: '含磁力链接' }))
    await userEvent.click(screen.getByRole('button', { name: '创建' }))

    await waitFor(() => {
      expect(createCrawlTask).toHaveBeenCalledWith({
        name: '每日演员任务',
        is_skip: false,
        urls: [
          {
            url: 'https://javdb.com/actors/abc',
            url_type: 'actors',
            has_magnet: false,
            has_chinese_sub: false,
            sort_type: 0,
            url_name: '',
          },
        ],
      })
    })
  })
})
```

- [ ] **Step 2: Run the failing form test**

Run:

```bash
cd frontend
npm test -- tests/task-form-restore.ui.test.tsx -- --run
```

Expected: FAIL because the current form uses `keywords` and `target_websites`, not URL entries.

- [ ] **Step 3: Replace `TaskFormPage.tsx`**

Use the original `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/crawler/tasks/TaskForm.tsx` as the source, adapted to Media Forge imports:

```tsx
import { useCallback, useEffect, useMemo, useState } from 'react'
import { MinusCircleOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { useNavigate, useParams } from '@tanstack/react-router'
import { App, Button, Card, Col, Form, Input, Row, Select, Switch } from 'antd'
import {
  createCrawlTask,
  extractTaskName,
  getCrawlTask,
  updateCrawlTask,
} from '@/api/crawlTask'
import type { CrawlTaskCreateParams, TaskUrlEntry } from '@/api/crawlTask/types'
import {
  buildFinalUrlPreview,
  detectUrlType,
  SEARCH_SORT_OPTIONS,
  SORT_OPTIONS,
  type UrlType,
  URL_TYPE_LABELS,
} from './taskUrlUtils'
import styles from './TaskPages.module.less'

function UrlEntryCard({
  index,
  remove,
  onNameExtracted,
  onUrlTypeDetected,
}: {
  index: number
  remove?: () => void
  onNameExtracted: (index: number, name: string) => void
  onUrlTypeDetected: (index: number, urlType: UrlType) => void
}) {
  const { message } = App.useApp()
  const [extracting, setExtracting] = useState(false)

  return (
    <Card
      size="small"
      title={`URL ${index + 1}`}
      className={styles.urlCard}
      extra={
        remove ? (
          <Button type="text" danger icon={<MinusCircleOutlined />} onClick={remove} size="small" />
        ) : null
      }
    >
      <Form.Item noStyle shouldUpdate={(prev, cur) => prev.urls?.[index]?.url !== cur.urls?.[index]?.url}>
        {({ getFieldValue }) => {
          const url = getFieldValue(['urls', index, 'url']) as string
          const detected = url ? detectUrlType(url) : null
          const currentType = getFieldValue(['urls', index, 'url_type']) as UrlType | undefined

          if (detected && detected !== currentType) {
            window.setTimeout(() => onUrlTypeDetected(index, detected), 0)
          }

          return (
            <>
              <Form.Item name={[index, 'url']} label="URL" rules={[{ required: true, message: '请输入 URL' }]}>
                <Input placeholder="https://javdb.com/actors/..." />
              </Form.Item>
              <Form.Item label="URL 类型">
                <Input value={detected ? URL_TYPE_LABELS[detected] : url ? '无法识别' : '请输入 URL'} disabled />
              </Form.Item>
              <Form.Item name={[index, 'url_type']} hidden>
                <Input />
              </Form.Item>
            </>
          )
        }}
      </Form.Item>

      <Form.Item noStyle shouldUpdate={(prev, cur) => prev.urls?.[index]?.url_type !== cur.urls?.[index]?.url_type}>
        {({ getFieldValue }) => {
          const urlType = getFieldValue(['urls', index, 'url_type']) as UrlType
          if (!urlType) return null
          const sortOptions = urlType === 'search' ? SEARCH_SORT_OPTIONS : SORT_OPTIONS
          const showSort = urlType === 'video_codes' || urlType === 'search'
          return (
            <>
              <Form.Item name={[index, 'has_magnet']} label="含磁力链接" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item name={[index, 'has_chinese_sub']} label="含中文字幕" valuePropName="checked">
                <Switch />
              </Form.Item>
              {showSort ? (
                <Form.Item name={[index, 'sort_type']} label="排序方式">
                  <Select options={sortOptions} />
                </Form.Item>
              ) : null}
            </>
          )
        }}
      </Form.Item>

      <Form.Item noStyle shouldUpdate>
        {({ getFieldValue }) => {
          const baseUrl = (getFieldValue(['urls', index, 'url']) as string) ?? ''
          const urlType = getFieldValue(['urls', index, 'url_type']) as UrlType
          const hasMagnet = (getFieldValue(['urls', index, 'has_magnet']) as boolean) ?? false
          const hasSub = (getFieldValue(['urls', index, 'has_chinese_sub']) as boolean) ?? false
          const sortType = (getFieldValue(['urls', index, 'sort_type']) as number) ?? 0
          const finalUrl = urlType ? buildFinalUrlPreview(baseUrl, urlType, hasMagnet, hasSub, sortType) : baseUrl
          return (
            <Form.Item label="最终 URL 预览">
              <Input value={finalUrl} disabled />
            </Form.Item>
          )
        }}
      </Form.Item>

      <Form.Item noStyle shouldUpdate={(prev, cur) => prev.urls?.[index]?.url_name !== cur.urls?.[index]?.url_name}>
        {({ getFieldValue }) => {
          const urlName = getFieldValue(['urls', index, 'url_name']) as string | undefined
          return urlName ? (
            <Form.Item label="URL 名称">
              <Input value={urlName} disabled />
            </Form.Item>
          ) : null
        }}
      </Form.Item>

      <Form.Item noStyle shouldUpdate>
        {({ getFieldValue }) => {
          const url = getFieldValue(['urls', index, 'url']) as string
          const urlType = getFieldValue(['urls', index, 'url_type']) as string
          return (
            <Button
              icon={<SearchOutlined />}
              loading={extracting}
              disabled={!url || !urlType}
              onClick={async () => {
                setExtracting(true)
                try {
                  const result = await extractTaskName(url, urlType)
                  if (result.name) onNameExtracted(index, result.name)
                  else message.warning('未能提取到名称')
                } finally {
                  setExtracting(false)
                }
              }}
            >
              获取名称
            </Button>
          )
        }}
      </Form.Item>
    </Card>
  )
}

export default function TaskFormPage() {
  const params = useParams({ strict: false }) as { id?: string }
  const taskId = params.id
  const isEdit = Boolean(taskId)
  const navigate = useNavigate()
  const { message } = App.useApp()
  const [form] = Form.useForm<CrawlTaskCreateParams>()
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const title = useMemo(() => (isEdit ? '编辑任务' : '新建任务'), [isEdit])

  useEffect(() => {
    if (!isEdit || !taskId) return
    setLoading(true)
    getCrawlTask(taskId)
      .then((task) => {
        form.setFieldsValue({
          name: task.name,
          is_skip: task.is_skip,
          urls: task.urls.map((entry) => ({
            url: entry.url,
            url_type: entry.url_type,
            has_magnet: entry.has_magnet ?? true,
            has_chinese_sub: entry.has_chinese_sub ?? false,
            sort_type: entry.sort_type ?? 0,
            url_name: entry.url_name ?? '',
          })),
        })
      })
      .catch(() => message.error('任务详情加载失败'))
      .finally(() => setLoading(false))
  }, [form, isEdit, message, taskId])

  const setUrlEntryValue = useCallback(
    (index: number, patch: Partial<TaskUrlEntry>) => {
      const urls = form.getFieldValue('urls') ?? []
      form.setFieldsValue({
        urls: urls.map((entry: TaskUrlEntry, itemIndex: number) =>
          itemIndex === index ? { ...entry, ...patch } : entry,
        ),
      })
    },
    [form],
  )

  const handleSubmit = async (values: CrawlTaskCreateParams) => {
    const urlEntries = values.urls ?? []
    const urlSet = new Set<string>()
    for (const entry of urlEntries) {
      if (entry.url && urlSet.has(entry.url)) {
        message.error(`URL 重复: ${entry.url}`)
        return
      }
      if (entry.url) urlSet.add(entry.url)
    }

    setSubmitting(true)
    try {
      const payload: CrawlTaskCreateParams = {
        name: values.name,
        is_skip: values.is_skip ?? false,
        urls: urlEntries.map((entry) => ({
          url: entry.url,
          url_type: entry.url_type,
          has_magnet: entry.has_magnet ?? false,
          has_chinese_sub: entry.has_chinese_sub ?? false,
          sort_type: entry.sort_type ?? 0,
          url_name: entry.url_name ?? '',
        })),
      }
      if (isEdit && taskId) {
        await updateCrawlTask(taskId, payload)
        message.success('任务已更新')
      } else {
        await createCrawlTask(payload)
        message.success('任务已创建')
      }
      void navigate({ to: '/crawler/tasks' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{title}</h1>
          <p className={styles.subtitle}>按 URL 配置 JavDB 任务来源、筛选条件和排序规则。</p>
        </div>
      </div>

      <section className={`${styles.panel} ${styles.formPanel}`}>
        <Form<CrawlTaskCreateParams>
          form={form}
          layout="vertical"
          disabled={loading}
          onFinish={(values) => void handleSubmit(values)}
          initialValues={{
            urls: [{ has_magnet: true, has_chinese_sub: false, sort_type: 0 }],
            is_skip: false,
          }}
        >
          <Row gutter={24}>
            <Col flex="auto">
              <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称' }]}>
                <Input placeholder="例如：某演员名称" />
              </Form.Item>
            </Col>
            <Col flex="120px">
              <Form.Item name="is_skip" label="启用状态" valuePropName="checked">
                <Switch checkedChildren="禁用" unCheckedChildren="启用" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item label="URL 列表" required className={styles.urlListLabel} />

          <Form.List name="urls">
            {(fields, { add, remove }) => (
              <Row gutter={[16, 16]}>
                {fields.map((field) => (
                  <Col key={field.key} xs={24} lg={12} xl={8}>
                    <UrlEntryCard
                      index={field.name}
                      remove={fields.length > 1 ? () => remove(field.name) : undefined}
                      onNameExtracted={(index, name) => {
                        setUrlEntryValue(index, { url_name: name })
                        if (!form.getFieldValue('name')) form.setFieldsValue({ name })
                      }}
                      onUrlTypeDetected={(index, urlType) => setUrlEntryValue(index, { url_type: urlType })}
                    />
                  </Col>
                ))}
                <Col xs={24} lg={12} xl={8}>
                  <Button
                    type="dashed"
                    onClick={() => add({ has_magnet: true, has_chinese_sub: false, sort_type: 0 })}
                    icon={<PlusOutlined />}
                    className={styles.addUrlButton}
                  >
                    添加 URL
                  </Button>
                </Col>
              </Row>
            )}
          </Form.List>

          <div className={styles.actions}>
            <Button type="primary" htmlType="submit" loading={submitting}>
              {isEdit ? '更新' : '创建'}
            </Button>
            <Button onClick={() => navigate({ to: '/crawler/tasks' })}>取消</Button>
          </div>
        </Form>
      </section>
    </div>
  )
}
```

- [ ] **Step 4: Add form styles**

Append to `frontend/src/pages/crawler/tasks/TaskPages.module.less`:

```less
.urlListLabel {
  margin-bottom: 8px;
}

.urlCard {
  height: 100%;
}

.addUrlButton {
  width: 100%;
  min-height: 200px;
  height: 100%;
}
```

- [ ] **Step 5: Run the form test**

Run:

```bash
cd frontend
npm test -- tests/task-form-restore.ui.test.tsx -- --run
```

Expected: PASS.

- [ ] **Step 6: Commit restored form**

Run:

```bash
git add frontend/src/pages/crawler/tasks/TaskFormPage.tsx frontend/src/pages/crawler/tasks/TaskPages.module.less frontend/tests/task-form-restore.ui.test.tsx
git commit -m "feat(frontend): restore crawler task form"
```

Expected: one commit with restored task form.

---

### Task 6: Restore Task List Display

**Files:**
- Modify: `frontend/src/pages/crawlTasks/components/TaskListTable.tsx`
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/tests/App.test.tsx`
- Test: `frontend/tests/task-list-query-state.ui.test.tsx`

- [ ] **Step 1: Update the task list table**

Replace `frontend/src/pages/crawlTasks/components/TaskListTable.tsx` with:

```tsx
import { DeleteOutlined, EditOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Input, Space, Switch, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { CrawlTask } from '@/api/crawlTask/types'

type TaskListTableProps = {
  tasks: CrawlTask[]
  loading: boolean
  total: number
  current: number
  pageSize: number
  keyword: string
  onKeywordChange: (keyword: string) => void
  onPageChange: (page: number, pageSize: number) => void
  onEdit: (task: CrawlTask) => void
  onDelete: (task: CrawlTask) => void
  onToggleSkip: (task: CrawlTask) => void
  onSearch: (keyword: string) => void
}

function TaskListTable({
  tasks,
  loading,
  total,
  current,
  pageSize,
  keyword,
  onKeywordChange,
  onPageChange,
  onEdit,
  onDelete,
  onToggleSkip,
  onSearch,
}: TaskListTableProps) {
  const columns: ColumnsType<CrawlTask> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 220,
      ellipsis: true,
    },
    {
      title: 'URL 数量',
      key: 'url_count',
      width: 110,
      render: (_, record) => <Tag>{record.urls?.length ?? 0} 个 URL</Tag>,
    },
    {
      title: 'URL 名称',
      key: 'url_names',
      width: 280,
      render: (_, record) => {
        const names = record.urls?.filter((url) => url.url_name).map((url) => url.url_name) ?? []
        if (names.length === 0) return <Typography.Text type="secondary">-</Typography.Text>
        return (
          <Space size={4} wrap>
            {names.map((name, index) => (
              <Tag key={`${name}-${index}`}>{name}</Tag>
            ))}
          </Space>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'is_skip',
      key: 'is_skip',
      width: 100,
      render: (_, record) => (
        <Switch
          checked={!record.is_skip}
          onChange={() => onToggleSkip(record)}
          checkedChildren="启用"
          unCheckedChildren="禁用"
        />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 130,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="编辑">
            <Button type="text" size="small" icon={<EditOutlined />} onClick={() => onEdit(record)} />
          </Tooltip>
          <Tooltip title="删除">
            <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => onDelete(record)} />
          </Tooltip>
        </Space>
      ),
    },
  ]

  const pagination: TablePaginationConfig = {
    current,
    pageSize,
    total,
    showSizeChanger: true,
    showTotal: (count) => `共 ${count} 条`,
    onChange: onPageChange,
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder="搜索任务名称"
          allowClear
          enterButton={<SearchOutlined />}
          value={keyword}
          onChange={(event) => onKeywordChange(event.target.value)}
          onSearch={onSearch}
          style={{ maxWidth: 320 }}
        />
      </div>
      <Table rowKey="id" columns={columns} dataSource={tasks} loading={loading} pagination={pagination} />
    </div>
  )
}

export default TaskListTable
```

- [ ] **Step 2: Update TaskListPage actions**

In `frontend/src/pages/crawler/tasks/TaskListPage.tsx`, add `updateCrawlTask` to the API import:

```ts
import {
  deleteCrawlTask,
  getCrawlTasks,
  updateCrawlTask,
} from '@/api/crawlTask'
```

Add this callback before `return`:

```ts
  const handleToggleSkip = useCallback(
    async (task: CrawlTask) => {
      await updateCrawlTask(task.id, { is_skip: !task.is_skip })
      message.success(task.is_skip ? '任务已启用' : '任务已禁用')
      void fetchTasks(current, keyword)
    },
    [current, fetchTasks, keyword],
  )
```

Pass it to `TaskListTable`:

```tsx
          onToggleSkip={handleToggleSkip}
```

- [ ] **Step 3: Update frontend mocks**

In `frontend/tests/App.test.tsx`, replace the crawl task API mock with:

```ts
vi.mock('@/api/crawlTask', () => ({
  getCrawlTasks: vi.fn().mockResolvedValue({ rows: [], total: 0 }),
  deleteCrawlTask: vi.fn().mockResolvedValue(undefined),
  updateCrawlTask: vi.fn().mockResolvedValue(undefined),
}))
```

- [ ] **Step 4: Run task list tests**

Run:

```bash
cd frontend
npm test -- tests/task-list-query-state.ui.test.tsx tests/App.test.tsx -- --run
```

Expected: PASS. The list still preserves query state and renders the restored crawler task page.

- [ ] **Step 5: Commit restored list**

Run:

```bash
git add frontend/src/pages/crawlTasks/components/TaskListTable.tsx frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/tests/App.test.tsx
git commit -m "feat(frontend): restore crawler task list"
```

Expected: one commit with restored task list display and actions.

---

### Task 7: Final Verification

**Files:**
- Verify: backend and frontend files changed in Tasks 1-6.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd frontend
npm test -- tests/task-url-utils.test.ts tests/task-form-restore.ui.test.tsx tests/task-list-query-state.ui.test.tsx tests/App.test.tsx -- --run
```

Expected: PASS.

- [ ] **Step 3: Run backend full tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests -v
```

Expected: PASS, or only unrelated pre-existing failures with exact failing test names captured.

- [ ] **Step 4: Run frontend lint and build**

Run:

```bash
cd frontend
npm run lint
npm run build
```

Expected: PASS.

- [ ] **Step 5: Initialize the new database through unified init bootstrap**

Complete `docs/superpowers/plans/2026-07-02-init-database-bootstrap.md`, then start the backend and submit `/init` with:

```text
databaseHost=localhost
databasePort=54329
databaseName=mediaforge
databaseUser=admin
databasePassword=admin123
redisHost=localhost
redisPort=6379
```

Expected: unified init bootstrap creates the `mediaforge` database if missing, creates `users`, `crawl_tasks`, and `crawl_task_urls`, then inserts the default admin user if missing.

- [ ] **Step 6: Manual smoke test**

In the browser:

1. Log in as `admin / admin123`.
2. Open `/crawler/tasks`.
3. Click `新建任务`.
4. Enter `任务名称 = 每日演员任务`.
5. Enter `URL = https://javdb.com/actors/abc`.
6. Confirm URL type shows `演员 (actors)`.
7. Confirm final URL preview includes `page=1`.
8. Click `创建`.
9. Confirm task list shows `每日演员任务`, `1 个 URL`, status switch, edit and delete actions.

Expected: all nine steps work without console errors.

---

## Self-Review

- Spec coverage: Restores the crawler task list and new-task flow from `jav-scrapling`, registers crawler task tables with the unified init bootstrap plan, and normalizes original `urls` into `crawl_task_urls`.
- Scope control: Does not implement run history, schedules, storage integration, or queue workers beyond fields/actions needed for task list/new-task restoration.
- URL table decision: Child table is explicitly selected and justified.
- Placeholder scan: Every implementation step contains concrete commands or code.
- Type consistency: Backend `TaskUrlEntryCreate` maps to frontend `TaskUrlEntry`; API payloads use `urls`, `url_type`, `has_magnet`, `has_chinese_sub`, `sort_type`, `url_name`, `is_skip`.
