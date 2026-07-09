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
    storage_index_file: Path
    storage_index_meta_file: Path

    @classmethod
    def from_env(cls) -> "RuntimeConfigPaths":
        configured_dir = os.getenv(CONFIG_DIR_ENV)
        config_dir = Path(configured_dir).expanduser() if configured_dir else PROJECT_ROOT / "data/configs"
        return cls(
            config_dir=config_dir,
            database_file=config_dir / "database.conf",
            redis_file=config_dir / "redis.conf",
            storage_file=config_dir / "storage.conf",
            storage_index_file=config_dir / "storage_index.jsonl",
            storage_index_meta_file=config_dir / "storage_index.meta.json",
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
