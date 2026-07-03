import uuid

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.storage.config.schemas import StorageConfig
from backend.tests.conftest import TestingSessionLocal


def test_storage_config_has_magnet_attempt_limit() -> None:
    config = StorageConfig()
    assert config.magnet_max_attempts_per_subtask == 3


def test_storage_main_task_defaults() -> None:
    session = TestingSessionLocal()
    task = StorageMainTask(
        alias="云存储_20260704112233_0001",
        display_name="云存储_20260704112233_0001",
        source="single",
        storage_mode="single",
        status="queued",
        total_count=1,
        created_by=uuid.uuid4(),
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    assert task.success_count == 0
    assert task.failed_count == 0
    assert task.skipped_count == 0
    assert task.config_snapshot == {}
    session.close()


def test_storage_sub_task_json_defaults() -> None:
    session = TestingSessionLocal()
    main = StorageMainTask(
        alias="test",
        display_name="test",
        source="single",
        storage_mode="single",
        status="queued",
        total_count=1,
        created_by=uuid.uuid4(),
    )
    session.add(main)
    session.flush()

    subtask = StorageSubTask(
        main_task_id=main.id,
        movie_id=uuid.uuid4(),
        movie_code="ABC-123",
        movie_title="Title",
        status="queued",
        step="prepare",
        storage_mode="multiple",
    )
    session.add(subtask)
    session.commit()
    session.refresh(subtask)

    assert subtask.target_locations == []
    assert subtask.target_paths == []
    assert subtask.magnet_attempts == []
    assert subtask.result == {}
    session.close()
