from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from backend.app.modules.backup.schemas import BackupConfig, BackupConfigUpdate
from shared.runtime_config import PROJECT_ROOT


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
        raise ValueError("Backup configuration values must be single-line")
    if not text or any(char.isspace() for char in text) or "#" in text:
        return json.dumps(text, ensure_ascii=False)
    return text


class BackupConfigService:
    """Read and write automatic backup settings in dotenv style.

    Values are stored in ``data/configs/backup.conf`` and written one key per
    line so the file stays diff-friendly. Tests may pass explicit paths so no
    repository state is touched.
    """

    def __init__(
        self,
        config_file: Path | None = None,
        project_root: Path | None = None,
    ) -> None:
        root = project_root or PROJECT_ROOT
        self.config_file = config_file or root / "data" / "configs" / "backup.conf"
        self.project_root = root

    @property
    def default_backup_dir(self) -> Path:
        return self.project_root / "data" / "backups"

    def get_config(self) -> BackupConfig:
        defaults = BackupConfig(backup_dir=str(self.default_backup_dir)).model_dump()
        if not self.config_file.exists():
            return BackupConfig(**defaults)
        parsed = dotenv_values(self.config_file)
        for key, value in parsed.items():
            if value is not None:
                defaults[key] = _coerce_conf_value(str(value))
        return BackupConfig(**defaults)

    def update_config(self, payload: BackupConfigUpdate) -> BackupConfig:
        current = self.get_config().model_dump()
        incoming = payload.model_dump(exclude_none=True)
        merged = dict(current)
        merged.update(incoming)
        config = BackupConfig(**merged)
        self._write_config(config)
        return config

    def _write_config(self, config: BackupConfig) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(f"{key}={_serialize_conf_value(value)}\n" for key, value in config.model_dump().items())
        temp_path = self.config_file.with_suffix(self.config_file.suffix + ".tmp")
        temp_path.write_text(body, encoding="utf-8")
        temp_path.replace(self.config_file)
