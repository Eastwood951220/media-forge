from scraper.tasks.task_utils import build_final_url, determine_source


def test_determine_source_uses_hostname_not_substring() -> None:
    assert determine_source("https://javdb.com/search?q=abc") == "javdb"
    assert determine_source("https://www.javdb.com/actors/a") == "javdb"
    assert determine_source("https://javbus.com/ABCD-123") == "javbus"
    assert determine_source("https://www.javbus.com/page/1") == "javbus"
    assert determine_source("https://example.com/javdb.com") == "unknown"


def test_build_final_url_does_not_add_javdb_params_to_javbus() -> None:
    result = build_final_url(
        "https://www.javbus.com/page/1?foo=bar",
        "detail",
        has_magnet=True,
        has_chinese_sub=True,
        sort_type=5,
        source="javbus",
    )
    assert result == "https://www.javbus.com/page/1?foo=bar"


def test_build_final_url_preserves_existing_javdb_behavior() -> None:
    result = build_final_url("https://javdb.com/search?q=abc", "search", source="javdb")
    assert "page=1" in result
    assert "sb=0" in result
