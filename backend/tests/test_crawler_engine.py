from backend.app.modules.crawler.runtime.engine import CrawlCallbacks, JavdbCrawlerEngine
from scraper.tasks.task_schema import CrawlTask


class FakePipeline:
    def process_item(self, item, task_name=None, task_id=None):
        return {**item, "source_task_name": task_name, "source_task_id": task_id}


class FakeSpider:
    def __init__(self):
        self.detail_tasks = [
            {
                "code": "AAA-001",
                "url": "https://javdb.com/v/aaa001",
                "name": "AAA 001",
                "status": "completed",
                "detail": {"code": "AAA-001", "source_name": "AAA 001"},
            }
        ]

    def run_task(self, task, **kwargs):
        if kwargs.get("on_tasks_batch_created"):
            kwargs["on_tasks_batch_created"]([
                {"code": "AAA-001", "url": "https://javdb.com/v/aaa001", "name": "AAA 001"}
            ])
        if kwargs.get("on_detail_completed"):
            kwargs["on_detail_completed"](self.detail_tasks[0])
        return self.detail_tasks

    def run_detail_tasks(self, detail_tasks, **kwargs):
        for detail_task in detail_tasks:
            if kwargs.get("on_detail_completed"):
                kwargs["on_detail_completed"]({
                    **detail_task,
                    "status": "completed",
                    "detail": {"code": detail_task["code"], "source_name": detail_task["name"]},
                })
        return [{**detail_task, "status": "completed"} for detail_task in detail_tasks]


def test_crawl_task_triggers_callbacks_and_returns_result() -> None:
    batches = []
    saved = []
    logs = []
    engine = JavdbCrawlerEngine(spider_factory=lambda: FakeSpider(), pipeline_factory=lambda: FakePipeline())
    task = CrawlTask(name="任务A", urls=[])

    result = engine.crawl_task(
        task,
        task_id="task-1",
        crawl_mode="incremental",
        incremental_threshold=3,
        callbacks=CrawlCallbacks(
            on_tasks_batch_created=batches.append,
            on_item_saved=lambda task_info, item_data: saved.append((task_info, item_data)),
            log_callback=lambda message, level="INFO": logs.append((level, message)),
        ),
    )

    assert result["task_name"] == "任务A"
    assert result["total_tasks"] == 1
    assert batches[0][0]["code"] == "AAA-001"
    assert saved[0][1]["source_task_id"] == "task-1"
    assert any("详情完成" in message for _level, message in logs)


def test_crawl_detail_tasks_supports_restart_path() -> None:
    saved = []
    engine = JavdbCrawlerEngine(spider_factory=lambda: FakeSpider(), pipeline_factory=lambda: FakePipeline())
    task = CrawlTask(name="任务B", urls=[])

    result = engine.crawl_detail_tasks(
        task,
        detail_tasks=[{"code": "BBB-001", "url": "https://javdb.com/v/bbb001", "name": "BBB 001"}],
        task_id="task-2",
        callbacks=CrawlCallbacks(
            on_item_saved=lambda task_info, item_data: saved.append((task_info, item_data)),
        ),
    )

    assert result["total_tasks"] == 1
    assert saved[0][0]["code"] == "BBB-001"
    assert saved[0][1]["code"] == "BBB-001"


def test_crawl_task_returns_stopped_flag() -> None:
    engine = JavdbCrawlerEngine(spider_factory=lambda: FakeSpider(), pipeline_factory=lambda: FakePipeline())
    task = CrawlTask(name="任务C", urls=[])

    result = engine.crawl_task(
        task,
        task_id="task-3",
        crawl_mode="full",
        incremental_threshold=0,
        callbacks=CrawlCallbacks(stop_check=lambda: True),
    )

    assert result["stopped"] is True
