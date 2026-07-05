from http import HTTPStatus

import pytest

from shared.runtime_config import RuntimeConfigPaths


def _auth_headers(client, admin_user) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_storage_config_service_writes_conf_and_masks_token(tmp_path, monkeypatch):
    from backend.app.modules.storage.config.schemas import StorageConfigUpdate
    from backend.app.modules.storage.config.service import StorageConfigService

    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    service = StorageConfigService(paths=RuntimeConfigPaths.from_env())

    response = service.update_config(
        StorageConfigUpdate(
            grpc_host="http://192.168.31.10:9798/",
            api_token="secret-token-1234",
            operation_delay_min=1,
            operation_delay_max=2,
            video_extensions=[".mp4", ".mkv"],
        )
    )

    assert response["grpc_host"] == "192.168.31.10:9798"
    assert response["api_token"] == "************1234"
    assert response["api_token_configured"] is True

    conf_text = (tmp_path / "storage.conf").read_text(encoding="utf-8")
    assert "grpc_host=192.168.31.10:9798\n" in conf_text
    assert "api_token=secret-token-1234\n" in conf_text
    assert 'video_extensions=[".mp4", ".mkv"]\n' in conf_text

    loaded = service.get_config()
    assert loaded["api_token"] == "************1234"
    assert loaded["video_extensions"] == [".mp4", ".mkv"]


def test_storage_config_service_preserves_existing_token_when_masked(tmp_path, monkeypatch):
    from backend.app.modules.storage.config.schemas import StorageConfigUpdate
    from backend.app.modules.storage.config.service import StorageConfigService

    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    service = StorageConfigService(paths=RuntimeConfigPaths.from_env())
    service.update_config(StorageConfigUpdate(api_token="secret-token-1234"))

    response = service.update_config(
        StorageConfigUpdate(
            api_token="************1234",
            grpc_host="localhost:19798",
        )
    )

    assert response["api_token"] == "************1234"
    conf_text = (tmp_path / "storage.conf").read_text(encoding="utf-8")
    assert "api_token=secret-token-1234\n" in conf_text
    assert "grpc_host=localhost:19798\n" in conf_text


def test_storage_config_service_rejects_invalid_ranges(tmp_path, monkeypatch):
    from backend.app.modules.storage.config.schemas import StorageConfigUpdate
    from backend.app.modules.storage.config.service import StorageConfigService

    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    service = StorageConfigService(paths=RuntimeConfigPaths.from_env())

    with pytest.raises(ValueError, match="operation_delay_max must be >= operation_delay_min"):
        service.update_config(StorageConfigUpdate(operation_delay_min=5, operation_delay_max=1))


def test_storage_config_service_test_connection_uses_clouddrive_gateway(tmp_path, monkeypatch):
    from backend.app.modules.storage.config.schemas import StorageConfigUpdate
    from backend.app.modules.storage.config.service import StorageConfigService
    from shared.integrations.storage_providers.clouddrive2.models import ProviderHealthResult, RemoteFile

    class FakeFactory:
        def normalize_host(self, host: str) -> str:
            return host.replace("http://", "").replace("https://", "").rstrip("/")

        def create(self, config):
            assert config["grpc_host"] == "localhost:9798"
            assert config["api_token"] == "secret-token"
            return object()

    class FakeGateway:
        def __init__(self, client):
            self.client = client

        def health_check(self):
            return ProviderHealthResult(reachable=True, authorized=True, error_message=None)

        def find_file(self, path):
            return RemoteFile(
                name=path.rsplit("/", 1)[-1],
                full_path=path,
                size=0,
                is_directory=True,
            )

    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    service = StorageConfigService(
        paths=RuntimeConfigPaths.from_env(),
        provider_factory=FakeFactory(),
        gateway_class=FakeGateway,
    )
    service.update_config(StorageConfigUpdate(api_token="secret-token"))

    result = service.test_connection()

    assert result.grpc_reachable is True
    assert result.api_authorized is True
    assert result.download_root_exists is True
    assert result.target_folder_accessible is True


# -- API tests --


def test_storage_config_api_get_and_update_uses_success_envelope(
    client,
    admin_user,
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    headers = _auth_headers(client, admin_user)

    get_response = client.get("/api/storage/config", headers=headers)

    assert get_response.status_code == HTTPStatus.OK
    body = get_response.json()
    assert body["code"] == 200
    assert body["data"]["grpc_host"] == "localhost:9798"
    assert body["data"]["api_token"] == ""
    assert body["data"]["api_token_configured"] is False

    put_response = client.put(
        "/api/storage/config",
        headers=headers,
        json={
            "grpc_host": "http://127.0.0.1:19798/",
            "api_token": "secret-token-1234",
            "download_root_folder": "/Downloads",
            "target_folder": "/Movies",
        },
    )

    assert put_response.status_code == HTTPStatus.OK
    data = put_response.json()["data"]
    assert data["grpc_host"] == "127.0.0.1:19798"
    assert data["api_token"] == "************1234"
    assert data["api_token_configured"] is True
    assert (tmp_path / "storage.conf").exists()


def test_storage_config_api_returns_400_for_invalid_range(
    client,
    admin_user,
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))

    response = client.put(
        "/api/storage/config",
        headers=_auth_headers(client, admin_user),
        json={
            "operation_delay_min": 5,
            "operation_delay_max": 1,
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    body = response.json()
    assert body["code"] == 400
    assert "operation_delay_max must be >= operation_delay_min" in body["msg"]


def test_storage_config_api_test_endpoint(
    client,
    admin_user,
    tmp_path,
    monkeypatch,
) -> None:
    from backend.app.core.dependencies import get_storage_config_service
    from backend.app.main import app
    from backend.app.modules.storage.config.schemas import StorageTestResult

    class FakeService:
        def test_connection(self):
            return StorageTestResult(
                grpc_reachable=True,
                api_authorized=True,
                download_root_exists=True,
                target_folder_accessible=True,
            )

    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    app.dependency_overrides[get_storage_config_service] = lambda: FakeService()
    try:
        response = client.post(
            "/api/storage/config/test",
            headers=_auth_headers(client, admin_user),
        )
    finally:
        app.dependency_overrides.pop(get_storage_config_service, None)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"] == {
        "grpc_reachable": True,
        "grpc_error": None,
        "api_authorized": True,
        "api_error": None,
        "download_root_exists": True,
        "download_root_error": None,
        "target_folder_accessible": True,
        "target_folder_error": None,
    }


def test_storage_config_service_open_provider_closes_client(monkeypatch, tmp_path) -> None:
    from backend.app.modules.storage.config.service import StorageConfigService
    from shared.runtime_config import RuntimeConfigPaths

    class FakeClient:
        closed = False

        def close(self):
            self.closed = True

    class FakeFactory:
        client = FakeClient()

        def normalize_host(self, value: str) -> str:
            return value

        def create(self, config):
            return self.client

    class FakeGateway:
        def __init__(self, client):
            self.client = client

    paths = RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
    )
    service = StorageConfigService(paths=paths, provider_factory=FakeFactory(), gateway_class=FakeGateway)

    with service.open_provider() as (config, provider):
        assert config["grpc_host"]
        assert provider.client is service.provider_factory.client

    assert service.provider_factory.client.closed is True


def test_storage_config_service_open_provider_closes_client_on_error(monkeypatch, tmp_path) -> None:
    from backend.app.modules.storage.config.service import StorageConfigService
    from shared.runtime_config import RuntimeConfigPaths

    class FakeClient:
        closed = False

        def close(self):
            self.closed = True

    class FakeFactory:
        client = FakeClient()

        def normalize_host(self, value: str) -> str:
            return value

        def create(self, config):
            return self.client

    class FakeGateway:
        def __init__(self, client):
            self.client = client

    paths = RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
    )
    service = StorageConfigService(paths=paths, provider_factory=FakeFactory(), gateway_class=FakeGateway)

    try:
        with service.open_provider():
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert service.provider_factory.client.closed is True
