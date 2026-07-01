# Auto-Create Database & Admin User — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** On init save, after validating PostgreSQL connection via the default `postgres` database, auto-create the target database if it doesn't exist, create all tables, and seed the admin user (admin/admin123).

**Architecture:** The `save_config` endpoint connects to the `postgres` maintenance DB first, checks `pg_database` for the target DB, creates it if missing, then connects to the target DB, runs `Base.metadata.create_all()`, and seeds the admin user.

**Tech Stack:** Python, SQLAlchemy, psycopg

## Global Constraints

- Test connection (`test-postgres`) still just tests connectivity
- `save_config` does everything: check/create DB, create tables, seed admin
- Only one admin user: `admin` / `admin123`

---

### Task 1: Update `save_config` in init router

**Files:**
- Modify: `backend/app/modules/init/router.py`

**Changes:** After validating the PostgreSQL connection, add: check if target database exists (via `pg_database`), create if not, connect to target, run `Base.metadata.create_all()`, seed admin user.

**Note:** PostgreSQL doesn't allow `CREATE DATABASE` inside a transaction, so we must use `autocommit` mode for that step.

The updated `save_config` flow:
```
1. Connect to "postgres" maintenance DB (autocommit)
2. SELECT 1 FROM pg_database WHERE datname = '<target>'
3. If not exists: CREATE DATABASE "<target>"
4. Disconnect
5. Connect to target DB
6. Base.metadata.create_all()  -- creates all tables
7. Create admin user (admin/admin123) if not exists
8. Write config files
```

- [ ] **Step 1: Read router.py, add database creation + admin seed logic**

Add imports:
```python
from backend.app.core.security import get_password_hash
from backend.app.models.user import User
from shared.database.models.base import Base
```

In `save_config`, after the PostgreSQL validation block, add:

```python
    # Ensure target database exists (connect to postgres maintenance DB first)
    maintenance_url = (
        f"postgresql+psycopg://{body.databaseUser}:{body.databasePassword}"
        f"@{body.databaseHost}:{body.databasePort}/postgres"
    )
    try:
        maint_engine = create_engine(
            maintenance_url,
            isolation_level="AUTOCOMMIT",
            connect_args={"connect_timeout": body.postgresConnectTimeout},
        )
        with maint_engine.connect() as conn:
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                {"dbname": body.databaseName},
            )
            exists = result.fetchone() is not None

            if not exists:
                # CREATE DATABASE can't use parameters for the name
                conn.execute(text(f'CREATE DATABASE "{body.databaseName}"'))
                logger.info("Created database: %s", body.databaseName)
        maint_engine.dispose()
    except Exception as exc:
        logger.warning("Init: database creation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create database: {exc}",
        ) from exc

    # Connect to target DB and create tables + admin user
    try:
        target_engine = create_engine(
            sync_db_url,
            connect_args={"connect_timeout": body.postgresConnectTimeout},
        )
        # Create all tables
        Base.metadata.create_all(bind=target_engine)

        # Create admin user if not exists
        with target_engine.connect() as conn:
            result = conn.execute(
                text("SELECT id FROM users WHERE username = 'admin'")
            )
            if result.fetchone() is None:
                conn.execute(
                    text(
                        "INSERT INTO users (id, username, hashed_password, role) "
                        "VALUES (gen_random_uuid(), 'admin', :pw, 'admin')"
                    ),
                    {"pw": get_password_hash("admin123")},
                )
                conn.commit()
                logger.info("Admin user created.")

        target_engine.dispose()
    except Exception as exc:
        logger.warning("Init: table creation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to initialize database: {exc}",
        ) from exc
```

- [ ] **Step 2: Verify backend loads**

```bash
source .venv/bin/activate && python -c "from backend.app.modules.init.router import router; print('OK')"
```

- [ ] **Step 3: Run backend tests**

```bash
source .venv/bin/activate && python -m pytest backend/tests/ -v
```

Expected: 5 pass.

- [ ] **Step 4: Commit**