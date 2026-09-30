import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.models.crawler_agent import CrawlerAgent
from backend.app.modules.crawler.agent.auth import hash_agent_token
from backend.app.modules.crawler.runtime.service import CrawlerRunService
from backend.app.repositories.crawl_task import CrawlTaskRepository
from backend.tests.conftest import TestingSessionLocal


PAGE_ACTIONS = "/api/crawler/agent/page-actions"


class FakeRuntime:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def enqueue_run(self, run_id: str) -> None:
        self.enqueued.append(run_id)


@pytest.fixture
def agent_headers(db_session, test_user) -> dict[str, str]:
    token = "agt_page_actions"
    db_session.add(CrawlerAgent(owner_id=test_user.id, token_hash=hash_agent_token(token)))
    db_session.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def runtime(monkeypatch) -> FakeRuntime:
    value = FakeRuntime()
    monkeypatch.setattr(
        "backend.app.modules.crawler.agent.page_actions.service.get_runtime_state",
        lambda: value,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started",
        lambda _runtime: None,
    )
    return value


def make_task(db_session, owner_id: uuid.UUID, name: str, *, is_skip: bool = False) -> CrawlTask:
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


def test_task_choices_return_only_owned_enabled_tasks(
    client,
    agent_headers,
    db_session,
    test_user,
    other_user,
) -> None:
    make_task(db_session, test_user.id, "启用任务")
    make_task(db_session, test_user.id, "禁用任务", is_skip=True)
    make_task(db_session, other_user.id, "他人任务")

    response = client.get(f"{PAGE_ACTIONS}/tasks", headers=agent_headers)

    assert response.status_code == 200
    assert [row["name"] for row in response.json()["data"]] == ["启用任务"]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic invalid"},
        {"Authorization": "Bearer agt_invalid"},
    ],
)
def test_page_actions_reject_invalid_agent_token_without_leaking_it(client, headers) -> None:
    response = client.get(f"{PAGE_ACTIONS}/tasks", headers=headers)

    assert response.status_code == 401
    assert response.json()["data"] == {"reason": "invalid_agent_token"}
    assert "agt_invalid" not in response.text


def test_temporary_run_uses_selected_owned_task(
    client,
    agent_headers,
    db_session,
    test_user,
    runtime,
) -> None:
    task = make_task(db_session, test_user.id, "临时任务")

    response = client.post(
        f"{PAGE_ACTIONS}/temporary-runs",
        headers=agent_headers,
        json={"task_id": str(task.id), "detail_url": "https://javdb.com/v/abc"},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["task_id"] == str(task.id)
    assert data["crawl_mode"] == "temporary"
    assert data["accepted"] is True
    assert runtime.enqueued == [data["run_id"]]


@pytest.mark.parametrize("case", ["missing", "foreign", "disabled"])
def test_temporary_run_revalidates_owned_enabled_task(
    client,
    agent_headers,
    db_session,
    test_user,
    other_user,
    runtime,
    case,
) -> None:
    if case == "missing":
        task_id = uuid.uuid4()
    elif case == "foreign":
        task_id = make_task(db_session, other_user.id, "他人任务").id
    else:
        task_id = make_task(db_session, test_user.id, "禁用任务", is_skip=True).id

    response = client.post(
        f"{PAGE_ACTIONS}/temporary-runs",
        headers=agent_headers,
        json={"task_id": str(task_id), "detail_url": "https://javdb.com/v/abc"},
    )

    assert response.status_code in {400, 404}
    assert runtime.enqueued == []


def test_temporary_run_rejects_invalid_detail_url(
    client,
    agent_headers,
    db_session,
    test_user,
    runtime,
) -> None:
    task = make_task(db_session, test_user.id, "临时任务")

    response = client.post(
        f"{PAGE_ACTIONS}/temporary-runs",
        headers=agent_headers,
        json={"task_id": str(task.id), "detail_url": "https://javdb.com/actors/A"},
    )

    assert response.status_code == 400
    assert runtime.enqueued == []


def test_temporary_run_returns_persisted_run_when_activation_fails(
    client,
    agent_headers,
    db_session,
    test_user,
    monkeypatch,
    caplog,
) -> None:
    task = make_task(db_session, test_user.id, "临时部分成功任务")
    monkeypatch.setattr(
        CrawlerRunService,
        "activate_run",
        lambda _self, _run: (_ for _ in ()).throw(RuntimeError("agt_secret must not leak")),
    )

    response = client.post(
        f"{PAGE_ACTIONS}/temporary-runs",
        headers=agent_headers,
        json={"task_id": str(task.id), "detail_url": "https://javdb.com/v/partial"},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["accepted"] is False
    assert data["crawl_mode"] == "temporary"
    assert data["run_id"]
    assert data["runtime_error"]
    assert "agt_secret" not in response.text
    assert "agt_secret" not in caplog.text
    db_session.expire_all()
    assert db_session.get(CrawlRun, uuid.UUID(data["run_id"])) is not None


def test_quick_create_persists_normalized_url_and_full_run(
    client,
    agent_headers,
    runtime,
) -> None:
    response = client.post(
        f"{PAGE_ACTIONS}/quick-create-runs",
        headers=agent_headers,
        json={
            "name": "演员 A",
            "page_name": "演员 A 页面",
            "list_url": "https://JAVDB.com/actors/A?page=9&t=d#results",
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["crawl_mode"] == "full"
    assert data["accepted"] is True
    assert runtime.enqueued == [data["run_id"]]
    session = TestingSessionLocal()
    try:
        task = session.get(CrawlTask, uuid.UUID(data["task_id"]))
        run = session.get(CrawlRun, uuid.UUID(data["run_id"]))
        assert task.name == "演员 A"
        assert task.storage_location == "演员 A"
        assert task.is_skip is False
        assert task.urls[0].url == "https://javdb.com/actors/A?page=1&t=d"
        assert task.urls[0].final_url == task.urls[0].url
        assert task.urls[0].url_type == "actors"
        assert run.crawl_mode == "full"
        assert run.result["scope"] == "task_full"
    finally:
        session.close()


def test_quick_create_rejects_duplicate_name_without_creating_rows(
    client,
    agent_headers,
    db_session,
    test_user,
    runtime,
) -> None:
    make_task(db_session, test_user.id, "重复任务")
    before_tasks = db_session.query(CrawlTask).count()
    before_runs = db_session.query(CrawlRun).count()

    response = client.post(
        f"{PAGE_ACTIONS}/quick-create-runs",
        headers=agent_headers,
        json={
            "name": "重复任务",
            "page_name": "列表",
            "list_url": "https://javdb.com/future-list?page=4",
        },
    )

    db_session.expire_all()
    assert response.status_code == 409
    assert db_session.query(CrawlTask).count() == before_tasks
    assert db_session.query(CrawlRun).count() == before_runs
    assert runtime.enqueued == []


def test_quick_create_returns_persisted_run_when_activation_fails(
    client,
    agent_headers,
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setattr(
        CrawlerRunService,
        "activate_run",
        lambda _self, _run: (_ for _ in ()).throw(RuntimeError("agt_secret must not leak")),
    )

    response = client.post(
        f"{PAGE_ACTIONS}/quick-create-runs",
        headers=agent_headers,
        json={
            "name": "部分成功任务",
            "page_name": "未来列表",
            "list_url": "https://javdb.com/future-list?sort=desc",
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["accepted"] is False
    assert data["run_id"]
    assert data["runtime_error"]
    assert "agt_secret" not in response.text
    assert "agt_secret" not in caplog.text
    session = TestingSessionLocal()
    try:
        run = session.get(CrawlRun, uuid.UUID(data["run_id"]))
        task = session.get(CrawlTask, uuid.UUID(data["task_id"]))
        assert run is not None
        assert task.urls[0].url_type == "list"
    finally:
        session.close()


def test_add_url_reuses_equivalent_normalized_url_for_incremental_subset(
    client,
    agent_headers,
    db_session,
    test_user,
    runtime,
) -> None:
    task = make_task(db_session, test_user.id, "已有任务")

    first = client.post(
        f"{PAGE_ACTIONS}/add-url-runs",
        headers=agent_headers,
        json={
            "task_id": str(task.id),
            "page_name": "演员 A",
            "list_url": "https://javdb.com/actors/A?page=7&t=d",
        },
    )
    second = client.post(
        f"{PAGE_ACTIONS}/add-url-runs",
        headers=agent_headers,
        json={
            "task_id": str(task.id),
            "page_name": "演员 A 新名称",
            "list_url": "https://javdb.com/actors/A?t=d&page=3#top",
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    first_data = first.json()["data"]
    second_data = second.json()["data"]
    assert first_data["url_added"] is True
    assert second_data["url_added"] is False
    assert first_data["url_entry_id"] == second_data["url_entry_id"]
    assert len(runtime.enqueued) == 2
    db_session.expire_all()
    stored = db_session.query(CrawlTaskUrl).filter(CrawlTaskUrl.task_id == task.id).all()
    assert len(stored) == 1
    assert stored[0].url == "https://javdb.com/actors/A?page=1&t=d"
    runs = db_session.query(CrawlRun).filter(CrawlRun.task_id == task.id).all()
    assert len(runs) == 2
    for run in runs:
        assert run.crawl_mode == "incremental"
        assert [row["id"] for row in run.result["selected_task_urls"]] == [str(stored[0].id)]


def test_add_url_uses_owned_row_lock_lookup(
    client,
    agent_headers,
    db_session,
    test_user,
    runtime,
    monkeypatch,
) -> None:
    task = make_task(db_session, test_user.id, "锁定任务")
    original = CrawlTaskRepository.get_owned_for_update
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    def tracked(repo, task_id, owner_id):
        calls.append((task_id, owner_id))
        return original(repo, task_id, owner_id)

    monkeypatch.setattr(CrawlTaskRepository, "get_owned_for_update", tracked)

    response = client.post(
        f"{PAGE_ACTIONS}/add-url-runs",
        headers=agent_headers,
        json={
            "task_id": str(task.id),
            "page_name": "演员 A",
            "list_url": "https://javdb.com/actors/A",
        },
    )

    assert response.status_code == 201
    assert calls == [(task.id, test_user.id)]


@pytest.mark.parametrize("case", ["missing", "foreign", "disabled"])
def test_add_url_revalidates_owned_enabled_task(
    client,
    agent_headers,
    db_session,
    test_user,
    other_user,
    runtime,
    case,
) -> None:
    if case == "missing":
        task_id = uuid.uuid4()
    elif case == "foreign":
        task_id = make_task(db_session, other_user.id, "他人任务").id
    else:
        task_id = make_task(db_session, test_user.id, "禁用任务", is_skip=True).id

    response = client.post(
        f"{PAGE_ACTIONS}/add-url-runs",
        headers=agent_headers,
        json={
            "task_id": str(task_id),
            "page_name": "演员 A",
            "list_url": "https://javdb.com/actors/A",
        },
    )

    assert response.status_code in {400, 404}
    assert runtime.enqueued == []


def test_add_url_recovers_unique_collision_using_winning_row(
    client,
    agent_headers,
    db_session,
    test_user,
    runtime,
    monkeypatch,
) -> None:
    task = make_task(db_session, test_user.id, "竞态任务")
    normalized_url = "https://javdb.com/actors/A?page=1"
    original_get = CrawlTaskRepository.get_owned_for_update
    get_calls = 0

    def racing_get(repo, task_id, owner_id):
        nonlocal get_calls
        get_calls += 1
        if get_calls == 2:
            repo.session.add(
                CrawlTaskUrl(
                    task_id=task_id,
                    position=0,
                    url=normalized_url,
                    final_url=normalized_url,
                    url_type="actors",
                    source="javdb",
                    url_name="演员 A",
                )
            )
            repo.session.flush()
        return original_get(repo, task_id, owner_id)

    def collide(_repo, _task, _entry):
        raise IntegrityError("insert", {}, Exception("uq_crawl_task_urls_task_url"))

    monkeypatch.setattr(CrawlTaskRepository, "get_owned_for_update", racing_get)
    monkeypatch.setattr(CrawlTaskRepository, "append_url", collide)

    response = client.post(
        f"{PAGE_ACTIONS}/add-url-runs",
        headers=agent_headers,
        json={
            "task_id": str(task.id),
            "page_name": "演员 A",
            "list_url": "https://javdb.com/actors/A?page=8",
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["url_added"] is False
    assert get_calls == 2
    assert runtime.enqueued == [data["run_id"]]
