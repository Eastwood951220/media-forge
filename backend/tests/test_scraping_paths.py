from pathlib import Path

from backend.app.modules.scraping.paths import (
    cloud_to_local,
    code_from_folder_name,
    local_to_cloud,
    normalize_code,
)


def test_normalize_code_ignores_separators_and_case() -> None:
    assert normalize_code("abp-123") == "ABP123"
    assert normalize_code("ABP_123") == "ABP123"
    assert normalize_code(" ABP 123 ") == "ABP123"


def test_code_from_folder_name_supports_suffixes_and_titles() -> None:
    assert code_from_folder_name("ADN-784") == "ADN-784"
    assert code_from_folder_name("ADN-784 あなた、許して…。") == "ADN-784"
    assert code_from_folder_name("adn784") == "ADN-784"
    assert code_from_folder_name("ADN-784-C") == "ADN-784-C"
    assert code_from_folder_name("随机文件夹") is None


def test_cloud_to_local_and_back(tmp_path: Path) -> None:
    scrape_root = str(tmp_path)
    assert cloud_to_local(scrape_root, "/media", "/media/演员/ADN-784") == tmp_path / "演员" / "ADN-784"
    assert local_to_cloud(scrape_root, "/media", tmp_path / "演员" / "ADN-784") == "/media/演员/ADN-784"


def test_cloud_to_local_rejects_paths_outside_media_root(tmp_path: Path) -> None:
    assert cloud_to_local(str(tmp_path), "/media", "/downloads/ADN-784") is None
    assert cloud_to_local(str(tmp_path), "/media", "/media") is None
    assert local_to_cloud(str(tmp_path), "/media", "/somewhere/else") is None


def test_cloud_to_local_rejects_escaping_paths(tmp_path: Path) -> None:
    assert cloud_to_local(str(tmp_path), "/media", "/media/../etc") is None
