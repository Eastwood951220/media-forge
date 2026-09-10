from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class MovieDetailRequest:
    source: str
    url: str
    code: str = ""
    name: str = ""
    task_url: str = ""
    task_final_url: str = ""
    task_url_type: str = ""
    task_url_name: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MovieDetailPayload:
    data: dict[str, Any]
    status: str = "completed"
    reason: str = ""

    @classmethod
    def from_spider_result(cls, result: dict[str, Any], default_reason: str) -> "MovieDetailPayload":
        status = str(result.get("status") or "")
        data = result.get("detail") or {}
        reason = str(result.get("reason") or "")
        if status != "completed":
            return cls(status=status or "failed", data={}, reason=reason or default_reason)
        return cls(status="completed", data=data, reason="")


class MagnetProvider(Protocol):
    source: str

    def fetch_detail_with_magnets(self, request: MovieDetailRequest, **kwargs) -> MovieDetailPayload:
        ...


def get_magnet_provider(source: str, *, fetcher) -> MagnetProvider:
    if source == "javdb":
        from scraper.spiders.javdb.magnet_provider import JavdbMagnetProvider

        return JavdbMagnetProvider(fetcher=fetcher)
    if source == "javbus":
        from scraper.spiders.javbus.magnet_provider import JavbusMagnetProvider

        return JavbusMagnetProvider(fetcher=fetcher)
    raise ValueError(f"不支持的磁力来源: {source}")
