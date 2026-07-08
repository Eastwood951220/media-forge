from __future__ import annotations

import logging
from urllib.parse import urlparse, unquote

from sqlalchemy import text

from backend.app.modules.init.database_bootstrap import bootstrap_application_database
from backend.app.modules.init.schemas import InitConfigRequest
from shared.database.session import close_postgres, connect_postgres, get_session_factory
from shared.runtime_config import read_runtime_config, runtime_config_exists

logger = logging.getLogger(__name__)


def _int_value(values: dict[str, str], key: str, default: int) -> int:
    try:
        return int(values.get(key, default))
    except (TypeError, ValueError):
        return default


def build_init_request_from_runtime_config(values: dict[str, str]) -> InitConfigRequest:
    database_url = values.get("DATABASE_URL", "")
    redis_url = values.get("REDIS_URL", "redis://localhost:6379/0")
    parsed_db = urlparse(database_url)
    parsed_redis = urlparse(redis_url)
    return InitConfigRequest(
        databaseHost=parsed_db.hostname or "localhost",
        databasePort=parsed_db.port or 5432,
        databaseName=(parsed_db.path or "/mediaforge").lstrip("/") or "mediaforge",
        databaseUser=unquote(parsed_db.username or "admin"),
        databasePassword=unquote(parsed_db.password or "admin123"),
        postgresConnectTimeout=_int_value(values, "POSTGRES_CONNECT_TIMEOUT", 5),
        postgresPoolSize=_int_value(values, "POSTGRES_POOL_SIZE", 5),
        postgresMaxOverflow=_int_value(values, "POSTGRES_MAX_OVERFLOW", 10),
        postgresMaxRetries=_int_value(values, "POSTGRES_MAX_RETRIES", 10),
        postgresRetryDelay=_int_value(values, "POSTGRES_RETRY_DELAY", 3),
        redisHost=parsed_redis.hostname or "localhost",
        redisPort=parsed_redis.port or 6379,
        redisPassword=unquote(parsed_redis.password or ""),
        redisSocketTimeout=_int_value(values, "REDIS_SOCKET_TIMEOUT", 5),
        redisConnectTimeout=_int_value(values, "REDIS_SOCKET_CONNECT_TIMEOUT", 5),
        redisMaxConnections=_int_value(values, "REDIS_MAX_CONNECTIONS", 10),
    )


def _verify_application_tables() -> None:
    factory = get_session_factory()
    with factory() as session:
        session.execute(text("SELECT 1 FROM users LIMIT 1"))
        session.execute(text("SELECT 1 FROM crawl_tasks LIMIT 1"))


def ensure_database_ready_from_runtime_config() -> bool:
    request = build_init_request_from_runtime_config(read_runtime_config())
    bootstrap_application_database(request)
    return True


def connect_or_repair_postgres() -> bool:
    if not runtime_config_exists():
        return False

    try:
        connect_postgres()
        _verify_application_tables()
        return True
    except Exception as exc:
        logger.warning("PostgreSQL startup check failed, attempting bootstrap repair: %s", exc)
        close_postgres()

    ensure_database_ready_from_runtime_config()
    connect_postgres()
    _verify_application_tables()
    return True
