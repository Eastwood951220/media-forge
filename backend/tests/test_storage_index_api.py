from http import HTTPStatus

from fastapi.testclient import TestClient


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_storage_index_status_returns_never_built(client: TestClient, admin_user, tmp_path, monkeypatch):
    from shared.runtime_config import RuntimeConfigPaths
    paths = RuntimeConfigPaths(tmp_path, tmp_path / "database.conf", tmp_path / "redis.conf", tmp_path / "storage.conf", tmp_path / "storage_index.jsonl", tmp_path / "storage_index.meta.json")
    monkeypatch.setattr("backend.app.modules.storage.index.store.RuntimeConfigPaths.from_env", lambda: paths)

    response = client.get("/api/storage/index/status", headers=auth_headers(client, admin_user))

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["status"] == "never_built"


def test_storage_index_refresh_starts_background_task(client: TestClient, admin_user, monkeypatch):
    captured = {}

    def fake_start(mode, service_factory):
        captured["mode"] = mode
        captured["service_factory"] = service_factory
        return {"started": True, "mode": mode, "status": "running", "message": "存储索引任务启动成功"}

    monkeypatch.setattr("backend.app.modules.storage.index.router.start_storage_index_refresh", fake_start)

    response = client.post(
        "/api/storage/index/refresh",
        json={"mode": "incremental"},
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.OK
    assert captured["mode"] == "incremental"
    assert response.json()["data"] == {
        "started": True,
        "mode": "incremental",
        "status": "running",
        "message": "存储索引任务启动成功",
    }


def test_storage_index_refresh_rejects_when_already_running(client: TestClient, admin_user, monkeypatch):
    from backend.app.modules.storage.index.background import StorageIndexAlreadyRunningError

    def fake_start(mode, service_factory):
        raise StorageIndexAlreadyRunningError("存储索引任务正在进行中")

    monkeypatch.setattr("backend.app.modules.storage.index.router.start_storage_index_refresh", fake_start)

    response = client.post(
        "/api/storage/index/refresh",
        json={"mode": "full"},
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["msg"] == "存储索引任务正在进行中"


def test_storage_index_refresh_reports_startup_failure(client: TestClient, admin_user, monkeypatch):
    def fake_start(mode, service_factory):
        raise RuntimeError("missing storage config")

    monkeypatch.setattr("backend.app.modules.storage.index.router.start_storage_index_refresh", fake_start)

    response = client.post(
        "/api/storage/index/refresh",
        json={"mode": "full"},
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["msg"] == "存储索引任务启动失败: missing storage config"
