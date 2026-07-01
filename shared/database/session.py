import logging
import time
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from shared.database.postgres_config import get_postgres_config

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal: sessionmaker | None = None


def connect_postgres() -> None:
    """Create engine and session factory. Called during startup."""
    global _engine, _SessionLocal

    config = get_postgres_config()
    db_url = config.database_url

    # Support both asyncpg and psycopg URLs for the sync engine
    sync_url = db_url.replace("+asyncpg", "+psycopg")

    logger.info("Connecting to PostgreSQL: %s", _mask_url(sync_url))

    last_exception = None
    for attempt in range(1, config.max_retries + 1):
        try:
            _engine = create_engine(
                sync_url,
                pool_size=config.pool_size,
                max_overflow=config.max_overflow,
                pool_pre_ping=True,
                connect_args={"connect_timeout": config.connect_timeout},
                options="-c timezone=Asia/Shanghai",
            )
            # Verify connection
            with _engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
            logger.info("PostgreSQL connected (attempt %d).", attempt)
            return
        except Exception as exc:
            last_exception = exc
            logger.warning(
                "PostgreSQL connection attempt %d/%d failed: %s",
                attempt, config.max_retries, exc,
            )
            if attempt < config.max_retries:
                time.sleep(config.retry_delay)

    raise RuntimeError(
        f"PostgreSQL connection failed after {config.max_retries} attempts"
    ) from last_exception


def get_session_factory() -> sessionmaker:
    """Get the session factory (auto-connects if not yet connected)."""
    global _SessionLocal
    if _SessionLocal is None:
        connect_postgres()
    if _SessionLocal is None:
        raise RuntimeError("Failed to create database session factory.")
    return _SessionLocal


def get_session() -> Generator[Session, None, None]:
    """Yield a database session. Auto-closes after use."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def close_postgres() -> None:
    """Dispose engine and clear globals. Called during shutdown."""
    global _engine, _SessionLocal
    if _engine:
        _engine.dispose()
        _engine = None
    _SessionLocal = None
    logger.info("PostgreSQL connection closed.")


def postgres_health_check() -> bool:
    """Return True if PostgreSQL is reachable."""
    try:
        factory = get_session_factory()
        session = factory()
        try:
            session.execute(text("SELECT 1"))
            return True
        finally:
            session.close()
    except Exception:
        return False


def _mask_url(url: str) -> str:
    """Mask password in database URL for logging."""
    if "@" in url:
        parts = url.split("@")
        prefix = parts[0].rsplit(":", 1)[0] if ":" in parts[0] else parts[0]
        return f"{prefix}:****@{parts[1]}"
    return url
