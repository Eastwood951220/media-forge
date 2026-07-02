# Fix Crawler Task Create And Error Response Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix crawler task creation so a valid single-URL payload can be created and duplicate failures report the actual cause, while all failed backend responses use the shared `{code, msg, data}` envelope consumed by the frontend request layer.

**Architecture:** Add backend tests that reproduce the exact crawler task create payload and the duplicate-name/duplicate-URL failure contract. Because the reported `crawl_tasks` and `crawl_task_urls` tables are empty, treat the current `"任务 URL 或名称重复"` as an error-classification bug first and check for database schema drift caused by `create_all()` not altering existing empty tables. Centralize failed response wrapping with FastAPI exception handlers backed by `shared.schemas.common`, repair empty incompatible crawler task tables during init bootstrap, then make the crawler task route map database integrity errors to specific messages instead of the broad duplicate message. Update the frontend error-code map and Axios error branch so non-2xx wrapped backend errors display `msg` and reject with `BusinessError`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pydantic, Pytest, React 19, TypeScript, Axios, Vitest.

---

## Debugging Notes

- Current reproduction baseline: `./.venv/bin/python -m pytest backend/tests/test_crawl_tasks_api.py -v` passes in a clean in-memory SQLite database, so the exact one-URL payload is not inherently invalid.
- User confirmed both `crawl_tasks` and `crawl_task_urls` contain no rows. Therefore the reported failure is not caused by existing duplicate task data. The most likely production causes are:
  - existing empty tables still have the old schema because `Base.metadata.create_all()` does not alter existing tables;
  - a legacy NOT NULL column such as an old JSON `urls` column remains in `crawl_tasks` and is not populated by the new model;
  - a foreign key, UUID type, nullable/default, or constraint mismatch exists between PostgreSQL tables and SQLAlchemy models;
  - the broad `except IntegrityError` currently hides the actual `exc.orig`, SQLSTATE, and constraint name.
- Current backend route behavior in `backend/app/modules/crawler/tasks/router.py`:
  - `repo.get_by_name(current_user.id, data.name)` catches obvious same-owner duplicate task names before insert.
  - `_check_urls_unique(data.urls)` catches duplicate URLs inside the same request body.
  - Any remaining `IntegrityError` is caught and re-raised as `HTTPException(400, detail="任务 URL 或名称重复")`, which hides the real database constraint.
- Current failed response behavior:
  - FastAPI defaults return `{"detail": "..."}` for `HTTPException` and validation errors.
  - `shared/schemas/common.py` only has `success()` and `paginated()`.
  - `frontend/src/request/transform.ts` unwraps `{code,msg,data}` only for successful HTTP responses; non-2xx Axios errors are handled by `handleResponseError()`, which currently prefers `detail` or a generic network-style message.
- Working assumption for implementation: success responses keep body code `200`; failed responses use the same envelope shape with body `code` set to the HTTP/business code such as `400`, `401`, `409`, `422`, or `500`, while preserving the HTTP status code.

## File Structure

- Modify: `shared/schemas/common.py`
  - Add a reusable `failure()` helper returning `{"code": code, "msg": msg, "data": data}`.
  - Keep `success()` and `paginated()` unchanged for existing successful responses.
- Create: `backend/app/core/exception_handlers.py`
  - Register FastAPI exception handlers for `HTTPException`, `RequestValidationError`, and generic unhandled exceptions.
  - Convert every failed response to the shared envelope.
- Modify: `backend/app/main.py`
  - Import and call `register_exception_handlers(app)` immediately after app creation.
- Modify: `backend/app/modules/crawler/tasks/router.py`
  - Add integrity-error constraint parsing for `uq_crawl_tasks_owner_name` and `uq_crawl_task_urls_task_url`.
  - Replace the broad `"任务 URL 或名称重复"` fallback with specific 409/400 messages.
- Modify: `backend/app/modules/init/database_bootstrap.py`
  - Detect incompatible empty crawler task tables left from older schemas.
  - Drop and recreate only the empty `crawl_task_urls`/`crawl_tasks` tables when their physical schema cannot satisfy the current models.
- Modify: `backend/tests/test_init_database_bootstrap.py`
  - Add coverage for repairing empty legacy crawler task tables.
- Modify: `backend/tests/test_response.py`
  - Add tests for the new `failure()` helper.
- Modify: `backend/tests/test_crawl_tasks_api.py`
  - Add tests for the exact user payload, duplicate task name response envelope, duplicate request URL response envelope, and task-not-found response envelope.
- Create: `backend/tests/test_exception_handlers.py`
  - Add tests proving auth, validation, and not-found failures return `{code,msg,data}` instead of `detail`.
- Modify: `frontend/src/enums/RespEnum.ts`
  - Add common HTTP/business codes used by backend failed envelopes.
- Modify: `frontend/src/request/errorCode.ts`
  - Add messages for 400, 409, 422, 429, and 500.
- Modify: `frontend/src/request/transform.ts`
  - Teach `handleResponseError()` to read wrapped backend failures from `response.data.msg`, fall back to `detail`, and reject with `BusinessError`.
- Create: `frontend/tests/request-error-envelope.test.ts`
  - Add Vitest coverage for non-2xx wrapped backend errors.

---

### Task 1: Add Backend Failure Envelope Tests

**Files:**
- Modify: `backend/tests/test_response.py`

- [ ] **Step 1: Write failing tests for `failure()`**

Append these tests below `TestSuccessFunction` in `backend/tests/test_response.py` and update the import to include `failure`.

```python
from shared.schemas.common import ApiResponse, PaginatedResponse, failure, paginated, success
```

```python
class TestFailureFunction:
    """Tests for the failure() helper."""

    def test_failure_returns_dict_with_code_msg_data(self) -> None:
        result = failure(code=409, msg="任务名称 '巨乳' 已存在")

        assert result["code"] == 409
        assert result["msg"] == "任务名称 '巨乳' 已存在"
        assert result["data"] is None

    def test_failure_with_data(self) -> None:
        data = [{"loc": ["body", "name"], "msg": "Field required"}]
        result = failure(code=422, msg="请求参数错误", data=data)

        assert result["code"] == 422
        assert result["msg"] == "请求参数错误"
        assert result["data"] == data
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest backend/tests/test_response.py::TestFailureFunction -v
```

Expected: FAIL with `ImportError: cannot import name 'failure'`.

- [ ] **Step 3: Implement `failure()`**

Add this function to `shared/schemas/common.py` after `success()`:

```python
def failure(code: int = 500, msg: str = "error", data: Any = None) -> dict:
    """Build a failed response dict with the standard data wrapper."""
    return {
        "code": code,
        "msg": msg,
        "data": data,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest backend/tests/test_response.py::TestFailureFunction -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/schemas/common.py backend/tests/test_response.py
git commit -m "test: cover failed api response envelope"
```

---

### Task 2: Add Global Backend Exception Handlers

**Files:**
- Create: `backend/app/core/exception_handlers.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_exception_handlers.py`
- Modify: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing tests for wrapped HTTP and validation failures**

Create `backend/tests/test_exception_handlers.py`:

```python
from http import HTTPStatus

from fastapi.testclient import TestClient


def test_http_exception_uses_standard_envelope(client: TestClient, admin_user) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json() == {
        "code": 401,
        "msg": "Incorrect username or password",
        "data": None,
    }


def test_validation_error_uses_standard_envelope(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    body = response.json()
    assert body["code"] == 422
    assert body["msg"] == "请求参数错误"
    assert isinstance(body["data"], list)
    assert body["data"][0]["loc"][0] == "body"
```

Update existing assertions in `backend/tests/test_auth.py` so they match the new envelope:

```python
    def test_login_wrong_password(self, client: TestClient, admin_user) -> None:
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.json()["code"] == 401
        assert response.json()["msg"] == "Incorrect username or password"
        assert response.json()["data"] is None

    def test_login_nonexistent_user(self, client: TestClient) -> None:
        response = client.post(
            "/api/auth/login",
            json={"username": "nobody", "password": "secret"},
        )
        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.json()["code"] == 401
        assert response.json()["msg"] == "Incorrect username or password"
        assert response.json()["data"] is None

    def test_login_missing_fields(self, client: TestClient) -> None:
        response = client.post("/api/auth/login", json={})
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert response.json()["code"] == 422
        assert response.json()["msg"] == "请求参数错误"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/python -m pytest backend/tests/test_exception_handlers.py backend/tests/test_auth.py -v
```

Expected: FAIL because responses still contain `detail` or, for existing auth success, old tests may still assume an unwrapped `access_token`.

- [ ] **Step 3: Implement exception handlers**

Create `backend/app/core/exception_handlers.py`:

```python
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette import status

from shared.schemas.common import failure

logger = logging.getLogger(__name__)


def _detail_to_message_and_data(detail: Any) -> tuple[str, Any, int | None]:
    if isinstance(detail, dict):
        msg = detail.get("msg") or detail.get("message") or detail.get("detail") or "请求失败"
        code = detail.get("code")
        data = detail.get("data")
        return str(msg), data, int(code) if isinstance(code, int) else None
    if isinstance(detail, str) and detail:
        return detail, None, None
    if detail is None:
        return "请求失败", None, None
    return str(detail), detail, None


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        msg, data, body_code = _detail_to_message_and_data(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=failure(code=body_code or exc.status_code, msg=msg, data=data),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=failure(
                code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                msg="请求参数错误",
                data=exc.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception("Unhandled request error: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=failure(
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                msg="服务器内部错误",
                data=None,
            ),
        )
```

Modify `backend/app/main.py`:

```python
from backend.app.core.exception_handlers import register_exception_handlers
```

Then call it after `app = FastAPI(...)`:

```python
register_exception_handlers(app)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./.venv/bin/python -m pytest backend/tests/test_exception_handlers.py backend/tests/test_auth.py -v
```

Expected: PASS after updating auth success assertions if needed. The login success body should be read as `response.json()["data"]["access_token"]`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/exception_handlers.py backend/app/main.py backend/tests/test_exception_handlers.py backend/tests/test_auth.py
git commit -m "feat: wrap backend error responses"
```

---

### Task 3: Repair Empty Legacy Crawler Task Tables During Init

**Files:**
- Modify: `backend/app/modules/init/database_bootstrap.py`
- Modify: `backend/tests/test_init_database_bootstrap.py`

- [ ] **Step 1: Write failing schema-drift repair test**

Append this test to `backend/tests/test_init_database_bootstrap.py`:

```python
from sqlalchemy import text
```

```python
def test_create_application_tables_repairs_empty_legacy_crawler_task_tables() -> None:
    engine = sqlite_engine()
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE crawl_tasks (
                id VARCHAR PRIMARY KEY,
                created_at DATETIME NOT NULL,
                name VARCHAR(200) NOT NULL,
                urls TEXT NOT NULL,
                owner_id VARCHAR NOT NULL
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE crawl_task_urls (
                id VARCHAR PRIMARY KEY,
                task_id VARCHAR NOT NULL,
                url TEXT NOT NULL,
                legacy_required TEXT NOT NULL
            )
            """
        ))

    create_application_tables(engine)

    inspector = inspect(engine)
    task_columns = {column["name"] for column in inspector.get_columns("crawl_tasks")}
    url_columns = {column["name"] for column in inspector.get_columns("crawl_task_urls")}

    assert "urls" not in task_columns
    assert "legacy_required" not in url_columns
    assert {"status", "task_id", "total_found", "total_qualified"}.issubset(task_columns)
    assert {"position", "url_type", "final_url", "source"}.issubset(url_columns)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest backend/tests/test_init_database_bootstrap.py::test_create_application_tables_repairs_empty_legacy_crawler_task_tables -v
```

Expected: FAIL because `create_application_tables()` currently calls `Base.metadata.create_all()` and leaves existing incompatible tables untouched.

- [ ] **Step 3: Implement empty-table schema repair**

Modify `backend/app/modules/init/database_bootstrap.py` imports:

```python
from sqlalchemy import Engine, create_engine, event, inspect, text
```

Add this code after `import_application_models()`:

```python
CRAWLER_TASK_TABLE_NAMES = ("crawl_task_urls", "crawl_tasks")


def _table_row_count(engine: Engine, table_name: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one())


def _column_has_server_default(column: dict) -> bool:
    return column.get("default") is not None or column.get("server_default") is not None


def _is_incompatible_table(engine: Engine, table_name: str, expected_columns: set[str]) -> bool:
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return False

    columns = inspector.get_columns(table_name)
    actual_columns = {column["name"] for column in columns}
    if not expected_columns.issubset(actual_columns):
        return True

    for column in columns:
        name = column["name"]
        if name in expected_columns:
            continue
        if column.get("nullable") is False and not _column_has_server_default(column):
            return True

    return False


def repair_empty_crawler_task_tables(engine: Engine) -> bool:
    from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl

    expected = {
        "crawl_tasks": {column.name for column in CrawlTask.__table__.columns},
        "crawl_task_urls": {column.name for column in CrawlTaskUrl.__table__.columns},
    }

    incompatible = [
        table_name
        for table_name, expected_columns in expected.items()
        if _is_incompatible_table(engine, table_name, expected_columns)
    ]
    if not incompatible:
        return False

    non_empty = [
        table_name
        for table_name in CRAWLER_TASK_TABLE_NAMES
        if inspect(engine).has_table(table_name) and _table_row_count(engine, table_name) > 0
    ]
    if non_empty:
        names = ", ".join(non_empty)
        raise RuntimeError(f"爬虫任务表结构不兼容且已有数据，无法自动重建: {names}")

    logger.warning("Rebuilding empty incompatible crawler task tables: %s", ", ".join(incompatible))
    CrawlTaskUrl.__table__.drop(bind=engine, checkfirst=True)
    CrawlTask.__table__.drop(bind=engine, checkfirst=True)
    Base.metadata.create_all(bind=engine)
    return True
```

Update `create_application_tables()`:

```python
def create_application_tables(engine: Engine) -> None:
    import_application_models()
    repair_empty_crawler_task_tables(engine)
    Base.metadata.create_all(bind=engine)
```

- [ ] **Step 4: Run schema bootstrap tests**

Run:

```bash
./.venv/bin/python -m pytest backend/tests/test_init_database_bootstrap.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/init/database_bootstrap.py backend/tests/test_init_database_bootstrap.py
git commit -m "fix: rebuild empty incompatible crawler task tables"
```

---

### Task 4: Fix Crawler Task Create Duplicate Handling

**Files:**
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Modify: `backend/tests/test_crawl_tasks_api.py`

- [ ] **Step 1: Write failing crawler task create tests**

Add this helper and tests to `backend/tests/test_crawl_tasks_api.py`:

```python
def exact_user_payload() -> dict:
    return {
        "name": "巨乳",
        "is_skip": False,
        "urls": [
            {
                "url": "https://javdb.com/actors/QV49G",
                "url_type": "actors",
                "has_magnet": True,
                "has_chinese_sub": False,
                "sort_type": 0,
                "url_name": "",
            }
        ],
    }
```

```python
    def test_create_task_accepts_exact_single_url_payload(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)

        response = client.post(
            "/api/crawler/tasks",
            json=exact_user_payload(),
            headers=headers,
        )

        assert response.status_code == HTTPStatus.CREATED
        body = response.json()
        assert body["code"] == 200
        assert body["msg"] == "success"
        created = body["data"]
        assert created["name"] == "巨乳"
        assert created["urls"][0]["url"] == "https://javdb.com/actors/QV49G"
        assert created["urls"][0]["url_type"] == "actors"
        assert created["urls"][0]["has_magnet"] is True
        assert created["urls"][0]["has_chinese_sub"] is False

    def test_create_task_duplicate_name_returns_specific_envelope(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        payload = exact_user_payload()
        first = client.post("/api/crawler/tasks", json=payload, headers=headers)
        assert first.status_code == HTTPStatus.CREATED

        second_payload = exact_user_payload()
        second_payload["urls"][0]["url"] = "https://javdb.com/actors/OTHER"
        response = client.post("/api/crawler/tasks", json=second_payload, headers=headers)

        assert response.status_code == HTTPStatus.CONFLICT
        assert response.json() == {
            "code": 409,
            "msg": "任务名称 '巨乳' 已存在",
            "data": None,
        }

    def test_create_task_duplicate_urls_returns_standard_envelope(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        payload = exact_user_payload()
        payload["urls"].append(payload["urls"][0].copy())

        response = client.post("/api/crawler/tasks", json=payload, headers=headers)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json() == {
            "code": 400,
            "msg": "URL 重复: https://javdb.com/actors/QV49G",
            "data": None,
        }
```

Update the existing `test_create_task_rejects_duplicate_urls` assertion:

```python
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json()["code"] == 400
        assert "URL 重复" in response.json()["msg"]
        assert response.json()["data"] is None
```

- [ ] **Step 2: Run tests to verify current failures**

Run:

```bash
./.venv/bin/python -m pytest backend/tests/test_crawl_tasks_api.py -v
```

Expected before implementation:
- The exact single-url payload may already pass.
- Duplicate-name and duplicate-url envelope assertions fail because the body currently uses `detail` unless Task 2 is already complete.
- If a database `IntegrityError` path is triggered, the message is still the broad `"任务 URL 或名称重复"`.

- [ ] **Step 3: Implement specific integrity-error mapping and log unknown database errors**

In `backend/app/modules/crawler/tasks/router.py`, add these helpers near `_check_urls_unique()`:

```python
def _constraint_name_from_integrity_error(exc: IntegrityError) -> str:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name:
        return str(constraint_name)

    text = str(orig or exc).lower()
    if "uq_crawl_tasks_owner_name" in text or ("crawl_tasks" in text and "owner_id" in text and "name" in text):
        return "uq_crawl_tasks_owner_name"
    if "uq_crawl_task_urls_task_url" in text or ("crawl_task_urls" in text and "task_id" in text and "url" in text):
        return "uq_crawl_task_urls_task_url"
    return ""


def _raise_task_integrity_error(exc: IntegrityError, *, name: str | None = None) -> None:
    constraint_name = _constraint_name_from_integrity_error(exc)
    if constraint_name == "uq_crawl_tasks_owner_name":
        msg = f"任务名称 '{name}' 已存在" if name else "任务名称已存在"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from exc
    if constraint_name == "uq_crawl_task_urls_task_url":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务 URL 重复") from exc
    logger.exception(
        "Unexpected crawler task integrity error, constraint=%s, orig=%s",
        constraint_name or "<unknown>",
        getattr(exc, "orig", exc),
    )
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="创建任务失败，请检查数据库表结构") from exc
```

Then update `create_task()`:

```python
    except IntegrityError as exc:
        db.rollback()
        _raise_task_integrity_error(exc, name=data.name)
```

Update `update_task()`:

```python
    except IntegrityError as exc:
        db.rollback()
        _raise_task_integrity_error(exc, name=update_data.get("name") or task.name)
```

- [ ] **Step 4: Run crawler task API tests**

Run:

```bash
./.venv/bin/python -m pytest backend/tests/test_crawl_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/crawler/tasks/router.py backend/tests/test_crawl_tasks_api.py
git commit -m "fix: report specific crawler task duplicate errors"
```

---

### Task 5: Update Frontend Error Code And Axios Error Handling

**Files:**
- Modify: `frontend/src/enums/RespEnum.ts`
- Modify: `frontend/src/request/errorCode.ts`
- Modify: `frontend/src/request/transform.ts`
- Create: `frontend/tests/request-error-envelope.test.ts`

- [ ] **Step 1: Write failing frontend tests**

Create `frontend/tests/request-error-envelope.test.ts`:

```typescript
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosError } from 'axios'
import { message } from 'antd'
import { BusinessError } from '../src/request/error'
import { handleResponseError, isRelogin } from '../src/request/transform'

vi.mock('antd', () => ({
  message: { error: vi.fn(), warning: vi.fn() },
  notification: { error: vi.fn() },
  Modal: {
    confirm: vi.fn(),
  },
}))

function wrappedHttpError(status: number, data: unknown): AxiosError {
  return {
    name: 'AxiosError',
    message: `Request failed with status code ${status}`,
    isAxiosError: true,
    toJSON: () => ({}),
    config: {
      url: '/api/crawler/tasks',
      method: 'post',
      headers: {},
    },
    response: {
      status,
      statusText: 'Error',
      headers: {},
      config: {
        url: '/api/crawler/tasks',
        method: 'post',
        headers: {},
      },
      data,
    },
  } as AxiosError
}

describe('request error envelope handling', () => {
  beforeEach(() => {
    isRelogin.show = false
    vi.clearAllMocks()
  })

  it('uses backend msg from non-2xx wrapped response', async () => {
    const error = wrappedHttpError(409, {
      code: 409,
      msg: "任务名称 '巨乳' 已存在",
      data: null,
    })

    await expect(handleResponseError(error)).rejects.toMatchObject({
      name: 'BusinessError',
      message: "任务名称 '巨乳' 已存在",
      code: 409,
    } satisfies Partial<BusinessError>)

    expect(message.error).toHaveBeenCalledWith("任务名称 '巨乳' 已存在", 5)
  })

  it('falls back to legacy detail when response is not wrapped', async () => {
    const error = wrappedHttpError(400, {
      detail: 'URL 重复: https://javdb.com/actors/QV49G',
    })

    await expect(handleResponseError(error)).rejects.toThrow('URL 重复: https://javdb.com/actors/QV49G')
  })
})
```

- [ ] **Step 2: Run frontend tests to verify failure**

Run:

```bash
cd frontend && npm test -- request-error-envelope.test.ts auth-invalid-token.test.ts
```

Expected: FAIL because `handleResponseError()` currently returns the raw Axios error and uses generic `系统接口409异常`.

- [ ] **Step 3: Extend response enums and error-code map**

Modify `frontend/src/enums/RespEnum.ts`:

```typescript
export const HttpStatus = {
  SUCCESS: 200,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  CONFLICT: 409,
  TOO_MANY_REQUESTS: 429,
  VALIDATION_ERROR: 422,
  SERVER_ERROR: 500,
  WARN: 601,
} as const
```

Modify `frontend/src/request/errorCode.ts`:

```typescript
const errorCode: Record<string | number, string> = {
  400: '请求参数错误',
  401: '认证失败，无法访问系统资源',
  403: '当前操作没有权限',
  404: '访问资源不存在',
  409: '数据已存在，请勿重复提交',
  422: '请求参数校验失败',
  429: '请求过于频繁，请稍后重试',
  500: '服务器内部错误',
  default: '系统未知错误，请反馈给管理员',
}

export default errorCode
```

- [ ] **Step 4: Update non-2xx error parsing**

Modify `frontend/src/request/transform.ts` by replacing `getHttpErrorDetail()` with these helpers:

```typescript
function getResponseErrorPayload(error: AxiosError): {
  msg: string
  code?: string | number
  data?: unknown
} {
  const data = error.response?.data

  if (data && typeof data === 'object') {
    if ('msg' in data) {
      const wrapped = data as Partial<ApiResponse>
      const code = wrapped.code ?? error.response?.status
      const msg = wrapped.msg || errorCode[code as string | number] || errorCode.default
      return { msg, code, data }
    }

    if ('detail' in data) {
      const detail = (data as { detail?: unknown }).detail
      if (typeof detail === 'string') {
        return { msg: detail, code: error.response?.status, data }
      }
    }
  }

  return {
    msg: normalizeNetworkError(error),
    code: error.response?.status,
    data,
  }
}
```

Then replace `handleResponseError()` with:

```typescript
export function handleResponseError(error: AxiosError): Promise<never> {
  if (isCancelledError(error)) {
    return Promise.reject(error)
  }

  const requestConfig = error.config as RequestConfig | undefined
  const payload = getResponseErrorPayload(error)

  if (error.response?.status === HttpStatus.UNAUTHORIZED) {
    return expireSession(payload.msg)
  }

  if (requestConfig?.showError !== false) {
    void message.error(payload.msg, 5)
  }

  return Promise.reject(new BusinessError(payload.msg, payload.code, payload.data))
}
```

Keep `normalizeNetworkError()` in the file because the new helper calls it.

- [ ] **Step 5: Run frontend tests**

Run:

```bash
cd frontend && npm test -- request-error-envelope.test.ts auth-invalid-token.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/enums/RespEnum.ts frontend/src/request/errorCode.ts frontend/src/request/transform.ts frontend/tests/request-error-envelope.test.ts
git commit -m "fix: read wrapped backend error responses"
```

---

### Task 6: Verify End-To-End Contract

**Files:**
- No additional files.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
./.venv/bin/python -m pytest \
  backend/tests/test_response.py \
  backend/tests/test_exception_handlers.py \
  backend/tests/test_auth.py \
  backend/tests/test_init_database_bootstrap.py \
  backend/tests/test_crawl_tasks_api.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd frontend && npm test -- request-error-envelope.test.ts auth-invalid-token.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS, TypeScript emits no errors.

- [ ] **Step 4: Manually verify the reported payload through the API**

Start the backend using the project environment:

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

From another shell, log in and create the task:

```bash
TOKEN=$(curl -s http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["data"]["access_token"])')

curl -i http://127.0.0.1:8000/api/crawler/tasks \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"name":"巨乳","is_skip":false,"urls":[{"url":"https://javdb.com/actors/QV49G","url_type":"actors","has_magnet":true,"has_chinese_sub":false,"sort_type":0,"url_name":""}]}'
```

Expected on first create:

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "name": "巨乳"
  }
}
```

Expected if the same task name already exists:

```json
{
  "code": 409,
  "msg": "任务名称 '巨乳' 已存在",
  "data": null
}
```

- [ ] **Step 5: Commit final verification notes if tests required adjustments**

If no files changed during verification, do not create a commit. If a test or implementation needed a small correction, commit the exact changed files:

```bash
git add <changed-files>
git commit -m "test: verify crawler task error contract"
```

---

## Self-Review

- Spec coverage:
  - Exact create-task payload is covered by `test_create_task_accepts_exact_single_url_payload`.
  - The user-confirmed empty-table scenario is covered by `test_create_application_tables_repairs_empty_legacy_crawler_task_tables`.
  - Duplicate bug is covered by specific duplicate-name and duplicate-URL envelope tests plus integrity-error mapping; unknown integrity errors no longer claim duplicate data.
  - Failed responses are standardized through global exception handlers and `failure()`.
  - Frontend `errorCode.ts` and `RespEnum.ts` are updated, and the non-2xx Axios path reads backend `msg`.
- Placeholder scan:
  - No `TBD`, vague validation steps, or "similar to" tasks remain.
  - Every code-changing step includes concrete code.
- Type consistency:
  - Backend helper names are `failure()`, `register_exception_handlers()`, `_raise_task_integrity_error()`.
  - Frontend helper names are `getResponseErrorPayload()` and `handleResponseError()`.
  - Body codes are numeric and align with `HttpStatus` and `errorCode`.
