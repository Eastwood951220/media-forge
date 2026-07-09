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
