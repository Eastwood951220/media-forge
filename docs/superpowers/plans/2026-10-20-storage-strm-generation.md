# Storage-Queue-Idle STRM Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After the storage worker drains its main-task queue, wait for a configurable quiet period and then call an external STRM generation service, while exposing the service settings and a manual trigger in a new **刮削 / 刮削配置** page.

**Architecture:** A new backend module `backend/app/modules/scraping/` owns a dotenv-backed config service, an `httpx` client for the external service, a daemon-thread trigger tied to the storage worker drain, and a small FastAPI router. The storage worker sets its running flag to false on a natural drain and schedules the trigger; the trigger sleeps, re-checks worker/Redis/DB idle state, then calls the external service. The frontend adds a typed API module and one Ant Design configuration page, plus routing, sidebar, tab metadata, and README entries.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, httpx 0.28, python-dotenv, SQLAlchemy 2, Redis; React 19, TypeScript, Vite, Ant Design 6, TanStack Router, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-20-storage-strm-generation-design.md`

## Global Constraints

- Do not create or use Git worktrees. Work in this checkout.
- Do not modify `shared/runtime_config.py`. Resolve the scraping config path with `RuntimeConfigPaths.from_env().config_dir / "scraping.conf"`.
- Do not add database tables or Alembic migrations.
- Trigger delay is **default 30 seconds, minimum 10, maximum 3600**.
- The external call uses `POST {base_url}/api/sync/path/start` with `api_key` as a URL query parameter and `{"id": directory_id}` as the JSON body. Timeout is 30 seconds. No retries.
- Never log or return the raw API key. Masked GET values preserve the stored key on PUT.
- Automatic trigger failures are logged only; they never retry or affect the storage task.
- The trigger is global: one storage queue and one configured directory ID.
- Single backend process assumption: an in-memory generation counter coordinates delay checks. Document that an in-process restart loses a pending delay and the manual button remains available.
- Backend tests are split by concern for focused runs: `test_scraping_config_service.py`, `test_scraping_strm_client.py`, `test_scraping_api.py`, and `test_scraping_strm_trigger.py`. This refines the spec's broader two-file list without changing production behavior.
- The frontend page keeps two tiny shared helpers in `pages/scraping/config/utils/error.ts`; this is a page-local detail, not a new module.
- Stage intended files explicitly. Never use `git add .` or `git add -A`.
- Backend verification from `backend/`: `python -m pytest tests/<file> -v`.
- Frontend verification from `frontend/`: `pnpm build` and `pnpm test -- <path>`.

---

## Task 1: Scraping Config Schemas And Service

**Files:**
- Create: `backend/app/modules/scraping/__init__.py`
- Create: `backend/app/modules/scraping/schemas.py`
- Create: `backend/app/modules/scraping/config.py`
- Create: `backend/tests/test_scraping_config_service.py`

**Interfaces:**
- Consumes: `RuntimeConfigPaths.from_env()`, `dotenv_values(..., interpolate=False)`.
- Produces: `ScrapingConfig`, `ScrapingConfigUpdate`, `ScrapingConfigResponse`, `ScrapingConfigService(config_file: Path | None = None)`, `validate_run_config(config: Mapping[str, Any]) -> str | None`.

- [ ] **Step 1: Write the failing service tests**

Create `backend/tests/test_scraping_config_service.py`:

```python
from pathlib import Path

import pytest

from backend.app.modules.scraping.config import ScrapingConfigService
from backend.app.modules.scraping.schemas import ScrapingConfigUpdate


def _service(tmp_path: Path) -> ScrapingConfigService:
    return ScrapingConfigService(config_file=tmp_path / "scraping.conf")


def test_defaults_without_config_file(tmp_path: Path) -> None:
    assert _service(tmp_path).get_public_config() == {
        "base_url": "",
        "api_key": "",
        "api_key_configured": False,
        "directory_id": None,
        "trigger_delay_seconds": 30,
    }


def test_update_writes_conf_and_masks_the_key(tmp_path: Path) -> None:
    service = _service(tmp_path)

    public = service.update_config(
        ScrapingConfigUpdate(
            base_url="https://example.com/",
            api_key="secret-key-1234",
            directory_id=4,
            trigger_delay_seconds=45,
        )
    )

    assert public["base_url"] == "https://example.com"
    assert public["api_key"] == "************1234"
    assert public["api_key_configured"] is True

    text = (tmp_path / "scraping.conf").read_text(encoding="utf-8")
    assert "base_url=https://example.com\n" in text
    assert "api_key=secret-key-1234\n" in text
    assert "directory_id=4\n" in text
    assert "trigger_delay_seconds=45\n" in text


def test_masked_or_empty_key_preserves_the_stored_key(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.update_config(ScrapingConfigUpdate(api_key="secret-key-1234"))

    service.update_config(
        ScrapingConfigUpdate(
            api_key="************1234",
            base_url="https://new.example.com",
        )
    )
    service.update_config(ScrapingConfigUpdate(api_key=""))

    text = (tmp_path / "scraping.conf").read_text(encoding="utf-8")
    assert "api_key=secret-key-1234\n" in text
    assert "base_url=https://new.example.com\n" in text


def test_explicit_null_clears_directory_id(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.update_config(ScrapingConfigUpdate(directory_id=4))

    public = service.update_config(ScrapingConfigUpdate(directory_id=None))

    assert public["directory_id"] is None
    assert "directory_id=\n" in (tmp_path / "scraping.conf").read_text(encoding="utf-8")


def test_numeric_api_key_stays_a_string(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.update_config(ScrapingConfigUpdate(api_key="12345678"))

    assert service.get_raw_config()["api_key"] == "12345678"


def test_invalid_base_url_is_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(ValueError, match="http://"):
        service.update_config(ScrapingConfigUpdate(base_url="ftp://example.com"))


def test_invalid_persisted_values_fall_back_to_defaults(tmp_path: Path) -> None:
    (tmp_path / "scraping.conf").write_text(
        "base_url=https://example.com\n"
        "api_key=abc\n"
        "directory_id=0\n"
        "trigger_delay_seconds=1\n",
        encoding="utf-8",
    )

    raw = _service(tmp_path).get_raw_config()

    assert raw["base_url"] == "https://example.com"
    assert raw["api_key"] == "abc"
    assert raw["directory_id"] is None
    assert raw["trigger_delay_seconds"] == 30
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_scraping_config_service.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'backend.app.modules.scraping'`.

- [ ] **Step 3: Implement the schemas**

Create `backend/app/modules/scraping/__init__.py` as an empty file.

Create `backend/app/modules/scraping/schemas.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class ScrapingConfig(BaseModel):
    """Persisted scraping settings."""

    base_url: str = ""
    api_key: str = ""
    directory_id: int | None = Field(default=None, ge=1)
    trigger_delay_seconds: int = Field(default=30, ge=10, le=3600)


class ScrapingConfigUpdate(BaseModel):
    """Partial update; omitted fields keep their stored values."""

    base_url: str | None = None
    api_key: str | None = None
    directory_id: int | None = Field(default=None, ge=1)
    trigger_delay_seconds: int | None = Field(default=None, ge=10, le=3600)


class ScrapingConfigResponse(ScrapingConfig):
    api_key: str = ""
    api_key_configured: bool = False
```

- [ ] **Step 4: Implement the config service**

Create `backend/app/modules/scraping/config.py`:

```python
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import ValidationError

from backend.app.modules.scraping.schemas import (
    ScrapingConfig,
    ScrapingConfigResponse,
    ScrapingConfigUpdate,
)
from shared.runtime_config import RuntimeConfigPaths


def mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) < 8:
        return "****"
    return f"{'*' * 12}{token[-4:]}"


def is_masked_token(token: str) -> bool:
    if not token:
        return False
    prefix = token[:-4] if len(token) > 4 else token
    return len(prefix) >= 4 and set(prefix) == {"*"}


def _serialize_value(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ValueError("刮削配置值不能包含换行")
    if not text or any(char.isspace() for char in text) or "#" in text:
        return json.dumps(text, ensure_ascii=False)
    return text


def _normalize_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if normalized and not normalized.startswith(("http://", "https://")):
        raise ValueError("外部服务地址必须以 http:// 或 https:// 开头")
    return normalized


def _coerce_directory_id(value: str | None) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = int(text)
    except ValueError:
        return None
    return parsed if parsed >= 1 else None


def _coerce_delay(value: str | None) -> int:
    text = (value or "").strip()
    try:
        parsed = int(text)
    except ValueError:
        return 30
    return parsed if 10 <= parsed <= 3600 else 30


class ScrapingConfigService:
    """Read and write scraping settings in a dotenv style file."""

    def __init__(self, config_file: Path | None = None) -> None:
        if config_file is None:
            config_file = RuntimeConfigPaths.from_env().config_dir / "scraping.conf"
        self.config_file = config_file

    def get_public_config(self) -> dict[str, Any]:
        return self._public_config(self.get_raw_config())

    def get_raw_config(self) -> dict[str, Any]:
        defaults = ScrapingConfig().model_dump()
        if not self.config_file.exists():
            return defaults

        parsed = dotenv_values(self.config_file, interpolate=False)
        values = dict(defaults)
        values["base_url"] = str(parsed.get("base_url") or "").strip()
        values["api_key"] = str(parsed.get("api_key") or "")
        values["directory_id"] = _coerce_directory_id(parsed.get("directory_id"))
        values["trigger_delay_seconds"] = _coerce_delay(parsed.get("trigger_delay_seconds"))
        try:
            return ScrapingConfig(**values).model_dump()
        except ValidationError:
            return defaults

    def update_config(
        self,
        body: ScrapingConfigUpdate | Mapping[str, Any],
    ) -> dict[str, Any]:
        current = self.get_raw_config()
        if hasattr(body, "model_dump"):
            incoming = body.model_dump(exclude_unset=True)
        else:
            incoming = dict(body)

        if incoming.get("trigger_delay_seconds") is None:
            incoming.pop("trigger_delay_seconds", None)
        if "base_url" in incoming:
            incoming["base_url"] = _normalize_base_url(str(incoming.get("base_url") or ""))
        if "api_key" in incoming:
            key = str(incoming.get("api_key") or "")
            incoming["api_key"] = current.get("api_key", "") if not key or is_masked_token(key) else key

        merged = dict(current)
        merged.update(incoming)
        validated = ScrapingConfig(**merged).model_dump()
        self._write_config(validated)
        return self._public_config(validated)

    def _public_config(self, config: dict[str, Any]) -> dict[str, Any]:
        raw_key = str(config.get("api_key") or "")
        public = dict(config)
        public["api_key"] = mask_token(raw_key)
        public["api_key_configured"] = bool(raw_key)
        return ScrapingConfigResponse(**public).model_dump()

    def _write_config(self, data: dict[str, Any]) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(f"{key}={_serialize_value(value)}\n" for key, value in data.items())
        temp_path = self.config_file.with_suffix(self.config_file.suffix + ".tmp")
        temp_path.write_text(body, encoding="utf-8")
        temp_path.replace(self.config_file)


def validate_run_config(config: Mapping[str, Any]) -> str | None:
    """Return a human-readable reason when the config is not runnable."""
    base_url = str(config.get("base_url") or "").strip()
    if not base_url:
        return "未配置外部服务地址"
    if not base_url.startswith(("http://", "https://")):
        return "外部服务地址无效"
    if not str(config.get("api_key") or "").strip():
        return "未配置 API Key"
    if config.get("directory_id") in (None, ""):
        return "未配置目录 ID"
    return None
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_scraping_config_service.py -v
```

Expected: `7 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/scraping/__init__.py \
  backend/app/modules/scraping/schemas.py \
  backend/app/modules/scraping/config.py \
  backend/tests/test_scraping_config_service.py
git diff --cached --name-only
git commit -m "feat(scraping): add scraping configuration service"
```

---

## Task 2: External STRM Client

**Files:**
- Create: `backend/app/modules/scraping/strm.py`
- Create: `backend/tests/test_scraping_strm_client.py`

**Interfaces:**
- Consumes: `ScrapingConfig` raw dict, optional `httpx.BaseTransport`.
- Produces: `run_strm_generation(config: Mapping[str, Any], *, transport: httpx.BaseTransport | None = None) -> StrmRunResult`.

- [ ] **Step 1: Write the failing client tests**

Create `backend/tests/test_scraping_strm_client.py`:

```python
import json

import httpx

from backend.app.modules.scraping.strm import run_strm_generation


def _config() -> dict:
    return {
        "base_url": "https://example.com/",
        "api_key": "secret-key",
        "directory_id": 4,
        "trigger_delay_seconds": 30,
    }


def test_run_posts_the_expected_request() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    result = run_strm_generation(_config(), transport=httpx.MockTransport(handler))

    assert result.success is True
    assert result.status_code == 200
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/sync/path/start"
    assert captured["query"] == {"api_key": "secret-key"}
    assert captured["body"] == {"id": 4}


def test_non_2xx_returns_a_failure_result() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    result = run_strm_generation(_config(), transport=httpx.MockTransport(handler))

    assert result.success is False
    assert result.status_code == 500
    assert "HTTP 500" in result.message
    assert "boom" in result.message


def test_connect_error_is_captured_and_the_key_is_redacted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed to connect to {request.url}")

    result = run_strm_generation(_config(), transport=httpx.MockTransport(handler))

    assert result.success is False
    assert result.status_code is None
    assert "secret-key" not in result.message
    assert "***" in result.message


def test_long_response_body_is_truncated() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="x" * 1000)

    result = run_strm_generation(_config(), transport=httpx.MockTransport(handler))

    assert "x" * 300 in result.message
    assert "x" * 301 not in result.message
    assert result.message.endswith("...")


def test_httpx_request_log_redacts_the_api_key(caplog) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    with caplog.at_level("INFO", logger="httpx"):
        run_strm_generation(_config(), transport=httpx.MockTransport(handler))

    assert "secret-key" not in caplog.text
    assert "api_key=***" in caplog.text
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_scraping_strm_client.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'backend.app.modules.scraping.strm'`.

- [ ] **Step 3: Implement the client**

Create `backend/app/modules/scraping/strm.py`:

```python
from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

REQUEST_TIMEOUT_SECONDS = 30.0
BODY_EXCERPT_LIMIT = 300


@dataclass
class StrmRunResult:
    success: bool
    status_code: int | None
    message: str


_HTTPX_API_KEY_PATTERN = re.compile(r"(api_key=)[^&\s]+")


class _RedactApiKeyFilter(logging.Filter):
    """Redact the api_key query parameter from httpx request log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not isinstance(record.args, tuple):
            return True
        args = list(record.args)
        changed = False
        for index, value in enumerate(args):
            if isinstance(value, httpx.URL):
                text = str(value)
                redacted = _HTTPX_API_KEY_PATTERN.sub(r"\1***", text)
                if redacted != text:
                    args[index] = redacted
                    changed = True
        if changed:
            record.args = tuple(args)
        return True


logging.getLogger("httpx").addFilter(_RedactApiKeyFilter())


def _redact(text: str, api_key: str) -> str:
    if api_key:
        return text.replace(api_key, "***")
    return text


def _excerpt(response: httpx.Response) -> str:
    try:
        text = response.text
    except Exception:
        return ""
    collapsed = " ".join(text.split())
    if len(collapsed) > BODY_EXCERPT_LIMIT:
        return collapsed[:BODY_EXCERPT_LIMIT] + "..."
    return collapsed


def _message(status_code: int | None, body: str) -> str:
    message = f"HTTP {status_code}" if status_code is not None else "HTTP 请求失败"
    if body:
        message = f"{message}: {body}"
    return message


def run_strm_generation(
    config: Mapping[str, Any],
    *,
    transport: httpx.BaseTransport | None = None,
) -> StrmRunResult:
    base_url = str(config.get("base_url") or "").strip().rstrip("/")
    api_key = str(config.get("api_key") or "")
    directory_id = config.get("directory_id")
    url = f"{base_url}/api/sync/path/start"

    try:
        with httpx.Client(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
            transport=transport,
        ) as client:
            response = client.post(
                url,
                params={"api_key": api_key},
                json={"id": directory_id},
            )
            response.raise_for_status()
            return StrmRunResult(
                success=True,
                status_code=response.status_code,
                message=_redact(_message(response.status_code, _excerpt(response)), api_key),
            )
    except httpx.HTTPStatusError as exc:
        return StrmRunResult(
            success=False,
            status_code=exc.response.status_code,
            message=_redact(
                _message(exc.response.status_code, _excerpt(exc.response)),
                api_key,
            ),
        )
    except httpx.HTTPError as exc:
        return StrmRunResult(
            success=False,
            status_code=None,
            message=_redact(f"{type(exc).__name__}: {exc}", api_key),
        )
    except Exception as exc:
        return StrmRunResult(
            success=False,
            status_code=None,
            message=_redact(f"{type(exc).__name__}: {exc}", api_key),
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_scraping_strm_client.py -v
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/scraping/strm.py backend/tests/test_scraping_strm_client.py
git diff --cached --name-only
git commit -m "feat(scraping): add external STRM generation client"
```

---

## Task 3: Scraping HTTP API

**Files:**
- Create: `backend/app/modules/scraping/router.py`
- Modify: `backend/app/main.py` (import and register `scraping_router`)
- Create: `backend/tests/test_scraping_api.py`

**Interfaces:**
- Consumes: `ScrapingConfigService`, `validate_run_config`, `run_strm_generation`, `CurrentUser`, `success`.
- Produces: `GET /api/scraping/config`, `PUT /api/scraping/config`, `POST /api/scraping/strm/run`.

- [ ] **Step 1: Write the failing API tests**

Create `backend/tests/test_scraping_api.py`:

```python
from http import HTTPStatus

from backend.app.modules.scraping.strm import StrmRunResult


def _auth_headers(client, admin_user) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _write_config(tmp_path) -> None:
    (tmp_path / "scraping.conf").write_text(
        "base_url=https://example.com\n"
        "api_key=secret-key\n"
        "directory_id=4\n"
        "trigger_delay_seconds=30\n",
        encoding="utf-8",
    )


def test_get_and_put_scraping_config(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    headers = _auth_headers(client, admin_user)

    get_response = client.get("/api/scraping/config", headers=headers)

    assert get_response.status_code == HTTPStatus.OK
    assert get_response.json()["data"] == {
        "base_url": "",
        "api_key": "",
        "api_key_configured": False,
        "directory_id": None,
        "trigger_delay_seconds": 30,
    }

    put_response = client.put(
        "/api/scraping/config",
        headers=headers,
        json={
            "base_url": "https://example.com/",
            "api_key": "secret-key-1234",
            "directory_id": 4,
            "trigger_delay_seconds": 45,
        },
    )

    assert put_response.status_code == HTTPStatus.OK
    data = put_response.json()["data"]
    assert data["base_url"] == "https://example.com"
    assert data["api_key"] == "************1234"
    assert data["api_key_configured"] is True
    assert (tmp_path / "scraping.conf").exists()

    preserved = client.put(
        "/api/scraping/config",
        headers=headers,
        json={"api_key": "************1234", "base_url": "https://new.example.com"},
    )
    assert preserved.json()["data"]["api_key"] == "************1234"


def test_put_rejects_invalid_base_url(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    headers = _auth_headers(client, admin_user)

    response = client.put(
        "/api/scraping/config",
        headers=headers,
        json={"base_url": "ftp://example.com"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_put_rejects_out_of_range_values(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    headers = _auth_headers(client, admin_user)

    too_short = client.put(
        "/api/scraping/config",
        headers=headers,
        json={"trigger_delay_seconds": 5},
    )
    bad_directory = client.put(
        "/api/scraping/config",
        headers=headers,
        json={"directory_id": 0},
    )

    assert too_short.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert bad_directory.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_manual_run_rejects_unconfigured_service(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    headers = _auth_headers(client, admin_user)

    response = client.post("/api/scraping/strm/run", headers=headers)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "未配置外部服务地址" in response.json()["detail"]


def test_manual_run_returns_the_external_result(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    _write_config(tmp_path)
    headers = _auth_headers(client, admin_user)

    from backend.app.modules.scraping import router as scraping_router

    monkeypatch.setattr(
        scraping_router,
        "run_strm_generation",
        lambda config: StrmRunResult(success=True, status_code=200, message="HTTP 200"),
    )

    response = client.post("/api/scraping/strm/run", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"] == {
        "success": True,
        "status_code": 200,
        "message": "HTTP 200",
    }


def test_manual_run_reports_external_failure_with_200(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    _write_config(tmp_path)
    headers = _auth_headers(client, admin_user)

    from backend.app.modules.scraping import router as scraping_router

    monkeypatch.setattr(
        scraping_router,
        "run_strm_generation",
        lambda config: StrmRunResult(
            success=False,
            status_code=503,
            message="HTTP 503: unavailable",
        ),
    )

    response = client.post("/api/scraping/strm/run", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["success"] is False
    assert response.json()["data"]["status_code"] == 503
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_scraping_api.py -v
```

Expected: `404 Not Found` for `/api/scraping/config` (and import/collection errors while `router.py` does not exist).

- [ ] **Step 3: Implement the router**

Create `backend/app/modules/scraping/router.py`:

```python
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status

from backend.app.core.dependencies import CurrentUser
from backend.app.modules.scraping.config import ScrapingConfigService, validate_run_config
from backend.app.modules.scraping.schemas import ScrapingConfigUpdate
from backend.app.modules.scraping.strm import run_strm_generation
from shared.schemas.common import success

router = APIRouter(prefix="/api/scraping", tags=["scraping"])


@router.get("/config")
def get_scraping_config(_current_user: CurrentUser) -> dict:
    return success(data=ScrapingConfigService().get_public_config())


@router.put("/config")
def update_scraping_config(
    body: ScrapingConfigUpdate,
    _current_user: CurrentUser,
) -> dict:
    try:
        return success(data=ScrapingConfigService().update_config(body))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/strm/run")
def run_scraping_strm(_current_user: CurrentUser) -> dict:
    config = ScrapingConfigService().get_raw_config()
    reason = validate_run_config(config)
    if reason is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
    return success(data=asdict(run_strm_generation(config)))
```

- [ ] **Step 4: Register the router**

Modify `backend/app/main.py` by adding this import next to the other module router imports:

```python
from backend.app.modules.scraping.router import router as scraping_router
```

Add this line to the router registration block, after `app.include_router(storage_tasks_router)`:

```python
app.include_router(scraping_router)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_scraping_api.py -v
```

Expected: `6 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/scraping/router.py backend/app/main.py backend/tests/test_scraping_api.py
git diff --cached --name-only
git commit -m "feat(scraping): expose scraping config and manual trigger API"
```

---

## Task 4: Pending Storage Queue Count

**Files:**
- Modify: `backend/app/modules/storage/runtime/redis_state.py`
- Modify: `backend/tests/test_storage_runtime_redis.py`

**Interfaces:**
- Produces: `StorageRuntimeState.pending_main_task_count() -> int` using Redis `LLEN` on `storage:main_queue`.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_storage_runtime_redis.py`, add `llen` to `FakeRedis`:

```python
    def llen(self, key):
        return len(self.lists.get(key, []))
```

Append this test:

```python
def test_pending_main_task_count() -> None:
    runtime = StorageRuntimeState(FakeRedis())

    assert runtime.pending_main_task_count() == 0

    runtime.enqueue_main_task("main-1")
    runtime.enqueue_main_task("main-2")
    assert runtime.pending_main_task_count() == 2

    runtime.claim_next_main_task()
    assert runtime.pending_main_task_count() == 1
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && python -m pytest tests/test_storage_runtime_redis.py::test_pending_main_task_count -v
```

Expected: `AttributeError: 'StorageRuntimeState' object has no attribute 'pending_main_task_count'`.

- [ ] **Step 3: Implement the method**

Modify `backend/app/modules/storage/runtime/redis_state.py` by adding this method next to `claim_next_main_task`:

```python
    def pending_main_task_count(self) -> int:
        return int(self.redis.llen(self.QUEUE_KEY) or 0)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd backend && python -m pytest tests/test_storage_runtime_redis.py -v
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/storage/runtime/redis_state.py backend/tests/test_storage_runtime_redis.py
git diff --cached --name-only
git commit -m "feat(storage): expose pending main task count"
```

---

## Task 5: Drain-Triggered STRM Scheduler

**Files:**
- Create: `backend/app/modules/scraping/trigger.py`
- Create: `backend/tests/test_scraping_strm_trigger.py`

**Interfaces:**
- Consumes: `StorageRuntimeState.pending_main_task_count()`, `get_session_factory()`, `StorageMainTask`, `ScrapingConfigService`, `validate_run_config`, `run_strm_generation`.
- Produces: `schedule_strm_after_storage_drain(runtime, *, is_worker_idle: Callable[[], bool]) -> None`.

- [ ] **Step 1: Write the failing trigger tests**

Create `backend/tests/test_scraping_strm_trigger.py`:

```python
import threading
from pathlib import Path
from unittest.mock import Mock

from backend.app.models.storage_task import StorageMainTask
from backend.app.modules.scraping import trigger
from backend.app.modules.scraping.strm import StrmRunResult
from backend.tests.conftest import TestingSessionLocal


class FakeRuntime:
    def __init__(self, pending: int = 0) -> None:
        self.pending = pending

    def pending_main_task_count(self) -> int:
        return self.pending


class BrokenRuntime:
    def pending_main_task_count(self) -> int:
        raise RuntimeError("redis unavailable")


def _prepare_trigger(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    (tmp_path / "scraping.conf").write_text(
        "base_url=https://example.com\n"
        "api_key=secret-key\n"
        "directory_id=4\n"
        "trigger_delay_seconds=10\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(trigger, "_sleep", lambda seconds: None)
    monkeypatch.setattr(trigger, "get_session_factory", lambda: TestingSessionLocal)
    monkeypatch.setattr(trigger, "_generation", 4)


def test_skips_when_the_worker_is_busy(monkeypatch, tmp_path: Path) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    called = Mock()
    monkeypatch.setattr(trigger, "run_strm_generation", called)

    trigger._run_after_delay(trigger._generation, 10, FakeRuntime(), lambda: False)

    called.assert_not_called()


def test_skips_when_the_redis_queue_has_tasks(monkeypatch, tmp_path: Path) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    called = Mock()
    monkeypatch.setattr(trigger, "run_strm_generation", called)

    trigger._run_after_delay(trigger._generation, 10, FakeRuntime(pending=1), lambda: True)

    called.assert_not_called()


def test_skips_when_the_database_has_pending_tasks(
    monkeypatch,
    tmp_path: Path,
    db_session,
    test_user,
) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    db_session.add(
        StorageMainTask(
            alias="a",
            display_name="a",
            source="single",
            storage_mode="single",
            status="queued",
            created_by=test_user.id,
        )
    )
    db_session.commit()
    called = Mock()
    monkeypatch.setattr(trigger, "run_strm_generation", called)

    trigger._run_after_delay(trigger._generation, 10, FakeRuntime(), lambda: True)

    called.assert_not_called()


def test_skips_when_the_queue_cannot_be_verified(monkeypatch, tmp_path: Path) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    called = Mock()
    monkeypatch.setattr(trigger, "run_strm_generation", called)

    trigger._run_after_delay(trigger._generation, 10, BrokenRuntime(), lambda: True)

    called.assert_not_called()


def test_skips_a_stale_generation(monkeypatch, tmp_path: Path) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    called = Mock()
    monkeypatch.setattr(trigger, "run_strm_generation", called)

    trigger._run_after_delay(trigger._generation - 1, 10, FakeRuntime(), lambda: True)

    called.assert_not_called()


def test_runs_when_all_checks_pass(monkeypatch, tmp_path: Path) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    calls: list[dict] = []

    def fake_run(config):
        calls.append(dict(config))
        return StrmRunResult(success=True, status_code=200, message="HTTP 200")

    monkeypatch.setattr(trigger, "run_strm_generation", fake_run)

    trigger._run_after_delay(trigger._generation, 10, FakeRuntime(), lambda: True)

    assert len(calls) == 1
    assert calls[0]["base_url"] == "https://example.com"
    assert calls[0]["api_key"] == "secret-key"
    assert calls[0]["directory_id"] == 4


def test_schedule_skips_an_unconfigured_service(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(trigger, "_generation", 4)

    trigger.schedule_strm_after_storage_drain(FakeRuntime(), is_worker_idle=lambda: True)

    assert trigger._generation == 4


def test_schedule_waits_then_runs(monkeypatch, tmp_path: Path) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    finished = threading.Event()

    def fake_run(config):
        finished.set()
        return StrmRunResult(success=True, status_code=200, message="HTTP 200")

    monkeypatch.setattr(trigger, "run_strm_generation", fake_run)

    trigger.schedule_strm_after_storage_drain(FakeRuntime(), is_worker_idle=lambda: True)

    assert finished.wait(1.0) is True


def test_failure_is_only_logged(monkeypatch, tmp_path: Path, caplog) -> None:
    _prepare_trigger(monkeypatch, tmp_path)
    monkeypatch.setattr(
        trigger,
        "run_strm_generation",
        lambda config: StrmRunResult(success=False, status_code=500, message="HTTP 500: down"),
    )

    with caplog.at_level("WARNING"):
        trigger._run_after_delay(trigger._generation, 10, FakeRuntime(), lambda: True)

    assert "STRM generation failed" in caplog.text
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_scraping_strm_trigger.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'backend.app.modules.scraping.trigger'`.

- [ ] **Step 3: Implement the trigger**

Create `backend/app/modules/scraping/trigger.py`:

```python
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from backend.app.models.storage_task import StorageMainTask
from backend.app.modules.scraping.config import ScrapingConfigService, validate_run_config
from backend.app.modules.scraping.strm import run_strm_generation
from shared.database.session import get_session_factory

logger = logging.getLogger(__name__)

PENDING_STATUSES = ("queued", "running", "stopping")

_generation_lock = threading.Lock()
_generation = 0


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _next_generation() -> int:
    global _generation
    with _generation_lock:
        _generation += 1
        return _generation


def _is_current_generation(generation: int) -> bool:
    with _generation_lock:
        return generation == _generation


def _is_storage_idle(runtime: Any, is_worker_idle: Callable[[], bool]) -> bool:
    if not is_worker_idle():
        return False
    try:
        if runtime.pending_main_task_count() > 0:
            return False
    except Exception:
        logger.warning(
            "Cannot confirm the storage queue is empty; skipping STRM generation",
            exc_info=True,
        )
        return False
    try:
        factory = get_session_factory()
        with factory() as session:
            pending = (
                session.query(StorageMainTask.id)
                .filter(StorageMainTask.status.in_(PENDING_STATUSES))
                .first()
            )
        return pending is None
    except Exception:
        logger.warning(
            "Cannot confirm storage tasks are idle; skipping STRM generation",
            exc_info=True,
        )
        return False


def _run_after_delay(
    generation: int,
    delay_seconds: int,
    runtime: Any,
    is_worker_idle: Callable[[], bool],
) -> None:
    try:
        _sleep(delay_seconds)
        if not _is_current_generation(generation):
            logger.info("Skipping STRM generation: a newer storage drain scheduled it")
            return
        if not _is_storage_idle(runtime, is_worker_idle):
            logger.info("Skipping STRM generation: storage is still busy")
            return

        config = ScrapingConfigService().get_raw_config()
        reason = validate_run_config(config)
        if reason is not None:
            logger.info("Skipping STRM generation: %s", reason)
            return

        if not _is_current_generation(generation) or not is_worker_idle():
            logger.info("Skipping STRM generation: storage became busy during the final check")
            return

        result = run_strm_generation(config)
        if result.success:
            logger.info("STRM generation triggered: %s", result.message)
        else:
            logger.warning("STRM generation failed: %s", result.message)
    except Exception:
        logger.exception("STRM generation check failed")


def schedule_strm_after_storage_drain(
    runtime: Any,
    *,
    is_worker_idle: Callable[[], bool],
) -> None:
    try:
        config = ScrapingConfigService().get_raw_config()
        reason = validate_run_config(config)
        if reason is not None:
            logger.info("Not scheduling STRM generation: %s", reason)
            return

        generation = _next_generation()
        delay = int(config.get("trigger_delay_seconds") or 30)
        thread = threading.Thread(
            target=_run_after_delay,
            args=(generation, delay, runtime, is_worker_idle),
            daemon=True,
            name=f"strm-trigger-{generation}",
        )
        thread.start()
    except Exception:
        logger.exception("Failed to schedule STRM generation")
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_scraping_strm_trigger.py -v
```

Expected: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/scraping/trigger.py backend/tests/test_scraping_strm_trigger.py
git diff --cached --name-only
git commit -m "feat(scraping): schedule STRM generation after storage drain"
```

---

## Task 6: Storage Worker Drain Integration

**Files:**
- Modify: `backend/app/modules/storage/worker/runner.py`
- Modify: `backend/tests/test_storage_worker_service.py`

**Interfaces:**
- Consumes: `schedule_strm_after_storage_drain(runtime, is_worker_idle=is_storage_worker_idle)`.
- Produces: `is_storage_worker_idle() -> bool`; the worker schedules a trigger exactly once per natural drain that processed at least one task.

- [ ] **Step 1: Write the failing worker tests**

In `backend/tests/test_storage_worker_service.py`, replace `test_worker_loop_rechecks_queue_before_stopping` with:

```python
def test_worker_loop_rechecks_queue_before_stopping(monkeypatch):
    from backend.app.modules.storage.worker import runner

    class RaceRuntime:
        def __init__(self) -> None:
            self.claims = 0

        def claim_next_main_task(self):
            self.claims += 1
            if self.claims == 2:
                return "task-added-during-stop"
            return None

    processed: list[str] = []
    scheduled: list[tuple[object, object]] = []

    def fake_process_main_task(runtime, provider_factory, config_service, task_id: str) -> bool:
        processed.append(task_id)
        return True

    def fake_schedule(runtime, *, is_worker_idle):
        scheduled.append((runtime, is_worker_idle))

    monkeypatch.setattr(runner, "process_main_task", fake_process_main_task)
    monkeypatch.setattr(runner, "schedule_strm_after_storage_drain", fake_schedule)
    monkeypatch.setattr(runner, "_worker_running", True)

    runtime = RaceRuntime()
    runner._worker_loop(runtime, object(), object())

    assert processed == ["task-added-during-stop"]
    assert runner._worker_running is False
    assert len(scheduled) == 1
    assert scheduled[0][0] is runtime
    assert scheduled[0][1] is runner.is_storage_worker_idle
    assert runner.is_storage_worker_idle() is True


def test_worker_loop_does_not_schedule_without_processing_a_task(monkeypatch):
    from backend.app.modules.storage.worker import runner

    class EmptyRuntime:
        def claim_next_main_task(self):
            return None

    scheduled: list[object] = []

    def fake_schedule(runtime, *, is_worker_idle):
        scheduled.append(runtime)

    monkeypatch.setattr(runner, "schedule_strm_after_storage_drain", fake_schedule)
    monkeypatch.setattr(runner, "_worker_running", True)

    runner._worker_loop(EmptyRuntime(), object(), object())

    assert scheduled == []
    assert runner._worker_running is False
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_storage_worker_service.py -k worker_loop -v
```

Expected: the first test fails because `runner.schedule_strm_after_storage_drain` is not patched (the real function is called) or because `runner.is_storage_worker_idle` does not exist; the second fails because no scheduling hook exists.

- [ ] **Step 3: Implement the idle helper and drain hook**

Modify `backend/app/modules/storage/worker/runner.py`.

Add this import after `from backend.app.models.storage_task import StorageMainTask`:

```python
from backend.app.modules.scraping.trigger import schedule_strm_after_storage_drain
```

Add this function after `ensure_storage_worker_started`:

```python
def is_storage_worker_idle() -> bool:
    with _worker_lock:
        return not _worker_running
```

Replace `_worker_loop` with:

```python
def _worker_loop(runtime, provider_factory, config_service) -> None:
    global _worker_running
    processed_any = False
    try:
        while True:
            task_id = runtime.claim_next_main_task()
            if task_id is None:
                with _worker_lock:
                    task_id = runtime.claim_next_main_task()
                    if task_id is None:
                        _worker_running = False
                        break
            processed_any = True
            try:
                process_main_task(runtime, provider_factory, config_service, task_id)
            except Exception:
                logger.exception("Storage worker failed while processing main task %s", task_id)
    except Exception:
        logger.exception("Storage worker loop crashed")
        with _worker_lock:
            _worker_running = False
        raise

    if processed_any:
        try:
            schedule_strm_after_storage_drain(
                runtime,
                is_worker_idle=is_storage_worker_idle,
            )
        except Exception:
            logger.exception("Failed to schedule STRM generation after storage drain")
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_storage_worker_service.py -k worker_loop -v
```

Expected: `2 passed`.

- [ ] **Step 5: Run the storage worker regression tests**

```bash
cd backend && python -m pytest tests/test_storage_worker_service.py -v
```

Expected: all tests in the file pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/storage/worker/runner.py backend/tests/test_storage_worker_service.py
git diff --cached --name-only
git commit -m "feat(storage): trigger STRM generation when the worker drains"
```

---

## Task 7: Frontend Scraping Configuration Page

**Files:**
- Create: `frontend/src/api/scraping/scrapingConfig/types.ts`
- Create: `frontend/src/api/scraping/scrapingConfig/index.ts`
- Create: `frontend/src/pages/scraping/config/ScrapingConfigPage.tsx`
- Create: `frontend/src/pages/scraping/config/ScrapingConfigPage.module.less`
- Create: `frontend/src/pages/scraping/config/utils/error.ts`
- Create: `frontend/src/pages/scraping/config/__tests__/ScrapingConfigPage.test.tsx`
- Modify: `frontend/src/routes/index.tsx`
- Modify: `frontend/src/routes/tags.ts`
- Modify: `frontend/src/layout/Sidebar/index.tsx`
- Modify: `frontend/README.md`

**Interfaces:**
- Consumes: `GET /api/scraping/config`, `PUT /api/scraping/config`, `POST /api/scraping/strm/run`.
- Produces: route `/scraping/config`, sidebar group 刮削 with child 刮削配置, tab title 刮削配置, API functions `getScrapingConfig`, `updateScrapingConfig`, `runScrapingStrm`.

- [ ] **Step 1: Write the failing page test**

Create `frontend/src/pages/scraping/config/__tests__/ScrapingConfigPage.test.tsx`:

```tsx
import { App as AntApp } from 'antd'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScrapingConfigPage from '../ScrapingConfigPage'
import {
  getScrapingConfig,
  runScrapingStrm,
  updateScrapingConfig,
} from '@/api/scraping/scrapingConfig'

vi.mock('@/api/scraping/scrapingConfig', () => ({
  getScrapingConfig: vi.fn(),
  updateScrapingConfig: vi.fn(),
  runScrapingStrm: vi.fn(),
}))

const savedConfig = {
  base_url: 'https://example.com',
  api_key: '************1234',
  api_key_configured: true,
  directory_id: 4,
  trigger_delay_seconds: 30,
}

function renderPage() {
  return render(
    <AntApp>
      <ScrapingConfigPage />
    </AntApp>,
  )
}

describe('ScrapingConfigPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getScrapingConfig).mockResolvedValue(savedConfig)
    vi.mocked(updateScrapingConfig).mockResolvedValue(savedConfig)
    vi.mocked(runScrapingStrm).mockResolvedValue({
      success: true,
      status_code: 200,
      message: 'HTTP 200',
    })
  })

  it('loads the saved config', async () => {
    renderPage()

    expect(await screen.findByDisplayValue('https://example.com')).toBeInTheDocument()
    expect(screen.getByText('已配置: ************1234')).toBeInTheDocument()
  })

  it('does not send an untouched api key when saving', async () => {
    renderPage()
    const baseUrl = await screen.findByLabelText('服务地址')
    fireEvent.change(baseUrl, { target: { value: 'https://new.example.com' } })

    fireEvent.click(screen.getByRole('button', { name: '保存配置' }))

    await waitFor(() => expect(updateScrapingConfig).toHaveBeenCalled())
    const payload = vi.mocked(updateScrapingConfig).mock.calls[0][0]
    expect(payload.base_url).toBe('https://new.example.com')
    expect(payload).not.toHaveProperty('api_key')
  })

  it('saves before running the manual trigger', async () => {
    renderPage()
    await screen.findByDisplayValue('https://example.com')

    fireEvent.click(screen.getByRole('button', { name: '立即生成' }))

    await waitFor(() => expect(runScrapingStrm).toHaveBeenCalled())
    expect(vi.mocked(updateScrapingConfig).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(runScrapingStrm).mock.invocationCallOrder[0],
    )
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && pnpm test -- src/pages/scraping/config/__tests__/ScrapingConfigPage.test.tsx
```

Expected: the test file fails to resolve `../ScrapingConfigPage` and `@/api/scraping/scrapingConfig`.

- [ ] **Step 3: Implement the API module**

Create `frontend/src/api/scraping/scrapingConfig/types.ts`:

```ts
export interface ScrapingConfig {
  base_url: string
  api_key: string
  api_key_configured: boolean
  directory_id: number | null
  trigger_delay_seconds: number
}

export interface ScrapingConfigUpdate {
  base_url?: string
  api_key?: string
  directory_id?: number | null
  trigger_delay_seconds?: number
}

export interface ScrapingRunResult {
  success: boolean
  status_code: number | null
  message: string
}
```

Create `frontend/src/api/scraping/scrapingConfig/index.ts`:

```ts
import { request } from '@/request'
import type {
  ScrapingConfig,
  ScrapingConfigUpdate,
  ScrapingRunResult,
} from './types.ts'

export type {
  ScrapingConfig,
  ScrapingConfigUpdate,
  ScrapingRunResult,
} from './types.ts'

const BASE_URL = '/api/scraping'

export function getScrapingConfig(): Promise<ScrapingConfig> {
  return request.get<ScrapingConfig>(`${BASE_URL}/config`)
}

export function updateScrapingConfig(data: ScrapingConfigUpdate): Promise<ScrapingConfig> {
  return request.put<ScrapingConfig>(`${BASE_URL}/config`, data)
}

export function runScrapingStrm(): Promise<ScrapingRunResult> {
  return request.post<ScrapingRunResult>(`${BASE_URL}/strm/run`)
}
```

- [ ] **Step 4: Implement the page helpers and page**

Create `frontend/src/pages/scraping/config/utils/error.ts`:

```ts
export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return '操作失败'
}

export function isFormValidationError(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'errorFields' in error
}
```

Create `frontend/src/pages/scraping/config/ScrapingConfigPage.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  Spin,
  Tag,
} from 'antd'
import {
  ApiOutlined,
  ClockCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  getScrapingConfig,
  runScrapingStrm,
  updateScrapingConfig,
  type ScrapingConfig,
  type ScrapingConfigUpdate,
} from '@/api/scraping/scrapingConfig'
import { FullWidthNumberInput } from '@/components/common'
import { getErrorMessage, isFormValidationError } from './utils/error'
import styles from './ScrapingConfigPage.module.less'

type FormValues = {
  base_url: string
  api_key?: string
  directory_id: number
  trigger_delay_seconds: number
}

export default function ScrapingConfigPage() {
  const { message } = App.useApp()
  const [form] = Form.useForm<FormValues>()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [apiKeyConfigured, setApiKeyConfigured] = useState(false)
  const [maskedApiKey, setMaskedApiKey] = useState('')

  const applyConfig = useCallback(
    (config: ScrapingConfig) => {
      form.setFieldsValue({
        base_url: config.base_url,
        api_key: '',
        directory_id: config.directory_id ?? undefined,
        trigger_delay_seconds: config.trigger_delay_seconds,
      })
      setApiKeyConfigured(config.api_key_configured)
      setMaskedApiKey(config.api_key)
    },
    [form],
  )

  const loadConfig = useCallback(async () => {
    setLoading(true)
    try {
      applyConfig(await getScrapingConfig())
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [applyConfig, message])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Initial config load on mount is intentional.
    void loadConfig()
  }, [loadConfig])

  const buildPayload = (values: FormValues): ScrapingConfigUpdate => {
    const payload: ScrapingConfigUpdate = {
      base_url: values.base_url,
      directory_id: values.directory_id,
      trigger_delay_seconds: values.trigger_delay_seconds,
    }
    if (values.api_key?.trim()) {
      payload.api_key = values.api_key.trim()
    }
    return payload
  }

  const persist = async (values: FormValues): Promise<ScrapingConfig> => {
    const updated = await updateScrapingConfig(buildPayload(values))
    applyConfig(updated)
    return updated
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await persist(await form.validateFields())
      message.success('刮削配置已保存')
    } catch (error: unknown) {
      if (isFormValidationError(error)) return
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleRun = async () => {
    setRunning(true)
    try {
      await persist(await form.validateFields())
      const result = await runScrapingStrm()
      if (result.success) {
        message.success(result.message || 'STRM 生成已触发')
      } else {
        message.error(result.message || 'STRM 生成失败')
      }
    } catch (error: unknown) {
      if (isFormValidationError(error)) return
      message.error(getErrorMessage(error))
    } finally {
      setRunning(false)
    }
  }

  const delaySeconds = Form.useWatch('trigger_delay_seconds', form) ?? 30

  return (
    <div className={styles.page}>
      <Spin spinning={loading}>
        <Form form={form} layout="vertical">
          <div className={styles.layout}>
            <div className={styles.mainPanel}>
              <Card
                title={
                  <span className={styles.sectionTitle}>
                    <ApiOutlined />
                    服务配置
                  </span>
                }
                className={styles.formCard}
              >
                <div className={styles.fieldGrid}>
                  <Form.Item
                    name="base_url"
                    label="服务地址"
                    rules={[{ required: true, message: '请输入外部服务地址' }]}
                  >
                    <Input placeholder="https://2756e03c9b1c-1.eastwood951220.5ddd.com" />
                  </Form.Item>

                  <Form.Item className={styles.fieldSpan2} label="API Key">
                    <div className={styles.tokenStack}>
                      {apiKeyConfigured && (
                        <Tag color="blue">已配置: {maskedApiKey}</Tag>
                      )}
                      <Form.Item
                        name="api_key"
                        noStyle
                        rules={[
                          {
                            validator: (_, value?: string) =>
                              apiKeyConfigured || value?.trim()
                                ? Promise.resolve()
                                : Promise.reject(new Error('请输入 API Key')),
                          },
                        ]}
                      >
                        <Input.Password placeholder="留空保持不变" />
                      </Form.Item>
                    </div>
                  </Form.Item>

                  <Form.Item
                    name="directory_id"
                    label="目录 ID"
                    rules={[{ required: true, message: '请输入目录 ID' }]}
                  >
                    <FullWidthNumberInput min={1} placeholder="4" />
                  </Form.Item>
                </div>
              </Card>

              <Card
                title={
                  <span className={styles.sectionTitle}>
                    <ClockCircleOutlined />
                    自动触发
                  </span>
                }
                className={styles.formCard}
              >
                <div className={styles.fieldGrid}>
                  <Form.Item
                    name="trigger_delay_seconds"
                    label="触发等待时间（秒）"
                    rules={[{ required: true, message: '请输入触发等待时间' }]}
                  >
                    <FullWidthNumberInput min={10} max={3600} />
                  </Form.Item>
                </div>
                <Alert
                  type="info"
                  showIcon
                  message={`存储队列空闲 ${delaySeconds} 秒后自动调用；等待期间有新任务会重新计时。`}
                />
              </Card>
            </div>

            <div className={styles.sidePanel}>
              <Card
                title="操作"
                className={`${styles.formCard} ${styles.actionCard}`}
              >
                <div className={styles.actions}>
                  <Button
                    type="primary"
                    onClick={() => void handleSave()}
                    loading={saving}
                    disabled={running}
                  >
                    保存配置
                  </Button>
                  <Button
                    icon={<ThunderboltOutlined />}
                    onClick={() => void handleRun()}
                    loading={running}
                    disabled={saving}
                  >
                    立即生成
                  </Button>
                </div>
              </Card>
            </div>
          </div>
        </Form>
      </Spin>
    </div>
  )
}
```

Create `frontend/src/pages/scraping/config/ScrapingConfigPage.module.less`:

```less
.page {
  width: 100%;
}

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 340px);
  gap: 20px;
  align-items: start;
}

.mainPanel,
.sidePanel {
  min-width: 0;
}

.mainPanel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.formCard {
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);

  &:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }
}

.fieldGrid {
  display: grid;
  grid-template-columns: repeat(2, minmax(220px, 1fr));
  gap: 0 18px;

  :global(.ant-form-item) {
    margin-bottom: 18px;
  }
}

.fieldSpan2 {
  grid-column: span 2;
}

.tokenStack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sectionTitle {
  display: inline-flex;
  gap: 10px;
  align-items: center;
  font-weight: 600;

  svg {
    color: var(--app-primary-color, #1890ff);
  }
}

.actions {
  display: flex;
  flex-direction: column;
  gap: 10px;

  :global(.ant-btn) {
    width: 100%;
  }
}

.actionCard {
  :global(.ant-card-body) {
    padding-top: 16px;
  }
}

@media (max-width: 1180px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .actions {
    flex-direction: row;
    flex-wrap: wrap;

    :global(.ant-btn) {
      width: auto;
    }
  }
}

@media (max-width: 768px) {
  .fieldGrid {
    grid-template-columns: 1fr;
  }

  .fieldSpan2 {
    grid-column: auto;
  }
}
```

- [ ] **Step 5: Register the route, tab metadata, and sidebar entry**

In `frontend/src/routes/index.tsx`, add this lazy import after `StorageSubTaskDetailPage`:

```tsx
const ScrapingConfigPage = lazyRouteComponent(() => import('@/pages/scraping/config/ScrapingConfigPage'))
```

Add this route after `storageSubTaskDetailRoute`:

```tsx
const scrapingConfigRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/scraping/config',
  component: ScrapingConfigPage,
})
```

Add `scrapingConfigRoute` to the `layoutRoute.addChildren([...])` list after `storageSubTaskDetailRoute`.

In `frontend/src/routes/tags.ts`, add this entry after the storage entries:

```ts
  { pattern: /^\/scraping\/config$/, meta: { title: '刮削配置' } },
```

In `frontend/src/layout/Sidebar/index.tsx`:

Add `ScissorOutlined` to the `@ant-design/icons` import list.

Add this menu group after the `storage` group and before the `content` group:

```tsx
  {
    key: 'scraping',
    icon: <ScissorOutlined />,
    label: '刮削',
    children: [
      {
        key: '/scraping/config',
        icon: <SettingOutlined />,
        label: '刮削配置',
      },
    ],
  },
```

Add this branch to the `selectedKey` chain after the `/storage/config` branch:

```tsx
          : pathname.startsWith('/scraping/config')
            ? '/scraping/config'
```

Add this line to the `openKeys` memo:

```tsx
    if (pathname.startsWith('/scraping')) keys.push('scraping')
```

- [ ] **Step 6: Update the frontend README**

In `frontend/README.md`, add this route table row after `/storage/config`:

```markdown
| `/scraping/config` | `pages/scraping/config/ScrapingConfigPage.tsx` | Scraping service config and STRM generation trigger |
```

Add this API group bullet after the `storage/storageTasks/` bullet:

```markdown
- `scraping/scrapingConfig/`: scraping service config and manual STRM generation.
```

- [ ] **Step 7: Run the focused page test**

```bash
cd frontend && pnpm test -- src/pages/scraping/config/__tests__/ScrapingConfigPage.test.tsx
```

Expected: `3 passed`.

- [ ] **Step 8: Run the production build**

```bash
cd frontend && pnpm build
```

Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api/scraping/scrapingConfig/types.ts \
  frontend/src/api/scraping/scrapingConfig/index.ts \
  frontend/src/pages/scraping/config/ScrapingConfigPage.tsx \
  frontend/src/pages/scraping/config/ScrapingConfigPage.module.less \
  frontend/src/pages/scraping/config/utils/error.ts \
  frontend/src/pages/scraping/config/__tests__/ScrapingConfigPage.test.tsx \
  frontend/src/routes/index.tsx \
  frontend/src/routes/tags.ts \
  frontend/src/layout/Sidebar/index.tsx \
  frontend/README.md
git diff --cached --name-only
git commit -m "feat(frontend): add scraping configuration page"
```

---

## Final Verification

Run the focused backend suite from `backend/`:

```bash
cd backend && python -m pytest \
  tests/test_scraping_config_service.py \
  tests/test_scraping_strm_client.py \
  tests/test_scraping_api.py \
  tests/test_scraping_strm_trigger.py \
  tests/test_storage_worker_service.py \
  tests/test_storage_runtime_redis.py \
  -v
```

Expected: all selected tests pass.

Run the storage regression suite from `backend/`:

```bash
cd backend && python -m pytest \
  tests/test_storage_config_api.py \
  tests/test_storage_tasks_api.py \
  -v
```

Expected: all selected tests pass.

Run frontend verification from `frontend/`:

```bash
cd frontend && pnpm build
cd frontend && pnpm test -- src/pages/scraping/config/__tests__/ScrapingConfigPage.test.tsx
```

Expected: build succeeds; `3 passed`.

Manual smoke test after starting the backend and frontend:

1. Open `/scraping/config`, fill the service URL, API Key, directory ID, and delay; save. Reopen the page and confirm the key is masked and the other values persist.
2. Click 立即生成 with an unreachable service URL. Confirm one error toast and that no retry occurs.
3. Point the service at a reachable endpoint. Queue a storage task, let it finish, and confirm the worker logs `STRM generation triggered` only after the configured quiet period.
4. During the quiet period, queue another storage task. Confirm the pending check skips the old attempt, and a fresh delay starts after the new drain.
5. Leave the service unconfigured and let a storage task finish. Confirm the backend logs `Not scheduling STRM generation: 未配置外部服务地址` and storage behavior is unchanged.

## Self-Review

- Config persistence: `scraping.conf`, dotenv parsing without interpolation, atomic replace, masked key preservation, explicit null directory clearing, numeric key retained as a string.
- Trigger lifecycle: only a natural drain with `processed_any` schedules; generation counter invalidates older delays; worker, Redis queue, and DB pending statuses are all checked; any check error skips safely; external failures only log.
- API: GET/PUT/POST registered under `/api/scraping`, authenticated, 400 for invalid URL/unconfigured manual run, 422 for schema ranges, 200 result payload for external failures.
- Frontend: route, sidebar group, tab title, typed API module, save and manual run flow, key masking, dynamic delay alert, test coverage.
- Safety: no raw API key in responses or logs (including httpx request logs), no retries, no DB migrations, no runtime config changes.
