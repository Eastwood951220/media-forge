from datetime import datetime
from http import HTTPStatus

from fastapi.testclient import TestClient

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.tests.conftest import TestingSessionLocal


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
        "storage_location": "每日演员任务",
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
        "storage_location": "巨乳",
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

    def test_list_tasks_without_pagination_returns_all_matching_rows(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        session = TestingSessionLocal()
        session.add_all(
            [
                CrawlTask(name=f"任务{i:02d}", storage_location=f"P{i:02d}"[:10], owner_id=admin_user.id)
                for i in range(25)
            ]
        )
        session.commit()
        session.close()

        response = client.get("/api/crawler/tasks", headers=headers)

        assert response.status_code == HTTPStatus.OK
        body = response.json()
        assert body["total"] == 25
        assert len(body["rows"]) == 25

    def test_stats_returns_total_enabled_and_disabled_counts(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        session = TestingSessionLocal()
        session.add_all(
            [
                CrawlTask(name="启用任务1", storage_location="ENABLED1", owner_id=admin_user.id, is_skip=False),
                CrawlTask(name="启用任务2", storage_location="ENABLED2", owner_id=admin_user.id, is_skip=False),
                CrawlTask(name="禁用任务", storage_location="DISABLED", owner_id=admin_user.id, is_skip=True),
            ]
        )
        session.commit()
        session.close()

        response = client.get("/api/crawler/tasks/stats", headers=headers)

        assert response.status_code == HTTPStatus.OK
        assert response.json()["data"] == {
            "total": 3,
            "enabled": 2,
            "disabled": 1,
        }

    def test_list_tasks_returns_latest_run_metadata(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        session = TestingSessionLocal()
        task = CrawlTask(name="有码任务", storage_location="AV", owner_id=admin_user.id, status="success")
        session.add(task)
        session.flush()
        session.add_all(
            [
                CrawlRun(
                    task_id=task.id,
                    task_name=task.name,
                    status="failed",
                    crawl_mode="incremental",
                    created_at=datetime(2026, 7, 2, 8, 0, 0),
                ),
                CrawlRun(
                    task_id=task.id,
                    task_name=task.name,
                    status="completed",
                    crawl_mode="full",
                    created_at=datetime(2026, 7, 3, 8, 0, 0),
                ),
            ]
        )
        session.commit()
        session.close()

        response = client.get("/api/crawler/tasks", headers=headers)

        assert response.status_code == HTTPStatus.OK
        row = response.json()["rows"][0]
        assert row["name"] == "有码任务"
        assert row["last_run_status"] == "completed"
        assert row["last_run_at"].startswith("2026-07-03T08:00:00")


def test_create_temporary_run_seeds_detail_rows_and_enqueues(client: TestClient, admin_user, monkeypatch) -> None:
    import uuid as uuid_module

    from backend.app.models.crawl_run import CrawlRunDetailTask
    from backend.app.modules.crawler.runs.schemas import CrawlRunRead

    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = task_response.json()["data"]["id"]

    class Runtime:
        def __init__(self) -> None:
            self.enqueued: list[str] = []
            self.cleared: list[str] = []

        def enqueue_run(self, run_id: str) -> None:
            self.enqueued.append(run_id)

        def clear_stop(self, run_id: str) -> None:
            self.cleared.append(run_id)

    runtime = Runtime()
    monkeypatch.setattr("backend.app.modules.crawler.tasks.service.get_runtime_state", lambda: runtime)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started", lambda runtime: None)

    response = client.post(
        "/api/crawler/tasks/temp-run",
        json={
            "task_id": task_id,
            "detail_urls": [
                " https://javdb.com/v/abc123 ",
                "https://javdb.com/v/def456",
            ],
        },
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["task_id"] == task_id
    assert body["status"] == "queued"
    assert body["crawl_mode"] == "temporary"
    assert body["result"] == {"temporary": True, "detail_url_count": 2}
    assert runtime.enqueued == [body["id"]]

    session = TestingSessionLocal()
    try:
        run_uuid = uuid_module.UUID(body["id"])
        rows = (
            session.query(CrawlRunDetailTask)
            .filter(CrawlRunDetailTask.run_id == run_uuid)
            .order_by(CrawlRunDetailTask.created_at.asc())
            .all()
        )
        assert [row.source_url for row in rows] == [
            "https://javdb.com/v/abc123",
            "https://javdb.com/v/def456",
        ]
        assert [row.status for row in rows] == ["pending_crawl", "pending_crawl"]
        assert [row.task_url_type for row in rows] == ["temporary_detail", "temporary_detail"]
        assert [row.source_url_name for row in rows] == ["临时任务", "临时任务"]
    finally:
        session.close()


def test_create_temporary_run_rejects_invalid_inputs(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = task_response.json()["data"]["id"]

    cases = [
        ([], "至少需要 1 条详情页 URL"),
        (["https://javdb.com/actors/abc"], "第 1 条不是有效的 JavDB 详情页 URL"),
        (["https://javdb.com/v/abc", " https://javdb.com/v/abc "], "第 2 条详情页 URL 重复"),
        ([f"https://javdb.com/v/{index:03d}" for index in range(51)], "临时任务最多支持 50 条详情页 URL"),
    ]

    for detail_urls, expected_message in cases:
        response = client.post(
            "/api/crawler/tasks/temp-run",
            json={"task_id": task_id, "detail_urls": detail_urls},
            headers=headers,
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert expected_message in response.json()["msg"]


def test_create_temporary_run_rejects_disabled_task(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    payload = task_payload()
    payload["is_skip"] = True
    task_response = client.post("/api/crawler/tasks", json=payload, headers=headers)
    task_id = task_response.json()["data"]["id"]

    response = client.post(
        "/api/crawler/tasks/temp-run",
        json={"task_id": task_id, "detail_urls": ["https://javdb.com/v/abc123"]},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["msg"] == "禁用任务不能执行"
