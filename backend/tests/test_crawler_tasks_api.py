import pytest
from fastapi import HTTPException


def test_crawler_task_helper_modules_export_public_helpers() -> None:
    from backend.app.modules.crawler.tasks import errors, serializers, validation

    assert callable(serializers.serialize_task)
    assert callable(validation.check_urls_unique)
    assert callable(validation.ensure_delete_mode_supported)
    assert callable(errors.constraint_name_from_integrity_error)
    assert callable(errors.raise_task_integrity_error)


def test_check_urls_unique_rejects_duplicate_url() -> None:
    from types import SimpleNamespace
    from backend.app.modules.crawler.tasks.validation import check_urls_unique

    with pytest.raises(HTTPException) as exc:
        check_urls_unique([SimpleNamespace(url="https://example.test/a"), SimpleNamespace(url="https://example.test/a")])

    assert exc.value.status_code == 400
    assert "URL 重复" in exc.value.detail


def test_extract_task_name_from_search_url_without_scraper() -> None:
    from backend.app.modules.crawler.tasks.name_extractor import extract_task_name
    from backend.app.schemas.crawl_task import ExtractNameRequest

    name = extract_task_name(ExtractNameRequest(url="https://javdb.com/search?q=ABC-123&f=all", url_type="search"))

    assert name == "ABC-123"


def test_open_delete_provider_returns_empty_session_for_task_only() -> None:
    from backend.app.modules.crawler.tasks.provider import open_delete_provider

    with open_delete_provider("task_only") as provider:
        assert provider is None
