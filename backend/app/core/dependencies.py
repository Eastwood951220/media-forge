from collections.abc import Generator
from typing import Annotated

import redis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import decode_access_token
from backend.app.models.user import User
from backend.app.modules.storage.config.service import StorageConfigService
from backend.app.repositories.user import UserRepository
from shared.database.session import get_session
from shared.integrations.storage_providers.clouddrive2.factory import CloudDriveClientFactory

security_scheme = HTTPBearer()


# -- Database --


def get_db() -> Generator[Session, None, None]:
    yield from get_session()


# -- Redis --


_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def close_redis() -> None:
    global _redis_client
    if _redis_client:
        _redis_client.close()
        _redis_client = None


# -- Storage --


def get_clouddrive_client_factory() -> CloudDriveClientFactory:
    return CloudDriveClientFactory()


def get_storage_config_service() -> StorageConfigService:
    return StorageConfigService(provider_factory=get_clouddrive_client_factory())


# -- Auth --


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )

    user_repo = UserRepository(db)
    user = user_repo.get_by_username(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


# Re-exports for convenience
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
