from http import HTTPStatus

import pytest

from shared.runtime_config import RuntimeConfigPaths


def test_storage_config_service_writes_conf_and_masks_token(tmp_path, monkeypatch):
    from backend.app.modules.storage.config.schemas import StorageConfigUpdate
    from backend.app.modules.storage.config.service import StorageConfigService

    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    service = StorageConfigService(paths=RuntimeConfigPaths.from_env())

    response = service.update_config(
        StorageConfigUpdate(
            enabled=True,
            grpc_host="http://192.168.31.10:9798/",
            api_token="secret-token-1234",
            operation_delay_min=1,
            operation_delay_max=2,
            video_extensions=[".mp4", ".mkv"],
        )
    )

    assert response["enabled"] is True
    assert response["grpc_host"] == "192.168.31.10:9798"
    assert response["api_token"] == "************1234"
    assert response["api_token_configured"] is True

    conf_text = (tmp_path / "storage.conf").read_text(encoding="utf-8")
    assert "enabled=true\n" in conf_text
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
