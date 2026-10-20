from pathlib import Path

import httpx

from backend.app.modules.scraping.images import download_image, write_artwork


def _transport(content: bytes, content_type: str, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=content, headers={"content-type": content_type})
    return httpx.MockTransport(handler)


def test_download_image_writes_the_file(tmp_path: Path) -> None:
    dest = tmp_path / "folder.jpg"
    ok = download_image("https://example.com/a.jpg", dest, transport=_transport(b"jpeg-bytes", "image/jpeg"))
    assert ok is True
    assert dest.read_bytes() == b"jpeg-bytes"
    assert not list(tmp_path.glob("*.tmp"))


def test_download_image_rejects_non_image_content(tmp_path: Path) -> None:
    dest = tmp_path / "folder.jpg"
    ok = download_image("https://example.com/a", dest, transport=_transport(b"<html>", "text/html"))
    assert ok is False
    assert not dest.exists()


def test_download_image_handles_http_errors(tmp_path: Path) -> None:
    dest = tmp_path / "folder.jpg"
    ok = download_image("https://example.com/a.jpg", dest, transport=_transport(b"", "image/jpeg", status=404))
    assert ok is False
    assert not dest.exists()


def test_write_artwork_writes_available_images(tmp_path: Path) -> None:
    transport = _transport(b"img", "image/jpeg")
    count = write_artwork(
        tmp_path,
        cover_url="https://example.com/cover.jpg",
        backdrop_url="https://example.com/backdrop.jpg",
        landscape_url=None,
        transport=transport,
    )
    assert count == 2
    assert (tmp_path / "folder.jpg").exists()
    assert (tmp_path / "backdrop.jpg").exists()
    assert not (tmp_path / "landscape.jpg").exists()
