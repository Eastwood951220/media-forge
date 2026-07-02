from datetime import datetime
from http import HTTPStatus

from fastapi.testclient import TestClient

from backend.app.models.crawl_run import CrawlRun
from backend.tests.conftest import TestingSessionLocal


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


class FakeRuntime:
    def __init__(self) -> None:
        self.cleaned = False
        self.enqueued = []

    def cleanup_runtime(self) -> None:
        self.cleaned = True

    def enqueue_run(self, run_id: str) -> None:
        self.enqueued.append(run_id)

    def queue_status(self):
        return {"queue_size": len(self.enqueued), "is_running": False, "current_run_id": None, "stop_requested": False}


def test_cleanup_interrupted_runs_marks_queued_and_running_stopped() -> None:
    from backend.app.modules.crawler.runtime.service import cleanup_interrupted_runs

    session = TestingSessionLocal()
    queued = CrawlRun(task_name="queued task", status="queued", crawl_mode="incremental", queued_at=datetime.now())
    running = CrawlRun(task_name="running task", status="running", crawl_mode="full", queued_at=datetime.now())
    completed = CrawlRun(task_name="done task", status="completed", crawl_mode="full", queued_at=datetime.now())
    session.add_all([queued, running, completed])
    session.commit()

    runtime = FakeRuntime()
    count = cleanup_interrupted_runs(session, runtime)

    assert count == 2
    assert runtime.cleaned is True
    assert queued.status == "stopped"
    assert running.status == "stopped"
    assert completed.status == "completed"
    assert "服务重启" in (queued.error or "")


def test_queue_status_endpoint_returns_runtime_state(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)

    class Runtime:
        def queue_status(self):
            return {"queue_size": 0, "is_running": False, "current_run_id": None, "stop_requested": False}

    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: Runtime())

    response = client.get("/api/crawler/runs/queue-status", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["queue_size"] == 0


def test_task_run_endpoint_creates_queued_run(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = task_response.json()["data"]["id"]
    runtime = FakeRuntime()
    monkeypatch.setattr("backend.app.modules.crawler.tasks.router.get_runtime_state", lambda: runtime)

    response = client.post(
        f"/api/crawler/tasks/{task_id}/run",
        json={"crawl_mode": "incremental"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["task_id"] == task_id
    assert body["status"] == "queued"
    assert body["crawl_mode"] == "incremental"
    assert runtime.enqueued == [body["id"]]


def test_run_list_and_detail_endpoints(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = task_response.json()["data"]["id"]
    monkeypatch.setattr("backend.app.modules.crawler.tasks.router.get_runtime_state", lambda: FakeRuntime())

    run_response = client.post(f"/api/crawler/tasks/{task_id}/run", json={"crawl_mode": "full"}, headers=headers)
    run_id = run_response.json()["data"]["id"]

    list_response = client.get("/api/crawler/runs", headers=headers)
    detail_response = client.get(f"/api/crawler/runs/{run_id}", headers=headers)
    tasks_response = client.get(f"/api/crawler/runs/{run_id}/tasks", headers=headers)

    assert list_response.status_code == HTTPStatus.OK
    assert list_response.json()["total"] == 1
    assert detail_response.json()["data"]["id"] == run_id
    assert tasks_response.json()["rows"] == []


def task_payload() -> dict:
    return {
        "name": "test-task",
        "is_skip": False,
        "urls": [{"url": "https://javdb.com/actors/a", "url_type": "actors"}],
    }
