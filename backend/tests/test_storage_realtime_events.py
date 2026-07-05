from backend.app.modules.realtime.bus import event_bus
from backend.app.modules.storage.tasks.events import publish_storage_sub_log_appended
from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs, write_storage_subtask_log


def test_storage_subtask_log_round_trip_with_step_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    entry = write_storage_subtask_log(
        "sub-1",
        "INFO",
        "执行步骤: prepare",
        {"movie_id": "movie-1"},
        step="prepare",
        step_label="准备任务",
        event="step_started",
    )

    saved = read_storage_subtask_logs("sub-1")[0]
    assert entry == saved
    assert saved["message"] == "执行步骤: prepare"
    assert saved["context"] == {"movie_id": "movie-1"}
    assert saved["step"] == "prepare"
    assert saved["step_label"] == "准备任务"
    assert saved["event"] == "step_started"


def test_publish_storage_sub_log_appended_sends_entry_to_owner() -> None:
    owner_id = "user-storage-log"
    queue = event_bus.subscribe(owner_id)
    try:
        entry = {
            "timestamp": "2026-07-04T03:41:43.132033",
            "level": "INFO",
            "message": "执行步骤: cleanup_files",
            "context": {"download_path": "/云下载/storage_sub-1"},
            "step": "cleanup_files",
            "step_label": "清理临时文件",
            "event": "step_started",
        }

        publish_storage_sub_log_appended(owner_id, "sub-1", entry)

        event = queue.get_nowait()
        assert event.event == "storage.sub.log.appended"
        assert event.scope == "storage.sub"
        assert event.owner_id == owner_id
        assert event.resource_id == "sub-1"
        assert event.payload == entry
    finally:
        event_bus.unsubscribe(owner_id, queue)


def test_delete_storage_subtask_log_removes_jsonl_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    from backend.app.modules.storage.tasks.logs import (
        delete_storage_subtask_log,
        read_storage_subtask_logs,
        write_storage_subtask_log,
    )

    write_storage_subtask_log("sub-delete-1", "INFO", "存储子任务日志", {"value": 1})

    assert read_storage_subtask_logs("sub-delete-1")[0]["message"] == "存储子任务日志"
    assert delete_storage_subtask_log("sub-delete-1") is True
    assert read_storage_subtask_logs("sub-delete-1") == []
    assert delete_storage_subtask_log("sub-delete-1") is False


def test_publish_storage_main_deleted_sends_deleted_event_to_owner() -> None:
    from backend.app.modules.realtime.bus import event_bus
    from backend.app.modules.storage.tasks.events import publish_storage_main_deleted

    owner_id = "user-storage-delete"
    queue = event_bus.subscribe(owner_id)
    try:
        publish_storage_main_deleted(owner_id, "main-delete-1")

        event = queue.get_nowait()
        assert event.event == "storage.main.deleted"
        assert event.scope == "storage.main"
        assert event.owner_id == owner_id
        assert event.resource_id == "main-delete-1"
        assert event.payload == {"id": "main-delete-1"}
    finally:
        event_bus.unsubscribe(owner_id, queue)
