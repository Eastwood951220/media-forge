from datetime import datetime

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.storage.worker.runner import cleanup_interrupted_storage_tasks
from shared.database.models.content import Movie


class FakeRuntime:
    def __init__(self) -> None:
        self.cleaned = False

    def cleanup_runtime(self) -> None:
        self.cleaned = True


def test_cleanup_interrupted_storage_tasks_marks_running_stopped(db_session, test_user):
    movie = Movie(code="ABC-123", source_name="Title")
    db_session.add(movie)
    db_session.flush()

    main = StorageMainTask(
        alias="a",
        display_name="a",
        source="single",
        storage_mode="single",
        status="running",
        total_count=1,
        created_by=test_user.id,
        started_at=datetime.now(),
    )
    sub = StorageSubTask(
        main_task=main,
        movie_id=movie.id,
        movie_code="ABC-123",
        movie_title="Title",
        status="running",
        step="cloud_download",
        storage_mode="single",
    )
    db_session.add_all([main, sub])
    db_session.commit()

    runtime = FakeRuntime()
    stopped = cleanup_interrupted_storage_tasks(db_session, runtime)

    assert stopped == 1
    assert runtime.cleaned is True
    assert main.status == "stopped"
    assert sub.status == "queued"
    assert sub.step == "prepare"


def test_process_main_task_logs_provider_creation_failure(db_session, test_user, monkeypatch, tmp_path):
    import uuid
    from backend.app.modules.storage.worker.runner import process_main_task
    from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs
    from shared.database.models.content import Movie

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    # Patch get_session_factory so process_main_task uses the test DB
    from backend.tests.conftest import TestingSessionLocal
    monkeypatch.setattr(
        "shared.database.session.get_session_factory",
        lambda: TestingSessionLocal,
    )

    movie = Movie(code="ABC-LOG", source_name="Title")
    db_session.add(movie)
    db_session.flush()

    main = StorageMainTask(
        alias="a",
        display_name="a",
        source="single",
        storage_mode="single",
        status="queued",
        total_count=1,
        created_by=test_user.id,
        config_snapshot={"download_root_folder": "/Downloads", "target_folder": "/Movies"},
    )
    sub = StorageSubTask(
        main_task=main,
        movie_id=movie.id,
        movie_code="ABC-LOG",
        movie_title="Title",
        status="queued",
        step="prepare",
        storage_mode="single",
    )
    db_session.add_all([main, sub])
    db_session.commit()

    class FakeRuntime:
        def should_stop(self, task_id: str) -> bool:
            return False

    class FailingProviderFactory:
        def create(self, config):
            raise RuntimeError("boom-provider")

    process_main_task(FakeRuntime(), FailingProviderFactory(), None, str(main.id))

    logs = read_storage_subtask_logs(str(sub.id))
    assert any("创建 CloudDrive2 客户端失败" in entry["message"] for entry in logs)


def test_worker_loop_rechecks_queue_before_stopping(monkeypatch):
    from backend.app.modules.storage.worker import runner

    class RaceRuntime:
        def __init__(self) -> None:
            self.claims = 0

        def claim_next_main_task(self):
            self.claims += 1
            if self.claims == 2:
                return "task-added-during-stop"
            return None

    processed: list[str] = []

    def fake_process_main_task(runtime, provider_factory, config_service, task_id: str) -> bool:
        processed.append(task_id)
        return True

    monkeypatch.setattr(runner, "process_main_task", fake_process_main_task)
    monkeypatch.setattr(runner, "_worker_running", True)

    runner._worker_loop(RaceRuntime(), object(), object())

    assert processed == ["task-added-during-stop"]
    assert runner._worker_running is False


def test_process_main_task_publishes_recomputed_counts_after_subtask_completion(db_session, test_user, monkeypatch):
    import uuid

    from backend.app.models.storage_task import StorageMainTask, StorageSubTask
    from backend.app.modules.realtime.bus import event_bus
    from backend.app.modules.storage.worker.runner import process_main_task
    from backend.tests.conftest import TestingSessionLocal
    from shared.database.models.content import Movie

    monkeypatch.setattr(
        "shared.database.session.get_session_factory",
        lambda: TestingSessionLocal,
    )

    movie = Movie(code="ABC-COUNT", source_name="Title")
    db_session.add(movie)
    db_session.flush()

    main = StorageMainTask(
        alias="count-task",
        display_name="count-task",
        source="single",
        storage_mode="single",
        status="queued",
        total_count=1,
        success_count=0,
        failed_count=0,
        skipped_count=0,
        created_by=test_user.id,
        config_snapshot={"download_root_folder": "/Downloads", "target_folder": "/Movies"},
    )
    sub = StorageSubTask(
        main_task=main,
        movie_id=movie.id,
        movie_code="ABC-COUNT",
        movie_title="Title",
        status="queued",
        step="prepare",
        storage_mode="single",
    )
    db_session.add_all([main, sub])
    db_session.commit()

    def fake_execute_subtask_pipeline(context):
        context.subtask.status = "completed"
        context.subtask.step = "done"

    class FakeRuntime:
        def should_stop(self, task_id: str) -> bool:
            return False

    class FakeProviderFactory:
        def create(self, config):
            return object()

    queue = event_bus.subscribe(str(test_user.id))
    try:
        monkeypatch.setattr(
            "backend.app.modules.storage.worker.steps.execute_subtask_pipeline",
            fake_execute_subtask_pipeline,
        )

        process_main_task(FakeRuntime(), FakeProviderFactory(), None, str(main.id))

        main_events = []
        while not queue.empty():
            event = queue.get_nowait()
            if event.event == "storage.main.updated" and event.resource_id == str(main.id):
                main_events.append(event.payload)
    finally:
        event_bus.unsubscribe(str(test_user.id), queue)

    running_events = [payload for payload in main_events if payload["status"] == "running"]
    assert running_events
    assert running_events[-1]["success_count"] == 1
    assert running_events[-1]["failed_count"] == 0
    assert running_events[-1]["skipped_count"] == 0


def test_process_main_task_publishes_recomputed_counts_after_provider_creation_failure(db_session, test_user, monkeypatch):
    from backend.app.models.storage_task import StorageMainTask, StorageSubTask
    from backend.app.modules.realtime.bus import event_bus
    from backend.app.modules.storage.worker.runner import process_main_task
    from backend.tests.conftest import TestingSessionLocal
    from shared.database.models.content import Movie

    monkeypatch.setattr(
        "shared.database.session.get_session_factory",
        lambda: TestingSessionLocal,
    )

    movie = Movie(code="ABC-FAIL", source_name="Title")
    db_session.add(movie)
    db_session.flush()

    main = StorageMainTask(
        alias="fail-task",
        display_name="fail-task",
        source="single",
        storage_mode="single",
        status="queued",
        total_count=1,
        success_count=0,
        failed_count=0,
        skipped_count=0,
        created_by=test_user.id,
        config_snapshot={"download_root_folder": "/Downloads", "target_folder": "/Movies"},
    )
    sub = StorageSubTask(
        main_task=main,
        movie_id=movie.id,
        movie_code="ABC-FAIL",
        movie_title="Title",
        status="queued",
        step="prepare",
        storage_mode="single",
    )
    db_session.add_all([main, sub])
    db_session.commit()

    class FakeRuntime:
        def should_stop(self, task_id: str) -> bool:
            return False

    class FailingProviderFactory:
        def create(self, config):
            raise RuntimeError("boom-provider")

    queue = event_bus.subscribe(str(test_user.id))
    try:
        process_main_task(FakeRuntime(), FailingProviderFactory(), None, str(main.id))

        main_events = []
        while not queue.empty():
            event = queue.get_nowait()
            if event.event == "storage.main.updated" and event.resource_id == str(main.id):
                main_events.append(event.payload)
    finally:
        event_bus.unsubscribe(str(test_user.id), queue)

    running_events = [payload for payload in main_events if payload["status"] == "running"]
    assert running_events
    assert running_events[-1]["success_count"] == 0
    assert running_events[-1]["failed_count"] == 1
    assert running_events[-1]["skipped_count"] == 0
