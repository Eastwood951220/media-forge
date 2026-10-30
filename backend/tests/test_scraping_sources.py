from backend.app.modules.scraping import sources
from backend.app.modules.scraping.source_types import SourceMetadata


def test_fetch_by_priority_uses_only_metatube_in_configured_order(monkeypatch) -> None:
    calls: list[str] = []

    def fake_fetch(code, provider, *, base_url, token):
        calls.append(provider)
        return SourceMetadata(site_key=provider) if provider == "FANZA" else None

    monkeypatch.setattr(sources, "fetch_metatube_movie", fake_fetch)
    result = sources.fetch_by_priority(
        "ADN-784", ["javdb", "metatube:MGS", "fanza", "metatube:FANZA", "metatube:JavBus"],
        metatube_url="http://localhost:2048", metatube_token="secret",
    )

    assert result is not None and result.site_key == "FANZA"
    assert calls == ["MGS", "FANZA"]


def test_legacy_sources_do_not_fetch_directly(monkeypatch) -> None:
    monkeypatch.setattr(sources, "fetch_metatube_movie", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))
    assert sources.fetch_by_priority("ADN-784", ["javdb", "javbus", "fanza"]) is None


def test_referer_for_pre_existing_cover_url() -> None:
    assert sources.referer_for_url("https://javdb.com/v/abc123") == "https://javdb.com/"
    assert sources.referer_for_url("https://www.javbus.com/ADN-784") == "https://www.javbus.com/"
    assert sources.referer_for_url("https://example.com/cover.jpg") is None
    assert sources.referer_for_url(None) is None
