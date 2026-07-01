# Media Forge Backend FastAPI Scaffold — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold a FastAPI backend with JWT token auth, PostgreSQL 18, Redis 8 task queue, shared package — following the jav-scrapling architecture patterns.

**Architecture:** Single-file `main.py` with `lifespan` context manager. Modular routers under `app/modules/`. Repository pattern with `BaseRepository[T]`. Shared utilities (database session, models, logging) in `shared/` package. Alembic migrations. pydantic-settings configuration.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0+, Alembic, asyncpg/psycopg, Redis 5.x, python-jose (JWT), passlib (bcrypt), pydantic-settings, pytest

## Reference Source

Patterns adapted from: `/Users/eastwood/Code/PycharmProjects/jav-scrapling/`

## Global Constraints

- Python 3.12+ (matching .venv)
- Activate venv: `source /Users/eastwood/Code/PycharmProjects/media-forge/.venv/bin/activate`
- All imports use absolute paths from project root
- No `Any` type (use proper typing)
- Repository pattern for all data access
- Session management via FastAPI Depends
- Shared utilities go in `shared/` package
- CORS: `allow_origins=["*"]` (dev mode)
- JSONL structured logging

---

### Task 1: Install Python dependencies

**Files:**
- Create: `backend/requirements.txt`
- Modify: `.venv/` (pip install)

- [ ] **Step 1: Write backend/requirements.txt**

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pydantic-settings==2.7.1
SQLAlchemy>=2.0.0,<3.0.0
alembic>=1.14.0,<2.0.0
asyncpg>=0.30.0
psycopg[binary]>=3.2.0,<4.0.0
redis>=5.0.0,<6.0.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
httpx==0.28.1
python-multipart==0.0.20
```

- [ ] **Step 2: Install**

Run:
```bash
source /Users/eastwood/Code/PycharmProjects/media-forge/.venv/bin/activate
pip install -r /Users/eastwood/Code/PycharmProjects/media-forge/backend/requirements.txt
pip freeze | grep -E "fastapi|uvicorn|sqlalchemy|alembic|asyncpg|psycopg|redis|python-jose|passlib|pydantic|httpx|python-multipart" > /tmp/mf-deps-check.txt
cat /tmp/mf-deps-check.txt
```

Expected: All packages installed. Verify:
```bash
python -c "import fastapi, sqlalchemy, redis, jose, passlib; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/requirements.txt
git commit -m "chore: add backend Python dependencies"
```

---

### Task 2: Create `shared/` package — database, common, logging

**Files:**
- Create: `shared/common/__init__.py`
- Create: `shared/common/datetime.py`
- Create: `shared/database/__init__.py`
- Create: `shared/database/session.py`
- Create: `shared/database/postgres_config.py`
- Create: `shared/database/models/__init__.py`
- Create: `shared/database/models/base.py`
- Create: `shared/logging/__init__.py`
- Create: `shared/logging/jsonl.py`
- Create: `shared/logging/handlers.py`

- [ ] **Step 1: Write shared/common/__init__.py**

```python
"""Shared common utilities."""
```

- [ ] **Step 2: Write shared/common/datetime.py**

```python
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(tz=timezone.utc)
```

- [ ] **Step 3: Write shared/database/postgres_config.py**

```python
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
```

- [ ] **Step 4: Write shared/database/session.py**

```python
import logging
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

    _engine = create_engine(
        sync_url,
        pool_size=config.pool_size,
        max_overflow=config.max_overflow,
        pool_pre_ping=True,
    )

    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)

    logger.info("PostgreSQL connected successfully.")


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
```

- [ ] **Step 5: Write shared/database/models/base.py**

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """Mixin that adds a UUID primary key column."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Mixin that adds created_at and updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
        onupdate=lambda: datetime.now(tz=timezone.utc),
    )
```

- [ ] **Step 6: Write shared/database/models/__init__.py**

```python
"""SQLAlchemy models shared across backend and other packages."""

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

__all__ = ["Base", "UUIDPrimaryKeyMixin", "TimestampMixin"]
```

- [ ] **Step 7: Write shared/database/__init__.py**

```python
"""Shared database utilities."""

from shared.database.session import (
    close_postgres,
    connect_postgres,
    get_session,
    get_session_factory,
    postgres_health_check,
)
from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

__all__ = [
    "connect_postgres",
    "close_postgres",
    "get_session",
    "get_session_factory",
    "postgres_health_check",
    "Base",
    "UUIDPrimaryKeyMixin",
    "TimestampMixin",
]
```

- [ ] **Step 8: Write shared/logging/jsonl.py**

```python
"""Structured JSONL (JSON Lines) logging utilities."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


def build_log_entry(
    level: str,
    component: str,
    event: str,
    message: str,
    **context: Any,
) -> dict[str, Any]:
    """Build a structured log entry dict."""
    return {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "level": level,
        "component": component,
        "event": event,
        "message": message,
        "context": context if context else {},
    }


def append_jsonl_log(log_dir: str, filename: str, entry: dict[str, Any]) -> None:
    """Append a log entry as a JSON line to a file."""
    path = Path(log_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def load_jsonl_logs(log_dir: str, filename: str) -> list[dict[str, Any]]:
    """Load all entries from a JSONL file."""
    path = Path(log_dir) / filename
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def delete_jsonl_logs(log_dir: str, filename: str) -> None:
    """Delete a JSONL log file."""
    path = Path(log_dir) / filename
    if path.exists():
        os.remove(path)
```

- [ ] **Step 8: Write shared/logging/handlers.py**

```python
"""Python logging handler for JSONL output."""

import logging

from shared.logging.jsonl import append_jsonl_log, build_log_entry


class JSONLHandler(logging.Handler):
    """A logging.Handler that writes structured JSONL log entries to a file."""

    def __init__(self, log_dir: str, filename: str, component: str = "backend") -> None:
        super().__init__()
        self.log_dir = log_dir
        self.filename = filename
        self.component = component

    def emit(self, record: logging.LogRecord) -> None:
        entry = build_log_entry(
            level=record.levelname,
            component=self.component,
            event=record.msg,
            message=record.getMessage(),
            logger=record.name,
            exc_info=self.format(record) if record.exc_info else None,
        )
        try:
            append_jsonl_log(self.log_dir, self.filename, entry)
        except Exception:
            self.handleError(record)
```

- [ ] **Step 9: Write shared/logging/__init__.py**

```python
"""Shared structured logging."""

from shared.logging.jsonl import append_jsonl_log, build_log_entry, load_jsonl_logs
from shared.logging.handlers import JSONLHandler

__all__ = ["build_log_entry", "append_jsonl_log", "load_jsonl_logs", "JSONLHandler"]
```

- [ ] **Step 10: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add shared/common/ shared/database/ shared/logging/ shared/__init__.py
git commit -m "feat: add shared package (database, logging, common)"
```

---

### Task 3: Create backend config and core dependencies

**Files:**
- Create: `backend/app/__init__.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/dependencies.py`
- Create: `backend/app/core/security.py`

- [ ] **Step 1: Write backend/app/core/config.py**

```python
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
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
        )
    )
    log_dir: str = field(
        default_factory=lambda: os.getenv("LOG_DIR", "logs")
    )
    redis_url: str = field(
        default_factory=lambda: os.getenv(
            "REDIS_URL", "redis://localhost:6379/0"
        )
    )


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 2: Write backend/app/core/security.py**

```python
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

settings = get_settings()

ALGORITHM = "HS256"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(tz=timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
```

- [ ] **Step 3: Write backend/app/core/dependencies.py**

```python
from collections.abc import Generator
from typing import Annotated

import redis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.user import User
from backend.app.repositories.user import UserRepository
from backend.app.core.security import decode_access_token
from shared.database.session import get_session

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
```

- [ ] **Step 4: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/__init__.py backend/app/core/
git commit -m "feat: add backend config, security, and dependencies"
```

---

### Task 4: Create User model, schema, and repository

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/schemas/user.py`
- Create: `backend/app/repositories/__init__.py`
- Create: `backend/app/repositories/base.py`
- Create: `backend/app/repositories/user.py`

- [ ] **Step 1: Write backend/app/models/user.py**

```python
import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="user")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"
```

- [ ] **Step 2: Write backend/app/schemas/auth.py**

```python
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

- [ ] **Step 3: Write backend/app/schemas/user.py**

```python
import uuid
from datetime import datetime

from pydantic import BaseModel


class UserBase(BaseModel):
    username: str
    role: str = "user"


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Write backend/app/repositories/base.py**

```python
from typing import Generic, TypeVar

from sqlalchemy.orm import Session

from shared.database.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic base repository for SQLAlchemy models."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.model: type[ModelType] = self.__orig_class__.__args__[0]  # type: ignore[attr-defined]

    def get_by_id(self, id: str) -> ModelType | None:
        return self.session.get(self.model, id)

    def get_all(self, *, skip: int = 0, limit: int = 100) -> list[ModelType]:
        return (
            self.session.query(self.model)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def create(self, obj: ModelType) -> ModelType:
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        return obj

    def update(self, obj: ModelType) -> ModelType:
        self.session.merge(obj)
        self.session.commit()
        return obj

    def delete(self, obj: ModelType) -> None:
        self.session.delete(obj)
        self.session.commit()
```

- [ ] **Step 5: Write backend/app/repositories/user.py**

```python
from sqlalchemy.orm import Session

from backend.app.models.user import User
from backend.app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User model operations."""

    def __init__(self, session: Session) -> None:
        # Override to avoid generic type resolution issues
        self.session = session
        self.model = User

    def get_by_username(self, username: str) -> User | None:
        return self.session.query(User).filter(User.username == username).first()

    def username_exists(self, username: str) -> bool:
        return (
            self.session.query(User).filter(User.username == username).first()
            is not None
        )
```

- [ ] **Step 6: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/models/ backend/app/schemas/ backend/app/repositories/
git commit -m "feat: add User model, schemas, and repository"
```

---

### Task 5: Create Alembic migration setup

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/` (directory)

- [ ] **Step 1: Write backend/alembic.ini**

```ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql+psycopg://admin:admin123@localhost:54329/mediaforge

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Write backend/alembic/env.py**

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from shared.database.models.base import Base
from backend.app.models.user import User  # noqa: F401 — ensure model is registered

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Write backend/alembic/script.py.mako**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Generate initial migration**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/backend
source /Users/eastwood/Code/PycharmProjects/media-forge/.venv/bin/activate
mkdir -p alembic/versions
alembic revision --autogenerate -m "initial_user_schema"
```

Expected: Creates a migration file in `alembic/versions/`.

- [ ] **Step 5: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/alembic.ini backend/alembic/ backend/__init__.py
git commit -m "chore: add Alembic migration setup with initial user schema"
```

---

### Task 6: Create auth router (login/logout)

**Files:**
- Create: `backend/app/modules/__init__.py`
- Create: `backend/app/modules/auth/__init__.py`
- Create: `backend/app/modules/auth/router.py`

- [ ] **Step 1: Write backend/app/modules/auth/router.py**

```python
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_db
from backend.app.core.security import create_access_token, verify_password
from backend.app.repositories.user import UserRepository
from backend.app.schemas.auth import LoginRequest, TokenResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user_repo = UserRepository(db)
    user = user_repo.get_by_username(request.username)

    if user is None or not verify_password(request.password, user.hashed_password):
        logger.warning("Failed login attempt for username: %s", request.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    access_token = create_access_token(data={"sub": user.username})

    logger.info("User logged in: %s", user.username)

    return TokenResponse(access_token=access_token)


@router.post("/logout")
def logout() -> dict[str, str]:
    # Stateless JWT — client discards token.
    # Future: add token blacklist in Redis.
    return {"message": "Logged out"}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/
git commit -m "feat: add auth router (login/logout)"
```

---

### Task 7: Create health router

**Files:**
- Create: `backend/app/modules/health/__init__.py`
- Create: `backend/app/modules/health/router.py`

- [ ] **Step 1: Write backend/app/modules/health/router.py**

```python
from fastapi import APIRouter

from shared.database.session import postgres_health_check

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health_check() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "database": postgres_health_check(),
    }
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/health/
git commit -m "feat: add health check endpoint"
```

---

### Task 8: Create main.py with lifespan

**Files:**
- Create: `backend/app/main.py`

- [ ] **Step 1: Write backend/app/main.py**

```python
import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import get_settings
from backend.app.core.dependencies import close_redis
from backend.app.modules.auth.router import router as auth_router
from backend.app.modules.health.router import router as health_router
from shared.database.session import close_postgres, connect_postgres
from shared.logging.jsonl import JSONLHandler

# -- Logging setup --

settings = get_settings()

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)
logger.addHandler(console_handler)

# JSONL file handler
jsonl_handler = JSONLHandler(
    log_dir=settings.log_dir, filename="backend.jsonl", component="backend"
)
logger.addHandler(jsonl_handler)


# -- Lifespan --


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle."""
    logger.info("Starting Media Forge backend v%s", settings.app_version)

    # Startup
    connect_postgres()
    logger.info("PostgreSQL connected.")

    yield

    # Shutdown
    close_redis()
    close_postgres()
    logger.info("Media Forge backend shut down.")


# -- App --


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(health_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} API", "version": settings.app_version}
```

- [ ] **Step 2: Verify app loads**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/backend
source /Users/eastwood/Code/PycharmProjects/media-forge/.venv/bin/activate
python -c "from app.main import app; print('FastAPI app loaded:', app.title)"
```

Expected: Prints "FastAPI app loaded: Media Forge"

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/main.py
git commit -m "feat: add FastAPI main entry point with lifespan"
```

---

### Task 9: Create init_db script

**Files:**
- Create: `backend/scripts/__init__.py`
- Create: `backend/scripts/init_db.py`

- [ ] **Step 1: Write backend/scripts/init_db.py**

```python
#!/usr/bin/env python3
"""Initialize database: create tables and default admin user.

Usage:
    python scripts/init_db.py
    python scripts/init_db.py --username admin --password admin123
"""

import argparse
import logging
import sys

from backend.app.core.security import get_password_hash
from backend.app.models.user import User
from backend.app.repositories.user import UserRepository
from shared.database.models.base import Base
from shared.database.session import connect_postgres, get_session_factory

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize database.")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    args = parser.parse_args()

    logger.info("Connecting to PostgreSQL...")
    connect_postgres()

    factory = get_session_factory()
    session = factory()

    try:
        # Create all tables
        logger.info("Creating tables...")
        Base.metadata.create_all(bind=session.get_bind())
        logger.info("Tables created.")

        # Create admin user if not exists
        user_repo = UserRepository(session)

        if user_repo.username_exists(args.username):
            logger.info("Admin user '%s' already exists. Skipping.", args.username)
            return

        user = User(
            username=args.username,
            hashed_password=get_password_hash(args.password),
            role="admin",
        )
        session.add(user)
        session.commit()
        logger.info("Admin user created: %s", args.username)
    except Exception:
        session.rollback()
        logger.exception("Failed to initialize database.")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/scripts/
git commit -m "feat: add init_db script for database bootstrap"
```

---

### Task 10: Create Docker Compose for PostgreSQL + Redis

**Files:**
- Create: `docker-compose.yml` (at project root)

- [ ] **Step 1: Write docker-compose.yml**

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:18-alpine
    container_name: media-forge-postgres
    environment:
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: admin123
      POSTGRES_DB: mediaforge
    ports:
      - "54329:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U admin -d mediaforge"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:8-alpine
    container_name: media-forge-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
  redis_data:
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add docker-compose.yml
git commit -m "chore: add Docker Compose for PostgreSQL 18 and Redis 8"
```

---

### Task 11: Create test infrastructure

**Files:**
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Write backend/tests/conftest.py**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.dependencies import get_db
from app.core.security import get_password_hash
from app.models.user import User
from shared.database.models.base import Base

# In-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def override_get_db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db() -> None:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def admin_user() -> User:
    session = TestingSessionLocal()
    user = User(
        username="admin",
        hashed_password=get_password_hash("admin123"),
        role="admin",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user
```

- [ ] **Step 2: Write backend/tests/test_auth.py**

```python
from http import HTTPStatus

from fastapi.testclient import TestClient


class TestAuthLogin:
    def test_login_success(self, client: TestClient, admin_user) -> None:
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client: TestClient, admin_user) -> None:
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_login_nonexistent_user(self, client: TestClient) -> None:
        response = client.post(
            "/api/auth/login",
            json={"username": "nobody", "password": "secret"},
        )
        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_login_missing_fields(self, client: TestClient) -> None:
        response = client.post("/api/auth/login", json={})
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


class TestHealth:
    def test_health_check(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert data["status"] == "ok"
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/backend
source /Users/eastwood/Code/PycharmProjects/media-forge/.venv/bin/activate
python -m pytest tests/ -v
```

Expected: 5 tests pass.

- [ ] **Step 4: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/tests/
git commit -m "test: add auth and health endpoint tests"
```

---

### Task 12: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md — add backend section**

Read the current file. Update the directory structure line for backend:
```
backend/     # FastAPI server (Python 3.12, PostgreSQL 18, Redis 8)
```

Add a **Backend** section after the Frontend section:

```markdown
## Backend

**Stack:** Python 3.12+ + FastAPI 0.115 + SQLAlchemy 2.0 + Alembic + asyncpg
- JWT token auth (python-jose + passlib/bcrypt)
- Redis 8 for task queue
- Shared utilities in `shared/` package (database session, models, logging)
- Pytest for testing

**Setup:**
```bash
docker compose up -d          # Start PostgreSQL 18 + Redis 8
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
alembic upgrade head           # Run migrations
python scripts/init_db.py      # Create admin user
uvicorn app.main:app --reload  # Start dev server
```
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with backend scaffold info"
```

---

### Task 13: Final verification

**Files:** (none — verification only)

- [ ] **Step 1: Run tests**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/backend
source /Users/eastwood/Code/PycharmProjects/media-forge/.venv/bin/activate
python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Verify app loads**

```bash
python -c "from app.main import app; print('OK', app.title)"
```

- [ ] **Step 3: Commit any fixes**
