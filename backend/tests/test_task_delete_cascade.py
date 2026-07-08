"""Tests for task delete cascade and source_task_ids filtering."""

import uuid
from datetime import date
from decimal import Decimal
from http import HTTPStatus

from fastapi.testclient import TestClient

from backend.app.models.crawl_task import CrawlTask
from shared.database.models.content import Movie
from backend.tests.conftest import TestingSessionLocal


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_delete_task_with_task_and_movies_mode(client: TestClient, admin_user) -> None:
    """Test that deleting a task with task_and_movies mode deletes associated movies."""
    headers = auth_headers(client, admin_user)

    # Create task via API
    task_response = client.post(
        "/api/crawler/tasks",
        json={
            "name": "测试任务",
            "storage_location": "测试",
            "is_skip": False,
            "urls": [{"url": "https://javdb.com/actors/a", "url_type": "actors"}],
        },
        headers=headers,
    )
    task_id = task_response.json()["data"]["id"]

    # Seed movies with this task ID
    session = TestingSessionLocal()
    movie1 = Movie(
        code="TEST-001",
        source_url="https://javdb.com/v/test001",
        source_name="测试电影1",
        source_task_ids=[uuid.UUID(task_id)],
    )
    movie2 = Movie(
        code="TEST-002",
        source_url="https://javdb.com/v/test002",
        source_name="测试电影2",
        source_task_ids=[uuid.UUID(task_id)],
    )
    session.add_all([movie1, movie2])
    session.commit()
    session.close()

    # Delete the task with task_and_movies mode
    response = client.delete(f"/api/crawler/tasks/{task_id}?mode=task_and_movies", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["msg"] == "删除成功"
    assert body["data"]["deleted_movies"] == 2
    assert body["data"]["deleted_task"] is True


def test_delete_task_only_keeps_movies(client: TestClient, admin_user) -> None:
    """Test that task_only mode keeps movies."""
    headers = auth_headers(client, admin_user)

    # Create task via API
    task_response = client.post(
        "/api/crawler/tasks",
        json={
            "name": "测试任务",
            "storage_location": "测试",
            "is_skip": False,
            "urls": [{"url": "https://javdb.com/actors/a", "url_type": "actors"}],
        },
        headers=headers,
    )
    task_id = task_response.json()["data"]["id"]

    # Seed movie with this task ID
    session = TestingSessionLocal()
    movie = Movie(
        code="TEST-001",
        source_url="https://javdb.com/v/test001",
        source_name="测试电影",
        source_task_ids=[uuid.UUID(task_id)],
    )
    session.add(movie)
    session.commit()
    session.close()

    # Delete the task with task_only mode
    response = client.delete(f"/api/crawler/tasks/{task_id}?mode=task_only", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["data"]["deleted_task"] is True
    assert body["data"]["deleted_movies"] == 0

    # Verify movie still exists
    session = TestingSessionLocal()
    remaining = session.query(Movie).all()
    assert len(remaining) == 1
    assert remaining[0].code == "TEST-001"
    session.close()


def test_list_movies_filter_by_source_task_id(client: TestClient, admin_user) -> None:
    """Test filtering movies by source_task_id."""
    headers = auth_headers(client, admin_user)

    # Create movies with different source_task_ids
    session = TestingSessionLocal()
    task_id_1 = uuid.uuid4()
    task_id_2 = uuid.uuid4()

    movie1 = Movie(
        code="TASK1-001",
        source_url="https://javdb.com/v/task1-001",
        source_name="任务1电影",
        source_task_ids=[task_id_1],
    )
    movie2 = Movie(
        code="TASK2-001",
        source_url="https://javdb.com/v/task2-001",
        source_name="任务2电影",
        source_task_ids=[task_id_2],
    )
    session.add_all([movie1, movie2])
    session.commit()
    session.close()

    # Filter by source_task_id
    response = client.get(
        f"/api/content/movies?source_task_id={task_id_1}",
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["code"] == "TASK1-001"
    assert str(task_id_1) in body["rows"][0]["source_task_ids"]


def test_movie_payload_includes_source_task_ids(client: TestClient, admin_user) -> None:
    """Test that movie payload includes source_task_ids field."""
    headers = auth_headers(client, admin_user)

    session = TestingSessionLocal()
    task_id = uuid.uuid4()
    movie = Movie(
        code="PAYLOAD-001",
        source_url="https://javdb.com/v/payload001",
        source_name="Payload测试",
        source_task_ids=[task_id],
    )
    session.add(movie)
    session.commit()
    movie_id = str(movie.id)
    session.close()

    response = client.get(f"/api/content/movies/{movie_id}", headers=headers)

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert str(task_id) in data["source_task_ids"]


def test_task_dict_endpoint(client: TestClient, admin_user) -> None:
    """Test task dictionary endpoint."""
    headers = auth_headers(client, admin_user)

    # Create tasks
    client.post(
        "/api/crawler/tasks",
        json={
            "name": "任务A",
            "storage_location": "A",
            "is_skip": False,
            "urls": [{"url": "https://javdb.com/actors/a", "url_type": "actors"}],
        },
        headers=headers,
    )
    client.post(
        "/api/crawler/tasks",
        json={
            "name": "任务B",
            "storage_location": "B",
            "is_skip": False,
            "urls": [{"url": "https://javdb.com/actors/b", "url_type": "actors"}],
        },
        headers=headers,
    )

    response = client.get("/api/crawler/tasks/dict", headers=headers)

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert len(data) == 2
    assert all("id" in item and "name" in item for item in data)


def test_delete_task_movies_and_cloud_deletes_task_movies_and_cloud_folders(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post(
        "/api/crawler/tasks",
        json={
            "name": "云删除任务",
            "storage_location": "巨乳",
            "is_skip": False,
            "urls": [{"url": "https://javdb.com/actors/cloud", "url_type": "actors"}],
        },
        headers=headers,
    )
    task_id = task_response.json()["data"]["id"]

    session = TestingSessionLocal()
    movie = Movie(
        code="CLOUD-001",
        source_url="https://javdb.com/v/cloud001",
        source_name="云删除影片",
        source_task_ids=[uuid.UUID(task_id)],
        storage_summary={
            "locations": [
                {
                    "path": "/Movies/巨乳/CLOUD-001/CLOUD-001.mp4",
                    "target_folder": "/Movies/巨乳/CLOUD-001",
                    "storage_location": "巨乳",
                }
            ],
        },
    )
    session.add(movie)
    session.commit()
    session.close()

    deleted: list[str] = []

    class Factory:
        def create(self, config):
            return object()

    class Gateway:
        def __init__(self, client):
            return None

        def delete_file(self, path):
            deleted.append(path)

    monkeypatch.setattr(
        "backend.app.modules.storage.config.service.StorageConfigService",
        lambda: type("ConfigService", (), {
            "get_raw_config": lambda self: {"target_folder": "/Movies"},
            "provider_factory": Factory(),
            "gateway_class": Gateway,
        })(),
    )

    response = client.delete(f"/api/crawler/tasks/{task_id}?mode=task_movies_and_cloud", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()["data"]
    assert body["deleted_task"] is True
    assert body["deleted_movies"] == 1
    assert body["cloud_delete"] == "completed"
    assert body["cloud_deleted_folders"] == ["/Movies/巨乳/CLOUD-001"]
    assert deleted == ["/Movies/巨乳/CLOUD-001"]


def test_stopped_task_can_be_deleted_and_purges_runtime(monkeypatch, admin_user) -> None:
    from datetime import datetime

    from backend.app.models.crawl_run import CrawlRun
    from backend.app.modules.crawler.tasks.service import CrawlerTaskService

    session = TestingSessionLocal()
    task = CrawlTask(name="停止后删除", storage_location="测试", owner_id=admin_user.id, is_skip=False)
    session.add(task)
    session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="stopped",
        crawl_mode="incremental",
        queued_at=datetime.now(),
        finished_at=datetime.now(),
        error="用户停止任务",
    )
    session.add(run)
    session.commit()

    class Runtime:
        def __init__(self) -> None:
            self.purged: list[list[str]] = []

        def purge_runs(self, run_ids: list[str]) -> None:
            self.purged.append(run_ids)

    runtime = Runtime()
    monkeypatch.setattr("backend.app.modules.crawler.tasks.service.get_runtime_state", lambda: runtime)

    result = CrawlerTaskService(session).delete_task(task.id, admin_user.id, mode="task_only")

    assert result["deleted_task"] is True
    assert result["deleted_runs"] == 1
    assert runtime.purged == [[str(run.id)]]
    assert session.get(CrawlTask, task.id) is None


def test_delete_task_does_not_purge_runtime_when_database_delete_fails(monkeypatch, admin_user) -> None:
    from datetime import datetime

    from backend.app.models.crawl_run import CrawlRun
    from backend.app.modules.crawler.tasks.service import CrawlerTaskService

    session = TestingSessionLocal()
    task = CrawlTask(name="删除失败", storage_location="测试", owner_id=admin_user.id, is_skip=False)
    session.add(task)
    session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="stopped",
        crawl_mode="incremental",
        queued_at=datetime.now(),
        finished_at=datetime.now(),
    )
    session.add(run)
    session.commit()

    class Runtime:
        def __init__(self) -> None:
            self.purged: list[list[str]] = []

        def purge_runs(self, run_ids: list[str]) -> None:
            self.purged.append(run_ids)

    runtime = Runtime()
    monkeypatch.setattr("backend.app.modules.crawler.tasks.service.get_runtime_state", lambda: runtime)

    def fail_delete(*_args, **_kwargs):
        raise RuntimeError("delete failed")

    monkeypatch.setattr("backend.app.modules.crawler.tasks.service.delete_task", fail_delete)

    try:
        CrawlerTaskService(session).delete_task(task.id, admin_user.id, mode="task_only")
    except RuntimeError:
        pass

    assert runtime.purged == []
