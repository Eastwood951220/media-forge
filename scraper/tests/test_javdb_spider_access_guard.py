import pytest

from scraper.core.exceptions import AccessBlockedError
from scraper.spiders.javdb import javdb_spider as spider_module
from scraper.spiders.javdb.javdb_spider import JavdbSpider
from scraper.tasks.task_schema import CrawlTaskUrlEntry


class FakePage:
    def __init__(self, text: str = "Forbidden", status_code: int = 403):
        self.text = text
        self.status_code = status_code


class FakeFetcher:
    def __init__(self, page):
        self.page = page
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        return self.page


def test_list_collection_fails_after_blocked_retries(monkeypatch) -> None:
    from backend.app.modules.crawler.config.conf_reader import CrawlerRuntimeConfig

    monkeypatch.setattr(spider_module, "fixed_sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(spider_module, "random_sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        spider_module,
        "read_crawler_runtime_config",
        lambda: CrawlerRuntimeConfig(JAVDB_FETCH_MODE="static"),
    )

    fetcher = FakeFetcher(FakePage(status_code=403))
    spider = JavdbSpider(fetcher)
    logs: list[tuple[str, str]] = []

    with pytest.raises(AccessBlockedError) as exc:
        spider.collect_detail_tasks_for_url(
            CrawlTaskUrlEntry(
                url="https://javdb.com/actors/8VGXO",
                final_url="https://javdb.com/actors/8VGXO",
                url_type="actors",
                source="javdb",
            ),
            task_name="blocked-list",
            log_callback=lambda message, level: logs.append((message, level)),
        )

    assert fetcher.calls == 5
    assert "403" in str(exc.value)
    assert any(level == "ERROR" and "后端爬虫会话" in message for message, level in logs)


def test_detail_task_fails_after_blocked_retries(monkeypatch) -> None:
    from backend.app.modules.crawler.config.conf_reader import CrawlerRuntimeConfig

    monkeypatch.setattr(spider_module, "fixed_sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(spider_module, "random_sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        spider_module,
        "read_crawler_runtime_config",
        lambda: CrawlerRuntimeConfig(JAVDB_FETCH_MODE="static"),
    )

    fetcher = FakeFetcher(FakePage(status_code=403))
    spider = JavdbSpider(fetcher)
    failed: list[tuple[dict, str]] = []
    tasks = [{"code": "AAA-001", "name": "AAA-001", "url": "https://javdb.com/v/aaa001"}]

    result = spider.run_detail_tasks(
        tasks,
        task_name="blocked-detail",
        on_detail_failed=lambda task, reason: failed.append((task, reason)),
    )

    assert fetcher.calls == 5
    assert result[0]["status"] == "failed"
    assert "403" in result[0]["reason"]
    assert failed


def test_agent_mode_detail_403_fails_without_long_retry(monkeypatch) -> None:
    from backend.app.modules.crawler.config.conf_reader import CrawlerRuntimeConfig

    fetcher = FakeFetcher(FakePage(status_code=403))
    spider = JavdbSpider(fetcher=fetcher)
    monkeypatch.setattr(
        spider_module,
        "read_crawler_runtime_config",
        lambda: CrawlerRuntimeConfig(JAVDB_FETCH_MODE="agent", SECURITY_WAIT_SECONDS=120),
    )
    monkeypatch.setattr(spider_module, "fixed_sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(spider_module, "random_sleep", lambda *_args, **_kwargs: None)

    tasks = [{"code": "AAA-001", "name": "AAA-001", "url": "https://javdb.com/v/aaa001"}]

    result = spider.run_detail_tasks(tasks)

    assert result[0]["status"] == "failed"
    assert "Chrome 插件" in result[0]["reason"]
    assert fetcher.calls == 1
