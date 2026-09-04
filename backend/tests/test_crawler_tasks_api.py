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


def test_crawler_task_list_returns_total_and_static_list_fields(client, auth_headers):
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
    data = response.json()["data"]
    assert data["page"] == 1
    assert data["size"] == 2
    assert data["total"] == 3
    assert len(data["rows"]) == 2
    assert set(data["rows"][0]) == {"id", "name", "storage_location", "is_skip", "urls", "tags"}
    assert data["rows"][0]["tags"] == []
    assert set(data["rows"][0]["urls"][0]) == {
        "id",
        "position",
        "url",
        "url_type",
        "has_magnet",
        "has_chinese_sub",
        "url_name",
    }


def test_removed_task_aggregate_routes_return_404(client, auth_headers):
    for path in ("count", "stats", "statuses"):
        response = client.get(f"/api/crawler/tasks/{path}", headers=auth_headers)
        assert response.status_code == 404


def test_extract_javbus_star_task_name(monkeypatch) -> None:
    from scrapling.parser import Adaptor
    from backend.app.modules.crawler.tasks.name_extractor import extract_task_name
    from backend.app.schemas.crawl_task import ExtractNameRequest
    from scraper.fetchers.scrapling_fetcher import ScraplingFetcher

    page = Adaptor("""
    <div class="alert alert-success alert-common">
      <p><b>波多野結衣 - 女優 - 影片</b>：當前顯示</p>
    </div>
    """)

    monkeypatch.setattr(
        ScraplingFetcher,
        "get",
        lambda self, url, **kwargs: page,
    )

    name = extract_task_name(ExtractNameRequest(
        url="https://www.javbus.com/star/2jv",
        url_type="detail",
    ))

    assert name == "波多野結衣"


def test_create_task_accepts_long_storage_location(client, auth_headers):
    long_name = "演员名称超过十个字符"
    response = client.post(
        "/api/crawler/tasks",
        json={
            "name": long_name,
            "storage_location": long_name,
            "is_skip": False,
            "urls": [{"url": "https://javdb.com/actors/long-name", "url_type": "actors"}],
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["data"]["storage_location"] == long_name


def test_batch_create_route_rejects_empty_url_list(client, auth_headers):
    response = client.post(
        "/api/crawler/tasks/batch",
        json={"urls": ["", "   "]},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["msg"] == "请至少提供 1 个 URL"


def test_batch_create_creates_one_task_per_url(client, auth_headers, monkeypatch):
    from backend.app.modules.crawler.tasks import service as task_service

    names = {
        "https://javdb.com/actors/alpha": "Alpha Actor",
        "https://javdb.com/series/beta": "Beta Series",
    }
    monkeypatch.setattr(
        task_service,
        "extract_task_name",
        lambda body: names[body.url],
    )

    response = client.post(
        "/api/crawler/tasks/batch",
        json={
            "urls": [" https://javdb.com/actors/alpha ", "https://javdb.com/series/beta"],
            "has_magnet": True,
            "has_chinese_sub": True,
            "sort_type": 5,
            "is_skip": False,
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["created_count"] == 2
    assert data["failed_count"] == 0
    assert [item["task"]["name"] for item in data["created"]] == ["Alpha Actor", "Beta Series"]
    assert data["created"][0]["task"]["storage_location"] == "Alpha Actor"
    assert data["created"][0]["task"]["urls"][0]["url"] == "https://javdb.com/actors/alpha"
    assert data["created"][0]["task"]["urls"][0]["url_type"] == "actors"
    assert data["created"][0]["task"]["urls"][0]["has_magnet"] is True
    assert data["created"][0]["task"]["urls"][0]["has_chinese_sub"] is True
    assert data["created"][0]["task"]["urls"][0]["sort_type"] == 5
    assert data["created"][0]["task"]["urls"][0]["url_name"] == "Alpha Actor"


def test_batch_create_suffixes_duplicate_task_names(client, auth_headers, monkeypatch):
    from backend.app.modules.crawler.tasks import service as task_service

    monkeypatch.setattr(task_service, "extract_task_name", lambda body: "Same Name")

    existing = client.post(
        "/api/crawler/tasks",
        json={
            "name": "Same Name",
            "storage_location": "Same Name",
            "is_skip": False,
            "urls": [{"url": "https://javdb.com/actors/existing", "url_type": "actors"}],
        },
        headers=auth_headers,
    )
    assert existing.status_code == 201

    response = client.post(
        "/api/crawler/tasks/batch",
        json={"urls": ["https://javdb.com/actors/a", "https://javdb.com/actors/b"]},
        headers=auth_headers,
    )

    assert response.status_code == 201
    created = response.json()["data"]["created"]
    assert [item["task"]["name"] for item in created] == ["Same Name (2)", "Same Name (3)"]
    assert [item["task"]["storage_location"] for item in created] == ["Same Name (2)", "Same Name (3)"]


def test_batch_create_keeps_successes_when_some_urls_fail(client, auth_headers, monkeypatch):
    from fastapi import HTTPException
    from backend.app.modules.crawler.tasks import service as task_service

    def fake_extract(body):
        if body.url.endswith("/bad"):
            raise HTTPException(status_code=502, detail="页面不可访问")
        return "Good Name"

    monkeypatch.setattr(task_service, "extract_task_name", fake_extract)

    response = client.post(
        "/api/crawler/tasks/batch",
        json={
            "urls": [
                "https://javdb.com/actors/good",
                "https://javdb.com/actors/good",
                "https://example.com/nope",
                "https://javdb.com/actors/bad",
            ]
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["created_count"] == 1
    assert data["failed_count"] == 3
    assert data["created"][0]["task"]["name"] == "Good Name"
    assert data["failed"] == [
        {"url": "https://javdb.com/actors/good", "reason": "URL 重复"},
        {"url": "https://example.com/nope", "reason": "不支持的 URL 来源"},
        {"url": "https://javdb.com/actors/bad", "reason": "页面不可访问"},
    ]


def test_crawler_task_tag_tables_are_registered():
    from shared.database.models.base import Base

    assert "crawl_task_tags" in Base.metadata.tables
    assert "crawl_task_tag_links" in Base.metadata.tables


def test_crawler_task_schemas_accept_tag_names():
    from backend.app.schemas.crawl_task import CrawlTaskBatchCreate, CrawlTaskCreate, CrawlTaskUpdate

    create = CrawlTaskCreate(
        name="tag schema",
        storage_location="tag schema",
        tag_names=["VR", "演员"],
        urls=[{"url": "https://javdb.com/actors/schema", "url_type": "actors"}],
    )
    update = CrawlTaskUpdate(tag_names=[])
    batch = CrawlTaskBatchCreate(urls=["https://javdb.com/actors/schema"], tag_names=["VR"])

    assert create.tag_names == ["VR", "演员"]
    assert update.tag_names == []
    assert batch.tag_names == ["VR"]


def create_tagged_task(client, headers, name, tags):
    response = client.post(
        "/api/crawler/tasks",
        json={
            "name": name,
            "storage_location": name,
            "tag_names": tags,
            "is_skip": False,
            "urls": [{"url": f"https://javdb.com/actors/{name}", "url_type": "actors"}],
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["data"]


def test_create_task_with_tags_returns_tags(client, auth_headers):
    task = create_tagged_task(client, auth_headers, "tagged-task", ["VR", " 演员 ", "VR", ""])

    assert [tag["name"] for tag in task["tags"]] == ["VR", "演员"]


def test_task_list_includes_tags(client, auth_headers):
    create_tagged_task(client, auth_headers, "listed-tagged-task", ["VR"])

    response = client.get("/api/crawler/tasks", headers=auth_headers)

    assert response.status_code == 200
    row = response.json()["data"]["rows"][0]
    assert row["name"] == "listed-tagged-task"
    assert row["tags"][0]["name"] == "VR"


def test_tag_dictionary_returns_current_user_tags(client, auth_headers, other_user):
    create_tagged_task(client, auth_headers, "dict-a", ["VR", "演员"])
    create_tagged_task(client, auth_headers, "dict-b", ["VR", "系列"])

    response = client.get("/api/crawler/tasks/tags", headers=auth_headers)

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["data"]] == ["VR", "演员", "系列"]


def test_update_task_replaces_and_clears_tags(client, auth_headers):
    task = create_tagged_task(client, auth_headers, "replace-tags", ["VR", "演员"])

    replaced = client.put(
        f"/api/crawler/tasks/{task['id']}",
        json={
            "name": "replace-tags",
            "tag_names": ["系列"],
            "urls": [{"url": "https://javdb.com/actors/replace-tags", "url_type": "actors"}],
            "is_skip": False,
        },
        headers=auth_headers,
    )
    assert replaced.status_code == 200
    assert [tag["name"] for tag in replaced.json()["data"]["tags"]] == ["系列"]

    cleared = client.put(
        f"/api/crawler/tasks/{task['id']}",
        json={"tag_names": []},
        headers=auth_headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["tags"] == []


def test_update_task_omitting_tag_names_keeps_existing_tags(client, auth_headers):
    task = create_tagged_task(client, auth_headers, "keep-tags", ["VR"])

    response = client.put(
        f"/api/crawler/tasks/{task['id']}",
        json={"name": "keep-tags-renamed"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert [tag["name"] for tag in response.json()["data"]["tags"]] == ["VR"]


def test_task_list_filters_by_all_selected_tags(client, auth_headers):
    create_tagged_task(client, auth_headers, "vr-actor", ["VR", "演员"])
    create_tagged_task(client, auth_headers, "vr-only", ["VR"])
    create_tagged_task(client, auth_headers, "actor-only", ["演员"])

    response = client.get(
        "/api/crawler/tasks?tag_names=VR&tag_names=演员",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["rows"][0]["name"] == "vr-actor"


def test_create_task_rejects_too_long_tag_name(client, auth_headers):
    response = client.post(
        "/api/crawler/tasks",
        json={
            "name": "long-tag",
            "storage_location": "long-tag",
            "tag_names": ["标" * 51],
            "is_skip": False,
            "urls": [{"url": "https://javdb.com/actors/long-tag", "url_type": "actors"}],
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "标签长度不能超过 50 个字符" in response.json()["msg"]
