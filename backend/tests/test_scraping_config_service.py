from pathlib import Path

import pytest

from backend.app.modules.scraping.config import ScrapingConfigService, normalize_metadata_sources
from backend.app.modules.scraping.schemas import ScrapingConfigUpdate


def _service(tmp_path: Path) -> ScrapingConfigService:
    return ScrapingConfigService(config_file=tmp_path / "scraping.conf")


def test_defaults_without_config_file(tmp_path: Path) -> None:
    assert _service(tmp_path).get_public_config() == {
        "base_url": "http://192.168.0.36:12333",
        "api_key": "",
        "api_key_configured": False,
        "directory_id": None,
        "trigger_delay_seconds": 30,
        "scrape_root": "",
        "media_root": "/media",
        "metadata_sources": ["metatube:JavBus", "metatube:FANZA"],
        "metatube_url": "",
        "metatube_token": "",
        "metatube_token_configured": False,
        "jellyfin_base_url": "",
        "jellyfin_api_key": "",
        "jellyfin_api_key_configured": False,
        "jellyfin_auto_refresh_enabled": False,
        "jellyfin_watch_sync_enabled": False,
        "jellyfin_watch_sync_schedule_type": "daily",
        "jellyfin_watch_sync_time_of_day": "03:00",
        "jellyfin_watch_sync_weekdays": [],
    }


def test_update_writes_conf_and_masks_the_key(tmp_path: Path) -> None:
    service = _service(tmp_path)

    public = service.update_config(
        ScrapingConfigUpdate(
            base_url="https://example.com/",
            api_key="secret-key-1234",
            directory_id=4,
            trigger_delay_seconds=45,
        )
    )

    assert public["base_url"] == "https://example.com"
    assert public["api_key"] == "************1234"
    assert public["api_key_configured"] is True

    text = (tmp_path / "scraping.conf").read_text(encoding="utf-8")
    assert "base_url=https://example.com\n" in text
    assert "api_key=secret-key-1234\n" in text
    assert "directory_id=4\n" in text
    assert "trigger_delay_seconds=45\n" in text


def test_masked_or_empty_key_preserves_the_stored_key(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.update_config(ScrapingConfigUpdate(api_key="secret-key-1234"))

    service.update_config(
        ScrapingConfigUpdate(
            api_key="************1234",
            base_url="https://new.example.com",
        )
    )
    service.update_config(ScrapingConfigUpdate(api_key=""))

    text = (tmp_path / "scraping.conf").read_text(encoding="utf-8")
    assert "api_key=secret-key-1234\n" in text
    assert "base_url=https://new.example.com\n" in text


def test_explicit_null_clears_directory_id(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.update_config(ScrapingConfigUpdate(directory_id=4))

    public = service.update_config(ScrapingConfigUpdate(directory_id=None))

    assert public["directory_id"] is None
    assert "directory_id=\n" in (tmp_path / "scraping.conf").read_text(encoding="utf-8")


def test_numeric_api_key_stays_a_string(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.update_config(ScrapingConfigUpdate(api_key="12345678"))

    assert service.get_raw_config()["api_key"] == "12345678"


def test_invalid_base_url_is_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(ValueError, match="http://"):
        service.update_config(ScrapingConfigUpdate(base_url="ftp://example.com"))


def test_invalid_persisted_values_fall_back_to_defaults(tmp_path: Path) -> None:
    (tmp_path / "scraping.conf").write_text(
        "base_url=https://example.com\n"
        "api_key=abc\n"
        "directory_id=0\n"
        "trigger_delay_seconds=1\n",
        encoding="utf-8",
    )

    raw = _service(tmp_path).get_raw_config()

    assert raw["base_url"] == "https://example.com"
    assert raw["api_key"] == "abc"
    assert raw["directory_id"] is None
    assert raw["trigger_delay_seconds"] == 30


def test_metadata_sources_round_trip_and_fallback(tmp_path: Path) -> None:
    service = _service(tmp_path)
    public = service.update_config(
        ScrapingConfigUpdate(
            scrape_root=str(tmp_path),
            media_root="/media/",
            metatube_url="https://metatube.example",
            metadata_sources=["metatube:FANZA", "metatube:JavBus"],
        )
    )

    assert public["scrape_root"] == str(tmp_path)
    assert public["media_root"] == "/media"
    assert public["metadata_sources"] == ["metatube:FANZA", "metatube:JavBus"]
    text = (tmp_path / "scraping.conf").read_text(encoding="utf-8")
    assert 'metadata_sources=["metatube:FANZA", "metatube:JavBus"]' in text


def test_invalid_metadata_sources_are_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(ValueError, match="元数据源"):
        service.update_config(ScrapingConfigUpdate(metadata_sources=["unknown"]))


def test_invalid_persisted_metadata_sources_fall_back(tmp_path: Path) -> None:
    (tmp_path / "scraping.conf").write_text(
        'metadata_sources=["unknown"]\nmedia_root=media\n',
        encoding="utf-8",
    )
    config = _service(tmp_path).get_public_config()
    assert config["metadata_sources"] == ["metatube:JavBus", "metatube:FANZA"]
    assert config["media_root"] == "/media"


def test_saved_javdb_source_is_disabled_without_losing_other_sources(tmp_path: Path) -> None:
    (tmp_path / "scraping.conf").write_text(
        'metadata_sources=["javdb", "javbus", "fanza"]\n', encoding="utf-8",
    )
    assert _service(tmp_path).get_raw_config()["metadata_sources"] == ["metatube:JavBus", "metatube:FANZA"]


def test_legacy_task_sources_migrate_without_direct_javdb() -> None:
    assert normalize_metadata_sources(["javdb", "fanza", "javbus", "metatube:FANZA"]) == [
        "metatube:FANZA", "metatube:JavBus",
    ]


def test_direct_source_cannot_be_saved(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="不支持的元数据源"):
        _service(tmp_path).update_config(ScrapingConfigUpdate(
            metatube_url="http://127.0.0.1:2048", metadata_sources=["javbus"],
        ))


def test_metatube_connection_and_token_round_trip(tmp_path: Path) -> None:
    service = _service(tmp_path)
    public = service.update_config(ScrapingConfigUpdate(
        metatube_url="https://metatube.example/",
        metatube_token="secret-token-1234",
        metadata_sources=["metatube:FANZA", "metatube:JavBus"],
    ))
    assert public["metatube_url"] == "https://metatube.example"
    assert public["metatube_token"] == "************1234"
    assert public["metatube_token_configured"] is True
    assert service.get_raw_config()["metatube_token"] == "secret-token-1234"
    service.update_config(ScrapingConfigUpdate(metatube_token="************1234"))
    assert service.get_raw_config()["metatube_token"] == "secret-token-1234"


def test_metatube_source_requires_server_address(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="MetaTube Server 地址"):
        _service(tmp_path).update_config(ScrapingConfigUpdate(metadata_sources=["metatube:FANZA"]))


def test_scrape_root_must_be_an_existing_directory(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(ValueError, match="刮削目录"):
        service.update_config(ScrapingConfigUpdate(scrape_root=str(tmp_path / "missing")))


def test_scrape_root_rejects_filesystem_root_and_relative_paths(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(ValueError, match="刮削目录"):
        service.update_config(ScrapingConfigUpdate(scrape_root="/"))

    with pytest.raises(ValueError, match="刮削目录"):
        service.update_config(ScrapingConfigUpdate(scrape_root="relative/dir"))


def test_validate_scrape_root_rejects_filesystem_root_and_relative_paths() -> None:
    from backend.app.modules.scraping.config import validate_scrape_root

    assert validate_scrape_root({"scrape_root": "/"}) is not None
    assert validate_scrape_root({"scrape_root": "relative/dir"}) is not None
