from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from scraper.config import settings as cfg

FILTER_CONFIG_PATH = cfg.BASE_DIR / "data" / "configs" / "movie_filter_config.json"


class FilterItemConfig(BaseModel):
    visible: bool = True
    order: int = 0
    defaultValue: Any | None = None


class MovieFilterConfigPayload(BaseModel):
    filters: dict[str, FilterItemConfig] = Field(default_factory=dict)


def read_movie_filter_config() -> dict[str, Any]:
    if not FILTER_CONFIG_PATH.exists():
        return {"_key": "default", "filters": {}}
    try:
        data = json.loads(FILTER_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"_key": "default", "filters": {}}
    filters = data.get("filters") if isinstance(data, dict) else {}
    if not isinstance(filters, dict):
        filters = {}
    return {"_key": "default", "filters": filters, "updated_at": data.get("updated_at") if isinstance(data, dict) else None}


def write_movie_filter_config(filters: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime, timezone

    FILTER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_key": "default",
        "filters": filters,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    temp_path = Path(str(FILTER_CONFIG_PATH) + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(FILTER_CONFIG_PATH)
    return payload
