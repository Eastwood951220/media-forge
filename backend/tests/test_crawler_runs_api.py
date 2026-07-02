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

    def cleanup_runtime(self) -> None:
        self.cleaned = True


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
