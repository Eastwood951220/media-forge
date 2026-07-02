from __future__ import annotations

import importlib
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session

from backend.app.core.security import get_password_hash
from backend.app.models.user import User
from shared.database.models.base import Base

if TYPE_CHECKING:
    from backend.app.modules.init.schemas import InitConfigRequest

logger = logging.getLogger(__name__)

APPLICATION_MODEL_MODULES = (
    "backend.app.models.user",
    "backend.app.models.crawl_task",
)


@dataclass(frozen=True)
class DatabaseUrls:
    async_url: str
    sync_url: str
    maintenance_url: str


Seeder = Callable[[Engine], bool]


def import_application_models() -> None:
    for module_name in APPLICATION_MODEL_MODULES:
        importlib.import_module(module_name)


CRAWLER_TASK_TABLE_NAMES = ("crawl_task_urls", "crawl_tasks")


def _table_row_count(engine: Engine, table_name: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one())


def _column_has_server_default(column: dict) -> bool:
    return column.get("default") is not None or column.get("server_default") is not None


def _is_incompatible_table(engine: Engine, table_name: str, expected_columns: set[str]) -> bool:
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return False

    columns = inspector.get_columns(table_name)
    actual_columns = {column["name"] for column in columns}
    if not expected_columns.issubset(actual_columns):
        return True

    for column in columns:
        name = column["name"]
        if name in expected_columns:
            continue
        if column.get("nullable") is False and not _column_has_server_default(column):
            return True

    return False


def repair_empty_crawler_task_tables(engine: Engine) -> bool:
    from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl

    expected = {
        "crawl_tasks": {column.name for column in CrawlTask.__table__.columns},
        "crawl_task_urls": {column.name for column in CrawlTaskUrl.__table__.columns},
    }

    incompatible = [
        table_name
        for table_name, expected_columns in expected.items()
        if _is_incompatible_table(engine, table_name, expected_columns)
    ]
    if not incompatible:
        return False

    non_empty = [
        table_name
        for table_name in CRAWLER_TASK_TABLE_NAMES
        if inspect(engine).has_table(table_name) and _table_row_count(engine, table_name) > 0
    ]
    if non_empty:
        names = ", ".join(non_empty)
        raise RuntimeError(f"爬虫任务表结构不兼容且已有数据，无法自动重建: {names}")

    logger.warning("Rebuilding empty incompatible crawler task tables: %s", ", ".join(incompatible))
    CrawlTaskUrl.__table__.drop(bind=engine, checkfirst=True)
    CrawlTask.__table__.drop(bind=engine, checkfirst=True)
    Base.metadata.create_all(bind=engine)
    return True


def build_database_urls(body: InitConfigRequest) -> DatabaseUrls:
    credentials = (
        f"{body.databaseUser}:{body.databasePassword}"
        f"@{body.databaseHost}:{body.databasePort}"
    )
    return DatabaseUrls(
        async_url=f"postgresql+asyncpg://{credentials}/{body.databaseName}",
        sync_url=f"postgresql+psycopg://{credentials}/{body.databaseName}",
        maintenance_url=f"postgresql+psycopg://{credentials}/postgres",
    )


def add_timezone_listener(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_timezone(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("SET timezone = 'Asia/Shanghai'")
        cursor.close()


def validate_postgres_connection(maintenance_url: str, connect_timeout: int) -> None:
    engine = create_engine(
        maintenance_url,
        connect_args={"connect_timeout": connect_timeout},
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SET timezone = 'Asia/Shanghai'"))
            conn.execute(text("SELECT 1"))
    finally:
        engine.dispose()


def ensure_database_exists(
    *,
    maintenance_url: str,
    database_name: str,
    connect_timeout: int,
) -> None:
    engine = create_engine(
        maintenance_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": connect_timeout},
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SET timezone = 'Asia/Shanghai'"))
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                {"dbname": database_name},
            )
            if result.fetchone() is None:
                conn.execute(text(f'CREATE DATABASE "{database_name}"'))
                logger.info("Created database: %s", database_name)
    finally:
        engine.dispose()


def create_application_tables(engine: Engine) -> None:
    import_application_models()
    repair_empty_crawler_task_tables(engine)
    Base.metadata.create_all(bind=engine)


def seed_default_admin_user(
    engine: Engine,
    *,
    username: str = "admin",
    password: str = "admin123",
) -> bool:
    with Session(engine) as session:
        existing = session.query(User).filter(User.username == username).first()
        if existing is not None:
            logger.info("Admin user '%s' already exists. Skipping.", username)
            return False

        session.add(
            User(
                username=username,
                hashed_password=get_password_hash(password),
                role="admin",
            )
        )
        session.commit()
        logger.info("Admin user created: %s", username)
        return True


DEFAULT_SEEDERS: tuple[Seeder, ...] = (
    seed_default_admin_user,
)


def run_database_seeders(
    engine: Engine,
    seeders: Iterable[Seeder] = DEFAULT_SEEDERS,
) -> None:
    for seeder in seeders:
        seeder(engine)


def create_target_engine(sync_url: str, connect_timeout: int) -> Engine:
    engine = create_engine(
        sync_url,
        connect_args={"connect_timeout": connect_timeout},
    )
    add_timezone_listener(engine)
    return engine


def bootstrap_application_database(body: InitConfigRequest) -> DatabaseUrls:
    urls = build_database_urls(body)
    validate_postgres_connection(urls.maintenance_url, body.postgresConnectTimeout)
    ensure_database_exists(
        maintenance_url=urls.maintenance_url,
        database_name=body.databaseName,
        connect_timeout=body.postgresConnectTimeout,
    )

    target_engine = create_target_engine(urls.sync_url, body.postgresConnectTimeout)
    try:
        create_application_tables(target_engine)
        run_database_seeders(target_engine)
    finally:
        target_engine.dispose()

    return urls
