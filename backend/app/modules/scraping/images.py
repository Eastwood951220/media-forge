from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30.0
MAX_IMAGE_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class ArtworkResult:
    written: int
    available: set[str]


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
    try:
        temp.write_bytes(b"".join(chunks))
        temp.replace(target)
    except OSError:
        logger.warning("Artwork write failed: path=%s", target, exc_info=True)
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            logger.debug("Could not remove temp artwork file: path=%s", temp)
        return False
    return True


def _fetch_artwork(
    url: str,
    *,
    referer: str | None,
    transport: httpx.BaseTransport | None,
) -> bytes | None:
    headers = {"User-Agent": "Mozilla/5.0"}
    if referer:
        headers["Referer"] = referer
    try:
        with httpx.Client(timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS), transport=transport) as client:
            with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                if not response.headers.get("content-type", "").lower().startswith("image/"):
                    return None
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        logger.warning("Skipping oversized artwork: url=%s", url)
                        return None
                    chunks.append(chunk)
        data = b"".join(chunks)
        with Image.open(BytesIO(data)) as image:
            image.verify()
        return data
    except (httpx.HTTPError, OSError, UnidentifiedImageError, ValueError):
        logger.warning("Artwork fetch or decode failed: url=%s", url, exc_info=True)
        return None


def _same_picture(left: bytes, right: bytes) -> bool:
    try:
        with Image.open(BytesIO(left)) as first, Image.open(BytesIO(right)) as second:
            ratio_a = first.width / first.height
            ratio_b = second.width / second.height
            if abs(ratio_a - ratio_b) > 0.1:
                return False
            # Normalize size and small aspect differences before comparing pixels.
            a = ImageOps.fit(first.convert("L"), (32, 32), method=Image.Resampling.LANCZOS)
            b = ImageOps.fit(second.convert("L"), (32, 32), method=Image.Resampling.LANCZOS)
            difference = sum(abs(x - y) for x, y in zip(a.tobytes(), b.tobytes())) / 1024
            return difference <= 6.0
    except (OSError, UnidentifiedImageError, ValueError, ZeroDivisionError):
        return False


def _save_image(path: Path, data: bytes) -> bool:
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        temp.write_bytes(data)
        temp.replace(path)
        return True
    except OSError:
        logger.warning("Artwork write failed: path=%s", path, exc_info=True)
        temp.unlink(missing_ok=True)
        return False


def write_artwork(
    folder: Path,
    *,
    cover_url: str | None,
    backdrop_urls: list[str],
    landscape_urls: list[str],
    referer: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> ArtworkResult:
    folder = Path(folder)
    written = 0
    cache: dict[str, bytes | None] = {}

    def fetch(url: str) -> bytes | None:
        if url not in cache:
            cache[url] = _fetch_artwork(url, referer=referer, transport=transport)
        return cache[url]

    cover_path = folder / "folder.jpg"
    if cover_url and (data := fetch(cover_url)) and _save_image(cover_path, data):
        written += 1

    selected: dict[str, bytes] = {}
    if cover_path.is_file():
        selected["folder.jpg"] = cover_path.read_bytes()

    for filename, candidates in (("backdrop.jpg", backdrop_urls), ("landscape.jpg", landscape_urls)):
        target = folder / filename
        chosen = False
        for url in dict.fromkeys(candidates):
            if not url or not (data := fetch(url)):
                continue
            if any(_same_picture(data, previous) for previous in selected.values()):
                logger.info("Skipping duplicate artwork: slot=%s url=%s", filename, url)
                continue
            if _save_image(target, data):
                selected[filename] = data
                written += 1
                chosen = True
                break
        if not chosen and target.is_file():
            old = target.read_bytes()
            if any(_same_picture(old, previous) for previous in selected.values()):
                target.unlink(missing_ok=True)
                logger.info("Removed duplicate old artwork: path=%s", target)
            else:
                selected[filename] = old

    return ArtworkResult(written=written, available={name for name in ("folder.jpg", "backdrop.jpg", "landscape.jpg") if (folder / name).is_file()})
