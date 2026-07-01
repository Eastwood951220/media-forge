# Init Page — Test Connection Feature

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-connection test buttons (PostgreSQL + Redis) to the InitPage and auto-validate both connections on save — only allow saving if both pass.

**Architecture:** Backend exposes two test endpoints that accept the same params as save but don't write files. Frontend adds "Test Connection" buttons beside each section and calls tests before saving.

**Tech Stack:** FastAPI, SQLAlchemy, Redis, React, Ant Design

## Global Constraints

- No tsc/lint/build errors
- Existing tests must pass
- Save still uses `POST /api/init/config` (already validates internally)
- Test endpoints are bonus — save endpoint's existing validation is the final gate

---

### Task 1: Backend — add test endpoints

**Files:**
- Modify: `backend/app/modules/init/router.py`

**Interfaces:**
- Produces: `POST /api/init/test-postgres`, `POST /api/init/test-redis`
- Each accepts the same fields as `InitConfigRequest` and returns `{ success: bool, message: str }`

- [ ] **Step 1: Read router.py, add test endpoints**

Add after the existing routes, before `_get_init_status`:

```python
from pydantic import BaseModel, Field


class ConnectionTestResult(BaseModel):
    success: bool
    message: str


class PostgresTestRequest(BaseModel):
    host: str = Field(default="localhost", min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(default="mediaforge", min_length=1)
    user: str = Field(default="postgres", min_length=1)
    password: str = Field(default="postgres")
    connect_timeout: int = Field(default=5, ge=1, le=60)


class RedisTestRequest(BaseModel):
    host: str = Field(default="localhost", min_length=1)
    port: int = Field(default=6379, ge=1, le=65535)
    password: str = Field(default="")
    socket_timeout: int = Field(default=5, ge=1, le=60)
    connect_timeout: int = Field(default=5, ge=1, le=60)


@router.post("/test-postgres", response_model=ConnectionTestResult)
def test_postgres(body: PostgresTestRequest) -> ConnectionTestResult:
    sync_url = (
        f"postgresql+psycopg://{body.user}:{body.password}"
        f"@{body.host}:{body.port}/{body.database}"
    )
    try:
        engine = create_engine(
            sync_url,
            connect_args={"connect_timeout": body.connect_timeout},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return ConnectionTestResult(success=True, message="PostgreSQL 连接成功")
    except Exception as exc:
        return ConnectionTestResult(success=False, message=f"连接失败: {exc}")


@router.post("/test-redis", response_model=ConnectionTestResult)
def test_redis(body: RedisTestRequest) -> ConnectionTestResult:
    if body.password:
        redis_url = f"redis://:{body.password}@{body.host}:{body.port}/0"
    else:
        redis_url = f"redis://{body.host}:{body.port}/0"
    try:
        client = Redis.from_url(
            redis_url,
            socket_connect_timeout=body.connect_timeout,
            socket_timeout=body.socket_timeout,
            decode_responses=True,
        )
        client.ping()
        client.close()
        return ConnectionTestResult(success=True, message="Redis 连接成功")
    except Exception as exc:
        return ConnectionTestResult(success=False, message=f"连接失败: {exc}")
```

- [ ] **Step 2: Verify**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge && source .venv/bin/activate && python -c "from backend.app.modules.init.router import router; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/init/router.py
git commit -m "feat: add test-postgres and test-redis endpoints"
```

---

### Task 2: Frontend — add test API functions

**Files:**
- Modify: `frontend/src/api/init/types.ts`
- Modify: `frontend/src/api/init/index.ts`

- [ ] **Step 1: Add test types to types.ts**

Append:
```typescript
export interface ConnectionTestResult {
  success: boolean
  message: string
}

export interface PostgresTestParams {
  host: string
  port: number
  database: string
  user: string
  password: string
  connect_timeout: number
}

export interface RedisTestParams {
  host: string
  port: number
  password: string
  socket_timeout: number
  connect_timeout: number
}
```

- [ ] **Step 2: Add test functions to index.ts**

Append:
```typescript
import type { ConnectionTestResult, PostgresTestParams, RedisTestParams } from './types'

export function testPostgres(params: PostgresTestParams): Promise<ConnectionTestResult> {
  return request<ConnectionTestResult>({
    url: '/api/init/test-postgres',
    method: 'post',
    data: params,
    isToken: false,
  })
}

export function testRedis(params: RedisTestParams): Promise<ConnectionTestResult> {
  return request<ConnectionTestResult>({
    url: '/api/init/test-redis',
    method: 'post',
    data: params,
    isToken: false,
  })
}
```

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/api/init/types.ts src/api/init/index.ts
git commit -m "feat: add test-postgres and test-redis API functions"
```

---

### Task 3: Update InitPage — add test buttons + auto-test on save

**Files:**
- Modify: `frontend/src/pages/init/InitPage.tsx`
- Modify: `frontend/src/pages/init/InitPage.module.less`

- [ ] **Step 1: Add test button styles to module.less**

Append:
```less
.testRow {
  display: flex;
  align-items: flex-end;
  gap: 12px;
}

.testBtn {
  margin-bottom: 24px;
  flex-shrink: 0;
}

.testResult {
  font-size: 13px;
  margin-top: -16px;
  margin-bottom: 24px;

  &.success {
    color: #16A34A;
  }

  &.fail {
    color: #EF4444;
  }
}
```

- [ ] **Step 2: Update InitPage.tsx**

Key changes:
1. Add state: `pgTestResult`, `redisTestResult`
2. Add `handleTestPostgres` / `handleTestRedis` functions
3. Add "测试连接" buttons below each section
4. In `handleFinish`: test both connections before calling `saveInitConfig`, only save if both pass

Read current file and update:

```typescript
import { useState } from 'react'
import { Form, Input, InputNumber, Button, Divider, message, Space } from 'antd'
import { saveInitConfig, testPostgres, testRedis } from '@/api/init'
import type { InitConfigRequest, ConnectionTestResult, PostgresTestParams, RedisTestParams } from '@/api/init/types'
import styles from './InitPage.module.less'

function InitPage() {
  const [loading, setLoading] = useState(false)
  const [pgTesting, setPgTesting] = useState(false)
  const [redisTesting, setRedisTesting] = useState(false)
  const [pgResult, setPgResult] = useState<ConnectionTestResult | null>(null)
  const [redisResult, setRedisResult] = useState<ConnectionTestResult | null>(null)

  const [form] = Form.useForm<InitConfigRequest>()

  const getPgParams = (): PostgresTestParams => {
    const v = form.getFieldsValue()
    return {
      host: v.databaseHost,
      port: v.databasePort,
      database: v.databaseName,
      user: v.databaseUser,
      password: v.databasePassword,
      connect_timeout: v.postgresConnectTimeout,
    }
  }

  const getRedisParams = (): RedisTestParams => {
    const v = form.getFieldsValue()
    return {
      host: v.redisHost,
      port: v.redisPort,
      password: v.redisPassword,
      socket_timeout: v.redisSocketTimeout,
      connect_timeout: v.redisConnectTimeout,
    }
  }

  const handleTestPg = async () => {
    setPgTesting(true)
    setPgResult(null)
    try {
      const res = await testPostgres(getPgParams())
      setPgResult(res as ConnectionTestResult)
    } catch {
      setPgResult({ success: false, message: '测试请求失败' })
    } finally {
      setPgTesting(false)
    }
  }

  const handleTestRedis = async () => {
    setRedisTesting(true)
    setRedisResult(null)
    try {
      const res = await testRedis(getRedisParams())
      setRedisResult(res as ConnectionTestResult)
    } catch {
      setRedisResult({ success: false, message: '测试请求失败' })
    } finally {
      setRedisTesting(false)
    }
  }

  const handleFinish = async (values: InitConfigRequest) => {
    setLoading(true)
    try {
      // Auto-test both before save
      const [pgRes, redisRes] = await Promise.all([
        testPostgres({
          host: values.databaseHost, port: values.databasePort,
          database: values.databaseName, user: values.databaseUser,
          password: values.databasePassword, connect_timeout: values.postgresConnectTimeout,
        }),
        testRedis({
          host: values.redisHost, port: values.redisPort,
          password: values.redisPassword, socket_timeout: values.redisSocketTimeout,
          connect_timeout: values.redisConnectTimeout,
        }),
      ])

      const pgOk = (pgRes as ConnectionTestResult).success
      const redisOk = (redisRes as ConnectionTestResult).success
      if (!pgOk || !redisOk) {
        const msgs: string[] = []
        if (!pgOk) msgs.push('PostgreSQL: ' + (pgRes as ConnectionTestResult).message)
        if (!redisOk) msgs.push('Redis: ' + (redisRes as ConnectionTestResult).message)
        void message.error('连接测试失败，请修正后重试\n' + msgs.join('\n'))
        return
      }

      // Both passed — save
      await saveInitConfig(values)
      void message.success('配置保存成功！正在跳转...')
      setTimeout(() => { window.location.href = '/login' }, 1500)
    } catch {
      void message.error('配置保存失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <h1 className={styles.title}>初始化配置</h1>
        <p className={styles.subtitle}>首次运行需要配置 PostgreSQL 和 Redis 连接信息</p>

        <Form<InitConfigRequest>
          form={form}
          layout="vertical"
          onFinish={(values) => { void handleFinish(values) }}
          initialValues={{ /* same as before */ }}
        >
          {/* PostgreSQL Section — same fields */}
          {/* ... existing fields unchanged ... */}

          {/* Add test button after PostgreSQL fields, before Divider */}
          <Space>
            <Button onClick={() => { void handleTestPg() }} loading={pgTesting}>
              测试连接
            </Button>
            {pgResult && (
              <span className={`${styles.testResult} ${pgResult.success ? styles.success : styles.fail}`}>
                {pgResult.message}
              </span>
            )}
          </Space>

          <Divider />

          {/* Redis Section — same fields */}
          {/* ... existing fields unchanged ... */}

          {/* Add test button after Redis fields */}
          <Space>
            <Button onClick={() => { void handleTestRedis() }} loading={redisTesting}>
              测试连接
            </Button>
            {redisResult && (
              <span className={`${styles.testResult} ${redisResult.success ? styles.success : styles.fail}`}>
                {redisResult.message}
              </span>
            )}
          </Space>

          <Button type="primary" htmlType="submit" loading={loading}
            className={styles.submitBtn} size="large">
            保存并继续
          </Button>
        </Form>
      </div>
    </div>
  )
}
```

**Note:** The full InitPage.tsx is ~200 lines. The key structural changes are:
1. Add `form` ref via `Form.useForm()`
2. Add test state and handler functions
3. Add "测试连接" button after each section
4. In `handleFinish`: run both tests via `Promise.all` before calling `saveInitConfig`

- [ ] **Step 3: Verify**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b && npx eslint . 2>&1 | tail -1 && npm run build 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/pages/init/InitPage.tsx src/pages/init/InitPage.module.less
git commit -m "feat: add test connection buttons and auto-test on save"
```

---

### Task 4: Final verification

- [ ] **Step 1: Run backend tests**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge && source .venv/bin/activate && python -m pytest backend/tests/ -v
```

- [ ] **Step 2: Run frontend checks**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b && npx eslint . && npm run build
```
