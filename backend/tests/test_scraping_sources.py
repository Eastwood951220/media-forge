from backend.app.modules.scraping import sources
from backend.app.modules.scraping.sources import SOURCE_LABELS, SOURCE_REGISTRY, SourceMetadata


class _FakePage:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeFetcher:
    def __init__(self, pages: dict[str, object]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    def get(self, url: str, **_kwargs) -> object:
        self.requested.append(url)
        return self.pages[url]


def test_registry_contains_javdb_and_javbus() -> None:
    assert set(SOURCE_REGISTRY) == {"javdb", "javbus"}
    assert SOURCE_LABELS["javdb"]
    assert SOURCE_LABELS["javbus"]


def test_fetch_by_priority_uses_configured_order_and_stops_on_success(monkeypatch) -> None:
    calls: list[str] = []

    def fake_fetch(adapter, code):
        calls.append(adapter)
        if adapter == "javbus":
            return SourceMetadata(site_key="JavBus", title="ok")
        return None

    monkeypatch.setattr(sources, "fetch_with_source", fake_fetch)

    result = sources.fetch_by_priority("ADN-784", ["javdb", "javbus"])

    assert result is not None
    assert result.site_key == "JavBus"
    assert calls == ["javdb", "javbus"]


def test_fetch_by_priority_returns_none_when_all_sources_fail(monkeypatch) -> None:
    monkeypatch.setattr(sources, "fetch_with_source", lambda adapter, code: None)
    assert sources.fetch_by_priority("ADN-784", ["javdb", "javbus"]) is None


def test_javdb_adapter_parses_search_and_detail(monkeypatch) -> None:
    search_page = _FakePage("search")
    detail_page = _FakePage("detail")
    fetcher = _FakeFetcher({
        "https://javdb.com/search?q=ADN-784&f=all": search_page,
        "https://javdb.com/v/detail": detail_page,
    })

    monkeypatch.setattr(
        sources,
        "parse_javdb_search",
        lambda page, page_no: [
            {"url": "https://javdb.com/v/detail", "code": "ADN-784", "status": "pending", "name": "ADN-784"}
        ],
    )
    monkeypatch.setattr(
        sources,
        "parse_javdb_detail",
        lambda page: {
            "code": "ADN-784",
            "source_name": "ADN-784 タイトル",
            "cover": "https://javdb.com/cover.jpg",
            "release_date": "2026-07-03",
            "maker": "メーカー",
            "series": "シリーズ",
            "tags": ["タグ"],
            "actors": ["女優"],
            "preview_images": [
                "https://javdb.com/preview-1.jpg",
                "https://javdb.com/preview-2.jpg",
            ],
        },
    )

    adapter = sources.JavdbAdapter(fetcher_factory=lambda source: fetcher, throttle=lambda: None)
    metadata = adapter.fetch_by_code("ADN-784")

    assert metadata is not None
    assert metadata.site_key == "JavDB"
    assert metadata.cover_url == "https://javdb.com/cover.jpg"
    assert metadata.backdrop_url == "https://javdb.com/preview-1.jpg"
    assert metadata.landscape_url == "https://javdb.com/preview-2.jpg"
    assert metadata.premiered == "2026-07-03"
    assert metadata.studio == "メーカー"
    assert fetcher.requested[0].endswith("/search?q=ADN-784&f=all")


def test_javbus_adapter_parses_search_and_detail(monkeypatch) -> None:
    search_page = _FakePage("search")
    detail_page = _FakePage("detail")
    fetcher = _FakeFetcher({
        "https://www.javbus.com/search/ADN-784": search_page,
        "https://www.javbus.com/ADN-784": detail_page,
    })

    monkeypatch.setattr(
        sources,
        "parse_javbus_list",
        lambda page, source_url: ([{"url": "https://www.javbus.com/ADN-784", "code": "ADN-784"}], None),
    )
    monkeypatch.setattr(
        sources,
        "parse_javbus_detail",
        lambda page, source_url: {
            "code": "ADN-784",
            "source_name": "ADN-784 タイトル",
            "cover_url": "https://www.javbus.com/cover.jpg",
            "release_date": "2026-07-03",
            "maker": "メーカー",
            "series": "シリーズ",
            "tags": ["タグ"],
            "actors": ["女優"],
            "preview_images": [
                "https://www.javbus.com/preview-1.jpg",
                "https://www.javbus.com/preview-2.jpg",
            ],
        },
    )

    adapter = sources.JavbusAdapter(fetcher_factory=lambda source: fetcher, throttle=lambda: None)
    metadata = adapter.fetch_by_code("ADN-784")

    assert metadata is not None
    assert metadata.site_key == "JavBus"
    assert metadata.cover_url == "https://www.javbus.com/cover.jpg"
    assert metadata.backdrop_url == "https://www.javbus.com/preview-1.jpg"
    assert metadata.landscape_url == "https://www.javbus.com/preview-2.jpg"
    assert metadata.premiered == "2026-07-03"
    assert metadata.studio == "メーカー"
    assert fetcher.requested[1] == "https://www.javbus.com/ADN-784"


def test_adapters_return_none_when_fetch_raises() -> None:
    def failing_factory(source: str):
        raise RuntimeError("network down")

    adapter = sources.JavbusAdapter(fetcher_factory=failing_factory, throttle=lambda: None)

    assert adapter.fetch_by_code("ADN-784") is None


def test_source_referer_maps_registry_sites() -> None:
    assert sources.source_referer("JavDB") == "https://javdb.com/"
    assert sources.source_referer("JavBus") == "https://www.javbus.com/"
    assert sources.source_referer("unknown") is None
