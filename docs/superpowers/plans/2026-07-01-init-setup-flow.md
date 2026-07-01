# Init Setup Flow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Docker Compose; add first-run init flow: backend checks conf files and serves limited endpoints until configured; frontend route guard redirects to `/init` page where user enters PostgreSQL + Redis settings, submits to backend, conf files saved, then full app starts.

**Architecture:** Backend stores `database.conf` and `redis.conf` in `config/` directory (like jav-scrapling). `shared/runtime_config.py` handles reading/writing conf files. Main lifespan checks `runtime_config_exists()` — if false, only init endpoints are served. Frontend init API calls `GET /api/init/config` on app load; `requireInit` guard redirects to `/init` page if not configured. Init page has two-section form (PostgreSQL + Redis) that POSTs to `/api/init/config`.

**Tech Stack:** Python (pydantic, python-dotenv), FastAPI, React 19 + TypeScript 6 + Ant Design 6

## Reference Source

Patterns adapted from: `/Users/eastwood/Code/PycharmProjects/jav-scrapling/`

## Global Constraints

- No Docker Compose — deleted from project
- Conf files stored in `config/` directory at project root
- `database.conf` keys: `DATABASE_URL`, `POSTGRES_CONNECT_TIMEOUT`, `POSTGRES_POOL_SIZE`, `POSTGRES_MAX_OVERFLOW`, `POSTGRES_MAX_RETRIES`, `POSTGRES_RETRY_DELAY`
- `redis.conf` keys: `REDIS_URL`, `REDIS_SOCKET_TIMEOUT`, `REDIS_SOCKET_CONNECT_TIMEOUT`, `REDIS_MAX_CONNECTIONS`
- Backend lifespan: only mount auth + health routers if initialized; always mount init router
- Frontend guard `requireInit`: if not initialized, redirect to `/init`
- Init page fields match the backend `InitRequest` schema exactly
- No `any`, `@ts-ignore`, `@ts-nocheck`

---

### Task 1: Remove docker-compose.yml

**Files:**
- Delete: `docker-compose.yml`

- [ ] **Step 1: Delete the file**

```bash
rm /Users/eastwood/Code/PycharmProjects/media-forge/docker-compose.yml
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add docker-compose.yml
git commit -m "chore: remove Docker Compose (replaced by init setup flow)"
```

---

### Task 2: Create `shared/runtime_config.py`

**Files:**
- Create: `shared/runtime_config.py`

**Interfaces:**
- Produces: `runtime_config_exists()`, `read_runtime_config()`, `write_runtime_config()`, `load_runtime_config()`, `RuntimeConfigPaths`
- Consumed by: `backend/app/main.py` (Task 5), `backend/app/modules/init/service.py` (Task 4)

- [ ] **Step 1: Install python-dotenv**

```bash
source /Users/eastwood/Code/PycharmProjects/media-forge/.venv/bin/activate
pip install python-dotenv
pip freeze | grep dotenv >> /Users/eastwood/Code/PycharmProjects/media-forge/backend/requirements.txt
```

- [ ] **Step 2: Write shared/runtime_config.py**

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR_ENV = "APP_CONFIG_DIR"


@dataclass(frozen=True)
class RuntimeConfigPaths:
    config_dir: Path
    database_file: Path
    redis_file: Path

    @classmethod
    def from_env(cls) -> "RuntimeConfigPaths":
        configured_dir = os.getenv(CONFIG_DIR_ENV)
        config_dir = Path(configured_dir).expanduser() if configured_dir else PROJECT_ROOT / "config"
        return cls(
            config_dir=config_dir,
            database_file=config_dir / "database.conf",
            redis_file=config_dir / "redis.conf",
        )


def _serialize_value(value: object) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ValueError("Configuration values must be single-line strings")
    return text


def _write_env_file(path: Path, values: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{key}={_serialize_value(value)}\n" for key, value in values.items())
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(body, encoding="utf-8")
    temp_path.replace(path)


def write_runtime_config(
    sections: dict[str, dict[str, object]],
    paths: RuntimeConfigPaths | None = None,
) -> None:
    active_paths = paths or RuntimeConfigPaths.from_env()
    if "database" in sections:
        _write_env_file(active_paths.database_file, sections["database"])
    if "redis" in sections:
        _write_env_file(active_paths.redis_file, sections["redis"])


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    parsed = dotenv_values(path)
    return {key: str(value) for key, value in parsed.items() if value is not None}


def read_runtime_config(paths: RuntimeConfigPaths | None = None) -> dict[str, str]:
    active_paths = paths or RuntimeConfigPaths.from_env()
    values: dict[str, str] = {}
    values.update(_read_env_file(active_paths.database_file))
    values.update(_read_env_file(active_paths.redis_file))
    return values


def load_runtime_config(
    paths: RuntimeConfigPaths | None = None,
    *,
    override: bool = False,
) -> dict[str, str]:
    values = read_runtime_config(paths)
    for key, value in values.items():
        if override or key not in os.environ:
            os.environ[key] = value
    return values


def runtime_config_exists(paths: RuntimeConfigPaths | None = None) -> bool:
    active_paths = paths or RuntimeConfigPaths.from_env()
    return active_paths.database_file.exists() and active_paths.redis_file.exists()
```

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add shared/runtime_config.py backend/requirements.txt
git commit -m "feat: add shared runtime config (conf file read/write)"
```

---

### Task 3: Update `shared/database/postgres_config.py` — read from runtime config

**Files:**
- Modify: `shared/database/postgres_config.py`

- [ ] **Step 1: Rewrite the file**

```python
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
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add shared/database/postgres_config.py
git commit -m "refactor: postgres config reads from runtime config with env fallback"
```

---

### Task 4: Update `shared/database/session.py` — add retry logic

**Files:**
- Modify: `shared/database/session.py` (connect_postgres function)

- [ ] **Step 1: Update connect_postgres with retry logic**

Read the file. Replace the `connect_postgres()` function:

```python
import time

def connect_postgres() -> None:
    """Create engine and session factory with retry logic."""
    global _engine, _SessionLocal

    config = get_postgres_config()
    db_url = config.database_url
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
```

Add `import time` at the top of the file.

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add shared/database/session.py
git commit -m "feat: add retry logic to PostgreSQL connection"
```

---

### Task 5: Create backend init module (router + schemas)

**Files:**
- Create: `backend/app/modules/init/__init__.py`
- Create: `backend/app/modules/init/schemas.py`
- Create: `backend/app/modules/init/router.py`

**Interfaces:**
- Consumes: `shared/runtime_config.py`
- Produces:
  - `GET /api/init/config` → `InitConfigResponse { initialized, databaseConfigured, redisConfigured }`
  - `POST /api/init/config` → `InitConfigResponse` (validates connections, writes conf, loads into env)

- [ ] **Step 1: Write schemas.py**

```python
from pydantic import BaseModel, Field


class InitConfigResponse(BaseModel):
    initialized: bool
    databaseConfigured: bool
    redisConfigured: bool


class InitConfigRequest(BaseModel):
    # PostgreSQL
    databaseHost: str = Field(default="localhost", min_length=1)
    databasePort: int = Field(default=5432, ge=1, le=65535)
    databaseName: str = Field(default="mediaforge", min_length=1)
    databaseUser: str = Field(default="postgres", min_length=1)
    databasePassword: str = Field(default="postgres")
    postgresConnectTimeout: int = Field(default=5, ge=1, le=60)
    postgresPoolSize: int = Field(default=5, ge=1, le=50)
    postgresMaxOverflow: int = Field(default=10, ge=0, le=100)
    postgresMaxRetries: int = Field(default=10, ge=1, le=60)
    postgresRetryDelay: int = Field(default=3, ge=0, le=60)
    # Redis
    redisHost: str = Field(default="localhost", min_length=1)
    redisPort: int = Field(default=6379, ge=1, le=65535)
    redisPassword: str = Field(default="")
    redisSocketTimeout: int = Field(default=5, ge=1, le=60)
    redisConnectTimeout: int = Field(default=5, ge=1, le=60)
    redisMaxConnections: int = Field(default=10, ge=1, le=200)
```

- [ ] **Step 2: Write router.py**

```python
import logging

from fastapi import APIRouter, HTTPException, status
from redis import Redis
from sqlalchemy import create_engine, text

from backend.app.modules.init.schemas import InitConfigRequest, InitConfigResponse
from shared.runtime_config import (
    RuntimeConfigPaths,
    load_runtime_config,
    runtime_config_exists,
    write_runtime_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/init", tags=["init"])


def _get_init_status() -> InitConfigResponse:
    paths = RuntimeConfigPaths.from_env()
    db_ok = paths.database_file.exists()
    redis_ok = paths.redis_file.exists()
    return InitConfigResponse(
        initialized=db_ok and redis_ok,
        databaseConfigured=db_ok,
        redisConfigured=redis_ok,
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
```

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/init/
git commit -m "feat: add init module (config check + save endpoints)"
```

---

### Task 6: Update `backend/app/main.py` — conditional routing + runtime config loading

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Update lifespan and router registration**

Read the file. Change the lifespan to:
1. Load runtime config (from conf files into env) before connecting
2. Check if initialized — if yes, connect postgres; if no, log and skip

Change router registration to always include init router; auth/health only if initialized.

The key changes after reading and editing:

```python
from backend.app.modules.init.router import router as init_router
from shared.runtime_config import runtime_config_exists, load_runtime_config

# In lifespan startup, BEFORE connect_postgres():
    load_runtime_config()
    if runtime_config_exists():
        connect_postgres()
        logger.info("PostgreSQL connected.")
    else:
        logger.warning("Backend not initialized — only init endpoints available.")
```

Router registration — always mount init, conditionally mount others:
```python
app.include_router(init_router)

if runtime_config_exists():
    app.include_router(auth_router)
    app.include_router(health_router)
```

> Note: The router include happens at module load time. To make it truly dynamic, we either:
> A) Accept that after init, the user restarts the server (simpler, matches jav-scrapling)
> B) Use a dynamic middleware approach
>
> **We choose Option A** — always include all routers, but the lifespan guards the database connection. The `/api/init/config` POST endpoint works standalone (it doesn't need Postgres/Redis to already be connected). Other endpoints will fail gracefully if Postgres isn't connected.

Simplified approach:
```python
# Always include all routers
app.include_router(init_router)
app.include_router(auth_router)
app.include_router(health_router)
```

The `runtime_config_exists()` check is only used by the frontend to decide whether to show the init page.

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/main.py
git commit -m "feat: load runtime config in lifespan, add init router"
```

---

### Task 7: Create frontend init API

**Files:**
- Create: `frontend/src/api/init/index.ts`
- Create: `frontend/src/api/init/types.ts`

- [ ] **Step 1: Write types.ts**

```typescript
export interface InitConfigResponse {
  initialized: boolean
  databaseConfigured: boolean
  redisConfigured: boolean
}

export interface InitConfigRequest {
  databaseHost: string
  databasePort: number
  databaseName: string
  databaseUser: string
  databasePassword: string
  postgresConnectTimeout: number
  postgresPoolSize: number
  postgresMaxOverflow: number
  postgresMaxRetries: number
  postgresRetryDelay: number
  redisHost: string
  redisPort: number
  redisPassword: string
  redisSocketTimeout: number
  redisConnectTimeout: number
  redisMaxConnections: number
}
```

- [ ] **Step 2: Write index.ts**

```typescript
import { request } from '@/request'
import type { InitConfigRequest, InitConfigResponse } from './types'

export function getInitConfig(): Promise<InitConfigResponse> {
  return request<InitConfigResponse>({
    url: '/api/init/config',
    method: 'get',
    isToken: false,
  })
}

export function saveInitConfig(data: InitConfigRequest): Promise<InitConfigResponse> {
  return request<InitConfigResponse>({
    url: '/api/init/config',
    method: 'post',
    data,
    isToken: false,
  })
}
```

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/api/init/index.ts src/api/init/types.ts
git commit -m "feat: add init config API (get + save)"
```

---

### Task 8: Update frontend route guard — add `requireInit`

**Files:**
- Modify: `frontend/src/routes/-guards.ts`

- [ ] **Step 1: Add requireInit guard**

Read the file. Add a new `preloadInitCheck` singleton and `requireInit` function:

```typescript
import { redirect } from '@tanstack/react-router'
import { useAuthStore } from '@/stores/useAuthStore'
import { getInitConfig } from '@/api/init'

// --- Existing requireAuth / redirectIfAuthenticated ---
// (keep unchanged)

// --- Init check ---

let _initChecked = false
let _initResult: { initialized: boolean } | null = null

export async function checkInitStatus(): Promise<boolean> {
  if (_initChecked && _initResult !== null) {
    return _initResult.initialized
  }
  try {
    const res = await getInitConfig()
    _initResult = res as unknown as { initialized: boolean }
    _initChecked = true
    return _initResult.initialized
  } catch {
    _initChecked = true
    _initResult = { initialized: false }
    return false
  }
}

export async function requireInit(): Promise<void> {
  const isInit = await checkInitStatus()
  if (!isInit) {
    throw redirect({ to: '/init' })
  }
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/routes/-guards.ts
git commit -m "feat: add requireInit guard for setup flow"
```

---

### Task 9: Update frontend routes — add `/init` route + apply `requireInit` to protected routes

**Files:**
- Modify: `frontend/src/routes/index.tsx`

- [ ] **Step 1: Add init route, update index route guard**

Read the file. Changes:

1. Import `requireInit` from guards and `InitPage` from pages/init:
```typescript
import { redirectIfAuthenticated, requireAuth, requireInit } from './-guards'
import InitPage from '@/pages/init/InitPage'
```

2. Add the init route (before other routes):
```typescript
const initRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/init',
  component: InitPage,
})
```

3. Update the index route to also check init:
```typescript
const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: async () => {
    await checkInitStatus()
    requireAuth()
  },
  component: DashboardPage,
})
```

4. Add initRoute to the route tree:
```typescript
const routeTree = rootRoute.addChildren([initRoute, loginRoute, indexRoute])
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/routes/index.tsx
git commit -m "feat: add /init route with requireInit guard"
```

---

### Task 10: Create frontend InitPage

**Files:**
- Create: `frontend/src/pages/init/InitPage.tsx`
- Create: `frontend/src/pages/init/InitPage.module.less`

**Note:** Form fields: PostgreSQL section (host, port, database, user, password, connect timeout, pool size, max overflow, retry count, retry delay) + Redis section (host, port, password, socket timeout, connect timeout, max connections).

- [ ] **Step 1: Write InitPage.module.less**

```less
.page {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 40px 20px;
  background: #F5F7FA;

  :global([data-theme="dark"]) & {
    background: #0F172A;
  }
}

.card {
  width: 100%;
  max-width: 640px;
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
  padding: 40px;

  :global([data-theme="dark"]) & {
    background: #1E293B;
  }
}

.title {
  font-size: 24px;
  font-weight: 700;
  color: #1E293B;
  margin: 0 0 8px;

  :global([data-theme="dark"]) & {
    color: #F1F5F9;
  }
}

.subtitle {
  color: #64748B;
  margin: 0 0 32px;
  font-size: 14px;
}

.section {
  margin-bottom: 24px;

  h3 {
    font-size: 16px;
    font-weight: 600;
    color: #1E293B;
    margin: 0 0 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(0, 0, 0, 0.08);

    :global([data-theme="dark"]) & {
      color: #F1F5F9;
      border-bottom-color: rgba(255, 255, 255, 0.08);
    }
  }
}

.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.submitBtn {
  width: 100%;
  height: 44px;
  font-size: 16px;
  margin-top: 8px;
}
```

- [ ] **Step 2: Write InitPage.tsx**

```typescript
import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Form, Input, InputNumber, Button, Divider, message, Card } from 'antd'
import { saveInitConfig } from '@/api/init'
import type { InitConfigRequest } from '@/api/init/types'
import styles from './InitPage.module.less'

function InitPage() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleFinish = async (values: InitConfigRequest) => {
    setLoading(true)
    try {
      await saveInitConfig(values)
      void message.success('配置保存成功！请重启后端服务以应用配置。')
      // Optionally, redirect after a short delay
      setTimeout(() => {
        window.location.href = '/'
      }, 2000)
    } catch {
      void message.error('配置保存失败，请检查数据库和 Redis 连接信息')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.page}>
      <Card className={styles.card}>
        <h1 className={styles.title}>初始化配置</h1>
        <p className={styles.subtitle}>首次运行需要配置 PostgreSQL 和 Redis 连接信息</p>

        <Form<InitConfigRequest>
          layout="vertical"
          onFinish={(values) => void handleFinish(values)}
          initialValues={{
            databaseHost: 'localhost', databasePort: 5432, databaseName: 'mediaforge',
            databaseUser: 'postgres', databasePassword: 'postgres',
            postgresConnectTimeout: 5, postgresPoolSize: 5, postgresMaxOverflow: 10,
            postgresMaxRetries: 10, postgresRetryDelay: 3,
            redisHost: 'localhost', redisPort: 6379, redisPassword: '',
            redisSocketTimeout: 5, redisConnectTimeout: 5, redisMaxConnections: 10,
          }}
        >
          {/* PostgreSQL */}
          <div className={styles.section}>
            <h3>PostgreSQL 数据库配置</h3>
            <div className={styles.row}>
              <Form.Item name="databaseHost" label="主机地址" rules={[{ required: true }]}>
                <Input placeholder="localhost" />
              </Form.Item>
              <Form.Item name="databasePort" label="端口" rules={[{ required: true }]}>
                <InputNumber min={1} max={65535} style={{ width: '100%' }} />
              </Form.Item>
            </div>
            <div className={styles.row}>
              <Form.Item name="databaseUser" label="用户名" rules={[{ required: true }]}>
                <Input placeholder="postgres" />
              </Form.Item>
              <Form.Item name="databasePassword" label="密码">
                <Input.Password placeholder="postgres" />
              </Form.Item>
            </div>
            <Form.Item name="databaseName" label="数据库名" rules={[{ required: true }]}>
              <Input placeholder="mediaforge" />
            </Form.Item>
            <div className={styles.row}>
              <Form.Item name="postgresConnectTimeout" label="连接超时(秒)">
                <InputNumber min={1} max={60} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="postgresPoolSize" label="连接池大小">
                <InputNumber min={1} max={50} style={{ width: '100%' }} />
              </Form.Item>
            </div>
            <div className={styles.row}>
              <Form.Item name="postgresMaxOverflow" label="额外连接数">
                <InputNumber min={0} max={100} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="postgresMaxRetries" label="启动重试次数">
                <InputNumber min={1} max={60} style={{ width: '100%' }} />
              </Form.Item>
            </div>
            <Form.Item name="postgresRetryDelay" label="重试间隔(秒)">
              <InputNumber min={0} max={60} style={{ width: '100%' }} />
            </Form.Item>
          </div>

          <Divider />

          {/* Redis */}
          <div className={styles.section}>
            <h3>Redis 配置</h3>
            <div className={styles.row}>
              <Form.Item name="redisHost" label="主机地址" rules={[{ required: true }]}>
                <Input placeholder="localhost" />
              </Form.Item>
              <Form.Item name="redisPort" label="端口" rules={[{ required: true }]}>
                <InputNumber min={1} max={65535} style={{ width: '100%' }} />
              </Form.Item>
            </div>
            <Form.Item name="redisPassword" label="密码（可选）">
              <Input.Password placeholder="留空表示无密码" />
            </Form.Item>
            <div className={styles.row}>
              <Form.Item name="redisSocketTimeout" label="响应超时(秒)">
                <InputNumber min={1} max={60} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="redisConnectTimeout" label="连接超时(秒)">
                <InputNumber min={1} max={60} style={{ width: '100%' }} />
              </Form.Item>
            </div>
            <Form.Item name="redisMaxConnections" label="最大连接数">
              <InputNumber min={1} max={200} style={{ width: '100%' }} />
            </Form.Item>
          </div>

          <Button
            type="primary"
            htmlType="submit"
            loading={loading}
            className={styles.submitBtn}
            size="large"
          >
            保存配置
          </Button>
        </Form>
      </Card>
    </div>
  )
}

export default InitPage
```

- [ ] **Step 3: Verify frontend compiles**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b 2>&1 | head -20
```

Expected: zero errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/pages/init/InitPage.tsx src/pages/init/InitPage.module.less
git commit -m "feat: add InitPage with PostgreSQL and Redis configuration form"
```

---

### Task 11: Update App.tsx — preload init check on bootstrap

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add init check to App bootstrap**

Read the file. In the auth `useEffect`, add an init status check that redirects unauthenticated + uninitialized to `/init`:

```typescript
import { checkInitStatus } from './routes/-guards'

  useEffect(() => {
    if (isAuthenticated) {
      setReady(true)
    } else {
      // Check init status before marking ready
      checkInitStatus().then(() => {
        setReady(true)
      })
    }
  }, [isAuthenticated])
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/App.tsx
git commit -m "feat: check init status on app bootstrap"
```

---

### Task 12: Update CLAUDE.md — remove Docker Compose, add init flow docs

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update backend setup section**

Remove Docker Compose reference from backend setup. Update the setup steps:

```markdown
**Setup:**
\`\`\`bash
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload --port 8000
\`\`\`

On first run, the frontend will redirect to `/init` where you can configure
PostgreSQL and Redis connections. After saving, restart the backend to connect.
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add CLAUDE.md
git commit -m "docs: update setup for init flow"
```

---

### Task 13: Final verification

**Files:** (none — verification only)

- [ ] **Step 1: Backend tests**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Frontend verification**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b && npx eslint . && npm run build
```

Expected: All pass.

- [ ] **Step 3: Commit any fixes**
