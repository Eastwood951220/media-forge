import threading
from pathlib import Path
from unittest.mock import Mock

from backend.app.models.storage_task import StorageMainTask
from backend.app.modules.scraping import trigger
from backend.app.modules.scraping.strm import StrmRunResult
from backend.tests.conftest import TestingSessionLocal


class FakeRuntime:
    def __init__(self, pending: int = 0) -> None:
        self.pending = pending

    def pending_main_task_count(self) -> int:
        return self.pending


class BrokenRuntime:
    def pending_main_task_count(self) -> int:
        raise RuntimeError("redis unavailable")


def _prepare_trigger(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    (tmp_path / "scraping.conf").write_text(
        "base_url=https://example.com\n"
        "api_key=secret-key\n"
        "directory_id=4\n"
        "trigger_delay_seconds=10\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(trigger, "_sleep", lambda seconds: None)
    monkeypatch.setattr(trigger, "get_session_factory", lambda: TestingSessionLocal)
    monkeypatch.setattr(trigger, "_generation", 4)


def test_skips_when_the_worker_is_busy(monkeypatch, tmp_path: Path) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    called = Mock()
    monkeypatch.setattr(trigger, "run_strm_generation", called)

    trigger._run_after_delay(trigger._generation, 10, FakeRuntime(), lambda: False)

    called.assert_not_called()


def test_skips_when_the_redis_queue_has_tasks(monkeypatch, tmp_path: Path) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    called = Mock()
    monkeypatch.setattr(trigger, "run_strm_generation", called)

    trigger._run_after_delay(trigger._generation, 10, FakeRuntime(pending=1), lambda: True)

    called.assert_not_called()


def test_skips_when_the_database_has_pending_tasks(
    monkeypatch,
    tmp_path: Path,
    db_session,
    test_user,
    caplog,
) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    db_session.add(
        StorageMainTask(
            alias="a",
            display_name="a",
            source="single",
            storage_mode="single",
            status="queued",
            created_by=test_user.id,
        )
    )
    db_session.commit()
    called = Mock()
    monkeypatch.setattr(trigger, "run_strm_generation", called)

    with caplog.at_level("WARNING"):
        trigger._run_after_delay(trigger._generation, 10, FakeRuntime(), lambda: True)

    called.assert_not_called()
    assert "Cannot confirm storage tasks are idle" not in caplog.text


def test_skips_when_the_queue_cannot_be_verified(monkeypatch, tmp_path: Path) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    called = Mock()
    monkeypatch.setattr(trigger, "run_strm_generation", called)

    trigger._run_after_delay(trigger._generation, 10, BrokenRuntime(), lambda: True)

    called.assert_not_called()


def test_skips_a_stale_generation(monkeypatch, tmp_path: Path) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    called = Mock()
    monkeypatch.setattr(trigger, "run_strm_generation", called)

    trigger._run_after_delay(trigger._generation - 1, 10, FakeRuntime(), lambda: True)

    called.assert_not_called()


def test_runs_when_all_checks_pass(monkeypatch, tmp_path: Path) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    calls: list[dict] = []

    def fake_run(config):
        calls.append(dict(config))
        return StrmRunResult(success=True, status_code=200, message="HTTP 200")

    monkeypatch.setattr(trigger, "run_strm_generation", fake_run)

    trigger._run_after_delay(trigger._generation, 10, FakeRuntime(), lambda: True)

    assert len(calls) == 1
    assert calls[0]["base_url"] == "https://example.com"
    assert calls[0]["api_key"] == "secret-key"
    assert calls[0]["directory_id"] == 4


def test_schedule_skips_an_unconfigured_service(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(trigger, "_generation", 4)

    trigger.schedule_strm_after_storage_drain(FakeRuntime(), is_worker_idle=lambda: True)

    assert trigger._generation == 4


def test_schedule_waits_then_runs(monkeypatch, tmp_path: Path) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    finished = threading.Event()

    def fake_run(config):
        finished.set()
        return StrmRunResult(success=True, status_code=200, message="HTTP 200")

    monkeypatch.setattr(trigger, "run_strm_generation", fake_run)

    trigger.schedule_strm_after_storage_drain(FakeRuntime(), is_worker_idle=lambda: True)

    assert finished.wait(1.0) is True


def test_successful_strm_generation_schedules_scan(monkeypatch, tmp_path: Path) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    scheduled: list[dict] = []
    monkeypatch.setattr(
        trigger,
        "run_strm_generation",
        lambda config: StrmRunResult(success=True, status_code=200, message="HTTP 200"),
    )
    monkeypatch.setattr(
        trigger,
        "schedule_scan_after_strm",
        lambda config: scheduled.append(dict(config)),
    )

    trigger._run_after_delay(trigger._generation, 10, FakeRuntime(), lambda: True)

    assert len(scheduled) == 1
    assert scheduled[0]["directory_id"] == 4


def test_failed_strm_generation_does_not_schedule_scan(monkeypatch, tmp_path: Path) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    scheduled: list[dict] = []
    monkeypatch.setattr(
        trigger,
        "run_strm_generation",
        lambda config: StrmRunResult(success=False, status_code=500, message="HTTP 500: down"),
    )
    monkeypatch.setattr(
        trigger,
        "schedule_scan_after_strm",
        lambda config: scheduled.append(dict(config)),
    )

    trigger._run_after_delay(trigger._generation, 10, FakeRuntime(), lambda: True)

    assert scheduled == []


def test_failure_is_only_logged(monkeypatch, tmp_path: Path, caplog) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    monkeypatch.setattr(
        trigger,
        "run_strm_generation",
        lambda config: StrmRunResult(success=False, status_code=500, message="HTTP 500: down"),
    )

    with caplog.at_level("WARNING"):
        trigger._run_after_delay(trigger._generation, 10, FakeRuntime(), lambda: True)

    assert "STRM generation failed" in caplog.text
