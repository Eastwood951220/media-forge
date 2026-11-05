"""Cookie configuration adapters shared by backend, scraper and archive handling."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shared.settings_store import SettingsStore

COOKIE_FILES = {
    "javdb_cookies.json": ("cookies", "javdb.com"),
    "javbus_cookies.json": ("javbus_cookies", "javbus.com"),
    "avjoho_cookies.json": ("avjoho_cookies", "db.avjoho.com"),
}


def normalize_cookies(data: Any, domain: str = "javdb.com") -> list[dict]:
    if isinstance(data, dict):
        return [
            {"name": key, "value": value, "domain": domain, "path": "/"}
            for key, value in data.items() if key and value is not None
        ]
    if isinstance(data, list):
        return [dict(row) for row in data if isinstance(row, dict) and row.get("name") and row.get("value") is not None]
    return []


def read_legacy_cookies(path: Path) -> list[dict]:
    if not path.exists():
        return []
    domain = COOKIE_FILES.get(path.name, ("cookies", "javdb.com"))[1]
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, (dict, list)):
        raise ValueError(f"Invalid legacy cookie configuration: {path}")
    return normalize_cookies(data, domain)


def read_cookies(store: SettingsStore | None = None, *, filename: str = "javdb_cookies.json") -> list[dict]:
    key, domain = COOKIE_FILES[filename]
    return normalize_cookies((store or SettingsStore()).read("crawler_cookies").get(key, []), domain)


def write_cookies(rows: Any, store: SettingsStore | None = None, *, filename: str = "javdb_cookies.json") -> None:
    key, domain = COOKIE_FILES[filename]
    (store or SettingsStore()).write("crawler_cookies", {key: normalize_cookies(rows, domain)})
