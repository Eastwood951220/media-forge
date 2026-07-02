from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from backend.app.models.user import User
from backend.app.modules.init.database_bootstrap import (
    create_application_tables,
    import_application_models,
    seed_default_admin_user,
)
from shared.database.models.base import Base


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


from unittest.mock import Mock

from backend.app.modules.init.router import save_config
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
