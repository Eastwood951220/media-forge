import pytest

from scraper.spiders.javdb import javdb_spider as spider_module
from scraper.spiders.javdb.javdb_spider import JavdbSpider
from scraper.tasks.task_schema import CrawlTaskUrlEntry


class Fetcher:
    def get(self, url: str):
        return "<html></html>"


def test_list_phase_marks_existing_codes_skipped(monkeypatch) -> None:
    spider = JavdbSpider(fetcher=Fetcher())
    monkeypatch.setattr(spider_module, "MAX_LIST_PAGES", 1)
    monkeypatch.setattr(spider_module, "random_sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(spider_module, "is_security_check_page", lambda page: False)
    monkeypatch.setattr(
        spider_module,
        "parse_search_page",
        lambda page, source_page: [
            {"code": "AAA-030", "url": "https://javdb.com/v/aaa030", "name": "AAA 030"},
            {"code": "AAA-031", "url": "https://javdb.com/v/aaa031", "name": "AAA 031"},
        ],
    )

    created_batches = []
    result = spider.collect_detail_tasks_for_url(
        url_entry=CrawlTaskUrlEntry(url="https://javdb.com/actors/a", url_type="actors"),
        task_name="任务",
        db_check_callback=lambda codes: {"AAA-030"},
        on_tasks_batch_created=created_batches.append,
    )

    assert result[0]["status"] == "skipped"
    assert result[0]["reason"] == "already_exists"
    assert "status" not in result[1]
    assert created_batches[0][0]["code"] == "AAA-030"


def test_detail_phase_skips_existing_code_without_fetching(monkeypatch) -> None:
    spider = JavdbSpider(fetcher=Fetcher())
    monkeypatch.setattr(spider_module, "random_sleep", lambda *args, **kwargs: None)

    def fail_fetch(url: str):
        raise AssertionError("fetch should not be called for existing code")

    monkeypatch.setattr(spider, "fetch", fail_fetch)
    already_exists = []

    result = spider.run_detail_tasks(
        [{"code": "AAA-040", "url": "https://javdb.com/v/aaa040", "name": "AAA 040"}],
        task_name="任务",
        on_detail_check_callback=lambda code: code == "AAA-040",
        on_item_already_exists=already_exists.append,
    )

    assert result[0]["status"] == "skipped"
    assert result[0]["reason"] == "already_exists"
    assert already_exists[0]["code"] == "AAA-040"
