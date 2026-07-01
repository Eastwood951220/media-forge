import os
from dataclasses import dataclass, field


@dataclass
class PostgresConfig:
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/mediaforge",
        )
    )
    connect_timeout: int = field(
        default_factory=lambda: int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5"))
    )
    pool_size: int = field(
        default_factory=lambda: int(os.getenv("POSTGRES_POOL_SIZE", "5"))
    )
    max_overflow: int = field(
        default_factory=lambda: int(os.getenv("POSTGRES_MAX_OVERFLOW", "10"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("POSTGRES_MAX_RETRIES", "10"))
    )
    retry_delay: int = field(
        default_factory=lambda: int(os.getenv("POSTGRES_RETRY_DELAY", "3"))
    )


def get_postgres_config() -> PostgresConfig:
    return PostgresConfig()
