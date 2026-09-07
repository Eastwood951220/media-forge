"""Crawler task list keyword search and latest-run summary tests (Task 1).

Keyword filtering must match task name, URL name, and URL while keeping rows
and counts task-based. List serialization must carry the latest-run summary
fields (last_run_status/last_run_at/last_run_total/last_run_failed) derived
from the newest CrawlRun per task.
"""

from datetime import datetime, timedelta, timezone

from backend.app.models.crawl_run import CrawlRun
from backend.app.modules.crawler.tasks.service import CrawlerTaskService
from backend.app.repositories.crawl_task import CrawlTaskRepository
from backend.app.schemas.crawl_task import TaskUrlEntryCreate

URL_NAME_MATCH = "https://javdb.com/actors/url-name-only"
URL_MATCH = "https://javdb.com/search?q=prestige-actress&f=all"
NO_MATCH_URL = "https://javdb.com/actors/other"


def create_task(repo, owner_id, name, url, *, url_name=None):
    return repo.create_with_urls(
        owner_id=owner_id,
        name=name,
        storage_location=name,
        is_skip=False,
        urls=[
            TaskUrlEntryCreate(
                url=url,
                url_type="search" if "search?" in url else "actors",
                url_name=url_name,
            )
        ],
    )


def test_keyword_matches_task_name_url_name_and_url_without_duplicating_rows(
    db_session, test_user
) -> None:
    repo = CrawlTaskRepository(db_session)
    task_by_name = create_task(repo, test_user.id, "Prestige cars", NO_MATCH_URL)
    task_by_url_name = create_task(
        repo, test_user.id, "Other task", URL_NAME_MATCH, url_name="Prestige URL"
    )
    task_by_url = create_task(repo, test_user.id, "Plain task", URL_MATCH, url_name="Plain URL")
    create_task(repo, test_user.id, "Unrelated", NO_MATCH_URL, url_name="Other")

    rows, has_more = repo.get_by_owner(test_user.id, page=1, size=20, keyword="prestige")

    assert has_more is False
    assert {row.id for row in rows} == {task_by_name.id, task_by_url_name.id, task_by_url.id}
    assert repo.count_by_owner(test_user.id, keyword="prestige") == 3


def test_keyword_matches_each_matching_url_row_of_one_task_only_once(db_session, test_user) -> None:
    repo = CrawlTaskRepository(db_session)
    multi_url_task = repo.create_with_urls(
        owner_id=test_user.id,
        name="Two matching urls",
        storage_location="Two prestige urls",
        is_skip=False,
        urls=[
            TaskUrlEntryCreate(url="https://javdb.com/actors/prestige-a", url_type="actors"),
            TaskUrlEntryCreate(url="https://javdb.com/actors/prestige-b", url_type="actors"),
        ],
    )
    create_task(repo, test_user.id, "Unrelated", NO_MATCH_URL)

    rows, has_more = repo.get_by_owner(test_user.id, page=1, size=20, keyword="prestige")

    assert has_more is False
    assert [row.id for row in rows] == [multi_url_task.id]
    assert repo.count_by_owner(test_user.id, keyword="prestige") == 1


def test_keyword_is_trimmed_case_insensitive_and_blank_matches_all(db_session, test_user) -> None:
    repo = CrawlTaskRepository(db_session)
    task = create_task(repo, test_user.id, "Prestige cars", NO_MATCH_URL)
    unrelated = create_task(repo, test_user.id, "Unrelated", NO_MATCH_URL)

    trimmed_rows, _ = repo.get_by_owner(test_user.id, page=1, size=20, keyword="  prestige  ")
    assert [row.id for row in trimmed_rows] == [task.id]
    assert repo.count_by_owner(test_user.id, keyword="  prestige  ") == 1

    upper_rows, _ = repo.get_by_owner(test_user.id, page=1, size=20, keyword="PRESTIGE")
    assert [row.id for row in upper_rows] == [task.id]

    # Blank keywords behave like no keyword at all.
    blank_rows, _ = repo.get_by_owner(test_user.id, page=1, size=20, keyword="   ")
    assert {row.id for row in blank_rows} == {task.id, unrelated.id}
    assert repo.count_by_owner(test_user.id, keyword="   ") == 2


def test_keyword_does_not_leak_other_owners_tasks(db_session, test_user, other_user) -> None:
    repo = CrawlTaskRepository(db_session)
    create_task(repo, other_user.id, "Prestige owned by someone else", NO_MATCH_URL)
    my_task = create_task(repo, test_user.id, "My prestige", NO_MATCH_URL)

    rows, _ = repo.get_by_owner(test_user.id, page=1, size=20, keyword="prestige")
    assert [row.id for row in rows] == [my_task.id]
    assert repo.count_by_owner(test_user.id, keyword="prestige") == 1


def test_list_tasks_includes_latest_run_summary_of_newest_run_per_task(db_session, test_user) -> None:
    service = CrawlerTaskService(db_session)
    task_a = create_task(service.repo, test_user.id, "summary-a", NO_MATCH_URL)
    task_b = create_task(service.repo, test_user.id, "summary-b", NO_MATCH_URL)
    task_c = create_task(service.repo, test_user.id, "summary-c-no-runs", NO_MATCH_URL)

    now = datetime.now(timezone.utc)
    older_failed = CrawlRun(
        task_id=task_a.id,
        task_name=task_a.name,
        status="failed",
        crawl_mode="full",
        created_at=now - timedelta(hours=2),
        result={"total": 5, "failed": 5},
    )
    newest_completed = CrawlRun(
        task_id=task_a.id,
        task_name=task_a.name,
        status="completed",
        crawl_mode="full",
        created_at=now,
        result={"total": 63, "total_failed": 3},
    )
    run_without_counts = CrawlRun(
        task_id=task_b.id,
        task_name=task_b.name,
        status="completed",
        crawl_mode="full",
        created_at=now - timedelta(hours=1),
    )
    db_session.add_all([older_failed, newest_completed, run_without_counts])
    db_session.commit()

    data = service.list_tasks(owner_id=test_user.id, page=1, size=20)
    rows_by_name = {row["name"]: row for row in data["rows"]}

    row_a = rows_by_name["summary-a"]
    assert row_a["last_run_status"] == "completed"
    assert row_a["last_run_at"] is not None
    assert (
        datetime.fromisoformat(row_a["last_run_at"]).replace(tzinfo=None)
        == newest_completed.created_at.replace(tzinfo=None)
    )
    assert row_a["last_run_total"] == 63
    assert row_a["last_run_failed"] == 3

    row_b = rows_by_name["summary-b"]
    assert row_b.get("last_run_status") == "completed"
    assert row_b.get("last_run_at") is not None
    assert row_b.get("last_run_total") is None
    assert row_b.get("last_run_failed") is None

    row_c = rows_by_name["summary-c-no-runs"]
    assert row_c.get("last_run_status") is None
    assert row_c.get("last_run_at") is None
    assert row_c.get("last_run_total") is None
    assert row_c.get("last_run_failed") is None


def test_serialize_list_item_reads_counts_from_common_result_keys(db_session, test_user) -> None:
    from backend.app.modules.crawler.tasks.serializers import serialize_task_list_item

    repo = CrawlTaskRepository(db_session)
    task = create_task(repo, test_user.id, "counts-task", NO_MATCH_URL)
    now = datetime.now(timezone.utc)

    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="completed",
        crawl_mode="full",
        created_at=now,
        result={"total_found": 40, "total_failed": 2},
    )
    db_session.add(run)
    db_session.commit()

    item = serialize_task_list_item(task, run)
    assert item.last_run_status == "completed"
    assert item.last_run_at == run.created_at
    assert item.last_run_total == 40
    assert item.last_run_failed == 2

    without_run = serialize_task_list_item(task)
    assert without_run.last_run_status is None
    assert without_run.last_run_at is None
    assert without_run.last_run_total is None
    assert without_run.last_run_failed is None
