import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    app_name: str = field(
        default_factory=lambda: os.getenv("APP_NAME", "Media Forge")
    )
    app_version: str = field(
        default_factory=lambda: os.getenv("APP_VERSION", "0.1.0")
    )
    secret_key: str = field(
        default_factory=lambda: os.getenv(
            "SECRET_KEY",
            "change-me-in-production-use-a-random-secret-key",
        )
    )
    access_token_expire_minutes: int = field(
        default_factory=lambda: int(
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080")
        )
    )
    log_dir: str = field(
        default_factory=lambda: os.getenv("LOG_DIR", "data/logs")
    )
    redis_url: str = field(
        default_factory=lambda: os.getenv(
            "REDIS_URL", "redis://localhost:6379/0"
        )
    )


def get_settings() -> Settings:
    return Settings()
