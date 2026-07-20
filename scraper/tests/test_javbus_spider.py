from scrapling.parser import Adaptor

from scraper.spiders.javbus.javbus_spider import JavbusSpider
from scraper.spiders.registry import get_site_spider
from scraper.tasks.task_schema import CrawlTaskUrlEntry

LIST_PAGE_1 = """
<html><body>
<div class="item"><a class="movie-box" href="/AAA-001"><img title="AAA 001" src="x.jpg" /><date>2026-07-01</date></a></div>
<div class="item"><a class="movie-box" href="/AAA-002"><img title="AAA 002" src="x.jpg" /><date>2026-07-02</date></a></div>
<a id="next" href="https://www.javbus.com/page/2">Next</a>
</body></html>
"""

LIST_PAGE_2 = """
<html><body>
<div class="item"><a class="movie-box" href="/AAA-003"><img title="AAA 003" src="x.jpg" /><date>2026-07-03</date></a></div>
</body></html>
"""

DETAIL_PAGE = """
<html><body>
<div class="screencap"><img title="AAA 001" src="https://pics.example/cover.jpg" /></div>
<div class="col-md-3 info">
  <p><span class="header">識別碼:</span> AAA-001</p>
  <p><span class="header">發行日期:</span> 2026-07-01</p>
</div>
<script>var gid = 111; var uc = 222; var img = 'https://pics.example/cover.jpg';</script>
</body></html>
"""

AJAX_PAGE = """
<html><body>
<table>
<tr><td><a href="magnet:?xt=urn:btih:HASH1">AAA-001-A</a></td><td>1 GB<br>5 files</td><td>2026-07-01</td><td><span class="btn">HD</span></td></tr>
<tr><td><a href="magnet:?xt=urn:btih:HASH2">AAA-001-B</a></td><td>2 GB<br>10 files</td><td>2026-07-02</td><td><span class="btn">中字</span></td></tr>
</table>
</body></html>
"""


class FakeFetcher:
    def __init__(self, responses: dict[str, str]):
        self._responses = responses
        self.requested_urls: list[str] = []

    def get(self, url: str):
        self.requested_urls.append(url)
        for pattern, html in self._responses.items():
            if pattern in url:
                return Adaptor(html)
        raise ValueError(f"No response for: {url}")


def test_javbus_spider_collects_detail_tasks_with_pagination() -> None:
    fetcher = FakeFetcher({
        "/page/1": LIST_PAGE_1,
        "/page/2": LIST_PAGE_2,
    })
    spider = JavbusSpider(fetcher=fetcher)

    result = spider.collect_detail_tasks_for_url(
        url_entry=CrawlTaskUrlEntry(
            url="https://www.javbus.com/page/1",
            url_type="detail",
            source="javbus",
        ),
        task_name="test",
    )

    assert len(result) == 3
    assert result[0]["code"] == "AAA-001"
    assert result[1]["code"] == "AAA-002"
    assert result[2]["code"] == "AAA-003"
    assert all(t["_task_source"] == "javbus" for t in result)
    assert len(fetcher.requested_urls) == 2


def test_javbus_spider_does_not_read_max_list_pages(monkeypatch) -> None:
    fetcher = FakeFetcher({
        "/page/1": LIST_PAGE_1,
        "/page/2": LIST_PAGE_2,
    })
    spider = JavbusSpider(fetcher=fetcher)

    result = spider.collect_detail_tasks_for_url(
        url_entry=CrawlTaskUrlEntry(
            url="https://www.javbus.com/page/1",
            url_type="detail",
            source="javbus",
        ),
        task_name="test",
    )

    assert len(result) == 3


def test_javbus_spider_detail_task_requests_detail_and_ajax() -> None:
    fetcher = FakeFetcher({
        "AAA-001": DETAIL_PAGE,
        "uncledatoolsbyajax": AJAX_PAGE,
    })
    spider = JavbusSpider(fetcher=fetcher)

    completed = []
    result = spider.run_single_detail_task(
        {
            "url": "https://www.javbus.com/AAA-001",
            "name": "AAA 001",
            "code": "AAA-001",
            "_task_source": "javbus",
        },
        task_name="test",
        on_detail_completed=completed.append,
    )

    assert result["status"] == "completed"
    detail = result["detail"]
    assert detail["code"] == "AAA-001"
    assert detail["source"] == "javbus"
    assert len(detail["magnets"]) == 2
    assert detail["magnets"][0]["magnet"] == "magnet:?xt=urn:btih:HASH1"
    assert detail["magnets"][1]["magnet"] == "magnet:?xt=urn:btih:HASH2"
    assert len(fetcher.requested_urls) == 2


def test_javbus_spider_detail_fails_when_ajax_params_missing() -> None:
    no_ajax_html = """
    <html><body>
    <div class="screencap"><img title="No Ajax" src="https://pics.example/cover.jpg" /></div>
    </body></html>
    """
    fetcher = FakeFetcher({"NoAjax": no_ajax_html})
    spider = JavbusSpider(fetcher=fetcher)

    failed = []
    result = spider.run_single_detail_task(
        {
            "url": "https://www.javbus.com/NoAjax",
            "name": "No Ajax",
            "code": "NoAjax",
            "_task_source": "javbus",
        },
        task_name="test",
        on_detail_failed=lambda t, e: failed.append((t, e)),
    )

    assert result["status"] == "failed"
    assert "missing ajax params" in result["reason"]


def test_get_site_spider_returns_correct_types() -> None:
    fetcher = FakeFetcher({})
    assert get_site_spider("javdb", fetcher=fetcher).__class__.__name__ == "JavdbSpider"
    assert get_site_spider("javbus", fetcher=fetcher).__class__.__name__ == "JavbusSpider"


def test_get_site_spider_raises_for_unknown_source() -> None:
    fetcher = FakeFetcher({})
    try:
        get_site_spider("unknown", fetcher=fetcher)
        assert False, "Should have raised"
    except ValueError as exc:
        assert "不支持" in str(exc)
