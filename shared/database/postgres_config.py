import os
from dataclasses import dataclass, field


@dataclass
class PostgresConfig:
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://admin:admin123@localhost:54329/mediaforge",
        )
    )
    pool_size: int = field(
        default_factory=lambda: int(os.getenv("POSTGRES_POOL_SIZE", "10"))
    )
    max_overflow: int = field(
        default_factory=lambda: int(os.getenv("POSTGRES_MAX_OVERFLOW", "20"))
    )


def get_postgres_config() -> PostgresConfig:
    return PostgresConfig()
