from datetime import datetime

from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.modules.crawler.runtime.config import read_incremental_threshold_from_conf
from backend.app.modules.crawler.runtime.results import build_task_result, summarize_detail_tasks
from backend.app.modules.crawler.runtime.task_adapter import to_scraper_task


def test_to_scraper_task_preserves_task_fields(admin_user) -> None:
    task = CrawlTask(name="任务A", owner_id=admin_user.id, is_skip=True)
    task.urls = [
        CrawlTaskUrl(
            position=2,
            url="https://javdb.com/actors/a",
            url_type="actors",
            final_url="https://javdb.com/actors/a?page=1",
            source="javdb",
            has_magnet=True,
            has_chinese_sub=True,
            sort_type=1,
            url_name="演员A",
            created_at=datetime.now(),
        )
    ]

    converted = to_scraper_task(task)

    assert converted.name == "任务A"
    assert converted.is_skip is True
    assert len(converted.urls) == 1
    assert converted.urls[0].url == "https://javdb.com/actors/a"
    assert converted.urls[0].final_url == "https://javdb.com/actors/a?page=1"
    assert converted.urls[0].has_magnet is True
    assert converted.urls[0].has_chinese_sub is True
    assert converted.urls[0].source == "javdb"
    assert converted.urls[0].url_name == "演员A"


def test_read_incremental_threshold_from_backend_runtime_config(tmp_path) -> None:
    config_dir = tmp_path / "data" / "configs"
    config_dir.mkdir(parents=True)
    (config_dir / "crawler.conf").write_text(
        "OTHER=1\nINCREMENTAL_EXIST_THRESHOLD=7\n",
        encoding="utf-8",
    )

    assert read_incremental_threshold_from_conf(tmp_path) == 7


def test_build_task_result_matches_existing_shape(admin_user) -> None:
    task = CrawlTask(name="任务B", owner_id=admin_user.id, is_skip=False)
    task.urls = [
        CrawlTaskUrl(position=0, url="https://javdb.com/tags/a", url_type="tags", final_url="https://javdb.com/tags/a?page=1", source="javdb")
    ]
    detail_tasks = [
        {"status": "completed", "_task_url": "https://javdb.com/tags/a", "_task_final_url": "https://javdb.com/tags/a?page=1"},
        {"status": "failed", "_task_url": "https://javdb.com/tags/a", "_task_final_url": "https://javdb.com/tags/a?page=1"},
        {"status": "skipped", "_task_url": "https://javdb.com/tags/a", "_task_final_url": "https://javdb.com/tags/a?page=1"},
    ]

    result = build_task_result(task, detail_tasks, saved_items=[{"code": "AAA-001"}], stopped=True)

    assert summarize_detail_tasks(detail_tasks) == {"total_tasks": 3, "completed_tasks": 1, "failed_tasks": 1, "skipped_tasks": 1}
    assert result["task_name"] == "任务B"
    assert result["stopped"] is True
    assert result["total_tasks"] == 3
    assert result["items"][0]["final_url"] == "https://javdb.com/tags/a?page=1"
