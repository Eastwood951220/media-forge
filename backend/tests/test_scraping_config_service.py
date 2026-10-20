from pathlib import Path

import pytest

from backend.app.modules.scraping.config import ScrapingConfigService
from backend.app.modules.scraping.schemas import ScrapingConfigUpdate


def _service(tmp_path: Path) -> ScrapingConfigService:
    return ScrapingConfigService(config_file=tmp_path / "scraping.conf")


def test_defaults_without_config_file(tmp_path: Path) -> None:
    assert _service(tmp_path).get_public_config() == {
        "base_url": "",
        "api_key": "",
        "api_key_configured": False,
        "directory_id": None,
        "trigger_delay_seconds": 30,
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
