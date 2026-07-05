import uuid

from backend.app.models.crawl_task import CrawlTask
from shared.database.models.content import Movie, MovieMagnet


def _movie_with_source_and_magnet(db, owner_id, *, code="abc-123", location="A"):
    crawl_task = CrawlTask(name=f"task-{code}", storage_location=location, owner_id=owner_id)
    movie = Movie(code=code, source_name=f"title-{code}", source_task_ids=[crawl_task.id])
    magnet = MovieMagnet(
        movie=movie,
        magnet_url=f"magnet:?xt=urn:btih:{uuid.uuid4().hex}",
        dedupe_key=uuid.uuid4().hex,
        name=f"{code}.mp4",
        tags=["中字"],
        weight=50,
        selected=True,
    )
    db.add_all([crawl_task, movie, magnet])
    db.flush()
    movie.source_task_ids = [crawl_task.id]
    db.commit()
    return movie


def test_single_push_creates_main_and_subtask(client, db_session, auth_headers, test_user):
    movie = _movie_with_source_and_magnet(db_session, test_user.id)

    response = client.post(
        "/api/storage/tasks/push",
        json={
            "movie_id": str(movie.id),
            "storage_mode": "single",
            "selected_storage_location": "A",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["source"] == "single"
    assert payload["storage_mode"] == "single"
    assert payload["total_count"] == 1
    assert payload["skipped_count"] == 0
    assert payload["alias"].startswith("云存储_")


def test_batch_push_creates_skipped_subtask_for_missing_magnet(client, db_session, auth_headers, test_user):
    crawl_task = CrawlTask(name="task-empty", storage_location="A", owner_id=test_user.id)
    movie = Movie(code="abc-999", source_name="empty", source_task_ids=[])
    db_session.add_all([crawl_task, movie])
    db_session.flush()
    movie.source_task_ids = [crawl_task.id]
    db_session.commit()

    response = client.post(
        "/api/storage/tasks/batch",
        json={"movie_ids": [str(movie.id)], "storage_mode": "single"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total_count"] == 1
    assert payload["skipped_count"] == 1


def test_list_and_detail_storage_tasks(client, db_session, auth_headers, test_user):
    movie = _movie_with_source_and_magnet(db_session, test_user.id, code="abc-321")
    created = client.post(
        "/api/storage/tasks/push",
        json={"movie_id": str(movie.id), "storage_mode": "single", "selected_storage_location": "A"},
        headers=auth_headers,
    ).json()["data"]

    listing = client.get("/api/storage/tasks", headers=auth_headers)
    assert listing.status_code == 200
    assert listing.json()["data"]["total"] >= 1

    detail = client.get(f"/api/storage/tasks/{created['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == created["id"]

    subtasks = client.get(f"/api/storage/tasks/{created['id']}/subtasks", headers=auth_headers)
    assert subtasks.status_code == 200
    assert subtasks.json()["data"]["total"] == 1


def test_get_subtask_detail(client, db_session, auth_headers, test_user):
    movie = _movie_with_source_and_magnet(db_session, test_user.id, code="abc-654")
    created = client.post(
        "/api/storage/tasks/push",
        json={"movie_id": str(movie.id), "storage_mode": "single", "selected_storage_location": "A"},
        headers=auth_headers,
    ).json()["data"]

    subtasks_resp = client.get(f"/api/storage/tasks/{created['id']}/subtasks", headers=auth_headers)
    subtask_id = subtasks_resp.json()["data"]["rows"][0]["id"]

    detail = client.get(f"/api/storage/tasks/subtasks/{subtask_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == subtask_id
    assert detail.json()["data"]["main_task_id"] == created["id"]


def test_subtask_logs_empty(client, auth_headers):
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = client.get(f"/api/storage/tasks/subtasks/{fake_id}/logs", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_list_tasks_with_filters(client, db_session, auth_headers, test_user):
    movie = _movie_with_source_and_magnet(db_session, test_user.id, code="abc-111")
    created = client.post(
        "/api/storage/tasks/push",
        json={"movie_id": str(movie.id), "storage_mode": "single", "selected_storage_location": "A"},
        headers=auth_headers,
    ).json()["data"]

    alias = created["alias"]

    filtered = client.get(f"/api/storage/tasks?keyword={alias}", headers=auth_headers)
    assert filtered.status_code == 200
    assert filtered.json()["data"]["total"] >= 1

    by_status = client.get("/api/storage/tasks?status=queued", headers=auth_headers)
    assert by_status.status_code == 200
    assert by_status.json()["data"]["total"] >= 1

    not_found = client.get("/api/storage/tasks?keyword=nonexistent_alias_xyz", headers=auth_headers)
    assert not_found.status_code == 200
    assert not_found.json()["data"]["total"] == 0


def test_main_task_not_found(client, auth_headers):
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = client.get(f"/api/storage/tasks/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


def test_subtask_not_found(client, auth_headers):
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = client.get(f"/api/storage/tasks/subtasks/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


def test_single_push_enqueues_runtime_and_starts_worker(db_session, test_user, monkeypatch):
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.storage.tasks.schemas import StorageSinglePushRequest
    from backend.app.modules.storage.tasks.service import StorageTaskService

    movie = _movie_with_source_and_magnet(db_session, test_user.id, code="abc-queued")

    class FakeRuntime:
        def __init__(self) -> None:
            self.enqueued: list[str] = []

        def enqueue_main_task(self, task_id: str) -> None:
            self.enqueued.append(task_id)

    fake_runtime = FakeRuntime()
    started: list[str] = []

    def fake_start_worker(runtime, provider_factory, config_service):
        assert runtime is fake_runtime
        assert provider_factory is config_service.provider_factory
        started.append("started")

    monkeypatch.setattr(
        "backend.app.modules.storage.tasks.service.ensure_storage_worker_started",
        fake_start_worker,
        raising=False,
    )

    service = StorageTaskService(
        db=db_session,
        config_service=StorageConfigService(),
        runtime=fake_runtime,
    )

    main_task = service.create_single_push(
        StorageSinglePushRequest(
            movie_id=movie.id,
            storage_mode="single",
            selected_storage_location="A",
        ),
        test_user.id,
    )

    assert fake_runtime.enqueued == [str(main_task.id)]
    assert started == ["started"]


def test_delete_storage_main_task_removes_rows_and_subtask_logs(db_session, test_user, monkeypatch, tmp_path):
    from backend.app.models.storage_task import StorageMainTask, StorageSubTask
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs, write_storage_subtask_log
    from backend.app.modules.storage.tasks.service import StorageTaskService

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    movie = _movie_with_source_and_magnet(db_session, test_user.id, code="del-001")
    main = StorageMainTask(
        alias="delete-main",
        display_name="delete-main",
        source="single",
        storage_mode="single",
        status="completed",
        total_count=1,
        created_by=test_user.id,
        config_snapshot={},
    )
    db_session.add(main)
    db_session.flush()
    sub = StorageSubTask(
        main_task_id=main.id,
        movie_id=movie.id,
        movie_code="DEL-001",
        movie_title="delete movie",
        status="completed",
        step="done",
        storage_mode="single",
    )
    db_session.add(sub)
    db_session.flush()
    write_storage_subtask_log(str(sub.id), "INFO", "待删除日志", {"main_task_id": str(main.id)})
    db_session.commit()

    service = StorageTaskService(db_session, StorageConfigService())

    result = service.delete_main_task(main.id, test_user.id)

    assert result == {
        "id": str(main.id),
        "deleted_subtask_count": 1,
        "deleted_log_count": 1,
    }
    assert db_session.get(StorageMainTask, main.id) is None
    assert db_session.get(StorageSubTask, sub.id) is None
    assert read_storage_subtask_logs(str(sub.id)) == []


def test_delete_storage_main_task_rejects_active_status(db_session, test_user):
    import pytest

    from backend.app.models.storage_task import StorageMainTask
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.storage.tasks.service import StorageTaskService

    main = StorageMainTask(
        alias="active-main",
        display_name="active-main",
        source="batch",
        storage_mode="single",
        status="running",
        total_count=0,
        created_by=test_user.id,
        config_snapshot={},
    )
    db_session.add(main)
    db_session.commit()

    service = StorageTaskService(db_session, StorageConfigService())

    with pytest.raises(ValueError, match="运行中的存储任务不能删除，请先停止任务"):
        service.delete_main_task(main.id, test_user.id)

    assert db_session.get(StorageMainTask, main.id) is not None
