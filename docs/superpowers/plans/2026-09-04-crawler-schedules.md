# Crawler Schedules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build per-user crawler schedule configurations that use APScheduler to run selected crawler tasks incrementally and optionally create one merged storage task for movies saved by that scheduled trigger.

**Architecture:** Add persistent schedule and schedule-run models, wrap APScheduler in a narrow crawler schedules module, and invoke the existing crawler run queue for execution. Automatic storage is coordinated after linked crawler runs reach terminal states and reuses the existing storage task creation service.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, APScheduler, React 19, Vite, TypeScript, Ant Design 6, TanStack Query.

**Spec:** `docs/superpowers/specs/2026-09-04-crawler-schedules-design.md`

## Global Constraints

- Do not create or use a Git worktree for this repository.
- Stage intended source files explicitly before every commit.
- Scheduled crawler runs are always incremental.
- One schedule configuration can contain multiple crawler tasks.
- Support daily recurrence and weekly recurrence with one time of day.
- Automatic storage includes only movies saved by the current scheduled trigger.
- Automatic storage creates one merged storage task per schedule trigger.
- Use the server local timezone for schedule evaluation in this iteration.
- Do not add arbitrary cron expression editing, monthly schedules, interval schedules, one-time schedules, or multiple times per day.
- Do not change manual crawler run behavior or crawler queue execution semantics.

---

## File Structure

Backend files to create:

- `backend/app/models/crawler_schedule.py`: SQLAlchemy schedule, schedule-task link, schedule-run, and schedule-run-to-crawl-run models.
- `backend/app/modules/crawler/schedules/__init__.py`: package marker.
- `backend/app/modules/crawler/schedules/schemas.py`: request and response models.
- `backend/app/modules/crawler/schedules/serializers.py`: conversion from models to response dictionaries.
- `backend/app/modules/crawler/schedules/service.py`: CRUD, validation, and scheduler synchronization.
- `backend/app/modules/crawler/schedules/scheduler.py`: APScheduler lifecycle and job registration boundary.
- `backend/app/modules/crawler/schedules/executor.py`: schedule trigger execution.
- `backend/app/modules/crawler/schedules/storage.py`: post-run automatic storage coordinator.
- `backend/app/modules/crawler/schedules/router.py`: FastAPI routes.
- `backend/tests/test_crawler_schedules_models.py`: model and serialization tests.
- `backend/tests/test_crawler_schedules_api.py`: CRUD and route tests.
- `backend/tests/test_crawler_schedules_executor.py`: trigger, overlap, and APScheduler boundary tests.
- `backend/tests/test_crawler_schedule_storage.py`: run-finalization storage coordinator tests.
- `sql/2026-09-04-crawler-schedules.sql`: root SQL change file matching the Alembic migration.

Backend files to modify:

- `backend/requirements.txt`: add APScheduler.
- `backend/app/models/__init__.py`: import and export new schedule models.
- `backend/app/models/crawl_run.py`: add schedule source metadata to `CrawlRun` and `movie_id` to `CrawlRunDetailTask`.
- `backend/app/modules/crawler/runtime/service.py`: allow `create_run()` to receive trigger metadata.
- `backend/app/modules/crawler/runtime/callbacks.py`: store `movie_id` on saved detail rows.
- `backend/app/modules/crawler/runtime/threaded.py`: store `movie_id` on saved threaded detail rows.
- `backend/app/modules/crawler/runtime/finalize.py`: call schedule storage coordinator after run finalization commits.
- `backend/app/modules/storage/tasks/service.py`: expose `create_schedule_push()` as the schedule-facing storage creation method.
- `backend/app/main.py`: include router and start/stop the scheduler in lifespan.
- `backend/alembic/versions/20260904_0001_add_crawler_schedules.py`: database migration.
- `backend/tests/conftest.py`: patch scheduler startup/shutdown in the TestClient fixture.

Frontend files to create:

- `frontend/src/api/crawler/crawlerSchedule/types.ts`: schedule API types.
- `frontend/src/api/crawler/crawlerSchedule/index.ts`: schedule API client functions.
- `frontend/src/pages/crawler/schedules/ScheduleListPage.tsx`: list page and action orchestration.
- `frontend/src/pages/crawler/schedules/SchedulePages.module.less`: page styles.
- `frontend/src/pages/crawler/schedules/components/ScheduleFormDrawer.tsx`: create/edit drawer.
- `frontend/src/pages/crawler/schedules/components/ScheduleHistoryDrawer.tsx`: history drawer.
- `frontend/src/pages/crawler/schedules/utils/recurrence.ts`: recurrence display helpers.
- `frontend/src/pages/crawler/schedules/__tests__/schedule-form.test.tsx`: form tests.
- `frontend/src/pages/crawler/schedules/__tests__/schedule-list-actions.test.tsx`: list action tests.

Frontend files to modify:

- `frontend/src/api/queryKeys.ts`: add crawler schedule query keys.
- `frontend/src/api/queryInvalidation.ts`: add crawler schedule invalidation helper.
- `frontend/src/routes/index.tsx`: register `/crawler/schedules`.
- `frontend/src/routes/tags.ts`: add schedule route metadata.
- `frontend/src/layout/Sidebar/index.tsx`: add a schedule menu item under crawler.

---

### Task 1: Database Models And Migration

**Files:**
- Create: `backend/app/models/crawler_schedule.py`
- Create: `backend/alembic/versions/20260904_0001_add_crawler_schedules.py`
- Create: `sql/2026-09-04-crawler-schedules.sql`
- Create: `backend/tests/test_crawler_schedules_models.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/crawl_run.py`

**Interfaces:**
- Produces: `CrawlerSchedule`, `crawler_schedule_tasks`, `CrawlerScheduleRun`, `CrawlerScheduleRunCrawlRun`.
- Produces: `CrawlRun.trigger_source: str | None`, `CrawlRun.schedule_id: UUID | None`, `CrawlRun.schedule_run_id: UUID | None`.
- Produces: `CrawlRunDetailTask.movie_id: UUID | None`.

- [ ] **Step 1: Write the failing model relationship test**

Add this test to `backend/tests/test_crawler_schedules_models.py`:

```python
import uuid
from datetime import datetime

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.models.crawler_schedule import (
    CrawlerSchedule,
    CrawlerScheduleRun,
    CrawlerScheduleRunCrawlRun,
)


def test_schedule_model_links_tasks_runs_and_saved_movies(db_session, test_user):
    task = CrawlTask(
        owner_id=test_user.id,
        name="JavDB",
        storage_location="JavDB",
        is_skip=False,
    )
    schedule = CrawlerSchedule(
        owner_id=test_user.id,
        name="Nightly",
        enabled=True,
        schedule_type="daily",
        time_of_day="03:30",
        weekdays=[],
        auto_storage_enabled=True,
        storage_mode="single",
        selected_storage_location=None,
    )
    schedule.tasks.append(task)
    db_session.add(schedule)
    db_session.commit()
    db_session.refresh(schedule)

    schedule_run = CrawlerScheduleRun(
        schedule_id=schedule.id,
        owner_id=test_user.id,
        status="running",
        trigger_type="scheduled",
        triggered_at=datetime.now(),
        result={"accepted": []},
        storage_status="pending",
    )
    crawl_run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="queued",
        crawl_mode="incremental",
        trigger_source="schedule",
        schedule_id=schedule.id,
        schedule_run_id=schedule_run.id,
    )
    link = CrawlerScheduleRunCrawlRun(schedule_run=schedule_run, crawl_run=crawl_run, task_id=task.id)
    detail = CrawlRunDetailTask(
        run=crawl_run,
        task_name=task.name,
        source_url="https://example.test/movie",
        source_name="Example",
        status="saved",
        created_at=datetime.now(),
        movie_id=uuid.uuid4(),
    )
    db_session.add_all([schedule_run, crawl_run, link, detail])
    db_session.commit()
    db_session.refresh(schedule_run)

    assert schedule.tasks[0].id == task.id
    assert schedule_run.crawl_run_links[0].crawl_run_id == crawl_run.id
    assert crawl_run.schedule_run_id == schedule_run.id
    assert crawl_run.detail_tasks[0].movie_id is not None
```

- [ ] **Step 2: Run the model test to verify it fails**

Run: `cd backend && python -m pytest tests/test_crawler_schedules_models.py::test_schedule_model_links_tasks_runs_and_saved_movies -v`

Expected: FAIL with an import error for `backend.app.models.crawler_schedule` or missing fields on `CrawlRun`.

- [ ] **Step 3: Add SQLAlchemy models**

Create `backend/app/models/crawler_schedule.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from shared.database.types import CompatibleJSON


class CrawlerSchedule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawler_schedules"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_crawler_schedules_owner_name"),
        Index("idx_crawler_schedules_owner_enabled", "owner_id", "enabled"),
        Index("idx_crawler_schedules_next_run", "enabled", "next_run_at"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schedule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    time_of_day: Mapped[str] = mapped_column(String(5), nullable=False)
    weekdays: Mapped[list[int]] = mapped_column(CompatibleJSON, nullable=False, default=list)
    auto_storage_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    storage_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="single")
    selected_storage_location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(nullable=True)

    tasks: Mapped[list["CrawlTask"]] = relationship(
        secondary="crawler_schedule_tasks",
        lazy="selectin",
    )
    runs: Mapped[list["CrawlerScheduleRun"]] = relationship(
        back_populates="schedule",
        cascade="all, delete-orphan",
        order_by="CrawlerScheduleRun.triggered_at.desc()",
        lazy="selectin",
    )


class CrawlerScheduleTask(Base):
    __tablename__ = "crawler_schedule_tasks"
    __table_args__ = (
        UniqueConstraint("schedule_id", "task_id", name="uq_crawler_schedule_tasks_schedule_task"),
        Index("idx_crawler_schedule_tasks_schedule_id", "schedule_id"),
        Index("idx_crawler_schedule_tasks_task_id", "task_id"),
    )

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawler_schedules.id", ondelete="CASCADE"),
        primary_key=True,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )


class CrawlerScheduleRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawler_schedule_runs"
    __table_args__ = (
        Index("idx_crawler_schedule_runs_schedule_triggered", "schedule_id", "triggered_at"),
        Index("idx_crawler_schedule_runs_owner_status", "owner_id", "status"),
    )

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawler_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    result: Mapped[dict] = mapped_column(CompatibleJSON, nullable=False, default=dict)
    storage_status: Mapped[str] = mapped_column(String(30), nullable=False, default="disabled")
    storage_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("storage_main_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    storage_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    schedule: Mapped[CrawlerSchedule] = relationship(back_populates="runs")
    crawl_run_links: Mapped[list["CrawlerScheduleRunCrawlRun"]] = relationship(
        back_populates="schedule_run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CrawlerScheduleRunCrawlRun(Base):
    __tablename__ = "crawler_schedule_run_crawl_runs"
    __table_args__ = (
        UniqueConstraint("schedule_run_id", "crawl_run_id", name="uq_crawler_schedule_run_crawl_run"),
        Index("idx_crawler_schedule_run_crawl_runs_schedule_run", "schedule_run_id"),
        Index("idx_crawler_schedule_run_crawl_runs_crawl_run", "crawl_run_id"),
    )

    schedule_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawler_schedule_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    crawl_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawl_tasks.id", ondelete="SET NULL"), nullable=True)

    schedule_run: Mapped[CrawlerScheduleRun] = relationship(back_populates="crawl_run_links")
    crawl_run: Mapped["CrawlRun"] = relationship(lazy="joined")
```

- [ ] **Step 4: Extend crawl run models and model exports**

Modify `backend/app/models/crawl_run.py`:

```python
class CrawlRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    # existing fields
    trigger_source: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawler_schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    schedule_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawler_schedule_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class CrawlRunDetailTask(Base, UUIDPrimaryKeyMixin):
    # existing fields
    movie_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("movies.id", ondelete="SET NULL"), nullable=True, index=True)
```

Modify `backend/app/models/__init__.py` to import and export all new schedule models.

- [ ] **Step 5: Add Alembic migration and root SQL**

The Alembic migration must create the four schedule tables and add these columns:

```python
op.add_column("crawl_runs", sa.Column("trigger_source", sa.String(length=30), nullable=True))
op.add_column("crawl_runs", sa.Column("schedule_id", sa.UUID(), nullable=True))
op.add_column("crawl_runs", sa.Column("schedule_run_id", sa.UUID(), nullable=True))
op.add_column("crawl_run_detail_tasks", sa.Column("movie_id", sa.UUID(), nullable=True))
```

It must also add indexes and foreign keys matching the SQLAlchemy models, and the downgrade must drop them in reverse dependency order.

Create `sql/2026-09-04-crawler-schedules.sql` with equivalent PostgreSQL DDL for manual deployment.

- [ ] **Step 6: Run model tests**

Run: `cd backend && python -m pytest tests/test_crawler_schedules_models.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/crawler_schedule.py backend/app/models/crawl_run.py backend/app/models/__init__.py backend/alembic/versions/20260904_0001_add_crawler_schedules.py backend/tests/test_crawler_schedules_models.py sql/2026-09-04-crawler-schedules.sql
git diff --cached --name-only
git commit -m "feat: add crawler schedule models"
```

---

### Task 2: Schedule Schemas, Serialization, And Service Validation

**Files:**
- Create: `backend/app/modules/crawler/schedules/__init__.py`
- Create: `backend/app/modules/crawler/schedules/schemas.py`
- Create: `backend/app/modules/crawler/schedules/serializers.py`
- Create: `backend/app/modules/crawler/schedules/service.py`
- Create: `backend/tests/test_crawler_schedules_api.py`

**Interfaces:**
- Consumes: models from Task 1.
- Produces: `CrawlerScheduleService.create_schedule(data, owner_id) -> CrawlerSchedule`.
- Produces: `CrawlerScheduleService.update_schedule(schedule_id, data, owner_id) -> CrawlerSchedule`.
- Produces: `CrawlerScheduleService.list_schedules(owner_id, page, size) -> dict`.
- Produces: `CrawlerScheduleService.get_schedule(schedule_id, owner_id) -> dict`.
- Produces: `CrawlerScheduleService.enable_schedule(schedule_id, owner_id) -> CrawlerSchedule`.
- Produces: `CrawlerScheduleService.disable_schedule(schedule_id, owner_id) -> CrawlerSchedule`.
- Produces: `calculate_next_run_at(schedule_type: str, time_of_day: str, weekdays: list[int], now: datetime | None = None) -> datetime`.

- [ ] **Step 1: Write failing validation and serialization tests**

Add tests to `backend/tests/test_crawler_schedules_api.py`:

```python
from datetime import datetime

import pytest
from fastapi import HTTPException

from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.schedules.schemas import CrawlerScheduleCreate
from backend.app.modules.crawler.schedules.service import CrawlerScheduleService, calculate_next_run_at


def seed_task(db_session, owner_id, name="Task", is_skip=False):
    task = CrawlTask(owner_id=owner_id, name=name, storage_location=name, is_skip=is_skip)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def test_create_schedule_requires_owned_tasks(db_session, test_user, other_user):
    other_task = seed_task(db_session, other_user.id, "Other")
    service = CrawlerScheduleService(db_session, scheduler=None)
    data = CrawlerScheduleCreate(
        name="Nightly",
        enabled=True,
        task_ids=[other_task.id],
        schedule_type="daily",
        time_of_day="03:30",
        weekdays=[],
        auto_storage_enabled=False,
        storage_mode="single",
        selected_storage_location=None,
    )

    with pytest.raises(HTTPException) as exc:
        service.create_schedule(data, test_user.id)

    assert exc.value.status_code == 400
    assert "任务不存在或无权限" in str(exc.value.detail)


def test_create_weekly_schedule_normalizes_weekdays(db_session, test_user):
    task = seed_task(db_session, test_user.id)
    service = CrawlerScheduleService(db_session, scheduler=None)
    data = CrawlerScheduleCreate(
        name="Weekday",
        enabled=True,
        task_ids=[task.id, task.id],
        schedule_type="weekly",
        time_of_day="04:15",
        weekdays=[4, 0, 4],
        auto_storage_enabled=True,
        storage_mode="single",
        selected_storage_location="",
    )

    schedule = service.create_schedule(data, test_user.id)

    assert schedule.weekdays == [0, 4]
    assert [t.id for t in schedule.tasks] == [task.id]
    assert schedule.selected_storage_location is None
    assert schedule.next_run_at is not None


def test_calculate_next_run_at_daily_moves_to_tomorrow_after_time():
    now = datetime(2026, 9, 4, 5, 0)
    next_run = calculate_next_run_at("daily", "03:30", [], now=now)
    assert next_run == datetime(2026, 9, 5, 3, 30)


def test_calculate_next_run_at_weekly_uses_selected_weekdays():
    now = datetime(2026, 9, 4, 5, 0)  # Friday
    next_run = calculate_next_run_at("weekly", "03:30", [0], now=now)
    assert next_run == datetime(2026, 9, 7, 3, 30)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_crawler_schedules_api.py -v`

Expected: FAIL because schedule schemas and service do not exist.

- [ ] **Step 3: Add Pydantic schemas**

Create `backend/app/modules/crawler/schedules/schemas.py`:

```python
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


ScheduleType = Literal["daily", "weekly"]
StorageMode = Literal["single", "multiple"]
TriggerType = Literal["scheduled", "manual"]


class CrawlerScheduleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    enabled: bool = True
    schedule_type: ScheduleType
    time_of_day: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekdays: list[int] = Field(default_factory=list)
    auto_storage_enabled: bool = False
    storage_mode: StorageMode = "single"
    selected_storage_location: str | None = Field(default=None, max_length=500)

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("weekdays must contain values from 0 to 6")
        return value


class CrawlerScheduleCreate(CrawlerScheduleBase):
    task_ids: list[uuid.UUID] = Field(..., min_length=1)


class CrawlerScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    task_ids: list[uuid.UUID] | None = None
    schedule_type: ScheduleType | None = None
    time_of_day: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekdays: list[int] | None = None
    auto_storage_enabled: bool | None = None
    storage_mode: StorageMode | None = None
    selected_storage_location: str | None = Field(default=None, max_length=500)


class CrawlerScheduleTaskSummary(BaseModel):
    id: uuid.UUID
    name: str
    is_skip: bool


class CrawlerScheduleRead(CrawlerScheduleBase):
    id: uuid.UUID
    task_count: int
    tasks: list[CrawlerScheduleTaskSummary] = []
    last_triggered_at: datetime | None = None
    next_run_at: datetime | None = None
    latest_run_status: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CrawlerScheduleListResponse(BaseModel):
    rows: list[CrawlerScheduleRead]
    total: int
    page: int
    size: int
```

- [ ] **Step 4: Add serializers**

Create `backend/app/modules/crawler/schedules/serializers.py`:

```python
from backend.app.models.crawler_schedule import CrawlerSchedule, CrawlerScheduleRun
from backend.app.modules.crawler.schedules.schemas import CrawlerScheduleRead, CrawlerScheduleTaskSummary


def serialize_schedule(schedule: CrawlerSchedule) -> CrawlerScheduleRead:
    latest = schedule.runs[0] if schedule.runs else None
    return CrawlerScheduleRead(
        id=schedule.id,
        name=schedule.name,
        enabled=schedule.enabled,
        schedule_type=schedule.schedule_type,
        time_of_day=schedule.time_of_day,
        weekdays=schedule.weekdays or [],
        auto_storage_enabled=schedule.auto_storage_enabled,
        storage_mode=schedule.storage_mode,
        selected_storage_location=schedule.selected_storage_location,
        task_count=len(schedule.tasks),
        tasks=[
            CrawlerScheduleTaskSummary(id=task.id, name=task.name, is_skip=task.is_skip)
            for task in schedule.tasks
        ],
        last_triggered_at=schedule.last_triggered_at,
        next_run_at=schedule.next_run_at,
        latest_run_status=latest.status if latest else None,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )
```

- [ ] **Step 5: Add service validation and persistence**

Create `backend/app/modules/crawler/schedules/service.py` with these concrete helpers:

```python
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.crawl_task import CrawlTask
from backend.app.models.crawler_schedule import CrawlerSchedule
from backend.app.modules.crawler.schedules.schemas import CrawlerScheduleCreate, CrawlerScheduleListResponse, CrawlerScheduleUpdate
from backend.app.modules.crawler.schedules.serializers import serialize_schedule


def normalize_weekdays(schedule_type: str, weekdays: list[int]) -> list[int]:
    if schedule_type == "daily":
        return []
    normalized = sorted(set(weekdays))
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="每周定时至少选择一天")
    if any(day < 0 or day > 6 for day in normalized):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="星期只能是 0 到 6")
    return normalized


def calculate_next_run_at(schedule_type: str, time_of_day: str, weekdays: list[int], now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    hour, minute = [int(part) for part in time_of_day.split(":", 1)]
    if schedule_type == "daily":
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return candidate if candidate > now else candidate + timedelta(days=1)
    normalized = normalize_weekdays(schedule_type, weekdays)
    for offset in range(0, 8):
        candidate_day = now + timedelta(days=offset)
        if candidate_day.weekday() not in normalized:
            continue
        candidate = candidate_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return candidate
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法计算下次执行时间")
```

Then implement `CrawlerScheduleService`:

```python
class CrawlerScheduleService:
    def __init__(self, db: Session, scheduler=None) -> None:
        self.db = db
        self.scheduler = scheduler

    def _owned_tasks(self, task_ids: list[uuid.UUID], owner_id: uuid.UUID) -> list[CrawlTask]:
        unique_ids = list(dict.fromkeys(task_ids))
        if not unique_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少选择 1 个任务")
        tasks = self.db.query(CrawlTask).filter(CrawlTask.owner_id == owner_id, CrawlTask.id.in_(unique_ids)).all()
        by_id = {task.id: task for task in tasks}
        if len(by_id) != len(unique_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务不存在或无权限")
        return [by_id[task_id] for task_id in unique_ids]

    def _sync_job(self, schedule: CrawlerSchedule) -> None:
        if self.scheduler is None:
            return
        if schedule.enabled:
            self.scheduler.upsert_schedule_job(schedule)
        else:
            self.scheduler.remove_schedule_job(schedule.id)

    def create_schedule(self, data: CrawlerScheduleCreate, owner_id: uuid.UUID) -> CrawlerSchedule:
        tasks = self._owned_tasks(list(data.task_ids), owner_id)
        weekdays = normalize_weekdays(data.schedule_type, data.weekdays)
        schedule = CrawlerSchedule(
            owner_id=owner_id,
            name=data.name.strip(),
            enabled=data.enabled,
            schedule_type=data.schedule_type,
            time_of_day=data.time_of_day,
            weekdays=weekdays,
            auto_storage_enabled=data.auto_storage_enabled,
            storage_mode=data.storage_mode,
            selected_storage_location=(data.selected_storage_location or "").strip() or None,
            next_run_at=calculate_next_run_at(data.schedule_type, data.time_of_day, weekdays),
        )
        schedule.tasks = tasks
        self.db.add(schedule)
        self.db.commit()
        self.db.refresh(schedule)
        self._sync_job(schedule)
        return schedule
```

Implement get and list:

```python
    def get_owned_model(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> CrawlerSchedule:
        schedule = self.db.get(CrawlerSchedule, schedule_id)
        if schedule is None or schedule.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="定时配置不存在")
        return schedule

    def get_schedule(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> dict:
        return serialize_schedule(self.get_owned_model(schedule_id, owner_id)).model_dump(mode="json")

    def list_schedules(self, owner_id: uuid.UUID, *, page: int, size: int) -> dict:
        query = self.db.query(CrawlerSchedule).filter(CrawlerSchedule.owner_id == owner_id)
        total = query.count()
        rows = query.order_by(CrawlerSchedule.created_at.desc()).offset((page - 1) * size).limit(size).all()
        return CrawlerScheduleListResponse(
            rows=[serialize_schedule(row) for row in rows],
            total=total,
            page=page,
            size=size,
        ).model_dump(mode="json")
```

Implement update:

```python
    def update_schedule(self, schedule_id: uuid.UUID, data: CrawlerScheduleUpdate, owner_id: uuid.UUID) -> CrawlerSchedule:
        schedule = self.get_owned_model(schedule_id, owner_id)
        update_data = data.model_dump(exclude_unset=True)
        if "name" in update_data and update_data["name"] is not None:
            schedule.name = update_data["name"].strip()
        next_type = update_data.get("schedule_type", schedule.schedule_type)
        next_time = update_data.get("time_of_day", schedule.time_of_day)
        next_weekdays = update_data.get("weekdays", schedule.weekdays or [])
        if "schedule_type" in update_data or "time_of_day" in update_data or "weekdays" in update_data:
            schedule.schedule_type = next_type
            schedule.time_of_day = next_time
            schedule.weekdays = normalize_weekdays(next_type, next_weekdays)
            schedule.next_run_at = calculate_next_run_at(schedule.schedule_type, schedule.time_of_day, schedule.weekdays)
        if "enabled" in update_data and update_data["enabled"] is not None:
            schedule.enabled = update_data["enabled"]
        if "auto_storage_enabled" in update_data and update_data["auto_storage_enabled"] is not None:
            schedule.auto_storage_enabled = update_data["auto_storage_enabled"]
        if "storage_mode" in update_data and update_data["storage_mode"] is not None:
            schedule.storage_mode = update_data["storage_mode"]
        if "selected_storage_location" in update_data:
            schedule.selected_storage_location = (update_data["selected_storage_location"] or "").strip() or None
        if data.task_ids is not None:
            schedule.tasks = self._owned_tasks(list(data.task_ids), owner_id)
        self.db.commit()
        self.db.refresh(schedule)
        self._sync_job(schedule)
        return schedule
```

- [ ] **Step 6: Run service tests**

Run: `cd backend && python -m pytest tests/test_crawler_schedules_api.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/schedules/__init__.py backend/app/modules/crawler/schedules/schemas.py backend/app/modules/crawler/schedules/serializers.py backend/app/modules/crawler/schedules/service.py backend/tests/test_crawler_schedules_api.py
git diff --cached --name-only
git commit -m "feat: validate crawler schedules"
```

---

### Task 3: APScheduler Lifecycle And Schedule Trigger Execution

**Files:**
- Create: `backend/app/modules/crawler/schedules/scheduler.py`
- Create: `backend/app/modules/crawler/schedules/executor.py`
- Create: `backend/tests/test_crawler_schedules_executor.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: `CrawlerScheduleService` and models from Tasks 1-2.
- Produces: `CrawlerScheduleScheduler.start() -> None`, `shutdown() -> None`, `load_enabled_schedules() -> None`, `upsert_schedule_job(schedule) -> None`, `remove_schedule_job(schedule_id) -> None`.
- Produces: `execute_schedule(schedule_id: UUID, trigger_type: str = "scheduled") -> CrawlerScheduleRun | None`.
- Extends: `CrawlerRunService.create_run(task, crawl_mode, selected_task_url_ids=None, trigger_source=None, schedule_id=None, schedule_run_id=None)`.

- [ ] **Step 1: Add APScheduler dependency**

Modify `backend/requirements.txt`:

```text
apscheduler>=3.10.4,<4.0.0
```

- [ ] **Step 2: Write failing executor tests**

Add tests to `backend/tests/test_crawler_schedules_executor.py`:

```python
from datetime import datetime
from unittest.mock import Mock

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.app.models.crawler_schedule import CrawlerSchedule, CrawlerScheduleRun
from backend.app.modules.crawler.schedules.executor import execute_schedule


def seed_schedule(db_session, test_user, *, enabled=True):
    task = CrawlTask(owner_id=test_user.id, name="Task", storage_location="Task", is_skip=False)
    schedule = CrawlerSchedule(
        owner_id=test_user.id,
        name="Nightly",
        enabled=enabled,
        schedule_type="daily",
        time_of_day="03:30",
        weekdays=[],
        auto_storage_enabled=False,
        storage_mode="single",
        next_run_at=datetime(2026, 9, 5, 3, 30),
    )
    schedule.tasks.append(task)
    db_session.add(schedule)
    db_session.commit()
    db_session.refresh(schedule)
    return schedule, task


def test_execute_schedule_creates_incremental_run(db_session, test_user, monkeypatch):
    schedule, task = seed_schedule(db_session, test_user)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started", lambda runtime: None)

    schedule_run = execute_schedule(schedule.id, db_factory=lambda: db_session, trigger_type="manual")

    crawl_run = db_session.query(CrawlRun).filter(CrawlRun.task_id == task.id).one()
    assert schedule_run is not None
    assert schedule_run.trigger_type == "manual"
    assert crawl_run.crawl_mode == "incremental"
    assert crawl_run.trigger_source == "schedule"
    assert crawl_run.schedule_id == schedule.id
    assert crawl_run.schedule_run_id == schedule_run.id


def test_execute_schedule_skips_when_existing_linked_run_active(db_session, test_user, monkeypatch):
    schedule, task = seed_schedule(db_session, test_user)
    first_history = CrawlerScheduleRun(
        schedule_id=schedule.id,
        owner_id=test_user.id,
        status="running",
        trigger_type="scheduled",
        triggered_at=datetime.now(),
        result={},
        storage_status="disabled",
    )
    active_run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        schedule_id=schedule.id,
        schedule_run_id=first_history.id,
    )
    db_session.add_all([first_history, active_run])
    db_session.commit()

    schedule_run = execute_schedule(schedule.id, db_factory=lambda: db_session)

    assert schedule_run.status == "skipped"
    assert schedule_run.result["reason"] == "previous_run_active"
```

- [ ] **Step 3: Run executor tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_crawler_schedules_executor.py -v`

Expected: FAIL because executor does not exist.

- [ ] **Step 4: Extend `CrawlerRunService.create_run()`**

Modify `backend/app/modules/crawler/runtime/service.py` signature and model creation:

```python
def create_run(
    self,
    task: CrawlTask,
    crawl_mode: str,
    *,
    selected_task_url_ids: list[uuid.UUID] | None = None,
    trigger_source: str | None = None,
    schedule_id: uuid.UUID | None = None,
    schedule_run_id: uuid.UUID | None = None,
) -> CrawlRun:
    # existing validation
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="queued",
        crawl_mode=crawl_mode,
        queued_at=datetime.now(),
        result=result,
        trigger_source=trigger_source,
        schedule_id=schedule_id,
        schedule_run_id=schedule_run_id,
    )
```

Keep all existing callers valid because new parameters are keyword-only and optional.

- [ ] **Step 5: Implement schedule executor**

Create `backend/app/modules/crawler/schedules/executor.py`:

```python
import uuid
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawler_schedule import CrawlerSchedule, CrawlerScheduleRun, CrawlerScheduleRunCrawlRun
from backend.app.modules.crawler.runtime.service import CrawlerRunService, get_runtime_state
from backend.app.modules.crawler.schedules.service import calculate_next_run_at
from shared.database.session import get_session_factory

TERMINAL_RUN_STATUSES = {"completed", "failed", "stopped"}


def _has_active_schedule_run(db: Session, schedule_id: uuid.UUID) -> bool:
    return (
        db.query(CrawlRun)
        .filter(CrawlRun.schedule_id == schedule_id, CrawlRun.status.in_(["queued", "running"]))
        .first()
        is not None
    )


def execute_schedule(
    schedule_id: uuid.UUID,
    *,
    db_factory: Callable[[], Session] | None = None,
    trigger_type: str = "scheduled",
) -> CrawlerScheduleRun | None:
    factory = db_factory or get_session_factory()
    db = factory()
    close_db = db_factory is None
    try:
        schedule = db.get(CrawlerSchedule, schedule_id)
        if schedule is None or not schedule.enabled:
            return None
        now = datetime.now()
        if _has_active_schedule_run(db, schedule.id):
            history = CrawlerScheduleRun(
                schedule_id=schedule.id,
                owner_id=schedule.owner_id,
                status="skipped",
                trigger_type=trigger_type,
                triggered_at=now,
                finished_at=now,
                result={"reason": "previous_run_active"},
                storage_status="disabled",
            )
            db.add(history)
            db.commit()
            db.refresh(history)
            return history

        history = CrawlerScheduleRun(
            schedule_id=schedule.id,
            owner_id=schedule.owner_id,
            status="running",
            trigger_type=trigger_type,
            triggered_at=now,
            result={"accepted": [], "skipped": [], "failed": []},
            storage_status="pending" if schedule.auto_storage_enabled else "disabled",
        )
        db.add(history)
        db.flush()
        service = CrawlerRunService(db, get_runtime_state())
        accepted = []
        skipped = []
        failed = []
        for task in schedule.tasks:
            if task.is_skip:
                skipped.append({"task_id": str(task.id), "reason": "禁用任务不能执行"})
                continue
            try:
                with db.begin_nested():
                    run = service.create_run(
                        task,
                        "incremental",
                        trigger_source="schedule",
                        schedule_id=schedule.id,
                        schedule_run_id=history.id,
                    )
                    db.add(CrawlerScheduleRunCrawlRun(schedule_run_id=history.id, crawl_run_id=run.id, task_id=task.id))
                    accepted.append({"task_id": str(task.id), "run_id": str(run.id)})
            except Exception as exc:
                failed.append({"task_id": str(task.id), "reason": str(exc)})
        history.result = {"accepted": accepted, "skipped": skipped, "failed": failed}
        if not accepted:
            history.status = "failed" if failed else "skipped"
            history.finished_at = datetime.now()
        schedule.last_triggered_at = now
        schedule.next_run_at = calculate_next_run_at(schedule.schedule_type, schedule.time_of_day, schedule.weekdays)
        db.commit()
        db.refresh(history)
        return history
    finally:
        if close_db:
            db.close()
```

The nested transaction keeps one task's run-creation failure from expiring the schedule history row or aborting the whole trigger.

- [ ] **Step 6: Implement scheduler wrapper**

Create `backend/app/modules/crawler/schedules/scheduler.py`:

```python
import uuid

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.app.models.crawler_schedule import CrawlerSchedule
from backend.app.modules.crawler.schedules.executor import execute_schedule
from shared.database.session import get_session_factory


def schedule_job_id(schedule_id: uuid.UUID | str) -> str:
    return f"crawler-schedule:{schedule_id}"


def build_trigger(schedule: CrawlerSchedule) -> CronTrigger:
    hour, minute = [int(part) for part in schedule.time_of_day.split(":", 1)]
    if schedule.schedule_type == "weekly":
        return CronTrigger(day_of_week=",".join(str(day) for day in schedule.weekdays), hour=hour, minute=minute)
    return CronTrigger(hour=hour, minute=minute)


class CrawlerScheduleScheduler:
    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler()

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def load_enabled_schedules(self) -> None:
        factory = get_session_factory()
        with factory() as db:
            for schedule in db.query(CrawlerSchedule).filter(CrawlerSchedule.enabled.is_(True)).all():
                self.upsert_schedule_job(schedule)

    def upsert_schedule_job(self, schedule: CrawlerSchedule) -> None:
        self.scheduler.add_job(
            execute_schedule,
            trigger=build_trigger(schedule),
            args=[schedule.id],
            id=schedule_job_id(schedule.id),
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    def remove_schedule_job(self, schedule_id: uuid.UUID) -> None:
        job_id = schedule_job_id(schedule_id)
        if self.scheduler.get_job(job_id) is not None:
            self.scheduler.remove_job(job_id)


crawler_schedule_scheduler = CrawlerScheduleScheduler()
```

- [ ] **Step 7: Wire scheduler into app lifespan**

Modify `backend/app/main.py`:

```python
from backend.app.modules.crawler.schedules.router import router as crawler_schedules_router
from backend.app.modules.crawler.schedules.scheduler import crawler_schedule_scheduler

# after cleanup succeeds
crawler_schedule_scheduler.start()
crawler_schedule_scheduler.load_enabled_schedules()

# shutdown
crawler_schedule_scheduler.shutdown()

# routers
app.include_router(crawler_schedules_router)
```

Modify `backend/tests/conftest.py` client fixture to patch scheduler methods:

```python
patch("backend.app.main.crawler_schedule_scheduler.start"), \
patch("backend.app.main.crawler_schedule_scheduler.load_enabled_schedules"), \
patch("backend.app.main.crawler_schedule_scheduler.shutdown"), \
```

- [ ] **Step 8: Run executor tests**

Run: `cd backend && python -m pytest tests/test_crawler_schedules_executor.py -v`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/requirements.txt backend/app/modules/crawler/schedules/scheduler.py backend/app/modules/crawler/schedules/executor.py backend/app/modules/crawler/runtime/service.py backend/app/main.py backend/tests/conftest.py backend/tests/test_crawler_schedules_executor.py
git diff --cached --name-only
git commit -m "feat: execute crawler schedules"
```

---

### Task 4: Automatic Storage After Scheduled Runs

**Files:**
- Create: `backend/app/modules/crawler/schedules/storage.py`
- Create: `backend/tests/test_crawler_schedule_storage.py`
- Modify: `backend/app/modules/crawler/runtime/callbacks.py`
- Modify: `backend/app/modules/crawler/runtime/threaded.py`
- Modify: `backend/app/modules/crawler/runtime/finalize.py`
- Modify: `backend/app/modules/storage/tasks/service.py`

**Interfaces:**
- Consumes: `CrawlRun.schedule_run_id`, `CrawlRunDetailTask.movie_id`, `CrawlerScheduleRun`.
- Produces: `process_schedule_run_completion(db: Session, run: CrawlRun) -> None`.
- Produces: `StorageTaskService.create_schedule_push(movie_ids, user_id, storage_mode, selected_storage_location) -> StorageMainTask`.

- [ ] **Step 1: Write failing automatic storage tests**

Add this test to `backend/tests/test_crawler_schedule_storage.py`:

```python
import uuid
from datetime import datetime

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.models.crawler_schedule import CrawlerSchedule, CrawlerScheduleRun, CrawlerScheduleRunCrawlRun
from backend.app.models.storage_task import StorageMainTask
from backend.app.modules.crawler.schedules.storage import process_schedule_run_completion
from shared.database.models.content import Movie


def test_process_schedule_completion_creates_one_storage_task(db_session, test_user, monkeypatch):
    task = CrawlTask(owner_id=test_user.id, name="Task", storage_location="Task", is_skip=False)
    movie = Movie(code="ABC-001", source_name="Movie", source_task_ids=[])
    schedule = CrawlerSchedule(
        owner_id=test_user.id,
        name="Nightly",
        enabled=True,
        schedule_type="daily",
        time_of_day="03:30",
        weekdays=[],
        auto_storage_enabled=True,
        storage_mode="single",
        selected_storage_location=None,
    )
    schedule.tasks.append(task)
    db_session.add_all([task, movie, schedule])
    db_session.commit()
    db_session.refresh(task)
    db_session.refresh(movie)
    db_session.refresh(schedule)
    schedule_run = CrawlerScheduleRun(
        schedule_id=schedule.id,
        owner_id=test_user.id,
        status="running",
        trigger_type="scheduled",
        triggered_at=datetime.now(),
        result={},
        storage_status="pending",
    )
    db_session.add(schedule_run)
    db_session.commit()
    db_session.refresh(schedule_run)
    crawl_run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="completed",
        crawl_mode="incremental",
        schedule_id=schedule.id,
        schedule_run_id=schedule_run.id,
    )
    db_session.add(crawl_run)
    db_session.commit()
    db_session.refresh(crawl_run)
    link = CrawlerScheduleRunCrawlRun(schedule_run_id=schedule_run.id, crawl_run_id=crawl_run.id, task_id=task.id)
    detail = CrawlRunDetailTask(
        run=crawl_run,
        task_name=task.name,
        source_url="https://example.test",
        source_name="Movie",
        status="saved",
        created_at=datetime.now(),
        movie_id=movie.id,
    )
    db_session.add_all([link, detail])
    db_session.commit()

    monkeypatch.setattr("backend.app.modules.storage.tasks.service.ensure_storage_worker_started", lambda *args, **kwargs: None)

    process_schedule_run_completion(db_session, crawl_run)
    db_session.refresh(schedule_run)

    storage_task = db_session.query(StorageMainTask).one()
    assert storage_task.source == "crawler_schedule"
    assert storage_task.total_count == 1
    assert schedule_run.status == "completed"
    assert schedule_run.storage_status == "created"
    assert schedule_run.storage_task_id == storage_task.id
```

- [ ] **Step 2: Run storage test to verify it fails**

Run: `cd backend && python -m pytest tests/test_crawler_schedule_storage.py -v`

Expected: FAIL because `process_schedule_run_completion` does not exist.

- [ ] **Step 3: Store saved movie ids on detail rows**

Modify `backend/app/modules/crawler/runtime/callbacks.py` inside `on_item_saved()` after `movie_id = upsert_movie_with_magnets(...)`:

```python
detail.movie_id = movie_id
```

Modify `backend/app/modules/crawler/runtime/threaded.py` where cleaned details are upserted:

```python
movie_id = upsert_movie_with_magnets(db, {**cleaned, "source_task_ids": [task.id]})
detail.movie_id = movie_id
```

- [ ] **Step 4: Add schedule-facing storage creation method**

Modify `backend/app/modules/storage/tasks/service.py`:

```python
def create_schedule_push(
    self,
    *,
    movie_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    storage_mode: str,
    selected_storage_location: str | None,
) -> StorageMainTask:
    return self._create_main_task(
        movie_ids=movie_ids,
        user_id=user_id,
        source="crawler_schedule",
        alias=None,
        storage_mode=storage_mode,
        selected_storage_location=selected_storage_location,
    )
```

- [ ] **Step 5: Implement automatic storage coordinator**

Create `backend/app/modules/crawler/schedules/storage.py`:

```python
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawler_schedule import CrawlerScheduleRun, CrawlerScheduleRunCrawlRun
from backend.app.modules.storage.runtime.redis_state import StorageRuntimeState
from backend.app.modules.storage.tasks.service import StorageTaskService
from backend.app.core.dependencies import get_redis
from backend.app.modules.storage.config.service import StorageConfigService

TERMINAL_RUN_STATUSES = {"completed", "failed", "stopped"}


def process_schedule_run_completion(db: Session, run: CrawlRun) -> None:
    if run.schedule_run_id is None:
        return
    schedule_run = db.get(CrawlerScheduleRun, run.schedule_run_id)
    if schedule_run is None or schedule_run.storage_status in {"created", "skipped", "failed", "disabled"}:
        return
    linked_runs = (
        db.query(CrawlRun)
        .join(CrawlerScheduleRunCrawlRun, CrawlerScheduleRunCrawlRun.crawl_run_id == CrawlRun.id)
        .filter(CrawlerScheduleRunCrawlRun.schedule_run_id == schedule_run.id)
        .all()
    )
    if any(linked.status not in TERMINAL_RUN_STATUSES for linked in linked_runs):
        return
    schedule_run.finished_at = datetime.now()
    if all(linked.status == "completed" for linked in linked_runs):
        schedule_run.status = "completed"
    elif any(linked.status == "completed" for linked in linked_runs):
        schedule_run.status = "partial_failed"
    else:
        schedule_run.status = "failed"
    schedule = schedule_run.schedule
    if not schedule.auto_storage_enabled:
        schedule_run.storage_status = "disabled"
        db.commit()
        return
    movie_ids = [
        row[0]
        for row in (
            db.query(CrawlRunDetailTask.movie_id)
            .join(CrawlerScheduleRunCrawlRun, CrawlerScheduleRunCrawlRun.crawl_run_id == CrawlRunDetailTask.run_id)
            .filter(
                CrawlerScheduleRunCrawlRun.schedule_run_id == schedule_run.id,
                CrawlRunDetailTask.status == "saved",
                CrawlRunDetailTask.movie_id.isnot(None),
            )
            .distinct()
            .all()
        )
    ]
    if not movie_ids:
        schedule_run.storage_status = "skipped"
        schedule_run.result = {**(schedule_run.result or {}), "storage_message": "本次无可自动存储影片"}
        db.commit()
        return
    try:
        service = StorageTaskService(db, StorageConfigService(), runtime=StorageRuntimeState(get_redis()))
        storage_task = service.create_schedule_push(
            movie_ids=movie_ids,
            user_id=schedule_run.owner_id,
            storage_mode=schedule.storage_mode,
            selected_storage_location=schedule.selected_storage_location,
        )
        schedule_run.storage_task_id = storage_task.id
        schedule_run.storage_status = "created"
        db.commit()
    except Exception as exc:
        db.rollback()
        schedule_run = db.get(CrawlerScheduleRun, run.schedule_run_id)
        if schedule_run is not None:
            schedule_run.finished_at = datetime.now()
            schedule_run.storage_status = "failed"
            schedule_run.storage_error = str(exc)[:1000]
            db.commit()
```

`StorageConfigService()` has optional constructor arguments in the current code, so the coordinator can construct it directly.

- [ ] **Step 6: Call coordinator from finalization**

Modify `backend/app/modules/crawler/runtime/finalize.py` after `db.commit()` and `publish_run_updated(db, run)`:

```python
from backend.app.modules.crawler.schedules.storage import process_schedule_run_completion

try:
    process_schedule_run_completion(db, run)
except Exception as exc:
    logger.warning("Failed to process schedule completion for run %s: %s", run.id, exc)
```

The import can be inside the function to avoid import cycles.

- [ ] **Step 7: Run storage coordinator tests**

Run: `cd backend && python -m pytest tests/test_crawler_schedule_storage.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/crawler/schedules/storage.py backend/app/modules/crawler/runtime/callbacks.py backend/app/modules/crawler/runtime/threaded.py backend/app/modules/crawler/runtime/finalize.py backend/app/modules/storage/tasks/service.py backend/tests/test_crawler_schedule_storage.py
git diff --cached --name-only
git commit -m "feat: create storage from scheduled crawls"
```

---

### Task 5: Schedule API Routes

**Files:**
- Create: `backend/app/modules/crawler/schedules/router.py`
- Modify: `backend/app/modules/crawler/schedules/schemas.py`
- Modify: `backend/app/modules/crawler/schedules/serializers.py`
- Modify: `backend/app/modules/crawler/schedules/service.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_crawler_schedules_api.py`

**Interfaces:**
- Consumes: service from Task 2 and executor from Task 3.
- Produces: `/api/crawler/schedules` endpoints from the spec.
- Produces: history list response including linked crawler run ids and storage task ids.

- [ ] **Step 1: Add failing route tests**

Extend `backend/tests/test_crawler_schedules_api.py`:

```python
def auth_payload(task_id):
    return {
        "name": "Nightly",
        "enabled": True,
        "task_ids": [str(task_id)],
        "schedule_type": "daily",
        "time_of_day": "03:30",
        "weekdays": [],
        "auto_storage_enabled": False,
        "storage_mode": "single",
        "selected_storage_location": None,
    }


def test_schedule_crud_routes(client, auth_headers, db_session, test_user, monkeypatch):
    task = seed_task(db_session, test_user.id)
    monkeypatch.setattr("backend.app.modules.crawler.schedules.service.CrawlerScheduleService._sync_job", lambda self, schedule: None)

    created = client.post("/api/crawler/schedules", json=auth_payload(task.id), headers=auth_headers)
    assert created.status_code == 201
    schedule_id = created.json()["data"]["id"]

    listed = client.get("/api/crawler/schedules", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1

    disabled = client.post(f"/api/crawler/schedules/{schedule_id}/disable", headers=auth_headers)
    assert disabled.status_code == 200
    assert disabled.json()["data"]["enabled"] is False

    deleted = client.delete(f"/api/crawler/schedules/{schedule_id}", headers=auth_headers)
    assert deleted.status_code == 200
```

- [ ] **Step 2: Run route test to verify it fails**

Run: `cd backend && python -m pytest tests/test_crawler_schedules_api.py::test_schedule_crud_routes -v`

Expected: FAIL with 404 for `/api/crawler/schedules`.

- [ ] **Step 3: Complete service methods**

Ensure `CrawlerScheduleService` includes:

```python
def delete_schedule(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> dict:
    schedule = self.get_owned_model(schedule_id, owner_id)
    self.db.delete(schedule)
    self.db.commit()
    if self.scheduler is not None:
        self.scheduler.remove_schedule_job(schedule_id)
    return {"id": str(schedule_id)}

def enable_schedule(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> CrawlerSchedule:
    schedule = self.get_owned_model(schedule_id, owner_id)
    schedule.enabled = True
    schedule.next_run_at = calculate_next_run_at(schedule.schedule_type, schedule.time_of_day, schedule.weekdays)
    self.db.commit()
    self.db.refresh(schedule)
    self._sync_job(schedule)
    return schedule

def disable_schedule(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> CrawlerSchedule:
    schedule = self.get_owned_model(schedule_id, owner_id)
    schedule.enabled = False
    self.db.commit()
    self.db.refresh(schedule)
    self._sync_job(schedule)
    return schedule

def list_schedule_runs(self, schedule_id: uuid.UUID, owner_id: uuid.UUID, *, page: int, size: int) -> dict:
    schedule = self.get_owned_model(schedule_id, owner_id)
    query = self.db.query(CrawlerScheduleRun).filter(CrawlerScheduleRun.schedule_id == schedule.id)
    total = query.count()
    rows = query.order_by(CrawlerScheduleRun.triggered_at.desc()).offset((page - 1) * size).limit(size).all()
    return {
        "rows": [
            {
                "id": str(row.id),
                "schedule_id": str(row.schedule_id),
                "status": row.status,
                "trigger_type": row.trigger_type,
                "triggered_at": row.triggered_at,
                "finished_at": row.finished_at,
                "result": row.result or {},
                "storage_status": row.storage_status,
                "storage_task_id": str(row.storage_task_id) if row.storage_task_id else None,
                "storage_error": row.storage_error,
                "crawl_run_ids": [str(link.crawl_run_id) for link in row.crawl_run_links],
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }
```

- [ ] **Step 4: Add router**

Create `backend/app/modules/crawler/schedules/router.py`:

```python
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.modules.crawler.schedules.executor import execute_schedule
from backend.app.modules.crawler.schedules.scheduler import crawler_schedule_scheduler
from backend.app.modules.crawler.schedules.schemas import CrawlerScheduleCreate, CrawlerScheduleUpdate
from backend.app.modules.crawler.schedules.serializers import serialize_schedule
from backend.app.modules.crawler.schedules.service import CrawlerScheduleService
from shared.schemas.common import success

router = APIRouter(prefix="/api/crawler/schedules", tags=["crawler-schedules"])


def get_service(db: Session) -> CrawlerScheduleService:
    return CrawlerScheduleService(db, scheduler=crawler_schedule_scheduler)


@router.get("")
def list_schedules(current_user: CurrentUser, db: Session = Depends(get_db), page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)) -> dict:
    return success(data=get_service(db).list_schedules(current_user.id, page=page, size=size))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_schedule(data: CrawlerScheduleCreate, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    return success(data=serialize_schedule(get_service(db).create_schedule(data, current_user.id)).model_dump(mode="json"))


@router.post("/{schedule_id}/disable")
def disable_schedule(schedule_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    return success(data=serialize_schedule(get_service(db).disable_schedule(schedule_id, current_user.id)).model_dump(mode="json"))
```

Add these additional route handlers:

```python
@router.get("/{schedule_id}")
def get_schedule(schedule_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    return success(data=get_service(db).get_schedule(schedule_id, current_user.id))


@router.put("/{schedule_id}")
def update_schedule(schedule_id: uuid.UUID, data: CrawlerScheduleUpdate, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    schedule = get_service(db).update_schedule(schedule_id, data, current_user.id)
    return success(data=serialize_schedule(schedule).model_dump(mode="json"))


@router.post("/{schedule_id}/enable")
def enable_schedule(schedule_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    schedule = get_service(db).enable_schedule(schedule_id, current_user.id)
    return success(data=serialize_schedule(schedule).model_dump(mode="json"))


@router.post("/{schedule_id}/trigger", status_code=status.HTTP_201_CREATED)
def trigger_schedule(schedule_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    get_service(db).get_owned_model(schedule_id, current_user.id)
    history = execute_schedule(schedule_id, trigger_type="manual")
    return success(data={"schedule_run_id": str(history.id) if history else None})


@router.get("/{schedule_id}/runs")
def list_schedule_runs(schedule_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db), page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)) -> dict:
    return success(data=get_service(db).list_schedule_runs(schedule_id, current_user.id, page=page, size=size))


@router.delete("/{schedule_id}")
def delete_schedule(schedule_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    return success(data=get_service(db).delete_schedule(schedule_id, current_user.id))
```

Manual trigger returns `{"schedule_run_id": null}` only when the schedule was disabled or removed between ownership validation and executor loading.

- [ ] **Step 5: Include router in `backend/app/main.py`**

Add:

```python
from backend.app.modules.crawler.schedules.router import router as crawler_schedules_router

app.include_router(crawler_schedules_router)
```

- [ ] **Step 6: Run API tests**

Run: `cd backend && python -m pytest tests/test_crawler_schedules_api.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/schedules/router.py backend/app/modules/crawler/schedules/schemas.py backend/app/modules/crawler/schedules/serializers.py backend/app/modules/crawler/schedules/service.py backend/app/main.py backend/tests/test_crawler_schedules_api.py
git diff --cached --name-only
git commit -m "feat: expose crawler schedule api"
```

---

### Task 6: Frontend Schedule Page

**Files:**
- Create: `frontend/src/api/crawler/crawlerSchedule/types.ts`
- Create: `frontend/src/api/crawler/crawlerSchedule/index.ts`
- Create: `frontend/src/pages/crawler/schedules/ScheduleListPage.tsx`
- Create: `frontend/src/pages/crawler/schedules/SchedulePages.module.less`
- Create: `frontend/src/pages/crawler/schedules/components/ScheduleFormDrawer.tsx`
- Create: `frontend/src/pages/crawler/schedules/components/ScheduleHistoryDrawer.tsx`
- Create: `frontend/src/pages/crawler/schedules/utils/recurrence.ts`
- Create: `frontend/src/pages/crawler/schedules/__tests__/schedule-form.test.tsx`
- Create: `frontend/src/pages/crawler/schedules/__tests__/schedule-list-actions.test.tsx`
- Modify: `frontend/src/api/queryKeys.ts`
- Modify: `frontend/src/api/queryInvalidation.ts`
- Modify: `frontend/src/routes/index.tsx`
- Modify: `frontend/src/routes/tags.ts`
- Modify: `frontend/src/layout/Sidebar/index.tsx`

**Interfaces:**
- Consumes: backend schedule API from Task 5 and task dictionary API.
- Produces: `/crawler/schedules` route.
- Produces: `CrawlerScheduleFormValues` used by create and update drawers.

- [ ] **Step 1: Write failing frontend tests**

Create `frontend/src/pages/crawler/schedules/__tests__/schedule-form.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ScheduleFormDrawer from '../components/ScheduleFormDrawer'

describe('ScheduleFormDrawer', () => {
  it('requires a weekday for weekly schedules', async () => {
    const user = userEvent.setup()
    render(
      <ScheduleFormDrawer
        open
        taskOptions={[{ id: 'task-1', name: 'Task 1' }]}
        submitting={false}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />,
    )

    await user.type(screen.getByLabelText('名称'), 'Nightly')
    await user.click(screen.getByText('每周'))
    await user.click(screen.getByRole('button', { name: '保存' }))

    expect(await screen.findByText('请选择至少一天')).toBeInTheDocument()
  })
})
```

Create `frontend/src/pages/crawler/schedules/__tests__/schedule-list-actions.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from 'antd'
import { describe, expect, it, vi } from 'vitest'
import * as scheduleApi from '@/api/crawler/crawlerSchedule'
import ScheduleListPage from '../ScheduleListPage'

vi.mock('@/api/crawler/crawlTask', () => ({
  getTaskDict: vi.fn().mockResolvedValue([{ id: 'task-1', name: 'Task 1' }]),
}))

describe('ScheduleListPage', () => {
  it('triggers a schedule immediately', async () => {
    const user = userEvent.setup()
    vi.spyOn(scheduleApi, 'getCrawlerSchedules').mockResolvedValue({
      rows: [{
        id: 'schedule-1',
        name: 'Nightly',
        enabled: true,
        schedule_type: 'daily',
        time_of_day: '03:30',
        weekdays: [],
        auto_storage_enabled: false,
        storage_mode: 'single',
        selected_storage_location: null,
        task_count: 1,
        tasks: [],
        last_triggered_at: null,
        next_run_at: null,
        latest_run_status: null,
        created_at: '2026-09-04T00:00:00',
        updated_at: null,
      }],
      total: 1,
      page: 1,
      size: 20,
    })
    const trigger = vi.spyOn(scheduleApi, 'triggerCrawlerSchedule').mockResolvedValue({ schedule_run_id: 'run-1' })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <App>
          <ScheduleListPage />
        </App>
      </QueryClientProvider>,
    )

    await user.click(await screen.findByRole('button', { name: '立即执行' }))

    await waitFor(() => expect(trigger).toHaveBeenCalledWith('schedule-1'))
  })
})
```

- [ ] **Step 2: Run frontend schedule tests to verify they fail**

Run: `cd frontend && pnpm test -- src/pages/crawler/schedules/__tests__/schedule-form.test.tsx src/pages/crawler/schedules/__tests__/schedule-list-actions.test.tsx`

Expected: FAIL because schedule components do not exist.

- [ ] **Step 3: Add frontend API types**

Create `frontend/src/api/crawler/crawlerSchedule/types.ts`:

```ts
export type ScheduleType = 'daily' | 'weekly'
export type StorageMode = 'single' | 'multiple'

export interface CrawlerSchedule {
  id: string
  name: string
  enabled: boolean
  schedule_type: ScheduleType
  time_of_day: string
  weekdays: number[]
  auto_storage_enabled: boolean
  storage_mode: StorageMode
  selected_storage_location: string | null
  task_count: number
  tasks: Array<{ id: string; name: string; is_skip: boolean }>
  last_triggered_at: string | null
  next_run_at: string | null
  latest_run_status: string | null
  created_at: string
  updated_at: string | null
}

export interface CrawlerSchedulePayload {
  name: string
  enabled: boolean
  task_ids: string[]
  schedule_type: ScheduleType
  time_of_day: string
  weekdays: number[]
  auto_storage_enabled: boolean
  storage_mode: StorageMode
  selected_storage_location: string | null
}

export interface CrawlerSchedulePage {
  rows: CrawlerSchedule[]
  total: number
  page: number
  size: number
}
```

Create `frontend/src/api/crawler/crawlerSchedule/index.ts`:

```ts
import request from '@/request'
import type { CrawlerSchedule, CrawlerSchedulePage, CrawlerSchedulePayload } from './types'

const BASE_URL = '/api/crawler/schedules'

export function getCrawlerSchedules(params: { page: number; size: number }): Promise<CrawlerSchedulePage> {
  return request.get<CrawlerSchedulePage>(BASE_URL, params)
}

export function createCrawlerSchedule(data: CrawlerSchedulePayload): Promise<CrawlerSchedule> {
  return request.post<CrawlerSchedule>(BASE_URL, data)
}

export function updateCrawlerSchedule(id: string, data: CrawlerSchedulePayload): Promise<CrawlerSchedule> {
  return request.put<CrawlerSchedule>(`${BASE_URL}/${id}`, data)
}

export function enableCrawlerSchedule(id: string): Promise<CrawlerSchedule> {
  return request.post<CrawlerSchedule>(`${BASE_URL}/${id}/enable`)
}

export function disableCrawlerSchedule(id: string): Promise<CrawlerSchedule> {
  return request.post<CrawlerSchedule>(`${BASE_URL}/${id}/disable`)
}

export function triggerCrawlerSchedule(id: string): Promise<{ schedule_run_id: string }> {
  return request.post<{ schedule_run_id: string }>(`${BASE_URL}/${id}/trigger`)
}

export function deleteCrawlerSchedule(id: string): Promise<{ id: string }> {
  return request.delete<{ id: string }>(`${BASE_URL}/${id}`)
}
```

- [ ] **Step 4: Add query keys and invalidation**

Modify `frontend/src/api/queryKeys.ts`:

```ts
crawlerSchedules: {
  all: () => ['crawlerSchedules'] as const,
  list: (params: { page: number; size: number }) => ['crawlerSchedules', params] as const,
  runs: (scheduleId: string, params: { page: number; size: number }) =>
    ['crawlerSchedules', scheduleId, 'runs', params] as const,
},
```

Modify `frontend/src/api/queryInvalidation.ts`:

```ts
export function invalidateCrawlerSchedules(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.crawlerSchedules.all() })
}
```

- [ ] **Step 5: Implement recurrence helper**

Create `frontend/src/pages/crawler/schedules/utils/recurrence.ts`:

```ts
const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

export function formatRecurrence(scheduleType: 'daily' | 'weekly', timeOfDay: string, weekdays: number[]): string {
  if (scheduleType === 'daily') return `每天 ${timeOfDay}`
  const labels = weekdays.map((day) => WEEKDAY_LABELS[day]).filter(Boolean)
  return `${labels.join('、')} ${timeOfDay}`
}
```

- [ ] **Step 6: Implement form drawer**

Create `ScheduleFormDrawer.tsx` using Ant Design `Drawer`, `Form`, `Input`, `Select`, `Segmented`, `TimePicker`, `Checkbox.Group`, and `Switch`.

The submit adapter must produce:

```ts
const payload: CrawlerSchedulePayload = {
  name: values.name.trim(),
  enabled: values.enabled ?? true,
  task_ids: values.task_ids,
  schedule_type: values.schedule_type,
  time_of_day: values.time_of_day.format('HH:mm'),
  weekdays: values.schedule_type === 'weekly' ? values.weekdays : [],
  auto_storage_enabled: values.auto_storage_enabled ?? false,
  storage_mode: values.storage_mode ?? 'single',
  selected_storage_location: values.selected_storage_location?.trim() || null,
}
```

Validation rules:

```tsx
{ required: true, message: '请输入名称' }
{ required: true, message: '请选择任务' }
{ required: true, message: '请选择时间' }
{
  validator: (_, value) => {
    if (form.getFieldValue('schedule_type') === 'weekly' && (!value || value.length === 0)) {
      return Promise.reject(new Error('请选择至少一天'))
    }
    return Promise.resolve()
  },
}
```

- [ ] **Step 7: Implement list page and history drawer**

Create `ScheduleListPage.tsx` with:

- `useQuery(queryKeys.crawlerSchedules.list({ page, size }), ...)`
- Ant Design `Table`
- top `MetricGrid`
- create/edit drawer state
- history drawer state
- enable/disable/trigger/delete mutations
- success and error messages through `App.useApp()`

Render actions as compact text buttons or icon buttons with labels:

```tsx
<Button size="small" onClick={() => openEdit(record)}>编辑</Button>
<Button size="small" onClick={() => handleToggleEnabled(record)}>
  {record.enabled ? '停用' : '启用'}
</Button>
<Button size="small" onClick={() => handleTrigger(record.id)}>立即执行</Button>
<Button size="small" danger onClick={() => handleDelete(record.id)}>删除</Button>
```

Create `ScheduleHistoryDrawer.tsx` backed by `queryKeys.crawlerSchedules.runs(scheduleId, { page, size })`. It renders `Empty` when there are no rows and a compact table when history is present.

- [ ] **Step 8: Register route and menu**

Modify `frontend/src/routes/index.tsx`:

```tsx
import ScheduleListPage from '@/pages/crawler/schedules/ScheduleListPage'

const crawlerSchedulesRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/schedules',
  component: ScheduleListPage,
})
```

Add `crawlerSchedulesRoute` to the route tree near crawler tasks and runs.

Modify `frontend/src/layout/Sidebar/index.tsx`:

```tsx
{
  key: '/crawler/schedules',
  icon: <ClockCircleOutlined />,
  label: '定时任务',
}
```

Update selected key logic:

```ts
: pathname.startsWith('/crawler/schedules')
  ? '/crawler/schedules'
```

Modify `frontend/src/routes/tags.ts`:

```ts
{ pattern: /^\/crawler\/schedules$/, meta: { title: '定时任务', activeMenu: '/crawler/schedules' } },
```

- [ ] **Step 9: Run frontend tests**

Run: `cd frontend && pnpm test -- src/pages/crawler/schedules/__tests__/schedule-form.test.tsx src/pages/crawler/schedules/__tests__/schedule-list-actions.test.tsx`

Expected: PASS.

- [ ] **Step 10: Run frontend build**

Run: `cd frontend && pnpm build`

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/api/crawler/crawlerSchedule/types.ts frontend/src/api/crawler/crawlerSchedule/index.ts frontend/src/pages/crawler/schedules/ScheduleListPage.tsx frontend/src/pages/crawler/schedules/SchedulePages.module.less frontend/src/pages/crawler/schedules/components/ScheduleFormDrawer.tsx frontend/src/pages/crawler/schedules/components/ScheduleHistoryDrawer.tsx frontend/src/pages/crawler/schedules/utils/recurrence.ts frontend/src/pages/crawler/schedules/__tests__/schedule-form.test.tsx frontend/src/pages/crawler/schedules/__tests__/schedule-list-actions.test.tsx frontend/src/api/queryKeys.ts frontend/src/api/queryInvalidation.ts frontend/src/routes/index.tsx frontend/src/routes/tags.ts frontend/src/layout/Sidebar/index.tsx
git diff --cached --name-only
git commit -m "feat: add crawler schedule page"
```

---

### Task 7: Final Integration Verification

**Files:**
- Modify only files required to fix defects discovered by verification.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: passing focused backend and frontend verification for crawler schedules.

- [ ] **Step 1: Run backend schedule tests**

Run:

```bash
cd backend && python -m pytest tests/test_crawler_schedules_models.py tests/test_crawler_schedules_api.py tests/test_crawler_schedules_executor.py tests/test_crawler_schedule_storage.py -v
```

Expected: PASS.

- [ ] **Step 2: Run affected existing backend tests**

Run:

```bash
cd backend && python -m pytest tests/test_crawl_tasks_api.py tests/test_crawler_runs_api.py tests/test_crawler_threaded_runtime.py tests/test_storage_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 3: Run frontend schedule tests**

Run:

```bash
cd frontend && pnpm test -- src/pages/crawler/schedules/__tests__/schedule-form.test.tsx src/pages/crawler/schedules/__tests__/schedule-list-actions.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && pnpm build
```

Expected: PASS.

- [ ] **Step 5: Commit verification fixes if needed**

If verification required code changes:

```bash
git status --short
git add backend/app/modules/crawler/schedules/storage.py backend/app/modules/crawler/schedules/executor.py backend/app/modules/crawler/schedules/service.py backend/app/modules/crawler/schedules/router.py backend/app/modules/crawler/runtime/finalize.py backend/app/modules/crawler/runtime/callbacks.py backend/app/modules/crawler/runtime/threaded.py backend/app/modules/storage/tasks/service.py frontend/src/pages/crawler/schedules/ScheduleListPage.tsx frontend/src/pages/crawler/schedules/components/ScheduleFormDrawer.tsx frontend/src/pages/crawler/schedules/components/ScheduleHistoryDrawer.tsx frontend/src/api/crawler/crawlerSchedule/index.ts frontend/src/api/crawler/crawlerSchedule/types.ts frontend/src/routes/index.tsx frontend/src/layout/Sidebar/index.tsx
git diff --cached --name-only
git commit -m "fix: stabilize crawler schedule integration"
```

If no changes were needed, do not create an empty commit.

- [ ] **Step 6: Report final state**

Summarize:

- commits created
- tests run and outcomes
- any tests not run
- any manual setup needed, such as running Alembic migration or installing updated backend requirements
