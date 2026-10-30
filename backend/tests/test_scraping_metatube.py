from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone

import httpx
from PIL import Image
from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem
from backend.app.modules.scraping.tasks import item_runner
from shared.database.models.content import Movie

from backend.app.modules.scraping.metatube import (
    fetch_metatube_movie,
    list_metatube_providers,
    write_metatube_artwork,
)


def _jpeg(size: tuple[int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "blue").save(output, format="JPEG")
    return output.getvalue()


def test_provider_listing_uses_enabled_movie_providers_only() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": {
        "movie_providers": {"MGS": "https://example.com", "FANZA": "https://example.org"},
        "actor_providers": {"Gfriends": "https://actors.example"},
    }}))
    assert list_metatube_providers("https://metatube.example", transport=transport) == ["FANZA", "MGS"]


def test_movie_lookup_requires_exact_code_and_uses_metatube_images() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"data": [
                {"provider": "FANZA", "id": "wrong", "number": "ADN-785"},
                {"provider": "FANZA", "id": "abc123", "number": "ADN-784"},
            ]})
        return httpx.Response(200, json={"data": {
            "number": "ADN-784", "title": "Title", "release_date": "2026-07-03",
            "genres": ["Tag"], "actors": ["Actor"], "maker": "Maker", "series": "Series",
        }})

    metadata = fetch_metatube_movie(
        "ADN-784", "FANZA", base_url="https://metatube.example", token="secret",
        transport=httpx.MockTransport(respond),
    )

    assert metadata is not None
    assert metadata.site_key == "FANZA"
    assert metadata.primary_image_url == "https://metatube.example/v1/images/primary/FANZA/abc123"
    assert metadata.backdrop_image_url == "https://metatube.example/v1/images/backdrop/FANZA/abc123"
    assert metadata.thumb_image_url == "https://metatube.example/v1/images/thumb/FANZA/abc123"
    assert metadata.actors == ["Actor"]
    assert requests[0].url.params["provider"] == "FANZA"
    assert requests[0].url.params["fallback"] == "false"
    assert all(request.headers["authorization"] == "Bearer secret" for request in requests)


def test_movie_lookup_does_not_accept_fuzzy_match() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": [
        {"provider": "MGS", "id": "wrong", "number": "ADN-785"},
    ]}))
    assert fetch_metatube_movie(
        "ADN-784", "MGS", base_url="https://metatube.example", transport=transport,
    ) is None


def test_artwork_keeps_metatube_image_roles_separate(tmp_path: Path) -> None:
    images = {
        "/v1/images/primary/FANZA/abc": _jpeg((400, 600)),
        "/v1/images/backdrop/FANZA/abc": _jpeg((800, 538)),
        "/v1/images/thumb/FANZA/abc": _jpeg((800, 450)),
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200, content=images[request.url.path], headers={"content-type": "image/jpeg"},
    ))
    from backend.app.modules.scraping.source_types import SourceMetadata
    metadata = SourceMetadata(
        site_key="FANZA",
        primary_image_url="https://metatube.example/v1/images/primary/FANZA/abc",
        backdrop_image_url="https://metatube.example/v1/images/backdrop/FANZA/abc",
        thumb_image_url="https://metatube.example/v1/images/thumb/FANZA/abc",
    )
    result = write_metatube_artwork(tmp_path, metadata, transport=transport)

    assert result.available == {"folder.jpg", "backdrop.jpg", "landscape.jpg"}
    assert (tmp_path / "folder.jpg").read_bytes() == images["/v1/images/primary/FANZA/abc"]
    assert (tmp_path / "backdrop.jpg").read_bytes() == images["/v1/images/backdrop/FANZA/abc"]
    assert (tmp_path / "landscape.jpg").read_bytes() == images["/v1/images/thumb/FANZA/abc"]


def test_metatube_miss_does_not_reuse_old_database_cover(db_session, admin_user, monkeypatch, tmp_path: Path) -> None:
    movie = Movie(
        code="ADN-784", cover="https://old.example/cover.jpg",
        storage_summary={"storage_status": "stored", "locations": [{"target_folder": "/media/ADN-784"}]},
    )
    db_session.add(movie)
    db_session.flush()
    task = ScrapingTask(status="running", total_count=1, created_by=admin_user.id, queued_at=datetime.now(timezone.utc))
    db_session.add(task)
    db_session.flush()
    item = ScrapingTaskItem(task_id=task.id, movie_id=movie.id, movie_code="ADN-784", status="pending")
    db_session.add(item)
    db_session.commit()
    (tmp_path / "ADN-784").mkdir()

    monkeypatch.setattr(item_runner, "fetch_by_priority", lambda *args, **kwargs: None)
    item_runner.run_item(db_session, item, config={
        "scrape_root": str(tmp_path), "media_root": "/media",
        "metadata_sources": ["metatube:FANZA"], "metatube_url": "http://127.0.0.1:2048",
    })

    assert item.status == "failed"
    assert item.error_message == "MetaTube 未找到该影片的元数据"
    assert not (tmp_path / "ADN-784" / "folder.jpg").exists()
