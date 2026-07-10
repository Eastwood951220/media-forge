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


def test_storage_index_refresh_accepts_incremental_mode(client: TestClient, admin_user, monkeypatch):
    from backend.app.modules.storage.index.models import StorageIndexMetadata

    captured = {}

    class Service:
        def open_provider(self):
            class Context:
                def __enter__(self):
                    return {"target_folder": "/Movies"}, object()
                def __exit__(self, exc_type, exc, tb):
                    return False
            return Context()

    class RefreshService:
        def refresh(self, config, provider, *, mode="full", force_refresh_mode=None):
            captured["mode"] = mode
            return StorageIndexMetadata(target_folder="/Movies", status="completed", force_refresh_mode=mode)

    monkeypatch.setattr("backend.app.modules.storage.index.router.StorageIndexRefreshService", RefreshService)
    monkeypatch.setattr("backend.app.core.dependencies.get_storage_config_service", lambda: Service())

    response = client.post(
        "/api/storage/index/refresh",
        json={"mode": "incremental"},
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.OK
    assert captured["mode"] == "incremental"
    assert response.json()["data"]["force_refresh_mode"] == "incremental"
