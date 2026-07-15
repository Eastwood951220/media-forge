from datetime import datetime, timedelta, timezone
from http import HTTPStatus
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

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


def test_dashboard_json_text_value_compiles_for_postgresql() -> None:
    from backend.app.modules.dashboard.service import _json_text_value

    expr = _json_text_value(Movie.storage_summary, "storage_status", "postgresql")
    compiled = str(expr.compile(dialect=postgresql.dialect()))

    assert "storage_summary" in compiled
    assert "->>" in compiled


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


def test_dashboard_content_section_counts_storage_status_without_loading_movie_entities(admin_user, monkeypatch) -> None:
    session = TestingSessionLocal()
    session.add_all(
        [
            Movie(code="SQL-001", source_url="https://example.test/sql-1", storage_summary={"storage_status": "stored"}),
            Movie(code="SQL-002", source_url="https://example.test/sql-2", storage_summary={"last_status": "completed"}),
            Movie(code="SQL-003", source_url="https://example.test/sql-3", storage_summary={"storage_status": "running"}),
            Movie(code="SQL-004", source_url="https://example.test/sql-4", storage_summary={}),
        ]
    )
    session.commit()

    def fail_on_entity_load(*args, **kwargs):
        raise AssertionError("Movie entities should not be loaded for dashboard content counts")

    monkeypatch.setattr(
        "backend.app.modules.dashboard.service.normalized_movie_storage_status",
        fail_on_entity_load,
        raising=False,
    )

    overview = build_dashboard_overview(
        db=session,
        owner_id=admin_user.id,
        queue_status={"queue_size": 0, "is_running": False, "current_run_id": None, "stop_requested": False},
        index_metadata={
            "target_folder": "",
            "status": "completed",
            "category_count": 0,
            "code_folder_count": 0,
            "video_count": 0,
            "completed_at": None,
            "errors": [],
        },
    )

    assert overview.content.movie_total == 4
    assert overview.content.storage_status.stored == 2
    assert overview.content.storage_status.storing == 1
    assert overview.content.storage_status.not_stored == 1
