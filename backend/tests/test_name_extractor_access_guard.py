import pytest
from fastapi import HTTPException
from scrapling.parser import Adaptor

from backend.app.modules.crawler.tasks.name_extractor import extract_task_name
from backend.app.schemas.crawl_task import ExtractNameRequest
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher


class FakePage:
    def __init__(self, text: str = "", status_code: int | None = None):
        self.text = text
        self.status_code = status_code


def test_extract_javdb_name_raises_for_403(monkeypatch) -> None:
    monkeypatch.setattr(
        ScraplingFetcher,
        "get",
        lambda self, url, **kwargs: FakePage("Forbidden", status_code=403),
    )

    with pytest.raises(HTTPException) as exc:
        extract_task_name(
            ExtractNameRequest(url="https://javdb.com/actors/8VGXO", url_type="actors")
        )

    assert exc.value.status_code == 429
    assert "403" in exc.value.detail
    assert "Cookie" in exc.value.detail


def test_extract_javdb_name_raises_for_empty_normal_page(monkeypatch) -> None:
    page = Adaptor("<html><body>normal but no section</body></html>")
    setattr(page, "status_code", 200)
    monkeypatch.setattr(
        ScraplingFetcher,
        "get",
        lambda self, url, **kwargs: page,
    )

    with pytest.raises(HTTPException) as exc:
        extract_task_name(
            ExtractNameRequest(url="https://javdb.com/actors/8VGXO", url_type="actors")
        )

    assert exc.value.status_code == 502
    assert "未解析到名称" in exc.value.detail


def test_extract_javdb_name_still_returns_actor_name(monkeypatch) -> None:
    page = Adaptor(
        """
        <section>
          <div class="actor-section-name">波多野結衣, Hatano Yui</div>
        </section>
        """
    )

    monkeypatch.setattr(ScraplingFetcher, "get", lambda self, url, **kwargs: page)

    name = extract_task_name(
        ExtractNameRequest(url="https://javdb.com/actors/8VGXO", url_type="actors")
    )

    assert name == "波多野結衣"
