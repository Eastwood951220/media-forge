from scraper.services.movie_result import build_skipped_task_result, build_task_result
from scraper.spiders.javdb.javdb_constants import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_SKIPPED,
)
from scraper.tasks.task_schema import CrawlTask, CrawlTaskUrlEntry


def make_multi_url_task(is_skip: bool = False) -> CrawlTask:
    return CrawlTask(
        name="多 URL 任务",
        is_skip=is_skip,
        urls=[
            CrawlTaskUrlEntry(
                url="https://javdb.com/actors/QV49G",
                url_type="actors",
                source="javdb",
                final_url="https://javdb.com/actors/QV49G?page=1&t=d&sort_type=0",
                url_name="演员A",
                has_magnet=True,
                has_chinese_sub=False,
                sort_type=0,
            ),
            CrawlTaskUrlEntry(
                url="https://javdb.com/actors/8VGXO",
                url_type="actors",
                source="javdb",
                final_url="https://javdb.com/actors/8VGXO?page=1&t=d&sort_type=0",
                url_name="演员B",
                has_magnet=False,
                has_chinese_sub=True,
                sort_type=1,
            ),
        ],
    )


def test_build_task_result_removes_top_level_urls_and_items_are_task_url_results() -> None:
    detail_tasks = [
        {
            "status": TASK_STATUS_COMPLETED,
            "_task_url": "https://javdb.com/actors/QV49G",
            "_task_final_url": "https://javdb.com/actors/QV49G?page=1&t=d&sort_type=0",
        },
        {
            "status": TASK_STATUS_SKIPPED,
            "_task_url": "https://javdb.com/actors/QV49G",
            "_task_final_url": "https://javdb.com/actors/QV49G?page=1&t=d&sort_type=0",
        },
        {
            "status": TASK_STATUS_FAILED,
            "_task_url": "https://javdb.com/actors/8VGXO",
            "_task_final_url": "https://javdb.com/actors/8VGXO?page=1&t=d&sort_type=0",
        },
    ]

    result = build_task_result(
        task=make_multi_url_task(),
        detail_tasks=detail_tasks,
        saved_items=[{"code": "AAA-001"}],
        stopped=False,
    )

    assert "url" not in result
    assert "final_url" not in result
    assert "urls" not in result
    assert "final_urls" not in result
    assert "url_entries" not in result
    assert result["total_tasks"] == 3
    assert result["completed_tasks"] == 1
    assert result["failed_tasks"] == 1
    assert result["skipped_tasks"] == 1
    assert result["saved"] == 0
    assert result["items"] == [
        {
            "url": "https://javdb.com/actors/QV49G",
            "final_url": "https://javdb.com/actors/QV49G?page=1&t=d&sort_type=0",
            "url_type": "actors",
            "source": "javdb",
            "url_name": "演员A",
            "has_magnet": True,
            "has_chinese_sub": False,
            "sort_type": 0,
            "total_tasks": 2,
            "completed_tasks": 1,
            "failed_tasks": 0,
            "skipped_tasks": 1,
        },
        {
            "url": "https://javdb.com/actors/8VGXO",
            "final_url": "https://javdb.com/actors/8VGXO?page=1&t=d&sort_type=0",
            "url_type": "actors",
            "source": "javdb",
            "url_name": "演员B",
            "has_magnet": False,
            "has_chinese_sub": True,
            "sort_type": 1,
            "total_tasks": 1,
            "completed_tasks": 0,
            "failed_tasks": 1,
            "skipped_tasks": 0,
        },
    ]


def test_build_skipped_task_result_items_include_each_task_url_with_zero_counts() -> None:
    result = build_skipped_task_result(make_multi_url_task(is_skip=True))

    assert result["is_skip"] is True
    assert "url" not in result
    assert "final_url" not in result
    assert result["items"] == [
        {
            "url": "https://javdb.com/actors/QV49G",
            "final_url": "https://javdb.com/actors/QV49G?page=1&t=d&sort_type=0",
            "url_type": "actors",
            "source": "javdb",
            "url_name": "演员A",
            "has_magnet": True,
            "has_chinese_sub": False,
            "sort_type": 0,
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "skipped_tasks": 0,
        },
        {
            "url": "https://javdb.com/actors/8VGXO",
            "final_url": "https://javdb.com/actors/8VGXO?page=1&t=d&sort_type=0",
            "url_type": "actors",
            "source": "javdb",
            "url_name": "演员B",
            "has_magnet": False,
            "has_chinese_sub": True,
            "sort_type": 1,
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "skipped_tasks": 0,
        },
    ]
