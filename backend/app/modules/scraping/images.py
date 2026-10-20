from __future__ import annotations

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30.0
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def download_image(
    url: str,
    dest: Path,
    *,
    referer: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> bool:
    if not url:
        return False
    headers = {"User-Agent": "Mozilla/5.0"}
    if referer:
        headers["Referer"] = referer
    target = Path(dest)
    try:
        with httpx.Client(timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS), transport=transport) as client:
            with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if not content_type.lower().startswith("image/"):
                    logger.warning("Skipping non-image artwork: url=%s type=%s", url, content_type)
                    return False
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        logger.warning("Skipping oversized artwork: url=%s", url)
                        return False
                    chunks.append(chunk)
    except Exception:
        logger.warning("Artwork download failed: url=%s", url, exc_info=True)
        return False

    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_bytes(b"".join(chunks))
    temp.replace(target)
    return True


def write_artwork(
    folder: Path,
    *,
    cover_url: str | None,
    backdrop_url: str | None,
    landscape_url: str | None,
    referer: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> int:
    folder = Path(folder)
    written = 0
    mapping = (
        (cover_url, "folder.jpg"),
        (backdrop_url, "backdrop.jpg"),
        (landscape_url, "landscape.jpg"),
    )
    for url, filename in mapping:
        if not url:
            continue
        if download_image(url, folder / filename, referer=referer, transport=transport):
            written += 1
    return written
