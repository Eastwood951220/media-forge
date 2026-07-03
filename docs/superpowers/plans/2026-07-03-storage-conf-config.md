# Storage Conf Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Media Forge storage configuration module from the original `jav-scrapling` behavior, backed by `data/configs/storage.conf`, and wire it to the copied CloudDrive2 integration.

**Architecture:** Keep this migration focused on storage configuration only: a file-backed backend service reads and writes `storage.conf`, exposes authenticated FastAPI endpoints under `/api/storage/config`, and uses the existing copied `shared.integrations.storage_providers.clouddrive2` factory/gateway for connection testing. The frontend adds a storage config API, route, sidebar entry, and Ant Design form matching the current Media Forge layout conventions.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic, python-dotenv, pytest, React 19, TypeScript 6, Vite 8, Ant Design 6, Vitest, React Testing Library.

---

## Scope

This plan migrates only the storage module shell and storage configuration from `/Users/eastwood/Code/PycharmProjects/jav-scrapling`.

Included:
- `storage.conf` support in shared runtime config paths.
- Backend storage config schemas, service, router, dependency injection, and route registration.
- CloudDrive2 connection test endpoint using the copied clouddrive provider code.
- Frontend storage config API, page, route, sidebar menu item, and UI tests.

Excluded:
- Storage task batches, workers, schedulers, storage task database tables, and file move/rename pipeline.
- Movie list storage sync actions.
- Any product expansion beyond preserving the original storage configuration behavior.

## Source References

- Original backend config schemas: `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/config/schemas.py`
- Original backend config service: `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/config/service.py`
- Original backend config router: `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/config/router.py`
- Original frontend page: `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/storage/config/Config.tsx`
- Current clouddrive integration: `shared/integrations/storage_providers/clouddrive2/`
- Current crawler config pattern: `backend/app/modules/crawler/config/router.py`
- Current runtime config pattern: `shared/runtime_config.py`

## File Structure

- Modify `shared/runtime_config.py`: add `storage_file` path, write/read support for a `"storage"` section, and keep initialization status based only on database + redis files.
- Modify `backend/tests/test_init_database_bootstrap.py`: add focused runtime-config tests for `storage.conf`.
- Create `backend/app/modules/storage/__init__.py`: package marker for storage module.
- Create `backend/app/modules/storage/config/__init__.py`: package marker for storage config submodule.
- Create `backend/app/modules/storage/config/schemas.py`: Pydantic models copied and adapted from `jav-scrapling`, plus an optional update model and response metadata for masked tokens.
- Create `backend/app/modules/storage/config/service.py`: file-backed `storage.conf` read/write service, token masking/preservation, range validation, and CloudDrive2 test logic.
- Create `backend/app/modules/storage/config/router.py`: authenticated `/api/storage/config` endpoints returning Media Forge `success(data=...)` envelopes.
- Modify `backend/app/core/dependencies.py`: expose `get_clouddrive_client_factory()` and `get_storage_config_service()`.
- Modify `backend/app/main.py`: include the storage config router.
- Create `backend/tests/test_storage_config_api.py`: backend API and service tests.
- Create `frontend/src/api/storage/storageConfig/types.ts`: frontend TypeScript contracts.
- Create `frontend/src/api/storage/storageConfig/index.ts`: request wrapper functions.
- Create `frontend/src/pages/storage/config/StorageConfigPage.module.less`: layout styling for the storage config page.
- Create `frontend/src/pages/storage/config/StorageConfigPage.tsx`: storage configuration form and connection test result UI.
- Modify `frontend/src/routes/index.tsx`: add `/storage/config` route.
- Modify `frontend/src/layout/Sidebar/index.tsx`: add storage menu group and selected/open key handling.
- Create `frontend/tests/storage-config.ui.test.tsx`: UI behavior tests for rendering and saving storage config.

---

### Task 1: Extend Runtime Config Paths for `storage.conf`

**Files:**
- Modify: `shared/runtime_config.py`
- Modify: `backend/tests/test_init_database_bootstrap.py`

- [ ] **Step 1: Add a failing runtime config test for `storage.conf`**

Append this test to `backend/tests/test_init_database_bootstrap.py`:

```python
def test_runtime_config_writes_and_loads_storage_file(tmp_path, monkeypatch):
    from shared.runtime_config import RuntimeConfigPaths, load_runtime_config, write_runtime_config

    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("grpc_host", raising=False)
    monkeypatch.delenv("api_token", raising=False)
    monkeypatch.delenv("enabled", raising=False)

    paths = RuntimeConfigPaths.from_env()

    write_runtime_config(
        {
            "storage": {
                "enabled": "true",
                "grpc_host": "192.168.31.10:9798",
                "api_token": "secret-token",
            },
        },
        paths,
    )

    assert paths.storage_file == tmp_path / "storage.conf"
    assert (tmp_path / "storage.conf").read_text(encoding="utf-8") == (
        "enabled=true\n"
        "grpc_host=192.168.31.10:9798\n"
        "api_token=secret-token\n"
    )

    loaded = load_runtime_config(paths, override=True)

    assert loaded["enabled"] == "true"
    assert loaded["grpc_host"] == "192.168.31.10:9798"
    assert loaded["api_token"] == "secret-token"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_init_database_bootstrap.py::test_runtime_config_writes_and_loads_storage_file -v
```

Expected: FAIL with an `AttributeError` saying `RuntimeConfigPaths` has no attribute `storage_file`, or an assertion failure because `storage.conf` is not written.

- [ ] **Step 3: Implement `storage.conf` path and section support**

Replace `shared/runtime_config.py` with:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR_ENV = "APP_CONFIG_DIR"


@dataclass(frozen=True)
class RuntimeConfigPaths:
    config_dir: Path
    database_file: Path
    redis_file: Path
    storage_file: Path

    @classmethod
    def from_env(cls) -> "RuntimeConfigPaths":
        configured_dir = os.getenv(CONFIG_DIR_ENV)
        config_dir = Path(configured_dir).expanduser() if configured_dir else PROJECT_ROOT / "data/configs"
        return cls(
            config_dir=config_dir,
            database_file=config_dir / "database.conf",
            redis_file=config_dir / "redis.conf",
            storage_file=config_dir / "storage.conf",
        )


def _serialize_value(value: object) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ValueError("Configuration values must be single-line strings")
    return text


def _write_env_file(path: Path, values: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{key}={_serialize_value(value)}\n" for key, value in values.items())
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(body, encoding="utf-8")
    temp_path.replace(path)


def write_runtime_config(
    sections: dict[str, dict[str, object]],
    paths: RuntimeConfigPaths | None = None,
) -> None:
    active_paths = paths or RuntimeConfigPaths.from_env()
    if "database" in sections:
        _write_env_file(active_paths.database_file, sections["database"])
    if "redis" in sections:
        _write_env_file(active_paths.redis_file, sections["redis"])
    if "storage" in sections:
        _write_env_file(active_paths.storage_file, sections["storage"])


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    parsed = dotenv_values(path)
    return {key: str(value) for key, value in parsed.items() if value is not None}


def read_runtime_config(paths: RuntimeConfigPaths | None = None) -> dict[str, str]:
    active_paths = paths or RuntimeConfigPaths.from_env()
    values: dict[str, str] = {}
    values.update(_read_env_file(active_paths.database_file))
    values.update(_read_env_file(active_paths.redis_file))
    values.update(_read_env_file(active_paths.storage_file))
    return values


def load_runtime_config(
    paths: RuntimeConfigPaths | None = None,
    *,
    override: bool = False,
) -> dict[str, str]:
    values = read_runtime_config(paths)
    for key, value in values.items():
        if override or key not in os.environ:
            os.environ[key] = value
    return values


def runtime_config_exists(paths: RuntimeConfigPaths | None = None) -> bool:
    active_paths = paths or RuntimeConfigPaths.from_env()
    return active_paths.database_file.exists() and active_paths.redis_file.exists()
```

- [ ] **Step 4: Run runtime config tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_init_database_bootstrap.py -v
```

Expected: PASS for all tests in `backend/tests/test_init_database_bootstrap.py`.

- [ ] **Step 5: Commit runtime config support**

Run:

```bash
git add shared/runtime_config.py backend/tests/test_init_database_bootstrap.py
git commit -m "feat: add storage runtime config file"
```

Expected: commit succeeds.

---

### Task 2: Add Backend Storage Config Schemas and Service

**Files:**
- Create: `backend/app/modules/storage/__init__.py`
- Create: `backend/app/modules/storage/config/__init__.py`
- Create: `backend/app/modules/storage/config/schemas.py`
- Create: `backend/app/modules/storage/config/service.py`
- Test: `backend/tests/test_storage_config_api.py`

- [ ] **Step 1: Write failing service tests**

Create `backend/tests/test_storage_config_api.py` with:

```python
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
```

- [ ] **Step 2: Run service tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_config_api.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.modules.storage'`.

- [ ] **Step 3: Create package markers**

Create `backend/app/modules/storage/__init__.py`:

```python
"""Storage module."""
```

Create `backend/app/modules/storage/config/__init__.py`:

```python
"""Storage configuration module."""
```

- [ ] **Step 4: Add storage config schemas**

Create `backend/app/modules/storage/config/schemas.py`:

```python
from pydantic import BaseModel, Field


class StorageConfig(BaseModel):
    """CloudDrive2 storage configuration."""

    enabled: bool = False

    grpc_host: str = "localhost:9798"
    api_token: str = ""
    request_timeout_seconds: int = Field(default=60, ge=1)
    connect_timeout_seconds: int = Field(default=10, ge=1)

    download_root_folder: str = "/Downloads"
    target_folder: str = "/Movies"
    use_task_subfolder: bool = True
    auto_create_target_folder: bool = True

    single_filename_template: str = "{code}{ext}"
    multi_filename_template: str = "{code}{ext}"

    operation_delay_min: float = Field(default=0.5, ge=0)
    operation_delay_max: float = Field(default=1.5, ge=0)
    download_poll_interval_min: float = Field(default=5.0, ge=0)
    download_poll_interval_max: float = Field(default=15.0, ge=0)
    retry_delay_min: float = Field(default=10.0, ge=0)
    retry_delay_max: float = Field(default=30.0, ge=0)
    max_step_retries: int = Field(default=3, ge=0)
    download_max_poll_count: int = Field(default=10, ge=1)

    minimum_video_size_mb: int = Field(default=100, ge=0)
    video_extensions: list[str] = Field(
        default_factory=lambda: [".mp4", ".mkv", ".avi", ".wmv", ".flv", ".mov"]
    )
    excluded_filename_keywords: list[str] = Field(default_factory=list)

    keep_subtitles: bool = True
    keep_cover_images: bool = True
    delete_empty_folders: bool = True


class StorageConfigUpdate(BaseModel):
    """Partial update payload for storage configuration."""

    enabled: bool | None = None
    grpc_host: str | None = None
    api_token: str | None = None
    request_timeout_seconds: int | None = Field(default=None, ge=1)
    connect_timeout_seconds: int | None = Field(default=None, ge=1)
    download_root_folder: str | None = None
    target_folder: str | None = None
    use_task_subfolder: bool | None = None
    auto_create_target_folder: bool | None = None
    single_filename_template: str | None = None
    multi_filename_template: str | None = None
    operation_delay_min: float | None = Field(default=None, ge=0)
    operation_delay_max: float | None = Field(default=None, ge=0)
    download_poll_interval_min: float | None = Field(default=None, ge=0)
    download_poll_interval_max: float | None = Field(default=None, ge=0)
    retry_delay_min: float | None = Field(default=None, ge=0)
    retry_delay_max: float | None = Field(default=None, ge=0)
    max_step_retries: int | None = Field(default=None, ge=0)
    download_max_poll_count: int | None = Field(default=None, ge=1)
    minimum_video_size_mb: int | None = Field(default=None, ge=0)
    video_extensions: list[str] | None = None
    excluded_filename_keywords: list[str] | None = None
    keep_subtitles: bool | None = None
    keep_cover_images: bool | None = None
    delete_empty_folders: bool | None = None


class StorageConfigResponse(StorageConfig):
    """Public storage configuration response with masked token."""

    api_token_configured: bool = False


class StorageTestResult(BaseModel):
    """Result of a CloudDrive2 connection test."""

    grpc_reachable: bool = False
    grpc_error: str | None = None
    api_authorized: bool = False
    api_error: str | None = None
    download_root_exists: bool = False
    download_root_error: str | None = None
    target_folder_accessible: bool = False
    target_folder_error: str | None = None
```

- [ ] **Step 5: Add file-backed storage config service**

Create `backend/app/modules/storage/config/service.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from backend.app.modules.storage.config.schemas import (
    StorageConfig,
    StorageConfigResponse,
    StorageConfigUpdate,
    StorageTestResult,
)
from shared.integrations.storage_providers.clouddrive2.factory import CloudDriveClientFactory
from shared.integrations.storage_providers.clouddrive2.gateway import CloudDrive2Gateway
from shared.runtime_config import RuntimeConfigPaths


def mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) < 8:
        return "****"
    return f"{'*' * 12}{token[-4:]}"


def is_masked_token(token: str) -> bool:
    if not token:
        return False
    prefix = token[:-4] if len(token) > 4 else token
    return len(prefix) >= 4 and set(prefix) == {"*"}


def _coerce_conf_value(value: str) -> Any:
    stripped = value.strip()
    if not stripped:
        return ""
    if stripped.startswith("[") or stripped.startswith("{"):
        return json.loads(stripped)
    lower = stripped.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    try:
        return int(stripped)
    except ValueError:
        try:
            return float(stripped)
        except ValueError:
            return stripped


def _serialize_conf_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | dict):
        return json.dumps(value, ensure_ascii=False)
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ValueError("Storage configuration values must be single-line")
    if not text or any(char.isspace() for char in text) or "#" in text:
        return json.dumps(text, ensure_ascii=False)
    return text


class StorageConfigService:
    def __init__(
        self,
        paths: RuntimeConfigPaths | None = None,
        provider_factory: CloudDriveClientFactory | None = None,
        gateway_class: type[CloudDrive2Gateway] | None = None,
    ) -> None:
        self.paths = paths or RuntimeConfigPaths.from_env()
        self.provider_factory = provider_factory or CloudDriveClientFactory()
        self.gateway_class = gateway_class or CloudDrive2Gateway

    @property
    def config_file(self) -> Path:
        return self.paths.storage_file

    def get_config(self) -> dict[str, Any]:
        config = self._load_raw_config()
        return self._public_config(config)

    def get_raw_config(self) -> dict[str, Any]:
        return self._load_raw_config()

    def update_config(self, body: StorageConfigUpdate | dict[str, Any]) -> dict[str, Any]:
        current = self._load_raw_config()
        incoming = body.model_dump(exclude_none=True) if hasattr(body, "model_dump") else dict(body)
        incoming = dict(incoming)
        if "grpc_host" in incoming and incoming["grpc_host"] is not None:
            incoming["grpc_host"] = self.provider_factory.normalize_host(str(incoming["grpc_host"]))
        if "api_token" in incoming:
            token = str(incoming.get("api_token") or "")
            if not token or is_masked_token(token):
                incoming["api_token"] = current.get("api_token", "")

        merged = dict(current)
        merged.update(incoming)
        validated = StorageConfig(**merged).model_dump()
        self._validate_ranges(validated)
        self._write_config(validated)
        return self._public_config(validated)

    def test_connection(self) -> StorageTestResult:
        config = self._load_raw_config()
        client = self.provider_factory.create(config)
        try:
            gateway = self.gateway_class(client)
            health = gateway.health_check()
            result = StorageTestResult(
                grpc_reachable=health.reachable,
                grpc_error=None if health.reachable else health.error_message,
                api_authorized=health.authorized,
                api_error=None if health.authorized else health.error_message,
            )
            if health.reachable and health.authorized:
                try:
                    result.download_root_exists = gateway.find_file(config["download_root_folder"]) is not None
                except Exception as exc:
                    result.download_root_error = str(exc)
                try:
                    result.target_folder_accessible = gateway.find_file(config["target_folder"]) is not None
                except Exception as exc:
                    result.target_folder_error = str(exc)
            return result
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    def _load_raw_config(self) -> dict[str, Any]:
        data = StorageConfig().model_dump()
        if not self.config_file.exists():
            return data
        parsed = dotenv_values(self.config_file)
        for key, value in parsed.items():
            if value is not None:
                data[key] = _coerce_conf_value(str(value))
        normalized = StorageConfig(**data).model_dump()
        normalized["grpc_host"] = self.provider_factory.normalize_host(normalized["grpc_host"])
        return normalized

    def _write_config(self, data: dict[str, Any]) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(f"{key}={_serialize_conf_value(value)}\n" for key, value in data.items())
        temp_path = self.config_file.with_suffix(self.config_file.suffix + ".tmp")
        temp_path.write_text(body, encoding="utf-8")
        temp_path.replace(self.config_file)

    def _public_config(self, config: dict[str, Any]) -> dict[str, Any]:
        raw_token = str(config.get("api_token") or "")
        public = dict(config)
        public["api_token"] = mask_token(raw_token)
        public["api_token_configured"] = bool(raw_token)
        return StorageConfigResponse(**public).model_dump()

    def _validate_ranges(self, data: dict[str, Any]) -> None:
        checks = [
            ("operation_delay_min", "operation_delay_max"),
            ("download_poll_interval_min", "download_poll_interval_max"),
            ("retry_delay_min", "retry_delay_max"),
        ]
        for minimum, maximum in checks:
            if data[maximum] < data[minimum]:
                raise ValueError(f"{maximum} must be >= {minimum}")
```

- [ ] **Step 6: Run service tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_config_api.py -v
```

Expected: PASS for the four service tests.

- [ ] **Step 7: Commit backend service**

Run:

```bash
git add backend/app/modules/storage backend/tests/test_storage_config_api.py
git commit -m "feat: add storage config service"
```

Expected: commit succeeds.

---

### Task 3: Wire Backend Storage Config API

**Files:**
- Create: `backend/app/modules/storage/config/router.py`
- Modify: `backend/app/core/dependencies.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_storage_config_api.py`

- [ ] **Step 1: Add failing API tests**

Append these tests to `backend/tests/test_storage_config_api.py`:

```python
def _auth_headers(client, admin_user) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


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
            "enabled": True,
            "grpc_host": "http://127.0.0.1:19798/",
            "api_token": "secret-token-1234",
            "download_root_folder": "/Downloads",
            "target_folder": "/Movies",
        },
    )

    assert put_response.status_code == HTTPStatus.OK
    data = put_response.json()["data"]
    assert data["enabled"] is True
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
    assert "operation_delay_max must be >= operation_delay_min" in response.json()["detail"]


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
```

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_config_api.py::test_storage_config_api_get_and_update_uses_success_envelope backend/tests/test_storage_config_api.py::test_storage_config_api_returns_400_for_invalid_range backend/tests/test_storage_config_api.py::test_storage_config_api_test_endpoint -v
```

Expected: FAIL with 404 responses or an import error for `get_storage_config_service`.

- [ ] **Step 3: Add storage config dependency providers**

In `backend/app/core/dependencies.py`, add these imports after existing imports:

```python
from backend.app.modules.storage.config.service import StorageConfigService
from shared.integrations.storage_providers.clouddrive2.factory import CloudDriveClientFactory
```

Then add these functions above the `# -- Auth --` section:

```python
# -- Storage --


def get_clouddrive_client_factory() -> CloudDriveClientFactory:
    return CloudDriveClientFactory()


def get_storage_config_service() -> StorageConfigService:
    return StorageConfigService(provider_factory=get_clouddrive_client_factory())
```

- [ ] **Step 4: Add storage config router**

Create `backend/app/modules/storage/config/router.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.dependencies import CurrentUser, get_storage_config_service
from backend.app.modules.storage.config.schemas import StorageConfigUpdate
from backend.app.modules.storage.config.service import StorageConfigService
from shared.schemas.common import success

router = APIRouter(prefix="/api/storage/config", tags=["storage-config"])


@router.get("")
def get_storage_config(
    _current_user: CurrentUser,
    service: StorageConfigService = Depends(get_storage_config_service),
) -> dict:
    return success(data=service.get_config())


@router.put("")
def update_storage_config(
    body: StorageConfigUpdate,
    _current_user: CurrentUser,
    service: StorageConfigService = Depends(get_storage_config_service),
) -> dict:
    try:
        return success(data=service.update_config(body))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/test")
def test_storage_connection(
    _current_user: CurrentUser,
    service: StorageConfigService = Depends(get_storage_config_service),
) -> dict:
    return success(data=service.test_connection().model_dump())
```

- [ ] **Step 5: Include the router in the backend app**

In `backend/app/main.py`, add this import with the other router imports:

```python
from backend.app.modules.storage.config.router import router as storage_config_router
```

In the router registration block, add this line after `app.include_router(crawler_events_router)`:

```python
app.include_router(storage_config_router)
```

- [ ] **Step 6: Run backend storage config API tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_config_api.py -v
```

Expected: PASS for all storage config tests.

- [ ] **Step 7: Run related backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_init_database_bootstrap.py backend/tests/test_crawler_config_api.py backend/tests/test_storage_config_api.py -v
```

Expected: PASS for all selected tests.

- [ ] **Step 8: Commit backend API wiring**

Run:

```bash
git add backend/app/core/dependencies.py backend/app/main.py backend/app/modules/storage/config/router.py backend/tests/test_storage_config_api.py
git commit -m "feat: expose storage config api"
```

Expected: commit succeeds.

---

### Task 4: Add Frontend Storage Config API

**Files:**
- Create: `frontend/src/api/storage/storageConfig/types.ts`
- Create: `frontend/src/api/storage/storageConfig/index.ts`

- [ ] **Step 1: Add TypeScript API contracts**

Create `frontend/src/api/storage/storageConfig/types.ts`:

```typescript
export interface StorageConfig {
  enabled: boolean
  grpc_host: string
  api_token: string
  api_token_configured: boolean
  request_timeout_seconds: number
  connect_timeout_seconds: number
  download_root_folder: string
  target_folder: string
  use_task_subfolder: boolean
  auto_create_target_folder: boolean
  single_filename_template: string
  multi_filename_template: string
  operation_delay_min: number
  operation_delay_max: number
  download_poll_interval_min: number
  download_poll_interval_max: number
  retry_delay_min: number
  retry_delay_max: number
  max_step_retries: number
  download_max_poll_count: number
  minimum_video_size_mb: number
  video_extensions: string[]
  excluded_filename_keywords: string[]
  keep_subtitles: boolean
  keep_cover_images: boolean
  delete_empty_folders: boolean
}

export type StorageConfigUpdate = Partial<Omit<StorageConfig, 'api_token_configured'>>

export interface StorageTestResult {
  grpc_reachable: boolean
  grpc_error: string | null
  api_authorized: boolean
  api_error: string | null
  download_root_exists: boolean
  download_root_error: string | null
  target_folder_accessible: boolean
  target_folder_error: string | null
}
```

- [ ] **Step 2: Add storage config request functions**

Create `frontend/src/api/storage/storageConfig/index.ts`:

```typescript
import { request } from '@/request'
import type { StorageConfig, StorageConfigUpdate, StorageTestResult } from './types.ts'

export type { StorageConfig, StorageConfigUpdate, StorageTestResult } from './types.ts'

const BASE_URL = '/api/storage/config'

export function fetchStorageConfig(): Promise<StorageConfig> {
  return request.get<StorageConfig>(BASE_URL)
}

export function updateStorageConfig(data: StorageConfigUpdate): Promise<StorageConfig> {
  return request.put<StorageConfig>(BASE_URL, data)
}

export function testStorageConnection(): Promise<StorageTestResult> {
  return request.post<StorageTestResult>(`${BASE_URL}/test`)
}
```

- [ ] **Step 3: Run frontend typecheck**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS. The build should complete with Vite output under `frontend/dist`.

- [ ] **Step 4: Commit frontend API**

Run:

```bash
git add frontend/src/api/storage/storageConfig
git commit -m "feat: add storage config frontend api"
```

Expected: commit succeeds.

---

### Task 5: Add Frontend Storage Config Page

**Files:**
- Create: `frontend/src/pages/storage/config/StorageConfigPage.module.less`
- Create: `frontend/src/pages/storage/config/StorageConfigPage.tsx`
- Test: `frontend/tests/storage-config.ui.test.tsx`

- [ ] **Step 1: Write failing UI tests**

Create `frontend/tests/storage-config.ui.test.tsx`:

```typescript
import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StorageConfigPage from '../src/pages/storage/config/StorageConfigPage'
import {
  fetchStorageConfig,
  testStorageConnection,
  updateStorageConfig,
} from '@/api/storage/storageConfig'

vi.mock('@/api/storage/storageConfig', () => ({
  fetchStorageConfig: vi.fn(),
  updateStorageConfig: vi.fn(),
  testStorageConnection: vi.fn(),
}))

function renderPage() {
  return render(
    <AntApp>
      <StorageConfigPage />
    </AntApp>,
  )
}

describe('StorageConfigPage', () => {
  beforeEach(() => {
    vi.mocked(fetchStorageConfig).mockResolvedValue({
      enabled: true,
      grpc_host: 'localhost:9798',
      api_token: '************1234',
      api_token_configured: true,
      request_timeout_seconds: 60,
      connect_timeout_seconds: 10,
      download_root_folder: '/Downloads',
      target_folder: '/Movies',
      use_task_subfolder: true,
      auto_create_target_folder: true,
      single_filename_template: '{code}{ext}',
      multi_filename_template: '{code}{ext}',
      operation_delay_min: 0.5,
      operation_delay_max: 1.5,
      download_poll_interval_min: 5,
      download_poll_interval_max: 15,
      retry_delay_min: 10,
      retry_delay_max: 30,
      max_step_retries: 3,
      download_max_poll_count: 10,
      minimum_video_size_mb: 100,
      video_extensions: ['.mp4', '.mkv'],
      excluded_filename_keywords: [],
      keep_subtitles: true,
      keep_cover_images: true,
      delete_empty_folders: true,
    })
    vi.mocked(updateStorageConfig).mockResolvedValue({
      enabled: true,
      grpc_host: 'localhost:9798',
      api_token: '************9999',
      api_token_configured: true,
      request_timeout_seconds: 60,
      connect_timeout_seconds: 10,
      download_root_folder: '/Downloads',
      target_folder: '/Movies',
      use_task_subfolder: true,
      auto_create_target_folder: true,
      single_filename_template: '{code}{ext}',
      multi_filename_template: '{code}{ext}',
      operation_delay_min: 0.5,
      operation_delay_max: 1.5,
      download_poll_interval_min: 5,
      download_poll_interval_max: 15,
      retry_delay_min: 10,
      retry_delay_max: 30,
      max_step_retries: 3,
      download_max_poll_count: 10,
      minimum_video_size_mb: 100,
      video_extensions: ['.mp4', '.mkv'],
      excluded_filename_keywords: [],
      keep_subtitles: true,
      keep_cover_images: true,
      delete_empty_folders: true,
    })
    vi.mocked(testStorageConnection).mockResolvedValue({
      grpc_reachable: true,
      grpc_error: null,
      api_authorized: true,
      api_error: null,
      download_root_exists: true,
      download_root_error: null,
      target_folder_accessible: true,
      target_folder_error: null,
    })
  })

  it('renders storage config sections from the original project', async () => {
    renderPage()

    expect(await screen.findByText('服务配置')).toBeInTheDocument()
    expect(screen.getByText('目录配置')).toBeInTheDocument()
    expect(screen.getByText('文件命名')).toBeInTheDocument()
    expect(screen.getByText('任务执行')).toBeInTheDocument()
    expect(screen.getByText('文件筛选')).toBeInTheDocument()
    expect(screen.getByText('当前已配置: ************1234')).toBeInTheDocument()
  })

  it('saves a new token without sending the masked token as the secret', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText('服务配置')).toBeInTheDocument()
    await user.type(screen.getByPlaceholderText('输入新的 API Token（留空则不修改）'), 'new-token-9999')
    await user.click(screen.getByText('保存配置'))

    await waitFor(() => {
      expect(updateStorageConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          api_token: 'new-token-9999',
          grpc_host: 'localhost:9798',
        }),
      )
    })
  })

  it('shows connection test result', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText('服务配置')).toBeInTheDocument()
    await user.click(screen.getByText('测试连接'))

    expect(await screen.findByText('测试结果')).toBeInTheDocument()
    expect(screen.getAllByText('通过')).toHaveLength(4)
  })
})
```

- [ ] **Step 2: Run UI tests and verify they fail**

Run:

```bash
cd frontend
npm test -- storage-config.ui.test.tsx
```

Expected: FAIL because `StorageConfigPage` does not exist.

- [ ] **Step 3: Add storage config page styling**

Create `frontend/src/pages/storage/config/StorageConfigPage.module.less`:

```less
.page {
  max-width: 960px;
}

.formCard {
  margin-bottom: 16px;
}

.sectionTitle {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}

.tokenStack {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tagList {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.resultCard {
  margin-top: 16px;
}
```

- [ ] **Step 4: Add storage config page**

Create `frontend/src/pages/storage/config/StorageConfigPage.tsx`:

```tsx
import { useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Space,
  Switch,
  Tag,
} from 'antd'
import {
  ApiOutlined,
  ClockCircleOutlined,
  CloudOutlined,
  FileOutlined,
  FilterOutlined,
  FolderOutlined,
} from '@ant-design/icons'
import {
  fetchStorageConfig,
  testStorageConnection,
  updateStorageConfig,
  type StorageConfig,
  type StorageTestResult,
} from '@/api/storage/storageConfig'
import styles from './StorageConfigPage.module.less'

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return '操作失败'
}

function SectionTitle({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <span className={styles.sectionTitle}>
      {icon}
      {text}
    </span>
  )
}

function SelectTags({
  value,
  onChange,
  placeholder,
}: {
  value?: string[]
  onChange?: (val: string[]) => void
  placeholder?: string
}) {
  const [input, setInput] = useState('')

  const handleInputConfirm = () => {
    const trimmed = input.trim()
    if (trimmed && !value?.includes(trimmed)) {
      onChange?.([...(value ?? []), trimmed])
    }
    setInput('')
  }

  const handleClose = (removed: string) => {
    onChange?.(value?.filter((item) => item !== removed) ?? [])
  }

  return (
    <div>
      <div className={styles.tagList}>
        {value?.map((tag) => (
          <Tag key={tag} closable onClose={() => handleClose(tag)}>
            {tag}
          </Tag>
        ))}
      </div>
      <Input
        size="small"
        placeholder={placeholder}
        value={input}
        onBlur={handleInputConfirm}
        onChange={(event) => setInput(event.target.value)}
        onPressEnter={handleInputConfirm}
      />
    </div>
  )
}

function TestResultCard({ result }: { result: StorageTestResult }) {
  const items = [
    { label: 'gRPC 连接', value: result.grpc_reachable, error: result.grpc_error },
    { label: 'API 授权', value: result.api_authorized, error: result.api_error },
    { label: '下载目录', value: result.download_root_exists, error: result.download_root_error },
    { label: '目标文件夹', value: result.target_folder_accessible, error: result.target_folder_error },
  ]
  const failedItems = items.filter((item) => !item.value && item.error)
  const allPassed = items.every((item) => item.value)

  return (
    <Card title="测试结果" className={styles.resultCard} size="small">
      <Descriptions column={2} size="small">
        {items.map((item) => (
          <Descriptions.Item key={item.label} label={item.label}>
            <Tag color={item.value ? 'success' : 'error'}>{item.value ? '通过' : '失败'}</Tag>
          </Descriptions.Item>
        ))}
      </Descriptions>

      {failedItems.length > 0 && (
        <Alert
          type="error"
          message="错误详情"
          description={
            <ul>
              {failedItems.map((item) => (
                <li key={item.label}>
                  {item.label}: {item.error}
                </li>
              ))}
            </ul>
          }
          showIcon
        />
      )}

      {allPassed && <Alert type="success" message="所有测试通过" showIcon />}
    </Card>
  )
}

export default function StorageConfigPage() {
  const { message } = App.useApp()
  const [form] = Form.useForm<StorageConfig>()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<StorageTestResult | null>(null)
  const [tokenInput, setTokenInput] = useState('')

  const loadConfig = async () => {
    setLoading(true)
    try {
      const data = await fetchStorageConfig()
      form.setFieldsValue(data)
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadConfig()
  }, [])

  const handleSave = async (values: StorageConfig) => {
    setSaving(true)
    try {
      const payload = { ...values }
      if (tokenInput) {
        payload.api_token = tokenInput
      } else {
        delete (payload as Partial<StorageConfig>).api_token
      }
      const updated = await updateStorageConfig(payload)
      form.setFieldsValue(updated)
      setTokenInput('')
      message.success('存储配置已保存')
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      setTestResult(await testStorageConnection())
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setTesting(false)
    }
  }

  const maskedToken = Form.useWatch('api_token', form)

  if (loading) return null

  return (
    <div className={styles.page}>
      <Form form={form} layout="vertical" onFinish={(values) => void handleSave(values)}>
        <Card
          title={<SectionTitle icon={<CloudOutlined />} text="服务配置" />}
          className={styles.formCard}
        >
          <Form.Item name="enabled" label="启用存储模块" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            name="grpc_host"
            label="gRPC 主机地址"
            rules={[{ required: true, message: '请输入 gRPC 主机地址' }]}
          >
            <Input placeholder="localhost:9798" />
          </Form.Item>
          <Form.Item label="API Token">
            <div className={styles.tokenStack}>
              {maskedToken && <Tag color="blue">当前已配置: {maskedToken}</Tag>}
              <Input.Password
                placeholder="输入新的 API Token（留空则不修改）"
                value={tokenInput}
                onChange={(event) => setTokenInput(event.target.value)}
              />
            </div>
          </Form.Item>
          <Form.Item name="request_timeout_seconds" label="请求超时 (秒)">
            <InputNumber min={1} max={300} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="connect_timeout_seconds" label="连接超时 (秒)">
            <InputNumber min={1} max={60} style={{ width: '100%' }} />
          </Form.Item>
        </Card>

        <Card
          title={<SectionTitle icon={<FolderOutlined />} text="目录配置" />}
          className={styles.formCard}
        >
          <Form.Item
            name="download_root_folder"
            label="下载根目录"
            rules={[{ required: true, message: '请输入下载根目录' }]}
          >
            <Input placeholder="/Downloads" />
          </Form.Item>
          <Form.Item
            name="target_folder"
            label="目标文件夹"
            rules={[{ required: true, message: '请输入目标文件夹' }]}
          >
            <Input placeholder="/Movies" />
          </Form.Item>
          <Form.Item name="use_task_subfolder" label="使用任务子文件夹" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="auto_create_target_folder" label="自动创建目标文件夹" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Card>

        <Card
          title={<SectionTitle icon={<FileOutlined />} text="文件命名" />}
          className={styles.formCard}
        >
          <Form.Item name="single_filename_template" label="单文件命名模板">
            <Input placeholder="{code}{ext}" />
          </Form.Item>
          <Form.Item name="multi_filename_template" label="多文件命名模板">
            <Input placeholder="{code}{ext}" />
          </Form.Item>
        </Card>

        <Card
          title={<SectionTitle icon={<ClockCircleOutlined />} text="任务执行" />}
          className={styles.formCard}
        >
          <Form.Item name="operation_delay_min" label="操作最小延迟 (秒)">
            <InputNumber min={0} max={60} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="operation_delay_max" label="操作最大延迟 (秒)">
            <InputNumber min={0} max={60} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="download_poll_interval_min" label="下载轮询最小间隔 (秒)">
            <InputNumber min={0} max={120} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="download_poll_interval_max" label="下载轮询最大间隔 (秒)">
            <InputNumber min={0} max={120} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="retry_delay_min" label="重试最小延迟 (秒)">
            <InputNumber min={0} max={120} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="retry_delay_max" label="重试最大延迟 (秒)">
            <InputNumber min={0} max={120} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="max_step_retries" label="最大重试次数">
            <InputNumber min={0} max={20} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="download_max_poll_count"
            label="下载轮询最大次数"
            tooltip="超过此次数将跳过当前任务，进入下一个任务"
          >
            <InputNumber min={1} max={100} style={{ width: '100%' }} />
          </Form.Item>
        </Card>

        <Card
          title={<SectionTitle icon={<FilterOutlined />} text="文件筛选" />}
          className={styles.formCard}
        >
          <Form.Item name="minimum_video_size_mb" label="最小视频大小 (MB)">
            <InputNumber min={0} max={10000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="video_extensions" label="视频扩展名" tooltip="输入扩展名后按回车添加">
            <SelectTags placeholder="例如: .mp4, .mkv" />
          </Form.Item>
          <Form.Item name="excluded_filename_keywords" label="排除文件名关键词" tooltip="输入关键词后按回车添加">
            <SelectTags placeholder="例如: sample, trailer" />
          </Form.Item>
          <Form.Item name="keep_subtitles" label="保留字幕文件" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="keep_cover_images" label="保留封面图片" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="delete_empty_folders" label="删除空文件夹" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Card>

        <Card title="操作" className={styles.formCard}>
          <Space className={styles.actions}>
            <Button icon={<ApiOutlined />} onClick={() => void handleTest()} loading={testing}>
              测试连接
            </Button>
            <Button type="primary" htmlType="submit" loading={saving}>
              保存配置
            </Button>
            <Button onClick={() => void loadConfig()}>重置</Button>
          </Space>
        </Card>
      </Form>

      {testResult && <TestResultCard result={testResult} />}
    </div>
  )
}
```

- [ ] **Step 5: Run storage config UI test**

Run:

```bash
cd frontend
npm test -- storage-config.ui.test.tsx
```

Expected: PASS for `frontend/tests/storage-config.ui.test.tsx`.

- [ ] **Step 6: Commit storage config page**

Run:

```bash
git add frontend/src/pages/storage/config frontend/tests/storage-config.ui.test.tsx
git commit -m "feat: add storage config page"
```

Expected: commit succeeds.

---

### Task 6: Wire Frontend Route and Sidebar

**Files:**
- Modify: `frontend/src/routes/index.tsx`
- Modify: `frontend/src/layout/Sidebar/index.tsx`
- Modify: `frontend/tests/storage-config.ui.test.tsx`

- [ ] **Step 1: Add route/sidebar assertions to frontend tests**

Append these tests to `frontend/tests/storage-config.ui.test.tsx`:

```typescript
it('exports storage config route in the router tree', async () => {
  const { router } = await import('../src/routes')

  expect(router.routesByPath['/storage/config']).toBeDefined()
})
```

- [ ] **Step 2: Run the route test and verify it fails**

Run:

```bash
cd frontend
npm test -- storage-config.ui.test.tsx
```

Expected: FAIL because `/storage/config` is not in `router.routesByPath`.

- [ ] **Step 3: Add storage route**

In `frontend/src/routes/index.tsx`, add this import:

```typescript
import StorageConfigPage from '@/pages/storage/config/StorageConfigPage'
```

Add this route definition after `crawlerRunsRoute`:

```typescript
const storageConfigRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/storage/config',
  component: StorageConfigPage,
})
```

Add `storageConfigRoute` to the `layoutRoute.addChildren` route list after `crawlerRunDetailRoute`:

```typescript
    storageConfigRoute,
```

- [ ] **Step 4: Add sidebar storage menu**

In `frontend/src/layout/Sidebar/index.tsx`, replace the icon import with:

```typescript
import {
  CloudOutlined,
  DashboardOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
  SearchOutlined,
  SettingOutlined,
  UnorderedListOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
```

Add this menu group between the crawler group and content group:

```tsx
  {
    key: 'storage',
    icon: <CloudOutlined />,
    label: '存储',
    children: [
      {
        key: '/storage/config',
        icon: <SettingOutlined />,
        label: '存储配置',
      },
    ],
  },
```

Replace the `selectedKey` expression with:

```typescript
  const selectedKey = pathname.startsWith('/crawler/tasks')
    ? '/crawler/tasks'
    : pathname.startsWith('/crawler/runs')
      ? '/crawler/runs'
      : pathname.startsWith('/crawler/config')
        ? '/crawler/config'
        : pathname.startsWith('/storage/config')
          ? '/storage/config'
          : pathname.startsWith('/content/movies')
            ? '/content/movies'
            : pathname
```

Replace the `openKeys` memo body with:

```typescript
  const openKeys = useMemo(() => {
    const keys: string[] = []
    if (pathname.startsWith('/crawler')) keys.push('crawler')
    if (pathname.startsWith('/storage')) keys.push('storage')
    if (pathname.startsWith('/content')) keys.push('content')
    return keys
  }, [pathname])
```

- [ ] **Step 5: Run frontend route/UI tests**

Run:

```bash
cd frontend
npm test -- storage-config.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Run existing navigation-adjacent tests**

Run:

```bash
cd frontend
npm test -- layout.ui.test.tsx routes-tags.test.ts App.test.tsx storage-config.ui.test.tsx
```

Expected: PASS for the selected tests.

- [ ] **Step 7: Commit frontend route wiring**

Run:

```bash
git add frontend/src/routes/index.tsx frontend/src/layout/Sidebar/index.tsx frontend/tests/storage-config.ui.test.tsx
git commit -m "feat: wire storage config route"
```

Expected: commit succeeds.

---

### Task 7: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run backend focused regression tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_init_database_bootstrap.py backend/tests/test_crawler_config_api.py backend/tests/test_storage_config_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests**

Run:

```bash
cd frontend
npm test -- storage-config.ui.test.tsx crawler-config.ui.test.tsx layout.ui.test.tsx routes-tags.test.tsx App.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Manual backend smoke check**

Run:

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

Expected: the backend starts and logs `Starting Media Forge backend`.

In another terminal, log in through the frontend or existing API client and verify:
- `GET /api/storage/config` returns `code: 200`.
- `PUT /api/storage/config` writes `data/configs/storage.conf`.
- `POST /api/storage/config/test` returns a structured test result. It may report failed authorization if CloudDrive2 is not running or the token is missing; that is acceptable.

- [ ] **Step 5: Manual frontend smoke check**

Run:

```bash
cd frontend
npm run dev
```

Expected: Vite starts and prints a local URL.

Open the app, navigate to `存储 -> 存储配置`, and verify:
- The five original sections render: `服务配置`, `目录配置`, `文件命名`, `任务执行`, `文件筛选`.
- Saving a new API token shows a masked token afterward.
- Reset reloads values from the backend.
- Testing connection shows the four result rows.

- [ ] **Step 6: Commit verification-only fixes if needed**

If any verification command requires a code fix, make the smallest code change, rerun the failing command, then run:

```bash
git add <changed-files>
git commit -m "fix: stabilize storage config verification"
```

Expected: commit succeeds only when there were verification fixes.

## Self-Review

- Spec coverage: The plan adds a storage module/configuration path based on the original project, uses the copied CloudDrive2 integration for connection testing, and persists storage configuration to a `storage.conf` file.
- Placeholder scan: The plan does not use placeholder code blocks; each creation step includes concrete file content or exact code to insert.
- Type consistency: Backend field names match original `StorageConfig` names and frontend `StorageConfig` fields. The response uses `api_token` for the masked display token and `api_token_configured` for boolean status.
- Scope guard: Storage task queues, batches, worker steps, and content storage sync are explicitly excluded from this plan.
