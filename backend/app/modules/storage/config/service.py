from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
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
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
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

    @contextmanager
    def open_provider(self) -> Iterator[tuple[dict[str, Any], CloudDrive2Gateway]]:
        config = self.get_raw_config()
        client = self.provider_factory.create(config)
        try:
            yield config, self.gateway_class(client)
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
