from backend.app.modules.scraping.config import ScrapingConfigService


def test_jellyfin_api_requires_authentication(client) -> None:
    assert client.get("/api/jellyfin/libraries").status_code == 401


def test_jellyfin_config_masks_key_and_preserves_it_on_empty_update(tmp_path) -> None:
    service = ScrapingConfigService(tmp_path / "scraping.conf")
    saved = service.update_config({
        "jellyfin_base_url": "http://jellyfin:8096/",
        "jellyfin_api_key": "secret-key-1234",
        "jellyfin_auto_refresh_enabled": True,
        "jellyfin_watch_sync_enabled": True,
        "jellyfin_watch_sync_schedule_type": "weekly",
        "jellyfin_watch_sync_time_of_day": "03:15",
        "jellyfin_watch_sync_weekdays": [0, 3],
    })
    assert saved["jellyfin_base_url"] == "http://jellyfin:8096"
    assert saved["jellyfin_api_key"] != "secret-key-1234"
    assert saved["jellyfin_api_key_configured"] is True
    assert service.get_raw_config()["jellyfin_api_key"] == "secret-key-1234"
    service.update_config({"jellyfin_api_key": ""})
    assert service.get_raw_config()["jellyfin_api_key"] == "secret-key-1234"


def test_jellyfin_config_rejects_invalid_schedule_and_url(tmp_path) -> None:
    service = ScrapingConfigService(tmp_path / "scraping.conf")
    for update in (
        {"jellyfin_base_url": "ftp://server"},
        {"jellyfin_watch_sync_enabled": True, "jellyfin_watch_sync_schedule_type": "weekly", "jellyfin_watch_sync_weekdays": []},
        {"jellyfin_watch_sync_time_of_day": "25:90"},
    ):
        try:
            service.update_config(update)
        except (ValueError, TypeError):
            pass
        else:
            raise AssertionError(f"Accepted invalid Jellyfin settings: {update}")
