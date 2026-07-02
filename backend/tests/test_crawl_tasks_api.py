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


def exact_user_payload() -> dict:
    return {
        "name": "巨乳",
        "is_skip": False,
        "urls": [
            {
                "url": "https://javdb.com/actors/QV49G",
                "url_type": "actors",
                "has_magnet": True,
                "has_chinese_sub": False,
                "sort_type": 0,
                "url_name": "",
            }
        ],
    }


class TestCrawlTasksApi:
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
        assert response.json()["code"] == 400
        assert "URL 重复" in response.json()["msg"]
        assert response.json()["data"] is None

    def test_create_task_accepts_exact_single_url_payload(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)

        response = client.post(
            "/api/crawler/tasks",
            json=exact_user_payload(),
            headers=headers,
        )

        assert response.status_code == HTTPStatus.CREATED
        body = response.json()
        assert body["code"] == 200
        assert body["msg"] == "success"
        created = body["data"]
        assert created["name"] == "巨乳"
        assert created["urls"][0]["url"] == "https://javdb.com/actors/QV49G"
        assert created["urls"][0]["url_type"] == "actors"
        assert created["urls"][0]["has_magnet"] is True
        assert created["urls"][0]["has_chinese_sub"] is False

    def test_create_task_duplicate_name_returns_specific_envelope(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        payload = exact_user_payload()
        first = client.post("/api/crawler/tasks", json=payload, headers=headers)
        assert first.status_code == HTTPStatus.CREATED

        second_payload = exact_user_payload()
        second_payload["urls"][0]["url"] = "https://javdb.com/actors/OTHER"
        response = client.post("/api/crawler/tasks", json=second_payload, headers=headers)

        assert response.status_code == HTTPStatus.CONFLICT
        assert response.json() == {
            "code": 409,
            "msg": "任务名称 '巨乳' 已存在",
            "data": None,
        }

    def test_create_task_duplicate_urls_returns_standard_envelope(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        payload = exact_user_payload()
        payload["urls"].append(payload["urls"][0].copy())

        response = client.post("/api/crawler/tasks", json=payload, headers=headers)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json() == {
            "code": 400,
            "msg": "URL 重复: https://javdb.com/actors/QV49G",
            "data": None,
        }

    def test_update_task_keeps_same_url_without_duplicate_error(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        payload = exact_user_payload()
        created_response = client.post("/api/crawler/tasks", json=payload, headers=headers)
        assert created_response.status_code == HTTPStatus.CREATED
        task_id = created_response.json()["data"]["id"]

        update_response = client.put(
            f"/api/crawler/tasks/{task_id}",
            json=payload,
            headers=headers,
        )

        assert update_response.status_code == HTTPStatus.OK
        body = update_response.json()
        assert body["code"] == 200
        assert body["data"]["name"] == "巨乳"
        assert body["data"]["urls"][0]["url"] == "https://javdb.com/actors/QV49G"

    def test_update_task_persists_url_name(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        payload = exact_user_payload()
        created_response = client.post("/api/crawler/tasks", json=payload, headers=headers)
        assert created_response.status_code == HTTPStatus.CREATED
        task_id = created_response.json()["data"]["id"]

        payload["urls"][0]["url_name"] = "演员 QV49G"
        update_response = client.put(
            f"/api/crawler/tasks/{task_id}",
            json=payload,
            headers=headers,
        )

        assert update_response.status_code == HTTPStatus.OK
        assert update_response.json()["data"]["urls"][0]["url_name"] == "演员 QV49G"

        detail_response = client.get(f"/api/crawler/tasks/{task_id}", headers=headers)
        assert detail_response.status_code == HTTPStatus.OK
        assert detail_response.json()["data"]["urls"][0]["url_name"] == "演员 QV49G"
