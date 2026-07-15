# Dashboard Runtime Overview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real homepage runtime dashboard backed by `GET /api/dashboard/overview`, with operational metrics, alerts, recent work, and lightweight G2 charts.

**Architecture:** Add a focused backend dashboard module that aggregates existing crawler, movie, storage task, and storage index state into one response. Add a focused frontend dashboard data layer and split the page into small presentation components that render the overview payload without static fallback metrics.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pydantic, pytest, React 19, TypeScript 6, Ant Design 6, Vitest, React Testing Library, `@antv/g2`.

## Global Constraints

- Replace static dashboard metrics with real data.
- Keep the dashboard focused on existing Media Forge behavior.
- Provide a single fast overview endpoint for homepage data.
- Use Ant Design and existing layout conventions.
- Add `@antv/g2` for lightweight diagnostic charts.
- Support light and dark themes.
- Avoid speculative product features or mock metrics in production code.
- Do not add new crawler, movie, or storage workflows.
- Do not turn the homepage into a marketing or welcome page.
- Do not add broad analytics beyond the data needed for operational status.
- Do not make frontend charts depend on fake fallback data.
- Chart colors must be stable: running or queued blue, completed green, failed red, stopped/skipped/neutral gray or orange.
- Keep cards at 8px radius or less.

---

## File Structure

Create backend dashboard files:

- `backend/app/modules/dashboard/__init__.py`: package marker.
- `backend/app/modules/dashboard/schemas.py`: Pydantic response models and status literals.
- `backend/app/modules/dashboard/service.py`: aggregation queries, status derivation, alerts, partial error helpers.
- `backend/app/modules/dashboard/router.py`: `GET /api/dashboard/overview`.
- `backend/tests/test_dashboard_overview.py`: endpoint and service coverage.

Modify backend app wiring:

- `backend/app/main.py`: include the dashboard router with the other API routers.

Create frontend dashboard API and components:

- `frontend/src/api/dashboard/types.ts`: TypeScript response model.
- `frontend/src/api/dashboard/index.ts`: `getDashboardOverview()`.
- `frontend/src/pages/dashboard/hooks/useDashboardOverview.ts`: loading, refresh, retry state around the API call.
- `frontend/src/pages/dashboard/components/DashboardStatusHeader.tsx`: overall status, refresh time, refresh button.
- `frontend/src/pages/dashboard/components/DashboardMetricCards.tsx`: four operational metric cards.
- `frontend/src/pages/dashboard/components/DashboardCharts.tsx`: G2 chart lifecycle and empty states.
- `frontend/src/pages/dashboard/components/DashboardRecentTabs.tsx`: recent crawler runs and storage tasks.
- `frontend/src/pages/dashboard/components/DashboardAlerts.tsx`: attention list and healthy empty state.

Modify frontend dashboard and tests:

- `frontend/src/pages/dashboard/DashboardPage.tsx`: compose the new data-driven dashboard.
- `frontend/src/pages/dashboard/DashboardPage.module.less`: operational dashboard layout, cards, charts, responsive rules, dark theme.
- `frontend/tests/dashboard.ui.test.tsx`: mock the dashboard hook and verify page states.
- `frontend/tests/setup.ts`: mock browser APIs needed by G2 if jsdom requires them.
- `frontend/package.json` and `frontend/package-lock.json`: add `@antv/g2`.

---

### Task 1: Backend Dashboard Schemas And Aggregation Service

**Files:**
- Create: `backend/app/modules/dashboard/__init__.py`
- Create: `backend/app/modules/dashboard/schemas.py`
- Create: `backend/app/modules/dashboard/service.py`
- Test: `backend/tests/test_dashboard_overview.py`

**Interfaces:**
- Consumes:
  - `build_task_runtime_status_response(db: Session, owner_id: uuid.UUID) -> CrawlTaskRuntimeStatusResponse`
  - `get_runtime_state().queue_status() -> dict`
  - `StorageIndexStore().read_metadata().to_dict() -> dict`
- Produces:
  - `build_dashboard_overview(db: Session, owner_id: uuid.UUID, queue_status: dict, index_metadata: dict) -> DashboardOverview`
  - `derive_system_status(payload: DashboardOverviewDraft) -> SystemStatus`

- [ ] **Step 1: Write failing service tests**

Create `backend/tests/test_dashboard_overview.py` with tests that exercise empty state, normal data, severity precedence, and partial section errors. Use the existing `TestingSessionLocal` pattern.

```python
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
import uuid

from fastapi.testclient import TestClient

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.app.models.storage_task import StorageMainTask
from backend.app.modules.dashboard.service import build_dashboard_overview, derive_system_status
from backend.app.modules.dashboard.schemas import DashboardOverviewDraft, PartialError
from backend.tests.conftest import TestingSessionLocal
from shared.database.models.content import Movie


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_build_dashboard_overview_empty_database(admin_user) -> None:
    session = TestingSessionLocal()

    overview = build_dashboard_overview(
        db=session,
        owner_id=admin_user.id,
        queue_status={
            "queue_size": 0,
            "is_running": False,
            "current_run_id": None,
            "stop_requested": False,
        },
        index_metadata={
            "target_folder": "",
            "status": "never_built",
            "category_count": 0,
            "code_folder_count": 0,
            "video_count": 0,
            "completed_at": None,
            "errors": [],
        },
    )

    assert overview.system_status == "warning"
    assert overview.crawler.task_stats.total == 0
    assert overview.crawler.runtime_stats.total == 0
    assert overview.content.movie_total == 0
    assert overview.storage.index.status == "never_built"
    assert overview.alerts == []
    assert overview.partial_errors == []


def test_build_dashboard_overview_counts_real_state(admin_user) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(
        name="actor-a",
        storage_location="JP",
        is_skip=False,
        owner_id=admin_user.id,
    )
    disabled = CrawlTask(
        name="actor-b",
        storage_location="JP",
        is_skip=True,
        owner_id=admin_user.id,
    )
    session.add_all([task, disabled])
    session.flush()
    now = datetime.now(timezone.utc)
    session.add_all(
        [
            CrawlRun(task_id=task.id, task_name="actor-a", status="completed", crawl_mode="full", created_at=now - timedelta(days=1)),
            CrawlRun(task_id=task.id, task_name="actor-a", status="failed", crawl_mode="full", error="boom", created_at=now),
            Movie(code="AAA-001", source_url="https://example.test/1", storage_summary={"storage_status": "stored"}),
            Movie(code="AAA-002", source_url="https://example.test/2", storage_summary={"storage_status": "not_stored"}),
            StorageMainTask(
                alias="storage-a",
                display_name="storage-a",
                source="single",
                storage_mode="single",
                status="completed",
                total_count=1,
                success_count=1,
                created_by=admin_user.id,
            ),
            StorageMainTask(
                alias="storage-b",
                display_name="storage-b",
                source="single",
                storage_mode="single",
                status="failed",
                total_count=1,
                failed_count=1,
                created_by=admin_user.id,
                error_message="copy failed",
            ),
        ]
    )
    session.commit()

    overview = build_dashboard_overview(
        db=session,
        owner_id=admin_user.id,
        queue_status={"queue_size": 0, "is_running": False, "current_run_id": None, "stop_requested": False},
        index_metadata={
            "target_folder": "/media",
            "status": "completed",
            "category_count": 2,
            "code_folder_count": 2,
            "video_count": 2,
            "completed_at": now.isoformat(),
            "errors": [],
        },
    )

    assert overview.system_status == "error"
    assert overview.crawler.task_stats.total == 2
    assert overview.crawler.task_stats.enabled == 1
    assert overview.crawler.task_stats.disabled == 1
    assert overview.content.movie_total == 2
    assert overview.content.storage_status.stored == 1
    assert overview.content.storage_status.not_stored == 1
    assert {item.status: item.count for item in overview.runs.status_distribution}["failed"] == 1
    assert overview.alerts[0].severity == "error"


def test_derive_system_status_precedence() -> None:
    draft = DashboardOverviewDraft(
        queue_status={"queue_size": 3, "is_running": True, "current_run_id": "run-1", "stop_requested": False},
        index_status="completed",
        index_errors=[],
        failed_run_count=1,
        failed_storage_count=0,
        stopped_runtime_count=0,
        running_runtime_count=1,
    )

    assert derive_system_status(draft) == "error"

    draft.failed_run_count = 0
    draft.stopped_runtime_count = 1
    assert derive_system_status(draft) == "warning"

    draft.stopped_runtime_count = 0
    draft.queue_status = {"queue_size": 0, "is_running": True, "current_run_id": "run-1", "stop_requested": False}
    assert derive_system_status(draft) == "busy"

    draft.queue_status = {"queue_size": 0, "is_running": False, "current_run_id": None, "stop_requested": False}
    draft.running_runtime_count = 0
    assert derive_system_status(draft) == "healthy"


def test_overview_endpoint_returns_partial_error_when_content_section_fails(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)

    def raise_content(*args, **kwargs):
        raise RuntimeError("content broken")

    monkeypatch.setattr("backend.app.modules.dashboard.service._build_content_section", raise_content)

    response = client.get("/api/dashboard/overview", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()["data"]
    assert body["content"]["movie_total"] == 0
    assert body["partial_errors"] == [{"section": "content", "message": "content broken"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_dashboard_overview.py -v
```

Expected: FAIL during import with `ModuleNotFoundError: No module named 'backend.app.modules.dashboard'`.

- [ ] **Step 3: Add Pydantic schemas**

Create `backend/app/modules/dashboard/__init__.py` as an empty package marker.

Create `backend/app/modules/dashboard/schemas.py`:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SystemStatus = Literal["healthy", "busy", "warning", "error"]
AlertSeverity = Literal["info", "warning", "error"]


class CountItem(BaseModel):
    status: str
    count: int


class DailyTrendItem(BaseModel):
    date: str
    completed: int = 0
    failed: int = 0


class DashboardTaskStats(BaseModel):
    total: int = 0
    enabled: int = 0
    disabled: int = 0


class DashboardRuntimeStats(BaseModel):
    total: int = 0
    idle: int = 0
    running: int = 0
    queued: int = 0
    stopped: int = 0


class DashboardQueueStatus(BaseModel):
    queue_size: int = 0
    is_running: bool = False
    current_run_id: str | None = None
    stop_requested: bool = False


class DashboardCrawlerSection(BaseModel):
    task_stats: DashboardTaskStats = Field(default_factory=DashboardTaskStats)
    runtime_stats: DashboardRuntimeStats = Field(default_factory=DashboardRuntimeStats)
    queue: DashboardQueueStatus = Field(default_factory=DashboardQueueStatus)


class RecentCrawlerRun(BaseModel):
    id: str
    task_name: str
    status: str
    crawl_mode: str
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


class DashboardRunsSection(BaseModel):
    status_distribution: list[CountItem] = Field(default_factory=list)
    daily_trend: list[DailyTrendItem] = Field(default_factory=list)
    recent: list[RecentCrawlerRun] = Field(default_factory=list)


class DashboardMovieStorageStatus(BaseModel):
    stored: int = 0
    storing: int = 0
    not_stored: int = 0


class DashboardContentSection(BaseModel):
    movie_total: int = 0
    storage_status: DashboardMovieStorageStatus = Field(default_factory=DashboardMovieStorageStatus)


class DashboardStorageIndex(BaseModel):
    target_folder: str = ""
    status: str = "never_built"
    category_count: int = 0
    code_folder_count: int = 0
    video_count: int = 0
    completed_at: str | None = None
    errors: list[dict] = Field(default_factory=list)


class RecentStorageTask(BaseModel):
    id: str
    alias: str
    display_name: str
    status: str
    total_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None


class DashboardStorageSection(BaseModel):
    task_status_distribution: list[CountItem] = Field(default_factory=list)
    recent_tasks: list[RecentStorageTask] = Field(default_factory=list)
    index: DashboardStorageIndex = Field(default_factory=DashboardStorageIndex)


class DashboardAlert(BaseModel):
    id: str
    title: str
    description: str
    severity: AlertSeverity
    source: str
    target_path: str | None = None
    occurred_at: str | None = None


class PartialError(BaseModel):
    section: str
    message: str


class DashboardOverview(BaseModel):
    system_status: SystemStatus
    refreshed_at: str
    crawler: DashboardCrawlerSection = Field(default_factory=DashboardCrawlerSection)
    runs: DashboardRunsSection = Field(default_factory=DashboardRunsSection)
    content: DashboardContentSection = Field(default_factory=DashboardContentSection)
    storage: DashboardStorageSection = Field(default_factory=DashboardStorageSection)
    alerts: list[DashboardAlert] = Field(default_factory=list)
    partial_errors: list[PartialError] = Field(default_factory=list)


class DashboardOverviewDraft(BaseModel):
    queue_status: dict
    index_status: str
    index_errors: list[dict] = Field(default_factory=list)
    failed_run_count: int = 0
    failed_storage_count: int = 0
    stopped_runtime_count: int = 0
    running_runtime_count: int = 0
```

- [ ] **Step 4: Add aggregation service**

Create `backend/app/modules/dashboard/service.py`:

```python
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.app.models.storage_task import StorageMainTask
from backend.app.modules.crawler.tasks.runtime_status import build_task_runtime_status_response
from backend.app.modules.dashboard.schemas import (
    CountItem,
    DailyTrendItem,
    DashboardAlert,
    DashboardContentSection,
    DashboardCrawlerSection,
    DashboardMovieStorageStatus,
    DashboardOverview,
    DashboardOverviewDraft,
    DashboardQueueStatus,
    DashboardRunsSection,
    DashboardRuntimeStats,
    DashboardStorageIndex,
    DashboardStorageSection,
    DashboardTaskStats,
    PartialError,
    RecentCrawlerRun,
    RecentStorageTask,
    SystemStatus,
)
from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
from shared.database.models.content import Movie


RECENT_LIMIT = 6
TREND_DAYS = 7


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _safe_section(
    section: str,
    partial_errors: list[PartialError],
    fallback,
    builder: Callable[[], object],
):
    try:
        return builder()
    except Exception as exc:
        partial_errors.append(PartialError(section=section, message=str(exc)))
        return fallback


def _count_items(rows) -> list[CountItem]:
    return [CountItem(status=str(status), count=int(count)) for status, count in rows]


def _build_crawler_section(db: Session, owner_id: uuid.UUID, queue_status: dict) -> DashboardCrawlerSection:
    total = int(db.query(func.count(CrawlTask.id)).filter(CrawlTask.owner_id == owner_id).scalar() or 0)
    disabled = int(
        db.query(func.count(CrawlTask.id))
        .filter(CrawlTask.owner_id == owner_id, CrawlTask.is_skip.is_(True))
        .scalar()
        or 0
    )
    runtime_response = build_task_runtime_status_response(db, owner_id)
    return DashboardCrawlerSection(
        task_stats=DashboardTaskStats(total=total, enabled=max(total - disabled, 0), disabled=disabled),
        runtime_stats=DashboardRuntimeStats(**runtime_response.stats.model_dump()),
        queue=DashboardQueueStatus(**queue_status),
    )


def _build_runs_section(db: Session, owner_id: uuid.UUID) -> DashboardRunsSection:
    owner_task_ids = db.query(CrawlTask.id).filter(CrawlTask.owner_id == owner_id).subquery()
    owner_runs = db.query(CrawlRun).filter(CrawlRun.task_id.in_(owner_task_ids))
    status_rows = owner_runs.with_entities(CrawlRun.status, func.count(CrawlRun.id)).group_by(CrawlRun.status).all()
    recent_rows = owner_runs.order_by(CrawlRun.created_at.desc()).limit(RECENT_LIMIT).all()
    since = datetime.now(timezone.utc) - timedelta(days=TREND_DAYS - 1)
    trend_rows = (
        owner_runs.filter(CrawlRun.created_at >= since)
        .with_entities(func.date(CrawlRun.created_at), CrawlRun.status, func.count(CrawlRun.id))
        .group_by(func.date(CrawlRun.created_at), CrawlRun.status)
        .all()
    )
    trend_by_day: dict[str, dict[str, int]] = defaultdict(lambda: {"completed": 0, "failed": 0})
    for day, status, count in trend_rows:
        day_key = str(day)
        if status in {"completed", "failed"}:
            trend_by_day[day_key][status] = int(count)
    today = datetime.now(timezone.utc).date()
    daily_trend = []
    for offset in range(TREND_DAYS - 1, -1, -1):
        day_key = (today - timedelta(days=offset)).isoformat()
        values = trend_by_day[day_key]
        daily_trend.append(DailyTrendItem(date=day_key, completed=values["completed"], failed=values["failed"]))
    return DashboardRunsSection(
        status_distribution=_count_items(status_rows),
        daily_trend=daily_trend,
        recent=[
            RecentCrawlerRun(
                id=str(row.id),
                task_name=row.task_name,
                status=row.status,
                crawl_mode=row.crawl_mode,
                created_at=_iso(row.created_at),
                started_at=_iso(row.started_at),
                finished_at=_iso(row.finished_at),
                error=row.error,
            )
            for row in recent_rows
        ],
    )


def _build_content_section(db: Session) -> DashboardContentSection:
    movies = db.query(Movie).all()
    counts = {"stored": 0, "storing": 0, "not_stored": 0}
    for movie in movies:
        status = normalized_movie_storage_status(movie)
        if status not in counts:
            status = "not_stored"
        counts[status] += 1
    return DashboardContentSection(
        movie_total=len(movies),
        storage_status=DashboardMovieStorageStatus(**counts),
    )


def _build_storage_section(db: Session, owner_id: uuid.UUID, index_metadata: dict) -> DashboardStorageSection:
    owner_tasks = db.query(StorageMainTask).filter(StorageMainTask.created_by == owner_id)
    status_rows = owner_tasks.with_entities(StorageMainTask.status, func.count(StorageMainTask.id)).group_by(StorageMainTask.status).all()
    recent_rows = owner_tasks.order_by(StorageMainTask.created_at.desc()).limit(RECENT_LIMIT).all()
    return DashboardStorageSection(
        task_status_distribution=_count_items(status_rows),
        recent_tasks=[
            RecentStorageTask(
                id=str(row.id),
                alias=row.alias,
                display_name=row.display_name,
                status=row.status,
                total_count=row.total_count,
                success_count=row.success_count,
                failed_count=row.failed_count,
                skipped_count=row.skipped_count,
                created_at=_iso(row.created_at),
                started_at=_iso(row.started_at),
                finished_at=_iso(row.finished_at),
                error_message=row.error_message,
            )
            for row in recent_rows
        ],
        index=DashboardStorageIndex(**index_metadata),
    )


def _build_alerts(runs: DashboardRunsSection, storage: DashboardStorageSection) -> list[DashboardAlert]:
    alerts: list[DashboardAlert] = []
    for run in runs.recent:
        if run.status == "failed":
            alerts.append(
                DashboardAlert(
                    id=f"crawler-run-{run.id}",
                    title=f"采集运行失败：{run.task_name}",
                    description=run.error or "采集运行失败",
                    severity="error",
                    source="crawler",
                    target_path=f"/crawler/runs/{run.id}",
                    occurred_at=run.finished_at or run.created_at,
                )
            )
    for task in storage.recent_tasks:
        if task.status == "failed":
            alerts.append(
                DashboardAlert(
                    id=f"storage-task-{task.id}",
                    title=f"存储任务失败：{task.display_name}",
                    description=task.error_message or "存储任务失败",
                    severity="error",
                    source="storage",
                    target_path=f"/storage/tasks/{task.id}",
                    occurred_at=task.finished_at or task.created_at,
                )
            )
    for index_error in storage.index.errors:
        path = str(index_error.get("path") or "存储索引")
        message = str(index_error.get("error") or "索引错误")
        alerts.append(
            DashboardAlert(
                id=f"storage-index-{len(alerts)}",
                title=f"存储索引错误：{path}",
                description=message,
                severity="error",
                source="storage.index",
                target_path="/storage/config",
                occurred_at=storage.index.completed_at,
            )
        )
    return alerts[:RECENT_LIMIT]


def derive_system_status(draft: DashboardOverviewDraft) -> SystemStatus:
    if (
        draft.failed_run_count > 0
        or draft.failed_storage_count > 0
        or draft.index_status == "failed"
        or len(draft.index_errors) > 0
    ):
        return "error"
    if (
        int(draft.queue_status.get("queue_size") or 0) > 0
        or bool(draft.queue_status.get("stop_requested"))
        or draft.index_status == "never_built"
        or draft.stopped_runtime_count > 0
    ):
        return "warning"
    if bool(draft.queue_status.get("is_running")) or draft.running_runtime_count > 0 or draft.index_status == "running":
        return "busy"
    return "healthy"


def build_dashboard_overview(
    *,
    db: Session,
    owner_id: uuid.UUID,
    queue_status: dict,
    index_metadata: dict,
) -> DashboardOverview:
    partial_errors: list[PartialError] = []
    crawler = _safe_section(
        "crawler",
        partial_errors,
        DashboardCrawlerSection(queue=DashboardQueueStatus(**queue_status)),
        lambda: _build_crawler_section(db, owner_id, queue_status),
    )
    runs = _safe_section("runs", partial_errors, DashboardRunsSection(), lambda: _build_runs_section(db, owner_id))
    content = _safe_section("content", partial_errors, DashboardContentSection(), lambda: _build_content_section(db))
    storage = _safe_section(
        "storage",
        partial_errors,
        DashboardStorageSection(index=DashboardStorageIndex(**index_metadata)),
        lambda: _build_storage_section(db, owner_id, index_metadata),
    )
    alerts = _build_alerts(runs, storage)
    failed_run_count = sum(item.count for item in runs.status_distribution if item.status == "failed")
    failed_storage_count = sum(item.count for item in storage.task_status_distribution if item.status == "failed")
    draft = DashboardOverviewDraft(
        queue_status=queue_status,
        index_status=storage.index.status,
        index_errors=storage.index.errors,
        failed_run_count=failed_run_count,
        failed_storage_count=failed_storage_count,
        stopped_runtime_count=crawler.runtime_stats.stopped,
        running_runtime_count=crawler.runtime_stats.running,
    )
    return DashboardOverview(
        system_status=derive_system_status(draft),
        refreshed_at=datetime.now(timezone.utc).isoformat(),
        crawler=crawler,
        runs=runs,
        content=content,
        storage=storage,
        alerts=alerts,
        partial_errors=partial_errors,
    )
```

- [ ] **Step 5: Run service tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_dashboard_overview.py::test_build_dashboard_overview_empty_database backend/tests/test_dashboard_overview.py::test_build_dashboard_overview_counts_real_state backend/tests/test_dashboard_overview.py::test_derive_system_status_precedence -v
```

Expected: service tests pass, endpoint partial-error test still fails because the route is not wired.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/dashboard backend/tests/test_dashboard_overview.py
git commit -m "feat: add dashboard overview aggregation"
```

---

### Task 2: Backend Dashboard Route And App Wiring

**Files:**
- Create: `backend/app/modules/dashboard/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_dashboard_overview.py`

**Interfaces:**
- Consumes:
  - `build_dashboard_overview(db: Session, owner_id: uuid.UUID, queue_status: dict, index_metadata: dict) -> DashboardOverview`
- Produces:
  - `GET /api/dashboard/overview` returning `success(data=overview.model_dump(mode="json"))`

- [ ] **Step 1: Add route file**

Create `backend/app/modules/dashboard/router.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.modules.crawler.runtime.service import get_runtime_state
from backend.app.modules.dashboard.service import build_dashboard_overview
from backend.app.modules.storage.index.store import StorageIndexStore
from shared.schemas.common import success

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview")
def get_dashboard_overview(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    overview = build_dashboard_overview(
        db=db,
        owner_id=current_user.id,
        queue_status=get_runtime_state().queue_status(),
        index_metadata=StorageIndexStore().read_metadata().to_dict(),
    )
    return success(data=overview.model_dump(mode="json"))
```

- [ ] **Step 2: Include router in app**

Modify `backend/app/main.py` imports:

```python
from backend.app.modules.dashboard.router import router as dashboard_router
```

Add the router before module-specific routers:

```python
app.include_router(realtime_router)
app.include_router(dashboard_router)
app.include_router(crawler_tasks_router)
```

- [ ] **Step 3: Run endpoint tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_dashboard_overview.py -v
```

Expected: all dashboard overview tests pass.

- [ ] **Step 4: Run adjacent API regression tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py backend/tests/test_storage_index_api.py backend/tests/test_storage_tasks_api.py backend/tests/test_content_movies_api.py -v
```

Expected: all selected API tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/app/modules/dashboard/router.py backend/tests/test_dashboard_overview.py
git commit -m "feat: expose dashboard overview api"
```

---

### Task 3: Frontend Dashboard API, Hook, And Tests

**Files:**
- Create: `frontend/src/api/dashboard/types.ts`
- Create: `frontend/src/api/dashboard/index.ts`
- Create: `frontend/src/pages/dashboard/hooks/useDashboardOverview.ts`
- Modify: `frontend/tests/dashboard.ui.test.tsx`

**Interfaces:**
- Consumes:
  - `GET /api/dashboard/overview`
- Produces:
  - `getDashboardOverview(): Promise<DashboardOverview>`
  - `useDashboardOverview(): { data, loading, error, refreshing, fetchOverview, refresh }`

- [ ] **Step 1: Write failing frontend tests for hook-driven states**

Replace `frontend/tests/dashboard.ui.test.tsx` with a hook mock that expects the new Chinese dashboard surface.

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DashboardOverview } from '../src/api/dashboard/types'
import DashboardPage from '../src/pages/dashboard/DashboardPage'

const refreshMock = vi.fn()

const overview: DashboardOverview = {
  system_status: 'healthy',
  refreshed_at: '2026-07-14T00:00:00Z',
  crawler: {
    task_stats: { total: 2, enabled: 1, disabled: 1 },
    runtime_stats: { total: 2, idle: 1, running: 1, queued: 0, stopped: 0 },
    queue: { queue_size: 0, is_running: true, current_run_id: 'run-1', stop_requested: false },
  },
  runs: {
    status_distribution: [{ status: 'completed', count: 2 }],
    daily_trend: [{ date: '2026-07-14', completed: 2, failed: 0 }],
    recent: [],
  },
  content: {
    movie_total: 10,
    storage_status: { stored: 6, storing: 1, not_stored: 3 },
  },
  storage: {
    task_status_distribution: [{ status: 'completed', count: 1 }],
    recent_tasks: [],
    index: {
      target_folder: '/media',
      status: 'completed',
      category_count: 2,
      code_folder_count: 10,
      video_count: 10,
      completed_at: '2026-07-14T00:00:00Z',
      errors: [],
    },
  },
  alerts: [],
  partial_errors: [],
}

let hookState = {
  data: overview,
  loading: false,
  error: null as Error | null,
  refreshing: false,
  fetchOverview: vi.fn(),
  refresh: refreshMock,
}

vi.mock('../src/pages/dashboard/hooks/useDashboardOverview', () => ({
  useDashboardOverview: () => hookState,
}))

vi.mock('../src/pages/dashboard/components/DashboardCharts', () => ({
  DashboardCharts: () => <div data-testid="dashboard-charts">charts</div>,
}))

describe('DashboardPage runtime overview', () => {
  beforeEach(() => {
    refreshMock.mockClear()
    hookState = {
      data: overview,
      loading: false,
      error: null,
      refreshing: false,
      fetchOverview: vi.fn(),
      refresh: refreshMock,
    }
  })

  it('renders runtime overview metrics from data', () => {
    render(<DashboardPage />)

    expect(screen.getByRole('heading', { name: '运行态总览' })).toBeInTheDocument()
    expect(screen.getByText('采集队列')).toBeInTheDocument()
    expect(screen.getByText('任务配置')).toBeInTheDocument()
    expect(screen.getByText('影片库')).toBeInTheDocument()
    expect(screen.getByText('存储索引')).toBeInTheDocument()
    expect(screen.getByText('暂无需要关注的问题')).toBeInTheDocument()
    expect(screen.queryByText('Operations Console')).not.toBeInTheDocument()
  })

  it('renders request failure and retries', () => {
    hookState = {
      ...hookState,
      data: null,
      error: new Error('dashboard failed'),
    }

    render(<DashboardPage />)

    expect(screen.getByText('首页数据加载失败')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(refreshMock).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2: Run frontend test to verify it fails**

Run:

```bash
cd frontend
npm test -- dashboard.ui.test.tsx --run
```

Expected: FAIL because `frontend/src/api/dashboard/types.ts` and the hook do not exist.

- [ ] **Step 3: Add TypeScript API types**

Create `frontend/src/api/dashboard/types.ts`:

```ts
export type SystemStatus = 'healthy' | 'busy' | 'warning' | 'error'
export type AlertSeverity = 'info' | 'warning' | 'error'

export interface CountItem {
  status: string
  count: number
}

export interface DailyTrendItem {
  date: string
  completed: number
  failed: number
}

export interface DashboardTaskStats {
  total: number
  enabled: number
  disabled: number
}

export interface DashboardRuntimeStats {
  total: number
  idle: number
  running: number
  queued: number
  stopped: number
}

export interface DashboardQueueStatus {
  queue_size: number
  is_running: boolean
  current_run_id: string | null
  stop_requested: boolean
}

export interface DashboardCrawlerSection {
  task_stats: DashboardTaskStats
  runtime_stats: DashboardRuntimeStats
  queue: DashboardQueueStatus
}

export interface RecentCrawlerRun {
  id: string
  task_name: string
  status: string
  crawl_mode: string
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  error: string | null
}

export interface DashboardRunsSection {
  status_distribution: CountItem[]
  daily_trend: DailyTrendItem[]
  recent: RecentCrawlerRun[]
}

export interface DashboardMovieStorageStatus {
  stored: number
  storing: number
  not_stored: number
}

export interface DashboardContentSection {
  movie_total: number
  storage_status: DashboardMovieStorageStatus
}

export interface DashboardStorageIndex {
  target_folder: string
  status: string
  category_count: number
  code_folder_count: number
  video_count: number
  completed_at: string | null
  errors: Array<Record<string, unknown>>
}

export interface RecentStorageTask {
  id: string
  alias: string
  display_name: string
  status: string
  total_count: number
  success_count: number
  failed_count: number
  skipped_count: number
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  error_message: string | null
}

export interface DashboardStorageSection {
  task_status_distribution: CountItem[]
  recent_tasks: RecentStorageTask[]
  index: DashboardStorageIndex
}

export interface DashboardAlert {
  id: string
  title: string
  description: string
  severity: AlertSeverity
  source: string
  target_path: string | null
  occurred_at: string | null
}

export interface PartialError {
  section: string
  message: string
}

export interface DashboardOverview {
  system_status: SystemStatus
  refreshed_at: string
  crawler: DashboardCrawlerSection
  runs: DashboardRunsSection
  content: DashboardContentSection
  storage: DashboardStorageSection
  alerts: DashboardAlert[]
  partial_errors: PartialError[]
}
```

- [ ] **Step 4: Add API client**

Create `frontend/src/api/dashboard/index.ts`:

```ts
import { request } from '@/request'
import type { DashboardOverview } from './types'

export type { DashboardOverview } from './types'

export function getDashboardOverview(): Promise<DashboardOverview> {
  return request.get<DashboardOverview>('/api/dashboard/overview')
}
```

- [ ] **Step 5: Add hook**

Create `frontend/src/pages/dashboard/hooks/useDashboardOverview.ts`:

```ts
import { useCallback, useEffect, useState } from 'react'
import { getDashboardOverview } from '@/api/dashboard'
import type { DashboardOverview } from '@/api/dashboard/types'

export function useDashboardOverview() {
  const [data, setData] = useState<DashboardOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const fetchOverview = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    if (mode === 'initial') {
      setLoading(true)
    } else {
      setRefreshing(true)
    }
    try {
      const overview = await getDashboardOverview()
      setData(overview)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err : new Error('首页数据加载失败'))
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void fetchOverview('initial')
  }, [fetchOverview])

  const refresh = useCallback(() => {
    void fetchOverview(data ? 'refresh' : 'initial')
  }, [data, fetchOverview])

  return {
    data,
    loading,
    error,
    refreshing,
    fetchOverview,
    refresh,
  }
}
```

- [ ] **Step 6: Run frontend test**

Run:

```bash
cd frontend
npm test -- dashboard.ui.test.tsx --run
```

Expected: tests still fail because `DashboardPage` has not been rewritten to use the hook.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/dashboard frontend/src/pages/dashboard/hooks/useDashboardOverview.ts frontend/tests/dashboard.ui.test.tsx
git commit -m "feat: add dashboard overview frontend data layer"
```

---

### Task 4: Frontend Runtime Dashboard Components And G2 Charts

**Files:**
- Create: `frontend/src/pages/dashboard/components/DashboardStatusHeader.tsx`
- Create: `frontend/src/pages/dashboard/components/DashboardMetricCards.tsx`
- Create: `frontend/src/pages/dashboard/components/DashboardCharts.tsx`
- Create: `frontend/src/pages/dashboard/components/DashboardRecentTabs.tsx`
- Create: `frontend/src/pages/dashboard/components/DashboardAlerts.tsx`
- Modify: `frontend/src/pages/dashboard/DashboardPage.tsx`
- Modify: `frontend/src/pages/dashboard/DashboardPage.module.less`
- Modify: `frontend/tests/setup.ts`
- Modify: `frontend/tests/dashboard.ui.test.tsx`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Interfaces:**
- Consumes:
  - `DashboardOverview` from `frontend/src/api/dashboard/types.ts`
  - `useDashboardOverview()` from Task 3
- Produces:
  - Data-driven dashboard UI with no old placeholder copy
  - G2 charts that render only when chart data is non-empty

- [ ] **Step 1: Install G2 dependency**

Run:

```bash
cd frontend
npm install @antv/g2
```

Expected: `frontend/package.json` and `frontend/package-lock.json` include `@antv/g2`.

- [ ] **Step 2: Add test environment canvas mocks if needed**

Modify `frontend/tests/setup.ts` to include request animation frame and canvas fallback for chart imports:

```ts
window.requestAnimationFrame = (callback: FrameRequestCallback) => window.setTimeout(() => callback(Date.now()), 16)
window.cancelAnimationFrame = (id: number) => window.clearTimeout(id)

HTMLCanvasElement.prototype.getContext = HTMLCanvasElement.prototype.getContext ?? (() => null)
```

If TypeScript reports assignment incompatibility, replace the last line with:

```ts
Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
  writable: true,
  value: () => null,
})
```

- [ ] **Step 3: Add status header component**

Create `frontend/src/pages/dashboard/components/DashboardStatusHeader.tsx`:

```tsx
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { Button, Tag } from 'antd'
import type { SystemStatus } from '@/api/dashboard/types'
import styles from '../DashboardPage.module.less'

const statusMeta: Record<SystemStatus, { label: string; color: string; icon: React.ReactNode }> = {
  healthy: { label: '健康', color: 'success', icon: <CheckCircleOutlined /> },
  busy: { label: '运行中', color: 'processing', icon: <SyncOutlined spin /> },
  warning: { label: '需要关注', color: 'warning', icon: <WarningOutlined /> },
  error: { label: '异常', color: 'error', icon: <CloseCircleOutlined /> },
}

interface Props {
  status: SystemStatus
  refreshedAt: string
  refreshing: boolean
  onRefresh: () => void
}

export function DashboardStatusHeader({ status, refreshedAt, refreshing, onRefresh }: Props) {
  const meta = statusMeta[status]
  return (
    <section className={styles.statusHeader}>
      <div>
        <p className={styles.eyebrow}>Media Forge</p>
        <h1>运行态总览</h1>
        <p className={styles.headerSummary}>采集、影片库、存储任务与索引状态的实时概览。</p>
      </div>
      <div className={styles.headerActions}>
        <Tag color={meta.color} icon={meta.icon}>{meta.label}</Tag>
        <span className={styles.refreshedAt}>刷新于 {new Date(refreshedAt).toLocaleString()}</span>
        <Button icon={<ReloadOutlined />} loading={refreshing} onClick={onRefresh}>刷新</Button>
      </div>
    </section>
  )
}
```

- [ ] **Step 4: Add metric cards component**

Create `frontend/src/pages/dashboard/components/DashboardMetricCards.tsx`:

```tsx
import {
  CloudSyncOutlined,
  DatabaseOutlined,
  UnorderedListOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import { Alert } from 'antd'
import type { DashboardOverview, PartialError } from '@/api/dashboard/types'
import styles from '../DashboardPage.module.less'

function sectionError(partialErrors: PartialError[], section: string) {
  return partialErrors.find((item) => item.section === section || item.section.startsWith(`${section}.`))
}

export function DashboardMetricCards({ overview }: { overview: DashboardOverview }) {
  const stored = overview.content.storage_status.stored
  const movieTotal = overview.content.movie_total
  const storedRatio = movieTotal > 0 ? Math.round((stored / movieTotal) * 100) : 0
  const cards = [
    {
      key: 'crawler',
      title: '采集队列',
      value: `${overview.crawler.runtime_stats.running} / ${overview.crawler.queue.queue_size}`,
      detail: '运行中 / 排队',
      icon: <CloudSyncOutlined />,
    },
    {
      key: 'crawler',
      title: '任务配置',
      value: `${overview.crawler.task_stats.enabled} / ${overview.crawler.task_stats.total}`,
      detail: '启用 / 总任务',
      icon: <UnorderedListOutlined />,
    },
    {
      key: 'content',
      title: '影片库',
      value: `${movieTotal}`,
      detail: `已入库 ${storedRatio}%`,
      icon: <VideoCameraOutlined />,
    },
    {
      key: 'storage',
      title: '存储索引',
      value: `${overview.storage.index.video_count}`,
      detail: `${overview.storage.index.status} · ${overview.storage.index.category_count} 分类`,
      icon: <DatabaseOutlined />,
    },
  ]

  return (
    <section className={styles.metricsGrid}>
      {cards.map((card) => {
        const error = sectionError(overview.partial_errors, card.key)
        return (
          <article className={styles.metricCard} key={`${card.key}-${card.title}`}>
            <span className={styles.metricIcon}>{card.icon}</span>
            <div className={styles.metricBody}>
              <span className={styles.metricLabel}>{card.title}</span>
              <strong>{card.value}</strong>
              <span className={styles.metricDetail}>{card.detail}</span>
              {error ? <Alert type="warning" showIcon message={error.message} className={styles.partialError} /> : null}
            </div>
          </article>
        )
      })}
    </section>
  )
}
```

- [ ] **Step 5: Add G2 charts component**

Create `frontend/src/pages/dashboard/components/DashboardCharts.tsx`:

```tsx
import { useEffect, useMemo, useRef } from 'react'
import { Chart } from '@antv/g2'
import { Empty } from 'antd'
import type { CountItem, DailyTrendItem } from '@/api/dashboard/types'
import styles from '../DashboardPage.module.less'

const statusColor: Record<string, string> = {
  queued: '#1677ff',
  running: '#1677ff',
  completed: '#52c41a',
  failed: '#ff4d4f',
  stopped: '#faad14',
  skipped: '#8c8c8c',
}

function StatusDistributionChart({ data }: { data: CountItem[] }) {
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!ref.current || data.length === 0) return
    const chart = new Chart({ container: ref.current, autoFit: true, height: 220 })
    chart
      .interval()
      .data(data)
      .encode('x', 'status')
      .encode('y', 'count')
      .encode('color', 'status')
      .scale('color', { range: data.map((item) => statusColor[item.status] ?? '#8c8c8c') })
    chart.render()
    return () => {
      chart.destroy()
    }
  }, [data])

  if (data.length === 0) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无运行状态数据" />
  return <div ref={ref} className={styles.chartCanvas} />
}

function TrendChart({ data }: { data: DailyTrendItem[] }) {
  const ref = useRef<HTMLDivElement | null>(null)
  const chartData = useMemo(
    () => data.flatMap((item) => [
      { date: item.date, type: '已完成', value: item.completed },
      { date: item.date, type: '失败', value: item.failed },
    ]),
    [data],
  )

  useEffect(() => {
    if (!ref.current || chartData.length === 0 || chartData.every((item) => item.value === 0)) return
    const chart = new Chart({ container: ref.current, autoFit: true, height: 220 })
    chart
      .line()
      .data(chartData)
      .encode('x', 'date')
      .encode('y', 'value')
      .encode('color', 'type')
      .scale('color', { range: ['#52c41a', '#ff4d4f'] })
    chart.render()
    return () => {
      chart.destroy()
    }
  }, [chartData])

  if (chartData.length === 0 || chartData.every((item) => item.value === 0)) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无近 7 天趋势数据" />
  }
  return <div ref={ref} className={styles.chartCanvas} />
}

export function DashboardCharts({ distribution, trend }: { distribution: CountItem[]; trend: DailyTrendItem[] }) {
  return (
    <section className={styles.chartGrid}>
      <article className={styles.panel}>
        <div className={styles.panelHeader}>
          <h2>运行状态分布</h2>
        </div>
        <StatusDistributionChart data={distribution} />
      </article>
      <article className={styles.panel}>
        <div className={styles.panelHeader}>
          <h2>近 7 天采集结果</h2>
        </div>
        <TrendChart data={trend} />
      </article>
    </section>
  )
}
```

- [ ] **Step 6: Add recent tabs and alerts components**

Create `frontend/src/pages/dashboard/components/DashboardRecentTabs.tsx`:

```tsx
import { Link } from '@tanstack/react-router'
import { Empty, Tabs, Tag } from 'antd'
import type { DashboardOverview } from '@/api/dashboard/types'
import styles from '../DashboardPage.module.less'

const statusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  stopped: { text: '已停止', color: 'warning' },
}

function tagFor(status: string) {
  const meta = statusLabels[status] ?? { text: status, color: 'default' }
  return <Tag color={meta.color}>{meta.text}</Tag>
}

export function DashboardRecentTabs({ overview }: { overview: DashboardOverview }) {
  return (
    <article className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>最近工作</h2>
      </div>
      <Tabs
        items={[
          {
            key: 'runs',
            label: '最近采集运行',
            children: overview.runs.recent.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无采集运行" />
            ) : (
              <div className={styles.recentList}>
                {overview.runs.recent.map((run) => (
                  <div className={styles.recentRow} key={run.id}>
                    <div>
                      <Link to="/crawler/runs/$id" params={{ id: run.id }}>{run.task_name}</Link>
                      <span>{new Date(run.created_at ?? '').toLocaleString()}</span>
                    </div>
                    {tagFor(run.status)}
                  </div>
                ))}
              </div>
            ),
          },
          {
            key: 'storage',
            label: '最近存储任务',
            children: overview.storage.recent_tasks.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无存储任务" />
            ) : (
              <div className={styles.recentList}>
                {overview.storage.recent_tasks.map((task) => (
                  <div className={styles.recentRow} key={task.id}>
                    <div>
                      <Link to="/storage/tasks/$id" params={{ id: task.id }}>{task.display_name}</Link>
                      <span>{new Date(task.created_at ?? '').toLocaleString()}</span>
                    </div>
                    {tagFor(task.status)}
                  </div>
                ))}
              </div>
            ),
          },
        ]}
      />
    </article>
  )
}
```

Create `frontend/src/pages/dashboard/components/DashboardAlerts.tsx`:

```tsx
import { Link } from '@tanstack/react-router'
import { Empty, Tag } from 'antd'
import type { DashboardAlert } from '@/api/dashboard/types'
import styles from '../DashboardPage.module.less'

export function DashboardAlerts({ alerts }: { alerts: DashboardAlert[] }) {
  return (
    <article className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>需要关注</h2>
      </div>
      {alerts.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无需要关注的问题" />
      ) : (
        <div className={styles.alertList}>
          {alerts.map((alert) => (
            <div className={styles.alertRow} key={alert.id}>
              <Tag color={alert.severity === 'error' ? 'error' : 'warning'}>{alert.source}</Tag>
              <div>
                {alert.target_path ? <Link to={alert.target_path}>{alert.title}</Link> : <strong>{alert.title}</strong>}
                <span>{alert.description}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </article>
  )
}
```

- [ ] **Step 7: Rewrite page composition**

Replace `frontend/src/pages/dashboard/DashboardPage.tsx`:

```tsx
import { Alert, Button, Skeleton } from 'antd'
import { DashboardAlerts } from './components/DashboardAlerts'
import { DashboardCharts } from './components/DashboardCharts'
import { DashboardMetricCards } from './components/DashboardMetricCards'
import { DashboardRecentTabs } from './components/DashboardRecentTabs'
import { DashboardStatusHeader } from './components/DashboardStatusHeader'
import { useDashboardOverview } from './hooks/useDashboardOverview'
import styles from './DashboardPage.module.less'

function DashboardPage() {
  const { data, loading, error, refreshing, refresh } = useDashboardOverview()

  if (loading && !data) {
    return (
      <div className={styles.dashboard}>
        <Skeleton active paragraph={{ rows: 3 }} />
        <section className={styles.metricsGrid}>
          <Skeleton active />
          <Skeleton active />
          <Skeleton active />
          <Skeleton active />
        </section>
      </div>
    )
  }

  if (error && !data) {
    return (
      <div className={styles.dashboard}>
        <Alert
          type="error"
          showIcon
          message="首页数据加载失败"
          description={error.message}
          action={<Button onClick={refresh}>重试</Button>}
        />
      </div>
    )
  }

  if (!data) return null

  return (
    <div className={styles.dashboard}>
      <DashboardStatusHeader
        status={data.system_status}
        refreshedAt={data.refreshed_at}
        refreshing={refreshing}
        onRefresh={refresh}
      />
      {data.partial_errors.length > 0 ? (
        <Alert type="warning" showIcon message="部分数据降级" description="部分模块暂时无法读取，页面已展示可用数据。" />
      ) : null}
      <DashboardMetricCards overview={data} />
      <DashboardCharts distribution={data.runs.status_distribution} trend={data.runs.daily_trend} />
      <section className={styles.workGrid}>
        <DashboardRecentTabs overview={data} />
        <DashboardAlerts alerts={data.alerts} />
      </section>
    </div>
  )
}

export default DashboardPage
```

- [ ] **Step 8: Replace dashboard styles**

Replace `frontend/src/pages/dashboard/DashboardPage.module.less` with operational styles:

```less
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.statusHeader,
.metricCard,
.panel {
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
}

.statusHeader {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px;
}

.statusHeader h1 {
  margin: 0;
  color: #0f172a;
  font-size: 24px;
  line-height: 32px;
}

.eyebrow,
.headerSummary,
.refreshedAt,
.metricLabel,
.metricDetail,
.recentRow span,
.alertRow span {
  color: #64748b;
  font-size: 12px;
}

.eyebrow {
  margin: 0 0 4px;
  font-weight: 700;
  text-transform: uppercase;
}

.headerSummary {
  margin: 6px 0 0;
  font-size: 13px;
}

.headerActions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
}

.metricsGrid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.metricCard {
  display: flex;
  gap: 12px;
  min-width: 0;
  padding: 14px;
}

.metricIcon {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 8px;
  background: rgba(0, 106, 255, 0.1);
  color: var(--app-primary-color, #006aff);
  font-size: 18px;
}

.metricBody {
  min-width: 0;
}

.metricBody strong {
  display: block;
  margin-top: 4px;
  color: #0f172a;
  font-size: 24px;
  line-height: 30px;
}

.metricDetail {
  display: block;
  margin-top: 2px;
}

.partialError {
  margin-top: 8px;
}

.chartGrid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.workGrid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.6fr);
  gap: 12px;
}

.panel {
  min-width: 0;
  padding: 16px;
}

.panelHeader {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.panelHeader h2 {
  margin: 0;
  color: #0f172a;
  font-size: 16px;
  line-height: 22px;
}

.chartCanvas {
  width: 100%;
  min-height: 220px;
}

.recentList,
.alertList {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recentRow,
.alertRow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 42px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f8fafc;
}

.recentRow > div,
.alertRow > div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.recentRow a,
.alertRow a,
.alertRow strong {
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
}

@media (max-width: 1100px) {
  .metricsGrid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chartGrid,
  .workGrid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .statusHeader,
  .headerActions {
    align-items: flex-start;
    flex-direction: column;
  }

  .metricsGrid {
    grid-template-columns: 1fr;
  }
}

:global(:root[data-theme="dark"]) {
  .statusHeader,
  .metricCard,
  .panel {
    border-color: rgba(51, 65, 85, 0.9);
    background: rgba(15, 23, 42, 0.9);
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.22);
  }

  .statusHeader h1,
  .metricBody strong,
  .panelHeader h2,
  .recentRow a,
  .alertRow a,
  .alertRow strong {
    color: #f8fafc;
  }

  .eyebrow,
  .headerSummary,
  .refreshedAt,
  .metricLabel,
  .metricDetail,
  .recentRow span,
  .alertRow span {
    color: #94a3b8;
  }

  .recentRow,
  .alertRow {
    background: rgba(30, 41, 59, 0.78);
  }
}
```

- [ ] **Step 9: Run frontend dashboard test**

Run:

```bash
cd frontend
npm test -- dashboard.ui.test.tsx --run
```

Expected: dashboard tests pass.

- [ ] **Step 10: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/pages/dashboard frontend/tests/dashboard.ui.test.tsx frontend/tests/setup.ts
git commit -m "feat: render runtime dashboard overview"
```

---

### Task 5: Final Verification And Cleanup

**Files:**
- Modify only files required by failures found during verification.

**Interfaces:**
- Consumes:
  - All backend and frontend work from Tasks 1-4.
- Produces:
  - Passing targeted backend tests, frontend dashboard test, frontend build, and clean review-ready diff.

- [ ] **Step 1: Run dashboard backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_dashboard_overview.py -v
```

Expected: PASS.

- [ ] **Step 2: Run adjacent backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py backend/tests/test_storage_index_api.py backend/tests/test_storage_tasks_api.py backend/tests/test_content_movies_api.py -v
```

Expected: PASS.

- [ ] **Step 3: Run frontend dashboard tests**

Run:

```bash
cd frontend
npm test -- dashboard.ui.test.tsx --run
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 5: Check for old placeholder copy**

Run:

```bash
rg -n "Operations Console|Media pipeline health|Active jobs|Queued assets|Storage used|Processing lanes|Recent activity" frontend/src/pages/dashboard frontend/tests/dashboard.ui.test.tsx
```

Expected: no matches.

- [ ] **Step 6: Check git status**

Run:

```bash
git status --short
```

Expected: only intentional dashboard/API/package/test files are modified. Existing unrelated user changes in `frontend/src/pages/content/movies/` must remain untouched.

- [ ] **Step 7: Commit verification fixes if any**

If verification required code fixes, commit them:

```bash
git add backend/app/modules/dashboard backend/app/main.py backend/tests/test_dashboard_overview.py frontend/package.json frontend/package-lock.json frontend/src/api/dashboard frontend/src/pages/dashboard frontend/tests/dashboard.ui.test.tsx frontend/tests/setup.ts
git commit -m "fix: verify runtime dashboard overview"
```

If no files changed after verification, do not create an empty commit.

---

## Self-Review Notes

- Spec coverage: the plan covers the overview endpoint, status derivation, partial errors, frontend API/hook, four page zones, icons, G2 charts, loading/error/empty states, tests, build verification, and removal of static placeholder copy.
- Scope: the work is a single dashboard feature spanning a backend aggregation endpoint and its frontend consumer; it does not add new crawler, movie, or storage workflows.
- Type consistency: backend schema names align with frontend type names and the response shape from the approved spec.
