import uuid

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.modules.crawler.runtime.service import CrawlerRunService
from backend.app.repositories.crawl_task import CrawlTaskRepository
from backend.app.schemas.crawl_task import TaskUrlEntryCreate


class FakeRuntime:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def enqueue_run(self, run_id: str) -> None:
        self.enqueued.append(run_id)


def make_url_entry(name: str = "演员 A") -> TaskUrlEntryCreate:
    return TaskUrlEntryCreate(
        url="https://javdb.com/actors/A?page=1",
        final_url="https://javdb.com/actors/A?page=1",
        url_type="actors",
        url_name=name,
    )


def make_task(db_session, owner_id: uuid.UUID, *, name: str, is_skip: bool = False) -> CrawlTask:
    task = CrawlTask(
        owner_id=owner_id,
        name=name,
        storage_location=name,
        is_skip=is_skip,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def test_add_with_urls_flushes_without_committing(db_session, test_user) -> None:
    repo = CrawlTaskRepository(db_session)

    task = repo.add_with_urls(
        owner_id=test_user.id,
        name="演员 A",
        storage_location="演员 A",
        is_skip=False,
        urls=[make_url_entry()],
    )

    task_id = task.id
    assert task_id is not None
    assert task.urls[0].id is not None
    db_session.rollback()
    assert db_session.get(CrawlTask, task_id) is None


def test_append_url_uses_maximum_position_plus_one(db_session, test_user) -> None:
    task = make_task(db_session, test_user.id, name="位置任务")
    task.urls = [
        CrawlTaskUrl(
            position=0,
            url="https://javdb.com/actors/first?page=1",
            final_url="https://javdb.com/actors/first?page=1",
            url_type="actors",
            source="javdb",
        ),
        CrawlTaskUrl(
            position=5,
            url="https://javdb.com/actors/last?page=1",
            final_url="https://javdb.com/actors/last?page=1",
            url_type="actors",
            source="javdb",
        ),
    ]
    db_session.commit()

    row = CrawlTaskRepository(db_session).append_url(task, make_url_entry("新增演员"))

    assert row.position == 6
    assert row.task_id == task.id


def test_get_owned_for_update_is_owner_scoped(db_session, test_user, other_user) -> None:
    task = make_task(db_session, test_user.id, name="归属任务")
    repo = CrawlTaskRepository(db_session)

    assert repo.get_owned_for_update(task.id, test_user.id).id == task.id
    assert repo.get_owned_for_update(task.id, other_user.id) is None


def test_get_enabled_dict_by_owner_excludes_disabled_and_orders_names(
    db_session,
    test_user,
    other_user,
) -> None:
    second = make_task(db_session, test_user.id, name="Task B")
    first = make_task(db_session, test_user.id, name="Task A")
    make_task(db_session, test_user.id, name="Task Disabled", is_skip=True)
    make_task(db_session, other_user.id, name="Task Foreign")

    rows = CrawlTaskRepository(db_session).get_enabled_dict_by_owner(test_user.id)

    assert rows == [
        {"id": str(first.id), "name": "Task A"},
        {"id": str(second.id), "name": "Task B"},
    ]


def test_prepare_run_and_activate_run_have_separate_boundaries(db_session, test_user) -> None:
    task = make_task(db_session, test_user.id, name="运行任务")
    runtime = FakeRuntime()
    service = CrawlerRunService(db_session, runtime)
    worker_starts: list[bool] = []
    service._ensure_worker_started = lambda: worker_starts.append(True)

    run = service.prepare_run(task, "full")

    assert run.id is not None
    assert runtime.enqueued == []
    assert worker_starts == []
    db_session.commit()
    service.activate_run(run)
    assert runtime.enqueued == [str(run.id)]
    assert worker_starts == [True]


def test_create_run_still_commits_and_enqueues_once(db_session, test_user) -> None:
    task = make_task(db_session, test_user.id, name="兼容任务")
    runtime = FakeRuntime()
    service = CrawlerRunService(db_session, runtime)
    worker_starts: list[bool] = []
    service._ensure_worker_started = lambda: worker_starts.append(True)

    run = service.create_run(task, "incremental")

    assert db_session.get(CrawlRun, run.id) is not None
    assert runtime.enqueued == [str(run.id)]
    assert worker_starts == [True]
