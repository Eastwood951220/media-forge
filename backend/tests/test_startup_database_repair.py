from __future__ import annotations

from unittest.mock import Mock


class SessionContext:
    def __init__(self) -> None:
        self.statements: list[object] = []

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None

    def execute(self, statement):
        self.statements.append(statement)
        return None


def test_connect_or_repair_postgres_returns_false_without_runtime_config(monkeypatch) -> None:
    from backend.app import startup_database

    monkeypatch.setattr(startup_database, "runtime_config_exists", lambda: False)

    assert startup_database.connect_or_repair_postgres() is False


def test_connect_or_repair_postgres_connects_without_repair(monkeypatch) -> None:
    from backend.app import startup_database

    connect = Mock()
    bootstrap = Mock()
    monkeypatch.setattr(startup_database, "runtime_config_exists", lambda: True)
    monkeypatch.setattr(startup_database, "connect_postgres", connect)
    monkeypatch.setattr(startup_database, "get_session_factory", lambda: SessionContext)
    monkeypatch.setattr(startup_database, "bootstrap_application_database", bootstrap)

    assert startup_database.connect_or_repair_postgres() is True
    assert connect.call_count == 1
    assert bootstrap.call_count == 0


def test_connect_or_repair_postgres_bootstraps_after_connect_failure(monkeypatch) -> None:
    from backend.app import startup_database

    connect = Mock(side_effect=[RuntimeError("database does not exist"), None])
    bootstrap = Mock()
    monkeypatch.setattr(startup_database, "runtime_config_exists", lambda: True)
    monkeypatch.setattr(startup_database, "connect_postgres", connect)
    monkeypatch.setattr(startup_database, "close_postgres", Mock())
    monkeypatch.setattr(startup_database, "get_session_factory", lambda: SessionContext)
    monkeypatch.setattr(startup_database, "read_runtime_config", lambda: {
        "DATABASE_URL": "postgresql+asyncpg://admin:secret@localhost:54329/mediaforge",
        "REDIS_URL": "redis://localhost:6379/0",
    })
    monkeypatch.setattr(startup_database, "bootstrap_application_database", bootstrap)

    assert startup_database.connect_or_repair_postgres() is True
    assert connect.call_count == 2
    assert bootstrap.call_count == 1
    assert bootstrap.call_args.args[0].databaseName == "mediaforge"


def test_connect_or_repair_postgres_bootstraps_after_table_check_failure(monkeypatch) -> None:
    from backend.app import startup_database

    connect = Mock()
    bootstrap = Mock()
    verify = Mock(side_effect=[RuntimeError("relation users does not exist"), None])

    monkeypatch.setattr(startup_database, "runtime_config_exists", lambda: True)
    monkeypatch.setattr(startup_database, "connect_postgres", connect)
    monkeypatch.setattr(startup_database, "close_postgres", Mock())
    monkeypatch.setattr(startup_database, "_verify_application_tables", verify)
    monkeypatch.setattr(startup_database, "read_runtime_config", lambda: {
        "DATABASE_URL": "postgresql+asyncpg://admin:secret@localhost:54329/mediaforge",
        "REDIS_URL": "redis://localhost:6379/0",
    })
    monkeypatch.setattr(startup_database, "bootstrap_application_database", bootstrap)

    assert startup_database.connect_or_repair_postgres() is True
    assert bootstrap.call_count == 1
