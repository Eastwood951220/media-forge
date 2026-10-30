from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import quote

import httpx

from backend.app.modules.scraping.images import ArtworkResult, _fetch_artwork, _save_image
from backend.app.modules.scraping.paths import normalize_code
from backend.app.modules.scraping.source_types import SourceMetadata

logger = logging.getLogger(__name__)
SOURCE_PATTERN = re.compile(r"^metatube:([A-Za-z0-9][A-Za-z0-9_-]{0,63})$")
TIMEOUT = httpx.Timeout(30.0)
PROVIDERS_TIMEOUT = httpx.Timeout(8.0)


def is_metatube_source(source: str) -> bool:
    return SOURCE_PATTERN.fullmatch(source) is not None


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _data(response: httpx.Response) -> object:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or "data" not in payload:
        raise ValueError("MetaTube 返回格式无效")
    return payload["data"]


def list_metatube_providers(
    base_url: str, *, transport: httpx.BaseTransport | None = None,
) -> list[str]:
    if not base_url:
        return []
    with httpx.Client(timeout=PROVIDERS_TIMEOUT, transport=transport) as client:
        data = _data(client.get(f"{base_url.rstrip('/')}/v1/providers"))
    if not isinstance(data, dict) or not isinstance(data.get("movie_providers"), dict):
        raise ValueError("MetaTube 影片来源列表格式无效")
    return sorted(
        (name for name in data["movie_providers"] if is_metatube_source(f"metatube:{name}")),
        key=str.casefold,
    )


def _movie_image_url(base_url: str, kind: str, provider: str, movie_id: str) -> str:
    return (
        f"{base_url.rstrip('/')}/v1/images/{kind}/"
        f"{quote(provider, safe='')}/{quote(movie_id, safe='')}"
    )


def fetch_metatube_movie(
    code: str,
    provider: str,
    *,
    base_url: str,
    token: str = "",
    transport: httpx.BaseTransport | None = None,
) -> SourceMetadata | None:
    if not base_url or not is_metatube_source(f"metatube:{provider}"):
        return None
    base_url = base_url.rstrip("/")
    try:
        with httpx.Client(timeout=TIMEOUT, transport=transport) as client:
            results = _data(client.get(
                f"{base_url}/v1/movies/search",
                params={"q": code, "provider": provider, "fallback": "false"},
                headers=_headers(token),
            ))
            if not isinstance(results, list):
                raise ValueError("MetaTube 搜索结果格式无效")
            wanted = normalize_code(code)
            match = next((item for item in results if isinstance(item, dict)
                          and str(item.get("provider") or "").casefold() == provider.casefold()
                          and normalize_code(str(item.get("number") or "")) == wanted
                          and str(item.get("id") or "")), None)
            if match is None:
                return None
            movie_id = str(match["id"])
            info = _data(client.get(
                f"{base_url}/v1/movies/{quote(provider, safe='')}/{quote(movie_id, safe='')}",
                params={"lazy": "true"},
                headers=_headers(token),
            ))
        if not isinstance(info, dict) or normalize_code(str(info.get("number") or "")) != wanted:
            return None
        primary = _movie_image_url(base_url, "primary", provider, movie_id)
        thumb = _movie_image_url(base_url, "thumb", provider, movie_id)
        backdrop = _movie_image_url(base_url, "backdrop", provider, movie_id)
        return SourceMetadata(
            site_key=provider,
            title=str(info.get("title") or "") or None,
            original_title=str(info.get("title") or "") or None,
            premiered=str(info.get("release_date") or "") or None,
            genres=list(info.get("genres") or []),
            tags=list(info.get("genres") or []),
            studio=str(info.get("maker") or "") or None,
            series=str(info.get("series") or "") or None,
            actors=list(info.get("actors") or []),
            cover_url=primary,
            primary_image_url=primary,
            thumb_image_url=thumb,
            backdrop_image_url=backdrop,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            logger.warning("MetaTube movie lookup failed: provider=%s code=%s", provider, code, exc_info=True)
        return None
    except (httpx.HTTPError, ValueError, TypeError):
        logger.warning("MetaTube movie lookup failed: provider=%s code=%s", provider, code, exc_info=True)
        return None


def write_metatube_artwork(
    folder: Path,
    metadata: SourceMetadata,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ArtworkResult:
    urls = {
        "folder.jpg": metadata.primary_image_url,
        "backdrop.jpg": metadata.backdrop_image_url,
        "landscape.jpg": metadata.thumb_image_url,
    }
    written = 0
    for filename, url in urls.items():
        if not url:
            continue
        data = _fetch_artwork(url, referer=None, transport=transport)
        if data and _save_image(folder / filename, data):
            written += 1
    return ArtworkResult(
        written=written,
        available={name for name in urls if (folder / name).is_file()},
    )
