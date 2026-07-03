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
