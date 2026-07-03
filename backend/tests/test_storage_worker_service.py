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
