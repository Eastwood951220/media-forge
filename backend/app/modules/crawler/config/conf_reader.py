from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from shared.runtime_config import PROJECT_ROOT

CONFIG_KEYS: tuple[str, ...] = (
    "MAX_LIST_PAGES",
    "LIST_PAGE_DELAY_MIN",
    "LIST_PAGE_DELAY_MAX",
    "DETAIL_PAGE_DELAY_MIN",
    "DETAIL_PAGE_DELAY_MAX",
    "SECURITY_WAIT_SECONDS",
    "REQUEST_TIMEOUT",
    "INCREMENTAL_EXIST_THRESHOLD",
)


@dataclass(frozen=True)
class CrawlerRuntimeConfig:
    MAX_LIST_PAGES: int = 50
    LIST_PAGE_DELAY_MIN: float = 4.0
    LIST_PAGE_DELAY_MAX: float = 5.0
    DETAIL_PAGE_DELAY_MIN: float = 2.0
    DETAIL_PAGE_DELAY_MAX: float = 3.0
    SECURITY_WAIT_SECONDS: float = 120.0
    REQUEST_TIMEOUT: int = 30
    INCREMENTAL_EXIST_THRESHOLD: int = 0


DEFAULT_CRAWLER_CONFIG = CrawlerRuntimeConfig()


def crawler_conf_path(base_dir: Path | None = None) -> Path:
    root = base_dir or PROJECT_ROOT
    return root / "data" / "configs" / "crawler.conf"


def _coerce_value(value: str) -> bool | int | float | str:
    text = value.strip().strip('"').strip("'")
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    if text.isdigit():
        return int(text)
    try:
        return float(text)
    except ValueError:
        return text


def read_crawler_conf_values(base_dir: Path | None = None) -> dict[str, str]:
    path = crawler_conf_path(base_dir)
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def read_crawler_config_dict(base_dir: Path | None = None) -> dict[str, int | float]:
    defaults = asdict(DEFAULT_CRAWLER_CONFIG)
    persisted = read_crawler_conf_values(base_dir)
    result: dict[str, int | float] = {}
    for key in CONFIG_KEYS:
        raw_value = persisted.get(key)
        if raw_value is None:
            result[key] = defaults[key]
            continue
        coerced = _coerce_value(raw_value)
        if key in {"MAX_LIST_PAGES", "REQUEST_TIMEOUT", "INCREMENTAL_EXIST_THRESHOLD"}:
            try:
                result[key] = int(coerced)
            except (TypeError, ValueError):
                result[key] = defaults[key]
        else:
            try:
                result[key] = float(coerced)
            except (TypeError, ValueError):
                result[key] = defaults[key]
    result["MAX_LIST_PAGES"] = min(int(result["MAX_LIST_PAGES"]), 50)
    return result


def read_crawler_runtime_config(base_dir: Path | None = None) -> CrawlerRuntimeConfig:
    data = read_crawler_config_dict(base_dir)
    return CrawlerRuntimeConfig(**data)


def _serialize_value(value: Any) -> str:
    text = str(value)
    if not text or any(char.isspace() for char in text) or "#" in text:
        return json.dumps(text, ensure_ascii=False)
    return text


def write_crawler_config(updated: dict[str, object], base_dir: Path | None = None) -> None:
    path = crawler_conf_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = {key: value for key, value in updated.items() if key in CONFIG_KEYS}
    next_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            next_lines.append(line)
            continue
        key, _value = line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key in remaining:
            next_lines.append(f"{normalized_key}={_serialize_value(remaining.pop(normalized_key))}")
        else:
            next_lines.append(line)

    for key, value in remaining.items():
        next_lines.append(f"{key}={_serialize_value(value)}")

    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")
    tmp_path.replace(path)
