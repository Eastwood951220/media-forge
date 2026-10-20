from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import ValidationError

from backend.app.modules.scraping.schemas import (
    DEFAULT_MEDIA_ROOT,
    DEFAULT_METADATA_SOURCES,
    ScrapingConfig,
    ScrapingConfigResponse,
    ScrapingConfigUpdate,
)
from backend.app.modules.scraping.sources import SOURCE_REGISTRY
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


def _serialize_value(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ValueError("刮削配置值不能包含换行")
    if not text or any(char.isspace() for char in text) or "#" in text:
        return json.dumps(text, ensure_ascii=False)
    return text


def _normalize_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if normalized and not normalized.startswith(("http://", "https://")):
        raise ValueError("外部服务地址必须以 http:// 或 https:// 开头")
    return normalized


def _coerce_directory_id(value: str | None) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = int(text)
    except ValueError:
        return None
    return parsed if parsed >= 1 else None


def _coerce_delay(value: str | None) -> int:
    text = (value or "").strip()
    try:
        parsed = int(text)
    except ValueError:
        return 30
    return parsed if 10 <= parsed <= 3600 else 30


def _normalize_media_root(value: str | None) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text.startswith("/") or text == "" or text == "/":
        raise ValueError("媒体库根路径必须是 / 开头的绝对路径")
    return text


def _normalize_scrape_root(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text)
    if not path.is_absolute():
        raise ValueError("刮削目录必须是绝对路径")
    if not path.is_dir():
        raise ValueError("刮削目录不存在或不是文件夹")
    return str(path)


def _parse_metadata_sources(raw: object) -> list[str]:
    try:
        parsed = json.loads(str(raw or ""))
    except (TypeError, ValueError):
        return list(DEFAULT_METADATA_SOURCES)
    if not isinstance(parsed, list):
        return list(DEFAULT_METADATA_SOURCES)
    sources = [str(item) for item in parsed if str(item) in SOURCE_REGISTRY]
    return sources or list(DEFAULT_METADATA_SOURCES)


def _safe_media_root(raw: object) -> str:
    text = str(raw or "").strip().rstrip("/")
    if not text.startswith("/") or text == "/":
        return DEFAULT_MEDIA_ROOT
    return text


class ScrapingConfigService:
    """Read and write scraping settings in a dotenv style file."""

    def __init__(self, config_file: Path | None = None) -> None:
        if config_file is None:
            config_file = RuntimeConfigPaths.from_env().config_dir / "scraping.conf"
        self.config_file = config_file

    def get_public_config(self) -> dict[str, Any]:
        return self._public_config(self.get_raw_config())

    def get_raw_config(self) -> dict[str, Any]:
        defaults = ScrapingConfig().model_dump()
        if not self.config_file.exists():
            return defaults

        parsed = dotenv_values(self.config_file, interpolate=False)
        values = dict(defaults)
        values["base_url"] = str(parsed.get("base_url") or "").strip()
        values["api_key"] = str(parsed.get("api_key") or "")
        values["directory_id"] = _coerce_directory_id(parsed.get("directory_id"))
        values["trigger_delay_seconds"] = _coerce_delay(parsed.get("trigger_delay_seconds"))
        values["scrape_root"] = str(parsed.get("scrape_root") or "").strip()
        values["media_root"] = _safe_media_root(parsed.get("media_root"))
        values["metadata_sources"] = _parse_metadata_sources(parsed.get("metadata_sources"))
        try:
            return ScrapingConfig(**values).model_dump()
        except ValidationError:
            values["media_root"] = DEFAULT_MEDIA_ROOT
            values["metadata_sources"] = list(DEFAULT_METADATA_SOURCES)
            return ScrapingConfig(**values).model_dump()

    def update_config(
        self,
        body: ScrapingConfigUpdate | Mapping[str, Any],
    ) -> dict[str, Any]:
        current = self.get_raw_config()
        if hasattr(body, "model_dump"):
            incoming = body.model_dump(exclude_unset=True)
        else:
            incoming = dict(body)

        if incoming.get("trigger_delay_seconds") is None:
            incoming.pop("trigger_delay_seconds", None)
        if "base_url" in incoming:
            incoming["base_url"] = _normalize_base_url(str(incoming.get("base_url") or ""))
        if "scrape_root" in incoming:
            incoming["scrape_root"] = _normalize_scrape_root(incoming.get("scrape_root"))
        if "media_root" in incoming:
            incoming["media_root"] = _normalize_media_root(incoming.get("media_root"))
        if "metadata_sources" in incoming:
            sources = [str(item) for item in (incoming.get("metadata_sources") or [])]
            unknown = [item for item in sources if item not in SOURCE_REGISTRY]
            if unknown:
                raise ValueError(f"不支持的元数据源: {', '.join(unknown)}")
            if not sources:
                raise ValueError("元数据源不能为空")
            incoming["metadata_sources"] = sources
        if "api_key" in incoming:
            key = str(incoming.get("api_key") or "")
            incoming["api_key"] = current.get("api_key", "") if not key or is_masked_token(key) else key

        merged = dict(current)
        merged.update(incoming)
        validated = ScrapingConfig(**merged).model_dump()
        self._write_config(validated)
        return self._public_config(validated)

    def _public_config(self, config: dict[str, Any]) -> dict[str, Any]:
        raw_key = str(config.get("api_key") or "")
        public = dict(config)
        public["api_key"] = mask_token(raw_key)
        public["api_key_configured"] = bool(raw_key)
        return ScrapingConfigResponse(**public).model_dump()

    def _write_config(self, data: dict[str, Any]) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(
            f"{key}={_serialize_value(value) if not isinstance(value, list) else json.dumps(value, ensure_ascii=False)}\n"
            for key, value in data.items()
        )
        temp_path = self.config_file.with_suffix(self.config_file.suffix + ".tmp")
        temp_path.write_text(body, encoding="utf-8")
        temp_path.replace(self.config_file)


def validate_run_config(config: Mapping[str, Any]) -> str | None:
    """Return a human-readable reason when the config is not runnable."""
    base_url = str(config.get("base_url") or "").strip()
    if not base_url:
        return "未配置外部服务地址"
    if not base_url.startswith(("http://", "https://")):
        return "外部服务地址无效"
    if not str(config.get("api_key") or "").strip():
        return "未配置 API Key"
    if config.get("directory_id") in (None, ""):
        return "未配置目录 ID"
    return None


def validate_scrape_root(config: Mapping[str, Any]) -> str | None:
    """Return a human-readable reason when directory scanning is not runnable."""
    scrape_root = str(config.get("scrape_root") or "").strip()
    if not scrape_root:
        return "未配置刮削目录"
    if not Path(scrape_root).is_dir():
        return "刮削目录不存在或不是文件夹"
    return None
