import logging

from fastapi import APIRouter, HTTPException, status
from redis import Redis
from sqlalchemy import create_engine, text

from backend.app.modules.init.schemas import InitConfigRequest, InitConfigResponse
from shared.runtime_config import (
    load_runtime_config,
    runtime_config_exists,
    write_runtime_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/init", tags=["init"])


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


@router.get("/config", response_model=InitConfigResponse)
def get_config() -> InitConfigResponse:
    return _get_init_status()


@router.post("/config", response_model=InitConfigResponse)
def save_config(body: InitConfigRequest) -> InitConfigResponse:
    # Build PostgreSQL URL
    db_url = (
        f"postgresql+asyncpg://{body.databaseUser}:{body.databasePassword}"
        f"@{body.databaseHost}:{body.databasePort}/{body.databaseName}"
    )
    sync_db_url = (
        f"postgresql+psycopg://{body.databaseUser}:{body.databasePassword}"
        f"@{body.databaseHost}:{body.databasePort}/{body.databaseName}"
    )

    # Build Redis URL
    if body.redisPassword:
        redis_url = f"redis://:{body.redisPassword}@{body.redisHost}:{body.redisPort}/0"
    else:
        redis_url = f"redis://{body.redisHost}:{body.redisPort}/0"

    # Validate PostgreSQL connection
    try:
        engine = create_engine(
            sync_db_url,
            connect_args={"connect_timeout": body.postgresConnectTimeout},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
    except Exception as exc:
        logger.warning("Init: PostgreSQL validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PostgreSQL connection failed: {exc}",
        ) from exc

    # Validate Redis connection
    try:
        client = Redis.from_url(
            redis_url,
            socket_connect_timeout=body.redisConnectTimeout,
            socket_timeout=body.redisSocketTimeout,
            decode_responses=True,
        )
        client.ping()
        client.close()
    except Exception as exc:
        logger.warning("Init: Redis validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Redis connection failed: {exc}",
        ) from exc

    # Write config files
    write_runtime_config({
        "database": {
            "DATABASE_URL": db_url,
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

    # Load into environment
    load_runtime_config(override=True)

    logger.info("Init: configuration saved and loaded.")
    return _get_init_status()
