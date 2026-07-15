from http import HTTPStatus
import uuid

from fastapi.testclient import TestClient

from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.models.crawl_run import CrawlRun
from backend.tests.conftest import TestingSessionLocal


def auth_headers(client: TestClient, username: str = "admin", password: str = "admin123") -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


class FakeRuntime:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def enqueue_run(self, run_id: str) -> None:
        self.enqueued.append(run_id)


def make_task(owner_id: uuid.UUID, *, name: str = "任务A", is_skip: bool = False) -> tuple[CrawlTask, CrawlTaskUrl, CrawlTaskUrl]:
    session = TestingSessionLocal()
    task = CrawlTask(name=name, storage_location="JP", is_skip=is_skip, owner_id=owner_id)
    task.urls = [
        CrawlTaskUrl(
            position=0,
            url="https://javdb.com/actors/a",
            url_type="actors",
            has_magnet=True,
            has_chinese_sub=False,
            sort_type=0,
            source="javdb",
            final_url="https://javdb.com/actors/a",
            url_name="演员A",
        ),
        CrawlTaskUrl(
            position=1,
            url="https://javdb.com/tags/b",
            url_type="tags",
            has_magnet=False,
            has_chinese_sub=True,
            sort_type=0,
            source="javdb",
            final_url="https://javdb.com/tags/b",
            url_name="标签B",
        ),
    ]
    session.add(task)
    session.commit()
    session.refresh(task)
    first, second = task.urls
    session.expunge(task)
    session.close()
    return task, first, second


def test_url_subset_run_creates_queued_incremental_run(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client)
    task, first_url, second_url = make_task(admin_user.id)
    runtime = FakeRuntime()
    monkeypatch.setattr("backend.app.modules.crawler.tasks.service.get_runtime_state", lambda: runtime)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started", lambda runtime: None)

    response = client.post(
        f"/api/crawler/tasks/{task.id}/url-run",
        json={"url_ids": [str(first_url.id), str(second_url.id)], "crawl_mode": "incremental"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["task_id"] == str(task.id)
    assert body["status"] == "queued"
    assert body["crawl_mode"] == "incremental"
    assert body["result"] == {
        "url_subset": True,
        "selected_task_url_ids": [str(first_url.id), str(second_url.id)],
        "selected_task_url_count": 2,
    }
    assert runtime.enqueued == [body["id"]]


def test_url_subset_run_accepts_full_mode(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client)
    task, first_url, _second_url = make_task(admin_user.id)
    runtime = FakeRuntime()
    monkeypatch.setattr("backend.app.modules.crawler.tasks.service.get_runtime_state", lambda: runtime)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started", lambda runtime: None)

    response = client.post(
        f"/api/crawler/tasks/{task.id}/url-run",
        json={"url_ids": [str(first_url.id)], "crawl_mode": "full"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["data"]["crawl_mode"] == "full"


def test_url_subset_run_rejects_duplicate_url_ids(client: TestClient, admin_user) -> None:
    headers = auth_headers(client)
    task, first_url, _second_url = make_task(admin_user.id)

    response = client.post(
        f"/api/crawler/tasks/{task.id}/url-run",
        json={"url_ids": [str(first_url.id), str(first_url.id)], "crawl_mode": "incremental"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "任务 URL 不能重复选择" in str(response.json())


def test_url_subset_run_rejects_empty_url_selection(client: TestClient, admin_user) -> None:
    headers = auth_headers(client)
    task, _first_url, _second_url = make_task(admin_user.id)

    response = client.post(
        f"/api/crawler/tasks/{task.id}/url-run",
        json={"url_ids": [], "crawl_mode": "incremental"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "至少选择 1 条任务 URL" in str(response.json())


def test_url_subset_run_rejects_foreign_url_id(client: TestClient, admin_user) -> None:
    headers = auth_headers(client)
    task, first_url, _second_url = make_task(admin_user.id, name="任务A")
    other_task, other_url, _other_second = make_task(admin_user.id, name="任务B")

    response = client.post(
        f"/api/crawler/tasks/{task.id}/url-run",
        json={"url_ids": [str(first_url.id), str(other_url.id)], "crawl_mode": "incremental"},
        headers=headers,
    )

    assert str(other_task.id) != str(task.id)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "选择的 URL 不属于该任务" in str(response.json())


def test_url_subset_run_rejects_disabled_task(client: TestClient, admin_user) -> None:
    headers = auth_headers(client)
    task, first_url, _second_url = make_task(admin_user.id, is_skip=True)

    response = client.post(
        f"/api/crawler/tasks/{task.id}/url-run",
        json={"url_ids": [str(first_url.id)], "crawl_mode": "incremental"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "禁用任务不能执行" in str(response.json())
