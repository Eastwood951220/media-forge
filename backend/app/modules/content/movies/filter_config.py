from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from scraper.config import settings as cfg
from shared.settings_store import SettingsStore

FILTER_CONFIG_PATH = cfg.BASE_DIR / "data" / "configs" / "movie_filter_config.json"


class FilterItemConfig(BaseModel):
    visible: bool = True
    order: int = 0
    defaultValue: Any | None = None


class MovieFilterConfigPayload(BaseModel):
    filters: dict[str, FilterItemConfig] = Field(default_factory=dict)


def read_movie_filter_config(*, store: SettingsStore | None = None, legacy_path: Path | None = None) -> dict[str, Any]:
    if legacy_path is None:
        data = (store or SettingsStore()).read("movie_filters")
        payload = {"_key": "default", "filters": data.get("filters", {})}
        if "updated_at" in data:
            payload["updated_at"] = data["updated_at"]
        return payload
    if not legacy_path.exists():
        return {"_key": "default", "filters": {}}
    data = json.loads(legacy_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("filters", {}), dict):
        raise ValueError("Invalid legacy movie filter configuration")
    filters = data.get("filters", {})
    return {"_key": "default", "filters": filters, "updated_at": data.get("updated_at") if isinstance(data, dict) else None}


def write_movie_filter_config(filters: dict[str, Any], *, store: SettingsStore | None = None, legacy_path: Path | None = None) -> dict[str, Any]:
    from datetime import datetime, timezone

    payload = {
        "_key": "default",
        "filters": filters,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if legacy_path is None:
        (store or SettingsStore()).write("movie_filters", {"filters": filters, "updated_at": payload["updated_at"]})
        return payload
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = Path(str(legacy_path) + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(legacy_path)
    return payload
