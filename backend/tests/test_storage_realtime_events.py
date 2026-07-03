from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs, write_storage_subtask_log


def test_storage_subtask_log_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    entry = write_storage_subtask_log("sub-1", "INFO", "hello", {"step": "prepare"})

    assert entry["message"] == "hello"
    assert read_storage_subtask_logs("sub-1")[0]["context"] == {"step": "prepare"}
