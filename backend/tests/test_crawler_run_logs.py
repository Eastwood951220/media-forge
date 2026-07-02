from backend.app.modules.crawler.runs import logs as run_logs


def test_run_logs_append_load_and_delete(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run_logs, "RUN_LOG_DIR", str(tmp_path))

    entry = run_logs.build_run_log("INFO", "任务开始执行")
    run_logs.append_run_log("run-1", entry)

    loaded = run_logs.load_run_logs("run-1")
    assert loaded == [entry]

    assert run_logs.delete_run_logs("run-1") is True
    assert run_logs.load_run_logs("run-1") == []
    assert run_logs.delete_run_logs("run-1") is False


def test_run_log_entry_has_expected_shape() -> None:
    entry = run_logs.build_run_log("WARNING", "入库失败", code="AAA-001")

    assert entry["level"] == "WARNING"
    assert entry["message"] == "入库失败"
    assert entry["component"] == "crawler.run"
    assert entry["event"] == "run_log"
    assert entry["context"] == {"code": "AAA-001"}
    assert isinstance(entry["timestamp"], str)
