import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from backend.app.core.dependencies import CurrentUser
from backend.app.modules.crawler.config.schemas import ConfigUpdate, CookiesConfig
from scraper.config import settings as cfg
from shared.schemas.common import success

router = APIRouter(prefix="/api/crawler/config", tags=["crawler-config"])

CONFIG_KEYS = [
    "MAX_LIST_PAGES",
    "LIST_PAGE_DELAY_MIN",
    "LIST_PAGE_DELAY_MAX",
    "DETAIL_PAGE_DELAY_MIN",
    "DETAIL_PAGE_DELAY_MAX",
    "SECURITY_WAIT_SECONDS",
    "REQUEST_TIMEOUT",
    "INCREMENTAL_EXIST_THRESHOLD",
]

CONFIG_DIR_NAME = "configs"
CONFIG_FILE_NAME = "crawler.conf"
DEFAULT_COOKIE_FILE = "javdb_cookies.json"


def _defaults() -> dict[str, Any]:
    return {
        "MAX_LIST_PAGES": cfg.MAX_LIST_PAGES,
        "LIST_PAGE_DELAY_MIN": cfg.LIST_PAGE_DELAY_MIN,
        "LIST_PAGE_DELAY_MAX": cfg.LIST_PAGE_DELAY_MAX,
        "DETAIL_PAGE_DELAY_MIN": cfg.DETAIL_PAGE_DELAY_MIN,
        "DETAIL_PAGE_DELAY_MAX": cfg.DETAIL_PAGE_DELAY_MAX,
        "SECURITY_WAIT_SECONDS": cfg.SECURITY_WAIT_SECONDS,
        "REQUEST_TIMEOUT": cfg.REQUEST_TIMEOUT,
        "INCREMENTAL_EXIST_THRESHOLD": cfg.INCREMENTAL_EXIST_THRESHOLD,
    }


def _config_file_path() -> Path:
    return cfg.BASE_DIR / "data" / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def _coerce_value(value: str) -> bool | int | float | str:
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    if value.isdigit():
        return int(value)
    try:
        return float(value)
    except ValueError:
        return value


def _read_conf_file() -> dict[str, str]:
    filepath = _config_file_path()
    if not filepath.exists():
        return {}

    values: dict[str, str] = {}
    for line in filepath.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _serialize_value(value: Any) -> str:
    text = str(value)
    if not text or any(char.isspace() for char in text) or "#" in text:
        return json.dumps(text, ensure_ascii=False)
    return text


def _write_conf_file(updated: dict[str, Any]) -> None:
    filepath = _config_file_path()
    filepath.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = filepath.read_text(encoding="utf-8").splitlines() if filepath.exists() else []
    remaining = dict(updated)
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

    tmp_path = filepath.with_name(f"{filepath.name}.tmp")
    tmp_path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")
    tmp_path.replace(filepath)


def _read_config() -> dict[str, Any]:
    defaults = _defaults()
    persisted = _read_conf_file()
    result: dict[str, Any] = {}
    for key in CONFIG_KEYS:
        if key in persisted:
            result[key] = _coerce_value(persisted[key])
        elif key in defaults:
            result[key] = defaults[key]
    return result


def _cookie_path() -> Path:
    return cfg.COOKIE_DIR / DEFAULT_COOKIE_FILE


@router.get("")
def get_config(_current_user: CurrentUser) -> dict:
    return success(data=_read_config())


@router.put("")
def update_config(body: ConfigUpdate, _current_user: CurrentUser) -> dict:
    updated = body.model_dump(exclude_none=True)
    _write_conf_file(updated)
    return success(data=_read_config())


@router.get("/cookies")
def get_cookies_config(_current_user: CurrentUser) -> dict:
    filepath = _cookie_path()
    if not filepath.exists():
        return success(data=CookiesConfig(cookies=[]).model_dump())

    try:
        with filepath.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return success(data=CookiesConfig(cookies=[]).model_dump())

    if isinstance(data, list):
        return success(data=CookiesConfig(cookies=data).model_dump())

    if isinstance(data, dict):
        cookies_list = [
            {"name": key, "value": value, "domain": "javdb.com", "path": "/"}
            for key, value in data.items()
        ]
        return success(data=CookiesConfig(cookies=cookies_list).model_dump())

    return success(data=CookiesConfig(cookies=[]).model_dump())


@router.put("/cookies")
def update_cookies_config(body: CookiesConfig, _current_user: CurrentUser) -> dict:
    filepath = _cookie_path()
    filepath.parent.mkdir(parents=True, exist_ok=True)
    cookies_list = [cookie.model_dump() for cookie in body.cookies]
    with filepath.open("w", encoding="utf-8") as file:
        json.dump(cookies_list, file, ensure_ascii=False, indent=2)
    return success(data=body.model_dump())
