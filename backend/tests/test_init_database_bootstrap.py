from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from backend.app.models.user import User
from backend.app.modules.init.database_bootstrap import (
    create_application_tables,
    import_application_models,
    seed_default_admin_user,
)
from shared.database.models.base import Base
from shared.runtime_config import (
    RuntimeConfigPaths,
    read_runtime_config,
    runtime_config_exists,
    write_runtime_config,
)


def sqlite_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_import_application_models_registers_known_tables() -> None:
    import_application_models()

    assert "users" in Base.metadata.tables
    assert "crawl_tasks" in Base.metadata.tables
    assert "crawl_task_urls" in Base.metadata.tables


def test_create_application_tables_uses_shared_metadata() -> None:
    engine = sqlite_engine()

    create_application_tables(engine)

    table_names = set(inspect(engine).get_table_names())
    assert "users" in table_names
    assert "crawl_tasks" in table_names
    assert "crawl_task_urls" in table_names


def test_seed_default_admin_user_is_idempotent() -> None:
    engine = sqlite_engine()
    create_application_tables(engine)

    first = seed_default_admin_user(engine, username="admin", password="admin123")
    second = seed_default_admin_user(engine, username="admin", password="admin123")

    assert first is True
    assert second is False

    with engine.connect() as conn:
        rows = conn.execute(User.__table__.select()).fetchall()
    assert len(rows) == 1
    assert rows[0].username == "admin"
    assert rows[0].role == "admin"


from backend.app.modules.init.router import (
    PostgresTestRequest,
    RedisTestRequest,
    test_postgres as call_test_postgres,
    test_redis as call_test_redis,
    save_config,
)
from backend.app.modules.init.schemas import InitConfigRequest


def test_save_config_uses_database_bootstrap(monkeypatch, tmp_path) -> None:
    bootstrap = Mock()
    bootstrap.return_value.async_url = "postgresql+asyncpg://admin:admin123@localhost:54329/mediaforge"
    bootstrap.return_value.sync_url = "postgresql+psycopg://admin:admin123@localhost:54329/mediaforge"
    bootstrap.return_value.maintenance_url = "postgresql+psycopg://admin:admin123@localhost:54329/postgres"
    monkeypatch.setattr("backend.app.modules.init.router.bootstrap_application_database", bootstrap)
    monkeypatch.setattr("backend.app.modules.init.router.validate_redis_connection", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))

    response = save_config(InitConfigRequest())

    assert response["code"] == 200
    assert bootstrap.call_count == 1


def test_docker_postgres_test_rejects_localhost(monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_FORGE_DOCKER", "1")

    response = call_test_postgres(PostgresTestRequest(host="localhost"))

    assert response["code"] == 200
    assert response["data"]["success"] is False
    assert "localhost/127.0.0.1 指向 Media Forge 容器自身" in response["data"]["message"]


def test_docker_redis_test_rejects_loopback_ip(monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_FORGE_DOCKER", "1")

    response = call_test_redis(RedisTestRequest(host="127.0.0.1"))

    assert response["code"] == 200
    assert response["data"]["success"] is False
    assert "localhost/127.0.0.1 指向 Media Forge 容器自身" in response["data"]["message"]


def test_docker_save_config_rejects_localhost_before_bootstrap(monkeypatch) -> None:
    bootstrap = Mock()
    monkeypatch.setenv("MEDIA_FORGE_DOCKER", "1")
    monkeypatch.setattr("backend.app.modules.init.router.bootstrap_application_database", bootstrap)

    with pytest.raises(HTTPException) as exc:
        save_config(InitConfigRequest(databaseHost="localhost", redisHost="192.168.1.20"))

    assert exc.value.status_code == 400
    assert "Docker 部署中 PostgreSQL 主机不能填写" in exc.value.detail
    assert bootstrap.call_count == 0


def test_script_imports_shared_bootstrap_functions() -> None:
    import backend.scripts.init_db as init_db

    assert init_db.create_application_tables is create_application_tables
    assert init_db.seed_default_admin_user is seed_default_admin_user


def test_create_application_tables_repairs_empty_legacy_crawler_task_tables() -> None:
    engine = sqlite_engine()
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE crawl_tasks (
                id VARCHAR PRIMARY KEY,
                created_at DATETIME NOT NULL,
                name VARCHAR(200) NOT NULL,
                urls TEXT NOT NULL,
                owner_id VARCHAR NOT NULL
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE crawl_task_urls (
                id VARCHAR PRIMARY KEY,
                task_id VARCHAR NOT NULL,
                url TEXT NOT NULL,
                legacy_required TEXT NOT NULL
            )
            """
        ))

    create_application_tables(engine)

    inspector = inspect(engine)
    task_columns = {column["name"] for column in inspector.get_columns("crawl_tasks")}
    url_columns = {column["name"] for column in inspector.get_columns("crawl_task_urls")}

    assert "urls" not in task_columns
    assert "legacy_required" not in url_columns
    assert {"status", "task_id", "total_found", "total_qualified"}.issubset(task_columns)
    assert {"position", "url_type", "final_url", "source"}.issubset(url_columns)


# -- Runtime config tests --


def test_runtime_config_paths_includes_storage_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    paths = RuntimeConfigPaths.from_env()
    assert paths.storage_file == tmp_path / "storage.conf"


def test_write_runtime_config_writes_storage_section(tmp_path) -> None:
    paths = RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
    )

    write_runtime_config({"storage": {"enabled": "true", "grpc_host": "192.168.31.10:9798"}}, paths)

    text = (tmp_path / "storage.conf").read_text(encoding="utf-8")
    assert "enabled=true\n" in text
    assert "grpc_host=192.168.31.10:9798\n" in text


def test_read_runtime_config_reads_storage_file(tmp_path) -> None:
    paths = RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
    )
    (tmp_path / "database.conf").write_text("DB_HOST=localhost\n", encoding="utf-8")
    (tmp_path / "redis.conf").write_text("REDIS_HOST=localhost\n", encoding="utf-8")
    (tmp_path / "storage.conf").write_text(
        "STORAGE_ENABLED=true\nSTORAGE_HOST=192.168.31.10\n", encoding="utf-8"
    )

    result = read_runtime_config(paths)

    assert result["DB_HOST"] == "localhost"
    assert result["REDIS_HOST"] == "localhost"
    assert result["STORAGE_ENABLED"] == "true"
    assert result["STORAGE_HOST"] == "192.168.31.10"


def test_runtime_config_exists_requires_storage_file(tmp_path) -> None:
    paths = RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
    )

    assert runtime_config_exists(paths) is False
    (tmp_path / "database.conf").write_text("DB_HOST=localhost\n", encoding="utf-8")
    assert runtime_config_exists(paths) is False
    (tmp_path / "redis.conf").write_text("REDIS_HOST=localhost\n", encoding="utf-8")
    assert runtime_config_exists(paths) is True
    (tmp_path / "storage.conf").write_text("STORAGE_ENABLED=true\n", encoding="utf-8")
    assert runtime_config_exists(paths) is True


def test_build_init_request_from_runtime_config_parses_database_and_redis_urls() -> None:
    from backend.app.startup_database import build_init_request_from_runtime_config

    request = build_init_request_from_runtime_config({
        "DATABASE_URL": "postgresql+asyncpg://admin:secret@db.example:5433/mediaforge",
        "POSTGRES_CONNECT_TIMEOUT": "7",
        "POSTGRES_POOL_SIZE": "8",
        "POSTGRES_MAX_OVERFLOW": "9",
        "POSTGRES_MAX_RETRIES": "4",
        "POSTGRES_RETRY_DELAY": "2",
        "REDIS_URL": "redis://:redispass@redis.example:6380/0",
        "REDIS_SOCKET_TIMEOUT": "11",
        "REDIS_SOCKET_CONNECT_TIMEOUT": "12",
        "REDIS_MAX_CONNECTIONS": "13",
    })

    assert request.databaseHost == "db.example"
    assert request.databasePort == 5433
    assert request.databaseName == "mediaforge"
    assert request.databaseUser == "admin"
    assert request.databasePassword == "secret"
    assert request.postgresConnectTimeout == 7
    assert request.postgresPoolSize == 8
    assert request.postgresMaxOverflow == 9
    assert request.postgresMaxRetries == 4
    assert request.postgresRetryDelay == 2
    assert request.redisHost == "redis.example"
    assert request.redisPort == 6380
    assert request.redisPassword == "redispass"
    assert request.redisSocketTimeout == 11
    assert request.redisConnectTimeout == 12
    assert request.redisMaxConnections == 13


def test_build_init_request_from_runtime_config_supports_passwordless_redis() -> None:
    from backend.app.startup_database import build_init_request_from_runtime_config

    request = build_init_request_from_runtime_config({
        "DATABASE_URL": "postgresql+asyncpg://admin:secret@localhost:54329/mediaforge",
        "REDIS_URL": "redis://localhost:6379/0",
    })

    assert request.redisHost == "localhost"
    assert request.redisPort == 6379
    assert request.redisPassword == ""
