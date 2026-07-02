# Init Database Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split init database creation, table creation, and default data insertion into one reusable bootstrap module that `/api/init/config` and CLI initialization both use.

**Architecture:** Move database URL construction, PostgreSQL validation, database creation, `Base.metadata.create_all`, and default seeders out of `backend/app/modules/init/router.py` into `backend/app/modules/init/database_bootstrap.py`. Keep the init router responsible for HTTP request/response flow, Redis validation, runtime config persistence, and error translation. Register all model imports and default seeders in the bootstrap module so future tables and seed data are added in one place.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, PostgreSQL 18, Redis 8, Pytest.

---

## File Structure

- Create: `backend/app/modules/init/database_bootstrap.py`
  - Central database bootstrap service for database URL construction, PostgreSQL validation, database creation, app table creation, and default seeders.
- Modify: `backend/app/modules/init/router.py`
  - Replace inline PostgreSQL/table/admin logic with calls to `database_bootstrap.py`.
- Modify: `backend/scripts/init_db.py`
  - Reuse the same table creation and default admin seeder as the init API.
- Create: `backend/tests/test_init_database_bootstrap.py`
  - Unit-test model import registration, table creation, and idempotent default admin seeding.
- Modify: `docs/superpowers/plans/2026-07-02-restore-jav-scrapling-crawler-tasks.md`
  - Treat this plan as the prerequisite for unified init table creation and remove duplicated init refactor work from the crawler task restoration plan.

---

### Task 1: Create the Database Bootstrap Service

**Files:**
- Create: `backend/app/modules/init/database_bootstrap.py`
- Test: `backend/tests/test_init_database_bootstrap.py`

- [ ] **Step 1: Write bootstrap service tests**

Create `backend/tests/test_init_database_bootstrap.py` with this complete content:

```python
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from backend.app.models.user import User
from backend.app.modules.init.database_bootstrap import (
    create_application_tables,
    import_application_models,
    seed_default_admin_user,
)
from shared.database.models.base import Base


def sqlite_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_import_application_models_registers_known_tables() -> None:
    import_application_models()

    assert "users" in Base.metadata.tables
    assert "crawl_tasks" in Base.metadata.tables


def test_create_application_tables_uses_shared_metadata() -> None:
    engine = sqlite_engine()

    create_application_tables(engine)

    table_names = set(inspect(engine).get_table_names())
    assert "users" in table_names
    assert "crawl_tasks" in table_names


def test_seed_default_admin_user_is_idempotent() -> None:
    engine = sqlite_engine()
    create_application_tables(engine)

    first = seed_default_admin_user(engine, username="admin", password="admin123")
    second = seed_default_admin_user(engine, username="admin", password="admin123")

    assert first is True
    assert second is False

    with engine.connect() as conn:
        rows = conn.execute(User.__table__.select()).fetchall()
    assert len(rows) == 1
    assert rows[0].username == "admin"
    assert rows[0].role == "admin"
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_init_database_bootstrap.py -v
```

Expected: FAIL because `backend.app.modules.init.database_bootstrap` does not exist.

- [ ] **Step 3: Create the bootstrap service**

Create `backend/app/modules/init/database_bootstrap.py` with this complete content:

```python
from __future__ import annotations

import importlib
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import Engine, create_engine, event, text
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
```

- [ ] **Step 4: Run bootstrap service tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_init_database_bootstrap.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit bootstrap service**

Run:

```bash
git add backend/app/modules/init/database_bootstrap.py backend/tests/test_init_database_bootstrap.py
git commit -m "refactor(init): add database bootstrap service"
```

Expected: one commit with the bootstrap service and tests.

---

### Task 2: Wire Init API to the Bootstrap Service

**Files:**
- Modify: `backend/app/modules/init/router.py`
- Test: `backend/tests/test_init_database_bootstrap.py`

- [ ] **Step 1: Add a router wiring test**

Append this test to `backend/tests/test_init_database_bootstrap.py`:

```python
from unittest.mock import Mock

from backend.app.modules.init.router import save_config
from backend.app.modules.init.schemas import InitConfigRequest


def test_save_config_uses_database_bootstrap(monkeypatch, tmp_path) -> None:
    bootstrap = Mock()
    bootstrap.return_value.async_url = "postgresql+asyncpg://admin:admin123@localhost:54329/mediaforge"
    bootstrap.return_value.sync_url = "postgresql+psycopg://admin:admin123@localhost:54329/mediaforge"
    bootstrap.return_value.maintenance_url = "postgresql+psycopg://admin:admin123@localhost:54329/postgres"
    monkeypatch.setattr("backend.app.modules.init.router.bootstrap_application_database", bootstrap)
    monkeypatch.setattr("backend.app.modules.init.router.validate_redis_connection", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))

    response = save_config(InitConfigRequest())

    assert response["code"] == 200
    assert bootstrap.call_count == 1
```

- [ ] **Step 2: Run the failing router wiring test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_init_database_bootstrap.py::test_save_config_uses_database_bootstrap -v
```

Expected: FAIL because `save_config()` still performs inline database work and does not import `bootstrap_application_database`.

- [ ] **Step 3: Refactor init router imports**

In `backend/app/modules/init/router.py`, replace these imports:

```python
from redis import Redis
from sqlalchemy import create_engine, event, text

from backend.app.core.security import get_password_hash
from backend.app.modules.init.schemas import InitConfigRequest, InitConfigResponse
from pydantic import BaseModel, Field
from shared.database.models.base import Base
```

with:

```python
from redis import Redis
from sqlalchemy import create_engine, text

from backend.app.modules.init.database_bootstrap import bootstrap_application_database
from backend.app.modules.init.schemas import InitConfigRequest, InitConfigResponse
from pydantic import BaseModel, Field
```

- [ ] **Step 4: Add Redis URL helpers to init router**

Add these functions above `save_config()` in `backend/app/modules/init/router.py`:

```python
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
```

- [ ] **Step 5: Replace `save_config()` body**

Replace `save_config()` in `backend/app/modules/init/router.py` with:

```python
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
```

- [ ] **Step 6: Run init bootstrap tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_init_database_bootstrap.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit init router wiring**

Run:

```bash
git add backend/app/modules/init/router.py backend/tests/test_init_database_bootstrap.py
git commit -m "refactor(init): delegate database bootstrap"
```

Expected: one commit with init router delegation.

---

### Task 3: Reuse Bootstrap in CLI Initialization

**Files:**
- Modify: `backend/scripts/init_db.py`
- Test: `backend/tests/test_init_database_bootstrap.py`

- [ ] **Step 1: Add a CLI bootstrap parity test**

Append this test to `backend/tests/test_init_database_bootstrap.py`:

```python
def test_script_imports_shared_bootstrap_functions() -> None:
    import backend.scripts.init_db as init_db

    assert init_db.create_application_tables is create_application_tables
    assert init_db.seed_default_admin_user is seed_default_admin_user
```

- [ ] **Step 2: Run the failing CLI parity test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_init_database_bootstrap.py::test_script_imports_shared_bootstrap_functions -v
```

Expected: FAIL because `backend/scripts/init_db.py` still imports `Base`, `User`, `UserRepository`, and `get_password_hash` directly instead of the bootstrap helpers.

- [ ] **Step 3: Replace `init_db.py`**

Replace `backend/scripts/init_db.py` with this complete content:

```python
#!/usr/bin/env python3
"""Initialize database tables and default data.

Usage:
    python scripts/init_db.py
    python scripts/init_db.py --username admin --password admin123
"""

import argparse
import logging
import sys

from backend.app.modules.init.database_bootstrap import (
    create_application_tables,
    seed_default_admin_user,
)
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
        engine = session.get_bind()
        logger.info("Creating tables...")
        create_application_tables(engine)
        logger.info("Tables created.")

        seed_default_admin_user(
            engine,
            username=args.username,
            password=args.password,
        )
    except Exception:
        session.rollback()
        logger.exception("Failed to initialize database.")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run bootstrap tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_init_database_bootstrap.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit CLI reuse**

Run:

```bash
git add backend/scripts/init_db.py backend/tests/test_init_database_bootstrap.py
git commit -m "refactor(init): reuse bootstrap in init script"
```

Expected: one commit with CLI bootstrap reuse.

---

### Task 4: Verify Existing Init Behavior

**Files:**
- Verify: `backend/app/modules/init/router.py`
- Verify: `backend/app/modules/init/database_bootstrap.py`
- Verify: `backend/scripts/init_db.py`

- [ ] **Step 1: Run focused init tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_init_database_bootstrap.py -v
```

Expected: PASS.

- [ ] **Step 2: Run backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests -v
```

Expected: PASS, or only unrelated pre-existing failures with exact failing test names captured.

- [ ] **Step 3: Manual init smoke test**

Start the backend, open `/init`, and submit:

```text
databaseHost=localhost
databasePort=54329
databaseName=mediaforge
databaseUser=admin
databasePassword=admin123
redisHost=localhost
redisPort=6379
```

Expected:

- PostgreSQL maintenance connection succeeds.
- `mediaforge` is created if missing.
- All models registered in `APPLICATION_MODEL_MODULES` are included in `Base.metadata.create_all`.
- `admin / admin123` is inserted only if missing.
- Runtime config files are written after database bootstrap and Redis validation succeed.

- [ ] **Step 4: Inspect changed files**

Run:

```bash
git status --short
git diff --stat
```

Expected: only files from this plan are changed.

---

## Future Extension Rule

When adding a new table:

1. Create the SQLAlchemy model under `backend/app/models/`.
2. Add that model module path to `APPLICATION_MODEL_MODULES` in `backend/app/modules/init/database_bootstrap.py`.
3. Add a bootstrap test asserting the table appears after `create_application_tables(engine)`.

When adding default data:

1. Add a seeder function in `backend/app/modules/init/database_bootstrap.py`.
2. Register it in `DEFAULT_SEEDERS`.
3. Add an idempotency test for that seeder.

---

## Self-Review

- Spec coverage: The plan splits init database creation, table creation, and default data insertion into reusable code.
- Scope control: The plan does not change frontend init UI or add configurable admin credentials.
- Type consistency: `DatabaseUrls.async_url` is the value persisted as `DATABASE_URL`; `DatabaseUrls.sync_url` is only used for synchronous SQLAlchemy bootstrap.
- Concrete steps: Every code-changing step includes the exact file content or exact replacement block.
