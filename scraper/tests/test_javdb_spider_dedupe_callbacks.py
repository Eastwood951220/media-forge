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


def test_incremental_threshold_stops_current_url_and_continues_next_url(monkeypatch) -> None:
    from scraper.tasks.task_schema import CrawlTask

    spider = JavdbSpider(fetcher=Fetcher())
    monkeypatch.setattr(spider_module, "MAX_LIST_PAGES", 5)
    monkeypatch.setattr(spider_module, "random_sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(spider_module, "is_security_check_page", lambda page: False)

    fetched_urls: list[str] = []

    def fake_fetch(url: str):
        fetched_urls.append(url)
        return url

    monkeypatch.setattr(spider, "fetch", fake_fetch)

    def fake_parse(page: str, source_page: int):
        if "actors/a" in page:
            return [
                {"code": f"AAA-{i:03d}", "url": f"https://javdb.com/v/aaa{i:03d}", "name": f"AAA {i:03d}"}
                for i in range(40)
            ]
        return [
            {"code": "BBB-001", "url": "https://javdb.com/v/bbb001", "name": "BBB 001"},
        ]

    monkeypatch.setattr(spider_module, "parse_search_page", fake_parse)

    created_batches: list[list[dict]] = []
    task = CrawlTask(
        name="任务",
        urls=[
            CrawlTaskUrlEntry(url="https://javdb.com/actors/a", url_type="actors"),
            CrawlTaskUrlEntry(url="https://javdb.com/actors/b", url_type="actors"),
        ],
    )

    result = spider.collect_all_detail_tasks(
        task,
        crawl_mode="incremental",
        incremental_threshold=20,
        db_check_callback=lambda codes: {code for code in codes if code.startswith("AAA-")},
        on_tasks_batch_created=created_batches.append,
    )

    assert any("actors/a" in url and "page=1" in url for url in fetched_urls)
    assert not any("actors/a" in url and "page=2" in url for url in fetched_urls)
    assert any("actors/b" in url and "page=1" in url for url in fetched_urls)
    assert [item["code"] for item in result] == ["BBB-001"]
    assert all(item[0]["code"] != "AAA-000" for item in created_batches if item)
