import uuid

import pytest


def _make_parent_and_subtask(db_session, *, user_id, subtask_status="failed", main_status="completed"):
    from backend.app.models.storage_task import StorageMainTask, StorageSubTask

    main = StorageMainTask(
        alias="retry-main",
        display_name="retry-main",
        source="single",
        storage_mode="single",
        status=main_status,
        total_count=1,
        success_count=0,
        failed_count=0,
        skipped_count=0,
        created_by=user_id,
    )
    db_session.add(main)
    db_session.flush()
    subtask = StorageSubTask(
        main_task_id=main.id,
        movie_id=uuid.uuid4(),
        movie_code="AAA-001",
        movie_title="Movie",
        status=subtask_status,
        step="waiting_download",
        error_message="not found",
        storage_mode="single",
        magnet_attempts=[{"id": "old"}],
        current_magnet_url="magnet:?xt=old",
        renamed_files=[{"old": 1}],
        moved_files=[{"old": 1}],
        skipped_files=[{"old": 1}],
        result={"failed": True},
    )
    db_session.add(subtask)
    db_session.commit()
    return main, subtask


def _make_service(db_session, fake_runtime, monkeypatch):
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.storage.tasks.service import StorageTaskService

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
    return service, started


class FakeRuntime:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def enqueue_main_task(self, task_id: str) -> None:
        self.enqueued.append(task_id)

    def clear_stop(self, task_id: str) -> None:
        pass


def test_retry_failed_storage_subtask_requeues_failed_subtask_and_parent(db_session, test_user, monkeypatch) -> None:
    from backend.app.models.storage_task import StorageMainTask, StorageSubTask

    main, subtask = _make_parent_and_subtask(db_session, user_id=test_user.id)
    main.total_count = 1
    main.success_count = 0
    main.failed_count = 1
    main.skipped_count = 0
    main.error_message = "boom"
    db_session.commit()

    fake_runtime = FakeRuntime()
    service, started = _make_service(db_session, fake_runtime, monkeypatch)

    retried = service.retry_subtask(subtask.id, test_user.id)

    assert retried.status == "queued"
    assert retried.step == "prepare"
    assert retried.error_message is None
    assert retried.started_at is None
    assert retried.finished_at is None
    assert retried.magnet_attempts == []
    assert retried.current_magnet_id is None
    assert retried.current_magnet_url == ""
    assert retried.renamed_files == []
    assert retried.moved_files == []
    assert retried.skipped_files == []
    assert retried.result == {}
    assert retried.main_task.status == "queued"
    assert retried.main_task.started_at is None
    assert retried.main_task.finished_at is None
    assert retried.main_task.error_message is None
    assert retried.main_task.total_count == 1
    assert retried.main_task.success_count == 0
    assert retried.main_task.failed_count == 0
    assert retried.main_task.skipped_count == 0
    assert fake_runtime.enqueued == [str(main.id)]
    assert started == ["started"]

    persisted = db_session.get(StorageSubTask, subtask.id)
    assert persisted is not None
    assert persisted.status == "queued"
    assert db_session.get(StorageMainTask, main.id).status == "queued"


def test_retry_failed_storage_subtask_does_not_touch_other_subtasks(db_session, test_user, monkeypatch) -> None:
    from backend.app.models.storage_task import StorageMainTask, StorageSubTask

    main, failed_subtask = _make_parent_and_subtask(db_session, user_id=test_user.id)
    completed_subtask = StorageSubTask(
        main_task_id=main.id,
        movie_id=uuid.uuid4(),
        movie_code="BBB-002",
        movie_title="Completed Movie",
        status="completed",
        step="done",
        storage_mode="single",
        result={"ok": True},
    )
    db_session.add(completed_subtask)
    db_session.commit()

    fake_runtime = FakeRuntime()
    service, _ = _make_service(db_session, fake_runtime, monkeypatch)

    service.retry_subtask(failed_subtask.id, test_user.id)

    assert fake_runtime.enqueued == [str(main.id)]
    untouched = db_session.get(StorageSubTask, completed_subtask.id)
    assert untouched.status == "completed"
    assert untouched.step == "done"
    assert untouched.result == {"ok": True}
    db_session.refresh(main)
    assert main.total_count == 2
    assert main.success_count == 1
    assert main.failed_count == 0


def test_retry_storage_subtask_rejects_non_failed_subtask(db_session, test_user, monkeypatch) -> None:
    from backend.app.models.storage_task import StorageSubTask

    _main, completed_subtask = _make_parent_and_subtask(
        db_session,
        user_id=test_user.id,
        subtask_status="completed",
    )
    completed_subtask.status = "completed"
    db_session.commit()

    fake_runtime = FakeRuntime()
    service, _ = _make_service(db_session, fake_runtime, monkeypatch)

    with pytest.raises(ValueError, match="只能重试失败的存储子任务"):
        service.retry_subtask(completed_subtask.id, test_user.id)

    assert fake_runtime.enqueued == []
    assert db_session.get(StorageSubTask, completed_subtask.id).status == "completed"


def test_retry_storage_subtask_rejects_active_parent(db_session, test_user, monkeypatch) -> None:
    main, failed_subtask = _make_parent_and_subtask(
        db_session,
        user_id=test_user.id,
        main_status="running",
    )
    main.status = "running"
    db_session.commit()

    fake_runtime = FakeRuntime()
    service, _ = _make_service(db_session, fake_runtime, monkeypatch)

    with pytest.raises(ValueError, match="运行中的存储任务不能重试子任务"):
        service.retry_subtask(failed_subtask.id, test_user.id)

    assert fake_runtime.enqueued == []


def test_retry_storage_subtask_rejects_other_user(db_session, test_user, other_user, monkeypatch) -> None:
    main, failed_subtask = _make_parent_and_subtask(db_session, user_id=test_user.id)

    fake_runtime = FakeRuntime()
    service, _ = _make_service(db_session, fake_runtime, monkeypatch)

    with pytest.raises(LookupError, match="存储子任务不存在"):
        service.retry_subtask(failed_subtask.id, other_user.id)

    assert fake_runtime.enqueued == []


def test_retry_storage_subtask_rejects_missing_subtask(db_session, test_user, monkeypatch) -> None:
    fake_runtime = FakeRuntime()
    service, _ = _make_service(db_session, fake_runtime, monkeypatch)

    with pytest.raises(LookupError, match="存储子任务不存在"):
        service.retry_subtask(uuid.uuid4(), test_user.id)

    assert fake_runtime.enqueued == []
