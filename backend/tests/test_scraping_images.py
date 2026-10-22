from pathlib import Path
from io import BytesIO

import httpx
from PIL import Image, ImageDraw

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


def test_download_image_rejects_oversized_content(tmp_path: Path, monkeypatch) -> None:
    from backend.app.modules.scraping import images

    monkeypatch.setattr(images, "MAX_IMAGE_BYTES", 4)
    dest = tmp_path / "folder.jpg"
    ok = download_image("https://example.com/a.jpg", dest, transport=_transport(b"12345", "image/jpeg"))
    assert ok is False
    assert not dest.exists()


def test_write_artwork_writes_available_images(tmp_path: Path) -> None:
    transport = _transport(_jpeg("cover"), "image/jpeg")
    result = write_artwork(
        tmp_path,
        cover_url="https://example.com/cover.jpg",
        backdrop_urls=["https://example.com/backdrop.jpg"],
        landscape_urls=[],
        transport=transport,
    )
    assert result.written == 1
    assert (tmp_path / "folder.jpg").exists()
    assert not (tmp_path / "backdrop.jpg").exists()
    assert not (tmp_path / "landscape.jpg").exists()


def _jpeg(scene: str, size: tuple[int, int] = (160, 100)) -> bytes:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    color = "red" if scene == "cover" else "blue"
    draw.rectangle((10, 10, size[0] // 2, size[1] // 2), fill=color)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def test_write_artwork_skips_resized_cover_then_uses_distinct_previews(tmp_path: Path) -> None:
    content = {
        "/cover.jpg": _jpeg("cover"),
        "/cover-large.jpg": _jpeg("cover", (320, 200)),
        "/scene-a.jpg": _jpeg("scene-a"),
        "/scene-b.jpg": Image.new("RGB", (160, 100), "green"),
    }
    green = BytesIO()
    content["/scene-b.jpg"].save(green, format="JPEG")
    content["/scene-b.jpg"] = green.getvalue()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=content[request.url.path], headers={"content-type": "image/jpeg"}))

    result = write_artwork(
        tmp_path, cover_url="https://example.com/cover.jpg",
        backdrop_urls=["https://example.com/cover-large.jpg", "https://example.com/scene-a.jpg", "https://example.com/scene-b.jpg"],
        landscape_urls=["https://example.com/cover-large.jpg", "https://example.com/scene-a.jpg", "https://example.com/scene-b.jpg"],
        transport=transport,
    )

    assert result.available == {"folder.jpg", "backdrop.jpg", "landscape.jpg"}
    assert (tmp_path / "backdrop.jpg").read_bytes() == content["/scene-a.jpg"]
    assert (tmp_path / "landscape.jpg").read_bytes() == content["/scene-b.jpg"]


def test_write_artwork_removes_only_proven_duplicate_old_slot(tmp_path: Path) -> None:
    (tmp_path / "folder.jpg").write_bytes(_jpeg("cover"))
    (tmp_path / "backdrop.jpg").write_bytes(_jpeg("cover", (320, 200)))
    (tmp_path / "landscape.jpg").write_bytes(_jpeg("scene-a"))

    result = write_artwork(tmp_path, cover_url=None, backdrop_urls=[], landscape_urls=[])

    assert result.available == {"folder.jpg", "landscape.jpg"}
    assert not (tmp_path / "backdrop.jpg").exists()
    assert (tmp_path / "landscape.jpg").exists()


def test_write_artwork_preserves_existing_unique_slot_on_download_failure(tmp_path: Path) -> None:
    original = _jpeg("scene-a")
    (tmp_path / "backdrop.jpg").write_bytes(original)
    transport = _transport(b"", "image/jpeg", status=500)

    result = write_artwork(
        tmp_path, cover_url="https://example.com/cover.jpg",
        backdrop_urls=["https://example.com/broken.jpg"], landscape_urls=[], transport=transport,
    )

    assert result.available == {"backdrop.jpg"}
    assert (tmp_path / "backdrop.jpg").read_bytes() == original


def test_write_artwork_uses_original_source_referer_for_saved_cover(tmp_path: Path) -> None:
    referers: dict[str, str | None] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        referers[request.url.path] = request.headers.get("referer")
        content = _jpeg("cover") if request.url.path == "/cover.jpg" else _jpeg("scene-a")
        return httpx.Response(200, content=content, headers={"content-type": "image/jpeg"})

    write_artwork(
        tmp_path, cover_url="https://javdb.example/cover.jpg",
        backdrop_urls=["https://dmm.example/scene.jpg"], landscape_urls=[],
        cover_referer="https://javdb.com/", referer="https://video.dmm.co.jp/",
        transport=httpx.MockTransport(handle),
    )

    assert referers == {"/cover.jpg": "https://javdb.com/", "/scene.jpg": "https://video.dmm.co.jp/"}


def test_write_artwork_does_not_confuse_different_colors_with_equal_luminance(tmp_path: Path) -> None:
    def jpeg(color: tuple[int, int, int]) -> bytes:
        buffer = BytesIO()
        Image.new("RGB", (160, 100), color).save(buffer, format="JPEG", quality=95)
        return buffer.getvalue()

    data = {"/cover.jpg": jpeg((255, 0, 0)), "/other.jpg": jpeg((0, 130, 0))}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=data[request.url.path], headers={"content-type": "image/jpeg"}))

    result = write_artwork(
        tmp_path, cover_url="https://example.com/cover.jpg",
        backdrop_urls=["https://example.com/other.jpg"], landscape_urls=[], transport=transport,
    )

    assert result.available == {"folder.jpg", "backdrop.jpg"}

