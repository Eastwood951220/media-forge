from http import HTTPStatus

from fastapi.testclient import TestClient


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def task_payload() -> dict:
    return {
        "name": "每日媒体索引",
        "description": "跟踪测试资源",
        "keywords": ["media", "forge"],
        "target_websites": ["https://example.com"],
        "schedule": "daily",
        "max_pages": 100,
        "crawl_depth": 3,
    }


class TestCrawlTasksApi:
    def test_legacy_route_returns_empty_list_instead_of_500(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        response = client.get(
            "/api/crawl-tasks?skip=0&limit=20",
            headers=auth_headers(client, admin_user),
        )

        assert response.status_code == HTTPStatus.OK
        assert response.json() == []

    def test_canonical_route_creates_and_lists_task(
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
        created = created_response.json()
        assert created["name"] == "每日媒体索引"
        assert created["owner_id"] == str(admin_user.id)
        assert created["status"] == "pending"

        list_response = client.get("/api/crawler/tasks", headers=headers)
        assert list_response.status_code == HTTPStatus.OK
        assert [item["name"] for item in list_response.json()] == ["每日媒体索引"]

    def test_legacy_route_uses_same_data_as_canonical_route(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        client.post("/api/crawler/tasks", json=task_payload(), headers=headers)

        response = client.get("/api/crawl-tasks?skip=0&limit=20", headers=headers)

        assert response.status_code == HTTPStatus.OK
        assert [item["name"] for item in response.json()] == ["每日媒体索引"]

    def test_canonical_route_filters_tasks_by_keyword(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        daily_payload = task_payload()
        daily_payload["name"] = "每日媒体索引"
        archive_payload = task_payload()
        archive_payload["name"] = "归档清理任务"

        client.post("/api/crawler/tasks", json=daily_payload, headers=headers)
        client.post("/api/crawler/tasks", json=archive_payload, headers=headers)

        response = client.get(
            "/api/crawler/tasks?keyword=每日",
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        body = response.json()
        rows = body["data"]["rows"] if "data" in body else body["rows"]
        total = body["data"]["total"] if "data" in body else body["total"]
        assert total == 1
        assert [item["name"] for item in rows] == ["每日媒体索引"]
