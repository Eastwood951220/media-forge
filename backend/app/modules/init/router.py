import logging

from fastapi import APIRouter, HTTPException, status
from redis import Redis
from sqlalchemy import create_engine, text

from backend.app.modules.init.database_bootstrap import bootstrap_application_database
from backend.app.modules.init.schemas import InitConfigRequest, InitConfigResponse
from pydantic import BaseModel, Field
from shared.runtime_config import (
    load_runtime_config,
    runtime_config_exists,
    write_runtime_config,
)
from shared.schemas.common import success

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/init", tags=["init"])


class ConnectionTestResult(BaseModel):
    success: bool
    message: str


class PostgresTestRequest(BaseModel):
    host: str = Field(default="localhost", min_length=1)
    port: int = Field(default=54329, ge=1, le=65535)
    database: str = Field(default="mediaforge", min_length=1)
    user: str = Field(default="admin", min_length=1)
    password: str = Field(default="admin123")
    connect_timeout: int = Field(default=5, ge=1, le=60)


class RedisTestRequest(BaseModel):
    host: str = Field(default="localhost", min_length=1)
    port: int = Field(default=6379, ge=1, le=65535)
    password: str = Field(default="")
    socket_timeout: int = Field(default=5, ge=1, le=60)
    connect_timeout: int = Field(default=5, ge=1, le=60)


@router.post("/test-postgres")
def test_postgres(body: PostgresTestRequest) -> dict:
    # Connect to postgres maintenance DB (always exists)
    sync_url = (
        f"postgresql+psycopg://{body.user}:{body.password}"
        f"@{body.host}:{body.port}/postgres"
    )
    try:
        engine = create_engine(
            sync_url,
            connect_args={"connect_timeout": body.connect_timeout},
        )
        with engine.connect() as conn:
            conn.execute(text("SET timezone = 'Asia/Shanghai'"))
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return success(data={"success": True, "message": "PostgreSQL 连接成功"})
    except Exception as exc:
        return success(data={"success": False, "message": f"连接失败: {exc}"})


@router.post("/test-redis")
def test_redis(body: RedisTestRequest) -> dict:
    if body.password:
        redis_url = f"redis://:{body.password}@{body.host}:{body.port}/0"
    else:
        redis_url = f"redis://{body.host}:{body.port}/0"
    try:
        client = Redis.from_url(
            redis_url,
            socket_connect_timeout=body.connect_timeout,
            socket_timeout=body.socket_timeout,
            decode_responses=True,
        )
        client.ping()
        client.close()
        return success(data={"success": True, "message": "Redis 连接成功"})
    except Exception as exc:
        return success(data={"success": False, "message": f"连接失败: {exc}"})


def _get_init_status() -> InitConfigResponse:
    db_ok = runtime_config_exists()
    # For detailed status, check files individually
    from shared.runtime_config import RuntimeConfigPaths

    paths = RuntimeConfigPaths.from_env()
    db_file_ok = paths.database_file.exists()
    redis_file_ok = paths.redis_file.exists()
    return InitConfigResponse(
        initialized=db_file_ok and redis_file_ok,
        databaseConfigured=db_file_ok,
        redisConfigured=redis_file_ok,
    )


@router.get("/config")
def get_config() -> dict:
    return success(data=_get_init_status())


def build_redis_url(body: InitConfigRequest) -> str:
    if body.redisPassword:
        return f"redis://:{body.redisPassword}@{body.redisHost}:{body.redisPort}/0"
    return f"redis://{body.redisHost}:{body.redisPort}/0"


def validate_redis_connection(body: InitConfigRequest, redis_url: str) -> None:
    client = Redis.from_url(
        redis_url,
        socket_connect_timeout=body.redisConnectTimeout,
        socket_timeout=body.redisSocketTimeout,
        decode_responses=True,
    )
    try:
        client.ping()
    finally:
        client.close()


@router.post("/config")
def save_config(body: InitConfigRequest) -> dict:
    try:
        database_urls = bootstrap_application_database(body)
    except Exception as exc:
        logger.warning("Init: database bootstrap failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database bootstrap failed: {exc}",
        ) from exc

    redis_url = build_redis_url(body)
    try:
        validate_redis_connection(body, redis_url)
    except Exception as exc:
        logger.warning("Init: Redis validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Redis connection failed: {exc}",
        ) from exc

    write_runtime_config({
        "database": {
            "DATABASE_URL": database_urls.async_url,
            "POSTGRES_CONNECT_TIMEOUT": str(body.postgresConnectTimeout),
            "POSTGRES_POOL_SIZE": str(body.postgresPoolSize),
            "POSTGRES_MAX_OVERFLOW": str(body.postgresMaxOverflow),
            "POSTGRES_MAX_RETRIES": str(body.postgresMaxRetries),
            "POSTGRES_RETRY_DELAY": str(body.postgresRetryDelay),
        },
        "redis": {
            "REDIS_URL": redis_url,
            "REDIS_SOCKET_TIMEOUT": str(body.redisSocketTimeout),
            "REDIS_SOCKET_CONNECT_TIMEOUT": str(body.redisConnectTimeout),
            "REDIS_MAX_CONNECTIONS": str(body.redisMaxConnections),
        },
    })

    load_runtime_config(override=True)

    logger.info("Init: configuration saved and loaded.")
    return success(data=_get_init_status())
