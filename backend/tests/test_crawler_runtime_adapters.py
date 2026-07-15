from datetime import datetime
import uuid

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


def test_incremental_threshold_ignores_env_when_conf_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("INCREMENTAL_EXIST_THRESHOLD", "99")

    assert read_incremental_threshold_from_conf(tmp_path) == 0


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


def test_to_scraper_task_filters_selected_url_ids_and_preserves_task_order(admin_user) -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    third_id = uuid.uuid4()
    task = CrawlTask(name="任务C", owner_id=admin_user.id, is_skip=False)
    task.urls = [
        CrawlTaskUrl(id=first_id, position=0, url="https://javdb.com/actors/a", url_type="actors", final_url="https://javdb.com/actors/a", source="javdb"),
        CrawlTaskUrl(id=second_id, position=1, url="https://javdb.com/tags/b", url_type="tags", final_url="https://javdb.com/tags/b", source="javdb"),
        CrawlTaskUrl(id=third_id, position=2, url="https://javdb.com/series/c", url_type="series", final_url="https://javdb.com/series/c", source="javdb"),
    ]

    converted = to_scraper_task(task, selected_url_ids=[third_id, first_id])

    assert [url.url for url in converted.urls] == [
        "https://javdb.com/actors/a",
        "https://javdb.com/series/c",
    ]


def test_to_scraper_task_raises_when_subset_matches_no_urls(admin_user) -> None:
    task = CrawlTask(name="任务D", owner_id=admin_user.id, is_skip=False)
    task.urls = [
        CrawlTaskUrl(id=uuid.uuid4(), position=0, url="https://javdb.com/actors/a", url_type="actors", final_url="https://javdb.com/actors/a", source="javdb")
    ]

    try:
        to_scraper_task(task, selected_url_ids=[uuid.uuid4()])
    except ValueError as exc:
        assert str(exc) == "选择的 URL 不属于该任务"
    else:
        raise AssertionError("expected ValueError")
