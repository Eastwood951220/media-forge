import pytest

from scraper.magnets.provider import MovieDetailPayload, MovieDetailRequest, get_magnet_provider


class DummyFetcher:
    def get(self, url: str, **kwargs):
        raise AssertionError("not used in registry type test")


def test_movie_detail_request_carries_source_context() -> None:
    request = MovieDetailRequest(
        source="javdb",
        url="https://javdb.com/v/abc",
        code="ABC-001",
        name="Example",
        task_url="https://javdb.com/actors/a",
        task_final_url="https://javdb.com/actors/a?page=1",
        task_url_type="actors",
        task_url_name="Actor",
    )

    assert request.source == "javdb"
    assert request.url == "https://javdb.com/v/abc"
    assert request.code == "ABC-001"
    assert request.task_url == "https://javdb.com/actors/a"
    assert request.task_final_url == "https://javdb.com/actors/a?page=1"
    assert request.task_url_name == "Actor"


def test_movie_detail_payload_wraps_existing_detail_status_and_shape() -> None:
    payload = MovieDetailPayload(data={"code": "ABC-001", "magnets": [{"name": "m"}]})

    assert payload.status == "completed"
    assert payload.reason == ""
    assert payload.data["code"] == "ABC-001"
    assert payload.data["magnets"] == [{"name": "m"}]


def test_movie_detail_payload_can_represent_failed_crawl_without_exception() -> None:
    payload = MovieDetailPayload(status="failed", reason="blocked", data={})

    assert payload.status == "failed"
    assert payload.reason == "blocked"
    assert payload.data == {}


def test_movie_detail_payload_builds_from_spider_result() -> None:
    completed = MovieDetailPayload.from_spider_result(
        {"status": "completed", "detail": {"code": "ABC-001"}},
        default_reason="detail fetch failed",
    )
    failed = MovieDetailPayload.from_spider_result(
        {"status": "failed", "reason": "blocked", "detail": {"ignored": True}},
        default_reason="detail fetch failed",
    )

    assert completed.status == "completed"
    assert completed.data == {"code": "ABC-001"}
    assert failed.status == "failed"
    assert failed.reason == "blocked"
    assert failed.data == {}


def test_get_magnet_provider_returns_javdb_and_javbus_providers() -> None:
    assert get_magnet_provider("javdb", fetcher=DummyFetcher()).source == "javdb"
    assert get_magnet_provider("javbus", fetcher=DummyFetcher()).source == "javbus"


def test_get_magnet_provider_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="不支持的磁力来源"):
        get_magnet_provider("unknown", fetcher=DummyFetcher())
