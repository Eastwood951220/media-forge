import pytest
from fastapi import HTTPException


def test_crawler_task_helper_modules_export_public_helpers() -> None:
    from backend.app.modules.crawler.tasks import errors, serializers, validation

    assert callable(serializers.serialize_task)
    assert callable(validation.check_urls_unique)
    assert callable(validation.ensure_delete_mode_supported)
    assert callable(errors.constraint_name_from_integrity_error)
    assert callable(errors.raise_task_integrity_error)


def test_check_urls_unique_rejects_duplicate_url() -> None:
    from types import SimpleNamespace
    from backend.app.modules.crawler.tasks.validation import check_urls_unique

    with pytest.raises(HTTPException) as exc:
        check_urls_unique([SimpleNamespace(url="https://example.test/a"), SimpleNamespace(url="https://example.test/a")])

    assert exc.value.status_code == 400
    assert "URL 重复" in exc.value.detail


def test_extract_task_name_from_search_url_without_scraper() -> None:
    from backend.app.modules.crawler.tasks.name_extractor import extract_task_name
    from backend.app.schemas.crawl_task import ExtractNameRequest

    name = extract_task_name(ExtractNameRequest(url="https://javdb.com/search?q=ABC-123&f=all", url_type="search"))

    assert name == "ABC-123"


def test_open_delete_provider_returns_empty_session_for_task_only() -> None:
    from backend.app.modules.crawler.tasks.provider import open_delete_provider

    with open_delete_provider("task_only") as provider:
        assert provider is None


def test_get_latest_runs_by_task_ids_returns_one_newest_run_per_task(admin_user) -> None:
    from datetime import datetime, timedelta, timezone
    from backend.app.models.crawl_run import CrawlRun
    from backend.app.models.crawl_task import CrawlTask
    from backend.app.repositories.crawl_task import CrawlTaskRepository
    from backend.tests.conftest import TestingSessionLocal

    session = TestingSessionLocal()
    task_a = CrawlTask(name="latest-a", storage_location="JP", is_skip=False, owner_id=admin_user.id)
    task_b = CrawlTask(name="latest-b", storage_location="JP", is_skip=False, owner_id=admin_user.id)
    session.add_all([task_a, task_b])
    session.flush()
    now = datetime.now(timezone.utc)
    older = CrawlRun(task_id=task_a.id, task_name="latest-a", status="failed", crawl_mode="full", created_at=now - timedelta(hours=2))
    newest = CrawlRun(task_id=task_a.id, task_name="latest-a", status="completed", crawl_mode="full", created_at=now)
    only_b = CrawlRun(task_id=task_b.id, task_name="latest-b", status="running", crawl_mode="full", created_at=now - timedelta(hours=1))
    session.add_all([older, newest, only_b])
    session.commit()

    latest = CrawlTaskRepository(session).get_latest_runs_by_task_ids([task_a.id, task_b.id])

    assert latest[task_a.id].id == newest.id
    assert latest[task_b.id].id == only_b.id
    assert set(latest) == {task_a.id, task_b.id}


def test_crawler_task_list_uses_page_size_and_has_more(client, auth_headers):
    for index in range(3):
        response = client.post(
            "/api/crawler/tasks",
            json={
                "name": f"paged-task-{index}",
                "storage_location": "A",
                "is_skip": False,
                "urls": [{"url": f"https://javdb.com/actors/{index}", "url_type": "actors"}],
            },
            headers=auth_headers,
        )
        assert response.status_code == 201

    response = client.get("/api/crawler/tasks?page=1&size=2", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    data = body["data"] if "data" in body else body
    assert data["page"] == 1
    assert data["size"] == 2
    assert data["has_more"] is True
    assert len(data["rows"]) == 2
    assert "total" not in data
    assert "runtime" in data
    assert len(data["runtime"]["tasks"]) == 2


def test_crawler_task_count_endpoint_uses_same_keyword_filter(client, auth_headers):
    response = client.post(
        "/api/crawler/tasks",
        json={
            "name": "count-filter-task",
            "storage_location": "A",
            "is_skip": False,
            "urls": [{"url": "https://javdb.com/actors/count", "url_type": "actors"}],
        },
        headers=auth_headers,
    )
    assert response.status_code == 201

    count_response = client.get("/api/crawler/tasks/count?keyword=count-filter", headers=auth_headers)

    assert count_response.status_code == 200
    assert count_response.json()["data"]["total"] == 1
