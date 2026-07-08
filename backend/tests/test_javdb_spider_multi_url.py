from __future__ import annotations

from scraper.spiders.javdb import javdb_spider
from scraper.spiders.javdb.javdb_spider import JavdbSpider
from scraper.tasks.task_schema import CrawlTask, CrawlTaskUrlEntry


class FakeFetcher:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str) -> str:
        self.urls.append(url)
        return url


def test_collect_all_detail_tasks_continues_to_next_url_after_empty_page(monkeypatch) -> None:
    fetcher = FakeFetcher()
    spider = JavdbSpider(fetcher)
    logs: list[str] = []

    monkeypatch.setattr(javdb_spider, "MAX_LIST_PAGES", 2)
    monkeypatch.setattr(javdb_spider, "random_sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(javdb_spider, "is_security_check_page", lambda _page: False)

    def fake_parse_search_page(page: str, source_page: int) -> list[dict]:
        if "actors/a" in page and source_page == 1:
            return [{"code": "AAA-001", "url": "https://javdb.com/v/aaa001", "name": "AAA 001"}]
        if "actors/a" in page and source_page == 2:
            return []
        if "tags/b" in page and source_page == 1:
            return [{"code": "BBB-001", "url": "https://javdb.com/v/bbb001", "name": "BBB 001"}]
        return []

    monkeypatch.setattr(javdb_spider, "parse_search_page", fake_parse_search_page)

    task = CrawlTask(
        name="任务",
        urls=[
            CrawlTaskUrlEntry(
                url="https://javdb.com/actors/a",
                url_type="actors",
                final_url="https://javdb.com/actors/a?page=1",
                url_name="演员A",
            ),
            CrawlTaskUrlEntry(
                url="https://javdb.com/tags/b",
                url_type="tags",
                final_url="https://javdb.com/tags/b?page=1",
                url_name="标签B",
            ),
        ],
    )

    detail_tasks = spider.collect_all_detail_tasks(task, log_callback=lambda message, _level="INFO": logs.append(message))

    assert [item["code"] for item in detail_tasks] == ["AAA-001", "BBB-001"]
    assert any("actors/a?page=1" in url for url in fetcher.urls)
    assert any("actors/a?page=2" in url for url in fetcher.urls)
    assert any("tags/b?page=1" in url for url in fetcher.urls)
    assert any("[任务][URL: 演员A] 列表页 2 无数据" in message for message in logs)
    assert any("[任务][URL: 标签B] 正在获取列表页 1/2" in message for message in logs)


def test_run_detail_tasks_logs_url_name(monkeypatch) -> None:
    fetcher = FakeFetcher()
    spider = JavdbSpider(fetcher)
    logs: list[str] = []

    monkeypatch.setattr(javdb_spider, "random_sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(javdb_spider, "is_security_check_page", lambda _page: False)
    monkeypatch.setattr(javdb_spider, "parse_detail_page", lambda _page: {"code": "AAA-001", "source_name": "AAA 001"})

    spider.run_detail_tasks(
        [
            {
                "code": "AAA-001",
                "url": "https://javdb.com/v/aaa001",
                "name": "AAA 001",
                "_task_url_name": "演员A",
            }
        ],
        task_name="任务",
        log_callback=lambda message, _level="INFO": logs.append(message),
    )

    assert any("[任务][URL: 演员A] 详情 1/1 处理中" in message for message in logs)
    assert any("[任务][URL: 演员A] 详情 1/1 完成" in message for message in logs)
