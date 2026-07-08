from datetime import datetime
from http import HTTPStatus
import uuid

from fastapi.testclient import TestClient

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.runs.logs import append_run_log, build_run_log
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

    def claim_next_run(self):
        return self.enqueued.pop(0) if self.enqueued else None

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
    task_id = uuid.UUID(task_response.json()["data"]["id"])
    runtime = FakeRuntime()
    monkeypatch.setattr("backend.app.modules.crawler.tasks.service.get_runtime_state", lambda: runtime)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started", lambda runtime: None)

    response = client.post(
        f"/api/crawler/tasks/{task_id}/run",
        json={"crawl_mode": "incremental"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["task_id"] == str(task_id)
    assert body["status"] == "queued"
    assert body["crawl_mode"] == "incremental"
    assert runtime.enqueued == [body["id"]]


def test_run_list_and_detail_endpoints(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = uuid.UUID(task_response.json()["data"]["id"])
    monkeypatch.setattr("backend.app.modules.crawler.tasks.service.get_runtime_state", lambda: FakeRuntime())

    run_response = client.post(f"/api/crawler/tasks/{task_id}/run", json={"crawl_mode": "full"}, headers=headers)
    run_id = run_response.json()["data"]["id"]

    list_response = client.get("/api/crawler/runs", headers=headers)
    detail_response = client.get(f"/api/crawler/runs/{run_id}", headers=headers)
    tasks_response = client.get(f"/api/crawler/runs/{run_id}/tasks", headers=headers)

    assert list_response.status_code == HTTPStatus.OK
    assert list_response.json()["total"] == 1
    assert detail_response.json()["data"]["id"] == run_id
    assert tasks_response.json()["rows"] == []


def test_run_detail_excludes_jsonl_logs_and_logs_endpoint_returns_them(client: TestClient, admin_user, monkeypatch, tmp_path) -> None:
    from backend.app.modules.crawler.runs import logs as run_logs

    monkeypatch.setattr(run_logs, "RUN_LOG_DIR", str(tmp_path))
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="running", crawl_mode="incremental", queued_at=datetime.now())
    session.add(run)
    session.commit()
    run_id = str(run.id)

    append_run_log(run_id, build_run_log("INFO", "任务开始执行"))
    append_run_log(run_id, build_run_log("ERROR", "入库失败", code="AAA-001"))

    detail_response = client.get(f"/api/crawler/runs/{run_id}", headers=headers)
    logs_response = client.get(f"/api/crawler/runs/{run_id}/logs", headers=headers)

    assert detail_response.status_code == HTTPStatus.OK
    detail_body = detail_response.json()["data"]
    assert detail_body["id"] == run_id
    assert detail_body["logs"] == []

    assert logs_response.status_code == HTTPStatus.OK
    logs_body = logs_response.json()["data"]
    assert [entry["message"] for entry in logs_body] == ["任务开始执行", "入库失败"]
    assert logs_body[1]["context"] == {"code": "AAA-001"}


def test_run_logs_endpoint_returns_404_for_missing_run(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)

    response = client.get("/api/crawler/runs/00000000-0000-0000-0000-000000000001/logs", headers=headers)

    assert response.status_code == HTTPStatus.NOT_FOUND


def task_payload() -> dict:
    return {
        "name": "test-task",
        "storage_location": "test",
        "is_skip": False,
        "urls": [{"url": "https://javdb.com/actors/a", "url_type": "actors"}],
    }


from backend.app.models.crawl_run import CrawlRunDetailTask


class RuntimeForStopRestart(FakeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.stopped = []
        self.cleared = []

    def request_stop(self, run_id: str) -> None:
        self.stopped.append(run_id)

    def clear_stop(self, run_id: str) -> None:
        self.cleared.append(run_id)


def test_stop_running_run_sets_stop_signal(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="running", crawl_mode="incremental")
    session.add(run)
    session.commit()
    run_id = str(run.id)
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(f"/api/crawler/runs/{run_id}/stop", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert runtime.stopped == [run_id]
    assert response.json()["data"]["status"] == "stopped"


def test_restart_copies_unfinished_subtasks(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started", lambda runtime: None)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="stopped", crawl_mode="incremental")
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="A", source_url="https://a", source_name="A", status="saved", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="B", source_url="https://b", source_name="B", status="crawl_failed", created_at=datetime.now()),
    ])
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(f"/api/crawler/runs/{run.id}/restart", headers=headers)

    assert response.status_code == HTTPStatus.CREATED
    new_run = response.json()["data"]
    assert new_run["id"] == str(run.id)
    assert new_run["resumed_from"] is None
    assert runtime.enqueued == [str(run.id)]

    tasks_response = client.get(f"/api/crawler/runs/{run.id}/tasks", headers=headers)
    assert [(row["code"], row["status"]) for row in tasks_response.json()["rows"]] == [
        ("A", "saved"),
        ("B", "pending_crawl"),
    ]


def test_stop_running_run_resets_unfinished_detail_tasks_to_pending(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="running", crawl_mode="incremental")
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="P", source_url="https://p", source_name="P", status="pending_crawl", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="C", source_url="https://c", source_name="C", status="crawl_failed", error="timeout", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="F", source_url="https://f", source_name="F", status="save_failed", error="db", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="S", source_url="https://s", source_name="S", status="saved", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="K", source_url="https://k", source_name="K", status="skipped", created_at=datetime.now()),
    ])
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(f"/api/crawler/runs/{run.id}/stop", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["status"] == "stopped"
    assert runtime.stopped == [str(run.id)]

    session.expire_all()
    statuses = {
        row.code: (row.status, row.error)
        for row in session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    }
    assert statuses["P"] == ("pending_crawl", None)
    assert statuses["C"] == ("pending_crawl", None)
    assert statuses["F"] == ("pending_crawl", None)
    assert statuses["S"] == ("saved", None)
    assert statuses["K"] == ("skipped", None)


def test_delete_run_removes_only_run_and_detail_tasks(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="completed", crawl_mode="incremental")
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="A", source_url="https://a", source_name="A", status="saved", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="B", source_url="https://b", source_name="B", status="pending_crawl", created_at=datetime.now()),
    ])
    session.commit()
    run_id = run.id

    response = client.delete(f"/api/crawler/runs/{run.id}", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"] == {"id": str(run_id), "deleted": True}
    session.expire_all()
    assert session.get(CrawlRun, run_id) is None
    assert session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run_id).count() == 0


def test_restart_after_detail_phase_requeues_same_run_and_keeps_terminal_details(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = uuid.UUID(task_response.json()["data"]["id"])
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started", lambda runtime: None)
    session = TestingSessionLocal()
    run = CrawlRun(
        task_id=task_id,
        task_name="任务",
        status="stopped",
        crawl_mode="incremental",
        queued_at=datetime.now(),
        started_at=datetime.now(),
        finished_at=datetime.now(),
        result={"stopped": True},
        error="用户停止任务",
    )
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="A", source_url="https://a", source_name="A", status="saved", created_at=datetime.now(), crawled_at=datetime.now(), saved_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="B", source_url="https://b", source_name="B", status="crawl_failed", error="timeout", created_at=datetime.now(), crawled_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="C", source_url="https://c", source_name="C", status="skipped", error="already_exists", created_at=datetime.now(), crawled_at=datetime.now()),
    ])
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(f"/api/crawler/runs/{run.id}/restart", headers=headers)

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["id"] == str(run.id)
    assert body["status"] == "queued"
    assert body["task_id"] == str(task_id)
    assert body["started_at"] is None
    assert body["finished_at"] is None
    assert body["result"] is None
    assert body["error"] is None
    assert runtime.enqueued == [str(run.id)]
    assert runtime.cleared == [str(run.id)]

    tasks_response = client.get(f"/api/crawler/runs/{run.id}/tasks", headers=headers)
    rows = tasks_response.json()["rows"]
    assert [(row["code"], row["status"], row["error"]) for row in rows] == [
        ("A", "saved", None),
        ("B", "pending_crawl", None),
        ("C", "skipped", "already_exists"),
    ]


def test_restart_after_list_phase_discards_partial_list_tasks_and_requeues_same_run(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = uuid.UUID(task_response.json()["data"]["id"])
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started", lambda runtime: None)
    session = TestingSessionLocal()
    run = CrawlRun(task_id=task_id, task_name="任务", status="stopped", crawl_mode="incremental")
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="P", source_url="https://p", source_name="P", status="pending_crawl", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="K", source_url="https://k", source_name="K", status="skipped", error="already_exists", created_at=datetime.now()),
    ])
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(f"/api/crawler/runs/{run.id}/restart", headers=headers)

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["id"] == str(run.id)
    assert body["status"] == "queued"
    assert body["task_id"] == str(task_id)
    assert runtime.enqueued == [str(run.id)]
    assert runtime.cleared == [str(run.id)]

    tasks_response = client.get(f"/api/crawler/runs/{run.id}/tasks", headers=headers)
    assert tasks_response.json()["rows"] == []


def test_restart_stopped_run_without_subtasks_requeues_same_run(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = uuid.UUID(task_response.json()["data"]["id"])
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started", lambda runtime: None)
    session = TestingSessionLocal()
    run = CrawlRun(task_id=task_id, task_name="任务", status="stopped", crawl_mode="incremental")
    session.add(run)
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(f"/api/crawler/runs/{run.id}/restart", headers=headers)

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["id"] == str(run.id)
    assert body["status"] == "queued"
    assert body["task_id"] == str(task_id)
    assert runtime.enqueued == [str(run.id)]
    assert runtime.cleared == [str(run.id)]

    tasks_response = client.get(f"/api/crawler/runs/{run.id}/tasks", headers=headers)
    assert tasks_response.json()["rows"] == []


def test_retry_one_failed_detail_requeues_same_run(client: TestClient, admin_user, monkeypatch) -> None:
    import uuid
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = uuid.UUID(task_response.json()["data"]["id"])
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started", lambda runtime: None)
    session = TestingSessionLocal()
    run = CrawlRun(
        task_id=task_id,
        task_name="任务",
        status="completed",
        crawl_mode="incremental",
        queued_at=datetime.now(),
        started_at=datetime.now(),
        finished_at=datetime.now(),
        result={"total_tasks": 2},
        error="old error",
    )
    session.add(run)
    session.flush()
    failed = CrawlRunDetailTask(
        run_id=run.id,
        task_name="任务",
        code="FAIL-001",
        source_url="https://example.test/fail-001",
        source_name="FAIL 001",
        status="crawl_failed",
        error="timeout",
        item_data={"stale": True},
        created_at=datetime.now(),
        crawled_at=datetime.now(),
    )
    other_failed = CrawlRunDetailTask(
        run_id=run.id,
        task_name="任务",
        code="FAIL-002",
        source_url="https://example.test/fail-002",
        source_name="FAIL 002",
        status="crawl_failed",
        error="dns",
        created_at=datetime.now(),
        crawled_at=datetime.now(),
    )
    saved = CrawlRunDetailTask(
        run_id=run.id,
        task_name="任务",
        code="SAVED-001",
        source_url="https://example.test/saved-001",
        source_name="SAVED 001",
        status="saved",
        created_at=datetime.now(),
        crawled_at=datetime.now(),
        saved_at=datetime.now(),
    )
    session.add_all([failed, other_failed, saved])
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(
        f"/api/crawler/runs/{run.id}/tasks/retry",
        json={"detail_ids": [str(failed.id)], "retry_all": False},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["id"] == str(run.id)
    assert body["status"] == "queued"
    assert body["started_at"] is None
    assert body["finished_at"] is None
    assert body["result"] == {"detail_retry": True}
    assert body["error"] is None
    assert runtime.cleared == [str(run.id)]
    assert runtime.enqueued == [str(run.id)]

    session.expire_all()
    statuses = {
        row.code: (row.status, row.error, row.item_data, row.crawled_at, row.saved_at)
        for row in session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    }
    assert statuses["FAIL-001"] == ("pending_crawl", None, None, None, None)
    assert statuses["FAIL-002"][0] == "crawl_failed"
    assert statuses["SAVED-001"][0] == "saved"


def test_retry_all_failed_details_requeues_all_crawl_failed_rows(client: TestClient, admin_user, monkeypatch) -> None:
    import uuid
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = uuid.UUID(task_response.json()["data"]["id"])
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started", lambda runtime: None)
    session = TestingSessionLocal()
    run = CrawlRun(task_id=task_id, task_name="任务", status="failed", crawl_mode="incremental")
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="A", source_url="https://a", source_name="A", status="crawl_failed", error="a", created_at=datetime.now(), crawled_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="B", source_url="https://b", source_name="B", status="crawl_failed", error="b", created_at=datetime.now(), crawled_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="C", source_url="https://c", source_name="C", status="save_failed", error="db", created_at=datetime.now(), crawled_at=datetime.now()),
    ])
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(
        f"/api/crawler/runs/{run.id}/tasks/retry",
        json={"retry_all": True},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["data"]["status"] == "queued"
    session.expire_all()
    statuses = {
        row.code: row.status
        for row in session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    }
    assert statuses == {"A": "pending_crawl", "B": "pending_crawl", "C": "save_failed"}


def test_retry_failed_details_rejects_running_run(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="running", crawl_mode="incremental")
    session.add(run)
    session.flush()
    detail = CrawlRunDetailTask(run_id=run.id, task_name="任务", code="A", source_url="https://a", source_name="A", status="crawl_failed", created_at=datetime.now())
    session.add(detail)
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(
        f"/api/crawler/runs/{run.id}/tasks/retry",
        json={"detail_ids": [str(detail.id)]},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    body = response.json()
    assert "运行中" in str(body)
    assert runtime.enqueued == []


def test_retry_failed_details_rejects_non_crawl_failed_selection(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="completed", crawl_mode="incremental")
    session.add(run)
    session.flush()
    detail = CrawlRunDetailTask(run_id=run.id, task_name="任务", code="A", source_url="https://a", source_name="A", status="save_failed", created_at=datetime.now())
    session.add(detail)
    session.commit()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: RuntimeForStopRestart())

    response = client.post(
        f"/api/crawler/runs/{run.id}/tasks/retry",
        json={"detail_ids": [str(detail.id)]},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "crawl_failed" in str(response.json())


def test_retry_failed_details_rejects_detail_from_other_run(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务1", status="completed", crawl_mode="incremental")
    other_run = CrawlRun(task_name="任务2", status="completed", crawl_mode="incremental")
    session.add_all([run, other_run])
    session.flush()
    detail = CrawlRunDetailTask(run_id=other_run.id, task_name="任务2", code="A", source_url="https://a", source_name="A", status="crawl_failed", created_at=datetime.now())
    session.add(detail)
    session.commit()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: RuntimeForStopRestart())

    response = client.post(
        f"/api/crawler/runs/{run.id}/tasks/retry",
        json={"detail_ids": [str(detail.id)]},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "不属于当前运行" in str(response.json()) or "无效" in str(response.json())


def test_run_tasks_returns_url_context_and_supports_keyword_filter(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="completed", crawl_mode="incremental")
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(
            run_id=run.id,
            task_name="任务",
            code="AAA-001",
            source_url="https://javdb.com/v/aaa001",
            source_name="AAA 001",
            source_url_name="演员A",
            task_url="https://javdb.com/actors/a",
            task_final_url="https://javdb.com/actors/a?page=1",
            task_url_type="actors",
            status="saved",
            created_at=datetime.now(),
        ),
        CrawlRunDetailTask(
            run_id=run.id,
            task_name="任务",
            code="BBB-001",
            source_url="https://javdb.com/v/bbb001",
            source_name="BBB 001",
            source_url_name="标签B",
            task_url="https://javdb.com/tags/b",
            task_final_url="https://javdb.com/tags/b?page=1",
            task_url_type="tags",
            status="pending_crawl",
            created_at=datetime.now(),
        ),
    ])
    session.commit()

    response = client.get(f"/api/crawler/runs/{run.id}/tasks?keyword=标签B", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["code"] == "BBB-001"
    assert body["rows"][0]["source_url_name"] == "标签B"
    assert body["rows"][0]["task_url"] == "https://javdb.com/tags/b"
    assert body["rows"][0]["task_final_url"] == "https://javdb.com/tags/b?page=1"
    assert body["rows"][0]["task_url_type"] == "tags"


def test_run_tasks_uses_server_side_pagination(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="completed", crawl_mode="incremental")
    session.add(run)
    session.flush()
    for index in range(5):
        session.add(
            CrawlRunDetailTask(
                run_id=run.id,
                task_name="任务",
                code=f"PAGE-{index}",
                source_url=f"https://javdb.com/v/page-{index}",
                source_name=f"PAGE {index}",
                source_url_name="分页来源",
                status="pending_crawl",
                created_at=datetime(2026, 7, 8, 0, 0, index),
            )
        )
    session.commit()

    response = client.get(f"/api/crawler/runs/{run.id}/tasks?skip=2&limit=2", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 5
    assert [row["code"] for row in body["rows"]] == ["PAGE-2", "PAGE-3"]


def test_detail_row_to_task_info_preserves_url_context() -> None:
    detail = CrawlRunDetailTask(
        run_id=uuid.uuid4(),
        task_name="任务",
        code="AAA-001",
        source_url="https://javdb.com/v/aaa001",
        source_name="AAA 001",
        source_url_name="演员A",
        task_url="https://javdb.com/actors/a",
        task_final_url="https://javdb.com/actors/a?page=1",
        task_url_type="actors",
        status="pending_crawl",
        created_at=datetime.now(),
    )

    from backend.app.modules.crawler.runtime.details import detail_row_to_task_info

    assert detail_row_to_task_info(detail) == {
        "code": "AAA-001",
        "url": "https://javdb.com/v/aaa001",
        "name": "AAA 001",
        "_task_url": "https://javdb.com/actors/a",
        "_task_final_url": "https://javdb.com/actors/a?page=1",
        "_task_url_type": "actors",
        "_task_url_name": "演员A",
    }


def test_on_tasks_batch_created_persists_url_context(admin_user) -> None:
    from backend.app.modules.crawler.runtime.callbacks import CrawlerCallbackContext, build_crawl_callbacks
    from backend.app.modules.crawler.runtime.detail_index import DetailTaskIndex
    from backend.app.modules.crawler.runtime.progress import new_progress

    class Runtime:
        def write_progress(self, _run_id: str, _progress: dict) -> None:
            return None

        def is_stop_requested(self, _run_id: str) -> bool:
            return False

    session = TestingSessionLocal()
    task = CrawlTask(name="任务", storage_location="local", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    run = CrawlRun(task_id=task.id, task_name="任务", status="running", crawl_mode="incremental")
    session.add(run)
    session.commit()

    ctx = CrawlerCallbackContext(
        db=session,
        run=run,
        task=task,
        runtime=Runtime(),
        detail_index=DetailTaskIndex(),
        progress=new_progress(),
    )
    callbacks = build_crawl_callbacks(ctx)

    callbacks.on_tasks_batch_created([
        {
            "code": "AAA-001",
            "url": "https://javdb.com/v/aaa001",
            "name": "AAA 001",
            "_task_url_name": "演员A",
            "_task_url": "https://javdb.com/actors/a",
            "_task_final_url": "https://javdb.com/actors/a?page=1",
            "_task_url_type": "actors",
        }
    ])

    detail = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).one()

    assert detail.source_url_name == "演员A"
    assert detail.task_url == "https://javdb.com/actors/a"
    assert detail.task_final_url == "https://javdb.com/actors/a?page=1"
    assert detail.task_url_type == "actors"


def test_run_task_rows_created_from_spider_payload_keep_url_context(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="running", crawl_mode="incremental")
    session.add(run)
    session.flush()
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name="任务",
        code="AAA-001",
        source_url="https://javdb.com/v/aaa001",
        source_name="AAA 001",
        source_url_name="演员A",
        task_url="https://javdb.com/actors/a",
        task_final_url="https://javdb.com/actors/a?page=1",
        task_url_type="actors",
        status="pending_crawl",
        created_at=datetime.now(),
    )
    session.add(detail)
    session.commit()

    response = client.get(f"/api/crawler/runs/{run.id}/tasks", headers=headers)

    assert response.status_code == HTTPStatus.OK
    row = response.json()["rows"][0]
    assert row["source_url_name"] == "演员A"
    assert row["task_url"] == "https://javdb.com/actors/a"
    assert row["task_final_url"] == "https://javdb.com/actors/a?page=1"
    assert row["task_url_type"] == "actors"
