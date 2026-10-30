"""Regression tests for disabling the old direct FANZA adapter."""

from backend.app.modules.scraping import sources


def test_plain_fanza_source_does_not_make_a_metadata_request(monkeypatch) -> None:
    def unexpected(*args, **kwargs):
        raise AssertionError("MetaTube must not be called for a legacy source key")

    monkeypatch.setattr(sources, "fetch_metatube_movie", unexpected)
    assert sources.fetch_by_priority("MIDA-819", ["fanza"]) is None
