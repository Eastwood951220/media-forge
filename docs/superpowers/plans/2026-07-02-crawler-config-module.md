# Crawler Config Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the original `jav-scrapling` crawler config module into Media Forge with only project-required adaptations and move cookie storage to `data/cookies/`.

**Architecture:** Keep the original backend endpoints, schema fields, cookie JSON behavior, and frontend page workflow. Adapt only import paths, Media Forge auth dependency, existing `success(data=...)` response wrapper, TanStack route/menu registration, and the cookie directory.

**Tech Stack:** FastAPI, Pydantic v2, Pytest, React 19, TypeScript 6, Ant Design 6, Monaco Editor, TanStack Router, Vitest.

---

## Source Parity Rules

The source of truth is the original project:

- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/crawler/config/router.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/crawler/config/schemas.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/crawler/cookies/router.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/crawler/cookies/schemas.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/crawler/config/Config.tsx`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/crawler/config/api.ts`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/crawler/config/types.ts`

Do these exact things:

- Keep config keys unchanged:
  `MAX_LIST_PAGES`, `LIST_PAGE_DELAY_MIN`, `LIST_PAGE_DELAY_MAX`, `DETAIL_PAGE_DELAY_MIN`, `DETAIL_PAGE_DELAY_MAX`, `SECURITY_WAIT_SECONDS`, `REQUEST_TIMEOUT`, `INCREMENTAL_EXIST_THRESHOLD`, `USE_DYNAMIC_FETCHER`.
- Keep cookie endpoint behavior unchanged:
  browser-export array format, old flat dict conversion, invalid or missing file returns empty cookies.
- Keep frontend behavior unchanged:
  load config, save config, load cookies, JSON validate, format JSON, save cookies.
- Keep `USE_DYNAMIC_FETCHER` as the original text `Input` with placeholder `false`; do not replace it with a switch.
- Keep Monaco editor; do not replace it with `Input.TextArea`.
- Change only the cookie storage directory to `data/cookies/`.
- Do not add unrelated dashboard cards, extra crawler settings, new actions, new API fields, or new page behavior.

## File Structure

- Modify `scraper/config/settings.py`
  - Change `COOKIE_DIR` from `BASE_DIR / "scraper" / "cookies" / "storage"` to `BASE_DIR / "data" / "cookies"`.
- Create `data/cookies/.gitkeep`
  - Track the empty cookie directory without committing real cookies.
- Create `backend/app/modules/crawler/config/__init__.py`
  - Package marker.
- Create `backend/app/modules/crawler/config/schemas.py`
  - Port original `ConfigUpdate`, `JavdbCookie`, and `CookiesConfig`.
- Create `backend/app/modules/crawler/config/router.py`
  - Port original config router and original cookie router behavior into one Media Forge module.
- Modify `backend/app/main.py`
  - Include the new crawler config router.
- Create `backend/tests/test_crawler_config_api.py`
  - Minimal parity and storage path tests.
- Modify `frontend/package.json` and `frontend/package-lock.json`
  - Add Monaco packages required by the original page.
- Create `frontend/src/api/crawlerConfig/types.ts`
  - Port original frontend types.
- Create `frontend/src/api/crawlerConfig/index.ts`
  - Port original API functions using Media Forge `request`.
- Create `frontend/src/pages/crawler/config/ConfigPage.tsx`
  - Port original page structure and behavior with only import/path adaptations.
- Create `frontend/src/pages/crawler/config/ConfigPage.module.less`
  - Provide the class names used by the original layout.
- Modify `frontend/src/routes/index.tsx`
  - Register `/crawler/config`.
- Modify `frontend/src/layout/Sidebar/index.tsx`
  - Add `爬虫配置` under the existing `爬虫` parent.
- Modify `frontend/src/routes/tags.ts`
  - Add the page title for TagsView.
- Create `frontend/tests/crawler-config.ui.test.tsx`
  - Verify the ported page renders original fields and saves original payload shape.
- Modify `frontend/tests/App.test.tsx`
  - Add API mock for crawler config and a route smoke test.
- Modify `frontend/tests/layout.ui.test.tsx`
  - Assert sidebar contains `爬虫配置`.

---

### Task 1: Move Cookie Storage To data/cookies

**Files:**
- Modify: `scraper/config/settings.py`
- Create: `data/cookies/.gitkeep`
- Test: `backend/tests/test_crawler_config_api.py`

- [ ] **Step 1: Add storage path regression test**

Create `backend/tests/test_crawler_config_api.py`:

```python
from scraper.config.settings import BASE_DIR, COOKIE_DIR


def test_cookie_dir_is_data_cookies() -> None:
    assert COOKIE_DIR == BASE_DIR / "data" / "cookies"
```

- [ ] **Step 2: Run the regression test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_config_api.py::test_cookie_dir_is_data_cookies -v
```

Expected: FAIL because `COOKIE_DIR` still points at `scraper/cookies/storage`.

- [ ] **Step 3: Change the cookie directory**

Modify the directory constants near the bottom of `scraper/config/settings.py` to:

```python
LOG_DIR = BASE_DIR / "logs"
RUN_DATA_DIR = BASE_DIR / "run_data"
COOKIE_DIR = BASE_DIR / "data" / "cookies"
```

- [ ] **Step 4: Track the new directory**

Create `data/cookies/.gitkeep` as an empty file:

```text

```

- [ ] **Step 5: Re-run the regression test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_config_api.py::test_cookie_dir_is_data_cookies -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

Run:

```bash
git add scraper/config/settings.py data/cookies/.gitkeep backend/tests/test_crawler_config_api.py
git commit -m "feat: move crawler cookies to data directory"
```

Expected: Commit succeeds.

---

### Task 2: Port Backend crawler/config Module

**Files:**
- Create: `backend/app/modules/crawler/config/__init__.py`
- Create: `backend/app/modules/crawler/config/schemas.py`
- Create: `backend/app/modules/crawler/config/router.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_crawler_config_api.py`

- [ ] **Step 1: Replace backend tests with parity checks**

Replace `backend/tests/test_crawler_config_api.py` with:

```python
import json
from http import HTTPStatus

from fastapi.testclient import TestClient

from scraper.config import settings


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_cookie_dir_is_data_cookies() -> None:
    assert settings.COOKIE_DIR == settings.BASE_DIR / "data" / "cookies"


def test_get_crawler_config_returns_original_keys(
    client: TestClient,
    admin_user,
) -> None:
    response = client.get(
        "/api/crawler/config",
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["MAX_LIST_PAGES"] == settings.MAX_LIST_PAGES
    assert body["data"]["LIST_PAGE_DELAY_MIN"] == settings.LIST_PAGE_DELAY_MIN
    assert body["data"]["LIST_PAGE_DELAY_MAX"] == settings.LIST_PAGE_DELAY_MAX
    assert body["data"]["DETAIL_PAGE_DELAY_MIN"] == settings.DETAIL_PAGE_DELAY_MIN
    assert body["data"]["DETAIL_PAGE_DELAY_MAX"] == settings.DETAIL_PAGE_DELAY_MAX
    assert body["data"]["SECURITY_WAIT_SECONDS"] == settings.SECURITY_WAIT_SECONDS
    assert body["data"]["REQUEST_TIMEOUT"] == settings.REQUEST_TIMEOUT
    assert body["data"]["INCREMENTAL_EXIST_THRESHOLD"] == settings.INCREMENTAL_EXIST_THRESHOLD
    assert body["data"]["USE_DYNAMIC_FETCHER"] == settings.USE_DYNAMIC_FETCHER


def test_update_crawler_config_matches_original_env_update(
    client: TestClient,
    admin_user,
) -> None:
    response = client.put(
        "/api/crawler/config",
        json={
            "MAX_LIST_PAGES": 12,
            "REQUEST_TIMEOUT": 45,
            "USE_DYNAMIC_FETCHER": True,
        },
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert data["MAX_LIST_PAGES"] == 12
    assert data["REQUEST_TIMEOUT"] == 45
    assert data["USE_DYNAMIC_FETCHER"] is True


def test_cookies_config_reads_and_writes_browser_export_array(
    client: TestClient,
    admin_user,
    monkeypatch,
    tmp_path,
) -> None:
    cookie_dir = tmp_path / "data" / "cookies"
    monkeypatch.setattr(settings, "COOKIE_DIR", cookie_dir)
    payload = {
        "cookies": [
            {
                "domain": "javdb.com",
                "expirationDate": None,
                "hostOnly": True,
                "httpOnly": False,
                "name": "session",
                "path": "/",
                "sameSite": "lax",
                "secure": False,
                "session": False,
                "storeId": None,
                "value": "abc123",
            }
        ]
    }
    headers = auth_headers(client, admin_user)

    put_response = client.put(
        "/api/crawler/config/cookies",
        json=payload,
        headers=headers,
    )

    assert put_response.status_code == HTTPStatus.OK
    cookie_file = cookie_dir / "javdb_cookies.json"
    assert cookie_file.exists()
    assert json.loads(cookie_file.read_text(encoding="utf-8")) == payload["cookies"]

    get_response = client.get("/api/crawler/config/cookies", headers=headers)

    assert get_response.status_code == HTTPStatus.OK
    assert get_response.json()["data"] == payload


def test_cookies_config_converts_old_flat_dict(
    client: TestClient,
    admin_user,
    monkeypatch,
    tmp_path,
) -> None:
    cookie_dir = tmp_path / "data" / "cookies"
    cookie_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "COOKIE_DIR", cookie_dir)
    (cookie_dir / "javdb_cookies.json").write_text(
        json.dumps({"session": "abc123"}),
        encoding="utf-8",
    )

    response = client.get(
        "/api/crawler/config/cookies",
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.OK
    cookies = response.json()["data"]["cookies"]
    assert cookies == [
        {
            "domain": "javdb.com",
            "expirationDate": None,
            "hostOnly": True,
            "httpOnly": False,
            "name": "session",
            "path": "/",
            "sameSite": "lax",
            "secure": False,
            "session": False,
            "storeId": None,
            "value": "abc123",
        }
    ]
```

- [ ] **Step 2: Run backend tests to verify the module is missing**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_config_api.py -v
```

Expected: FAIL because `/api/crawler/config` and `/api/crawler/config/cookies` are not implemented.

- [ ] **Step 3: Add package marker**

Create `backend/app/modules/crawler/config/__init__.py`:

```python
"""Crawler configuration endpoints."""
```

- [ ] **Step 4: Port original backend schemas**

Create `backend/app/modules/crawler/config/schemas.py`:

```python
from pydantic import BaseModel, Field


class ConfigUpdate(BaseModel):
    MAX_LIST_PAGES: int | None = Field(None, ge=1, le=100)
    LIST_PAGE_DELAY_MIN: float | None = Field(None, ge=0)
    LIST_PAGE_DELAY_MAX: float | None = Field(None, ge=0)
    DETAIL_PAGE_DELAY_MIN: float | None = Field(None, ge=0)
    DETAIL_PAGE_DELAY_MAX: float | None = Field(None, ge=0)
    SECURITY_WAIT_SECONDS: float | None = Field(None, ge=0)
    INCREMENTAL_EXIST_THRESHOLD: int | None = Field(None, ge=0)
    REQUEST_TIMEOUT: int | None = Field(None, ge=1)
    USE_DYNAMIC_FETCHER: bool | None = None


class JavdbCookie(BaseModel):
    """A single cookie entry matching the browser-export format."""

    domain: str
    expirationDate: float | None = None
    hostOnly: bool = True
    httpOnly: bool = False
    name: str
    path: str = "/"
    sameSite: str | None = "lax"
    secure: bool = False
    session: bool = False
    storeId: str | None = None
    value: str


class CookiesConfig(BaseModel):
    """Wrapper for the cookie array stored in the JSON file."""

    cookies: list[JavdbCookie] = Field(default_factory=list)
```

- [ ] **Step 5: Port original backend router behavior**

Create `backend/app/modules/crawler/config/router.py`:

```python
import json
import os
from typing import Any

from fastapi import APIRouter

from backend.app.core.dependencies import CurrentUser
from backend.app.modules.crawler.config.schemas import ConfigUpdate, CookiesConfig
from scraper.config import settings as cfg
from shared.schemas.common import success

router = APIRouter(prefix="/api/crawler/config", tags=["crawler-config"])

CONFIG_KEYS = [
    "MAX_LIST_PAGES",
    "LIST_PAGE_DELAY_MIN",
    "LIST_PAGE_DELAY_MAX",
    "DETAIL_PAGE_DELAY_MIN",
    "DETAIL_PAGE_DELAY_MAX",
    "SECURITY_WAIT_SECONDS",
    "REQUEST_TIMEOUT",
    "INCREMENTAL_EXIST_THRESHOLD",
    "USE_DYNAMIC_FETCHER",
]

DEFAULT_COOKIE_FILE = "javdb_cookies.json"


def _defaults() -> dict[str, Any]:
    return {
        "MAX_LIST_PAGES": cfg.MAX_LIST_PAGES,
        "LIST_PAGE_DELAY_MIN": cfg.LIST_PAGE_DELAY_MIN,
        "LIST_PAGE_DELAY_MAX": cfg.LIST_PAGE_DELAY_MAX,
        "DETAIL_PAGE_DELAY_MIN": cfg.DETAIL_PAGE_DELAY_MIN,
        "DETAIL_PAGE_DELAY_MAX": cfg.DETAIL_PAGE_DELAY_MAX,
        "SECURITY_WAIT_SECONDS": cfg.SECURITY_WAIT_SECONDS,
        "REQUEST_TIMEOUT": cfg.REQUEST_TIMEOUT,
        "INCREMENTAL_EXIST_THRESHOLD": cfg.INCREMENTAL_EXIST_THRESHOLD,
        "USE_DYNAMIC_FETCHER": cfg.USE_DYNAMIC_FETCHER,
    }


def _coerce_env_value(value: str) -> bool | int | float | str:
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    if value.isdigit():
        return int(value)
    try:
        return float(value)
    except ValueError:
        return value


def _read_config() -> dict[str, Any]:
    defaults = _defaults()
    result: dict[str, Any] = {}
    for key in CONFIG_KEYS:
        value = os.getenv(key)
        if value is not None:
            result[key] = _coerce_env_value(value)
        elif key in defaults:
            result[key] = defaults[key]
    return result


def _cookie_path():
    return cfg.COOKIE_DIR / DEFAULT_COOKIE_FILE


@router.get("")
def get_config(_current_user: CurrentUser) -> dict:
    return success(data=_read_config())


@router.put("")
def update_config(body: ConfigUpdate, _current_user: CurrentUser) -> dict:
    updated = body.model_dump(exclude_none=True)
    for key, value in updated.items():
        os.environ[key] = str(value)
    return success(data=_read_config())


@router.get("/cookies")
def get_cookies_config(_current_user: CurrentUser) -> dict:
    filepath = _cookie_path()
    if not filepath.exists():
        return success(data=CookiesConfig(cookies=[]).model_dump())

    try:
        with filepath.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return success(data=CookiesConfig(cookies=[]).model_dump())

    if isinstance(data, list):
        return success(data=CookiesConfig(cookies=data).model_dump())

    if isinstance(data, dict):
        cookies_list = [
            {"name": key, "value": value, "domain": "javdb.com", "path": "/"}
            for key, value in data.items()
        ]
        return success(data=CookiesConfig(cookies=cookies_list).model_dump())

    return success(data=CookiesConfig(cookies=[]).model_dump())


@router.put("/cookies")
def update_cookies_config(body: CookiesConfig, _current_user: CurrentUser) -> dict:
    filepath = _cookie_path()
    filepath.parent.mkdir(parents=True, exist_ok=True)
    cookies_list = [cookie.model_dump() for cookie in body.cookies]
    with filepath.open("w", encoding="utf-8") as file:
        json.dump(cookies_list, file, ensure_ascii=False, indent=2)
    return success(data=body.model_dump())
```

- [ ] **Step 6: Register the router**

Modify `backend/app/main.py` imports:

```python
from backend.app.modules.crawler.config.router import router as crawler_config_router
from backend.app.modules.crawler.tasks.router import router as crawler_tasks_router
```

Modify router registration:

```python
app.include_router(health_router)
app.include_router(crawler_tasks_router)
app.include_router(crawler_config_router)
app.include_router(crawl_tasks_compat_router)
```

- [ ] **Step 7: Run backend parity tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_config_api.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

Run:

```bash
git add backend/app/main.py backend/app/modules/crawler/config backend/tests/test_crawler_config_api.py
git commit -m "feat: add crawler config api"
```

Expected: Commit succeeds.

---

### Task 3: Port Frontend crawler/config Page

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/src/api/crawlerConfig/types.ts`
- Create: `frontend/src/api/crawlerConfig/index.ts`
- Create: `frontend/src/pages/crawler/config/ConfigPage.tsx`
- Create: `frontend/src/pages/crawler/config/ConfigPage.module.less`
- Test: `frontend/tests/crawler-config.ui.test.tsx`

- [ ] **Step 1: Install original page dependency**

Run:

```bash
cd frontend && npm install @monaco-editor/react monaco-editor
```

Expected: `frontend/package.json` and `frontend/package-lock.json` include Monaco packages.

- [ ] **Step 2: Add frontend page test**

Create `frontend/tests/crawler-config.ui.test.tsx`:

```tsx
import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ConfigPage from '../src/pages/crawler/config/ConfigPage'
import {
  fetchConfig,
  fetchCookiesConfig,
  updateConfig,
  updateCookiesConfig,
} from '../src/api/crawlerConfig'

vi.mock('@monaco-editor/react', () => ({
  default: ({
    value,
    onChange,
  }: {
    value: string
    onChange: (value: string | undefined) => void
  }) => (
    <textarea
      aria-label="Cookie JSON"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}))

vi.mock('../src/api/crawlerConfig', () => ({
  fetchConfig: vi.fn(),
  updateConfig: vi.fn(),
  fetchCookiesConfig: vi.fn(),
  updateCookiesConfig: vi.fn(),
}))

function renderPage() {
  return render(
    <AntApp>
      <ConfigPage />
    </AntApp>,
  )
}

describe('ConfigPage', () => {
  beforeEach(() => {
    vi.mocked(fetchConfig).mockResolvedValue({
      MAX_LIST_PAGES: 50,
      LIST_PAGE_DELAY_MIN: 1,
      LIST_PAGE_DELAY_MAX: 3,
      DETAIL_PAGE_DELAY_MIN: 2,
      DETAIL_PAGE_DELAY_MAX: 5,
      SECURITY_WAIT_SECONDS: 60,
      REQUEST_TIMEOUT: 30,
      INCREMENTAL_EXIST_THRESHOLD: 10,
      USE_DYNAMIC_FETCHER: false,
    })
    vi.mocked(fetchCookiesConfig).mockResolvedValue({
      cookies: [
        {
          domain: 'javdb.com',
          expirationDate: null,
          hostOnly: true,
          httpOnly: false,
          name: 'session',
          path: '/',
          sameSite: 'lax',
          secure: false,
          session: false,
          storeId: null,
          value: 'abc123',
        },
      ],
    })
    vi.mocked(updateConfig).mockResolvedValue({})
    vi.mocked(updateCookiesConfig).mockResolvedValue({ cookies: [] })
  })

  it('renders original crawler config fields and cookie editor', async () => {
    renderPage()

    expect(await screen.findByText('爬取参数')).toBeInTheDocument()
    expect(screen.getByText('最大翻页数')).toBeInTheDocument()
    expect(screen.getByText('列表页最小延迟 (秒)')).toBeInTheDocument()
    expect(screen.getByText('列表页最大延迟 (秒)')).toBeInTheDocument()
    expect(screen.getByText('详情页最小延迟 (秒)')).toBeInTheDocument()
    expect(screen.getByText('详情页最大延迟 (秒)')).toBeInTheDocument()
    expect(screen.getByText('安全验证等待 (秒)')).toBeInTheDocument()
    expect(screen.getByText('请求超时 (秒)')).toBeInTheDocument()
    expect(screen.getByText('增量爬取阈值')).toBeInTheDocument()
    expect(screen.getByText('动态抓取器')).toBeInTheDocument()
    expect(screen.getByText('Cookie 配置')).toBeInTheDocument()
    expect(screen.getByLabelText('Cookie JSON')).toHaveValue(expect.stringContaining('"name": "session"'))
  })

  it('saves cookies with original wrapper shape', async () => {
    renderPage()

    const editor = await screen.findByLabelText('Cookie JSON')
    await userEvent.clear(editor)
    await userEvent.type(editor, '[{"domain":"javdb.com","name":"session","value":"next","path":"/"}]')
    await userEvent.click(screen.getByText('保存 Cookie'))

    await waitFor(() => {
      expect(updateCookiesConfig).toHaveBeenCalledWith({
        cookies: [
          {
            domain: 'javdb.com',
            name: 'session',
            value: 'next',
            path: '/',
          },
        ],
      })
    })
  })
})
```

- [ ] **Step 3: Run frontend page test to verify files are missing**

Run:

```bash
cd frontend && npm test -- crawler-config.ui.test.tsx
```

Expected: FAIL because `src/api/crawlerConfig` and `src/pages/crawler/config/ConfigPage` do not exist.

- [ ] **Step 4: Port original frontend types**

Create `frontend/src/api/crawlerConfig/types.ts`:

```ts
/** A single cookie entry matching the browser-export format. */
export interface JavdbCookie {
  domain: string
  expirationDate: number | null
  hostOnly: boolean
  httpOnly: boolean
  name: string
  path: string
  sameSite: string | null
  secure: boolean
  session: boolean
  storeId: string | null
  value: string
}

/** Wrapper for the cookie array stored in the JSON file. */
export interface CookiesConfig {
  cookies: JavdbCookie[]
}

/** Application config stored in env vars. */
export interface AppConfig {
  MAX_LIST_PAGES?: number
  LIST_PAGE_DELAY_MIN?: number
  LIST_PAGE_DELAY_MAX?: number
  DETAIL_PAGE_DELAY_MIN?: number
  DETAIL_PAGE_DELAY_MAX?: number
  SECURITY_WAIT_SECONDS?: number
  REQUEST_TIMEOUT?: number
  INCREMENTAL_EXIST_THRESHOLD?: number
  USE_DYNAMIC_FETCHER?: boolean
  [key: string]: unknown
}
```

- [ ] **Step 5: Port original frontend API using Media Forge request wrapper**

Create `frontend/src/api/crawlerConfig/index.ts`:

```ts
import { request } from '@/request'
import type { AppConfig, CookiesConfig } from './types'

export type { AppConfig, CookiesConfig, JavdbCookie } from './types'

const BASE_URL = '/api/crawler/config'

export function fetchConfig(): Promise<AppConfig> {
  return request.get<AppConfig>(BASE_URL)
}

export function updateConfig(data: Partial<AppConfig>): Promise<AppConfig> {
  return request.put<AppConfig>(BASE_URL, data)
}

export function fetchCookiesConfig(): Promise<CookiesConfig> {
  return request.get<CookiesConfig>(`${BASE_URL}/cookies`)
}

export function updateCookiesConfig(data: CookiesConfig): Promise<CookiesConfig> {
  return request.put<CookiesConfig>(`${BASE_URL}/cookies`, data)
}
```

- [ ] **Step 6: Add styles matching original page structure**

Create `frontend/src/pages/crawler/config/ConfigPage.module.less`:

```less
.configLayout {
  display: grid;
  grid-template-columns: minmax(280px, 420px) minmax(420px, 1fr);
  gap: 24px;
  align-items: start;
}

.configLeft,
.configRight {
  min-width: 0;
}

.formCard {
  width: 100%;
}

.editorFrame {
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  overflow: hidden;
}

.cardExtra {
  display: flex;
  gap: 8px;
}

@media (max-width: 960px) {
  .configLayout {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 7: Port original frontend page**

Create `frontend/src/pages/crawler/config/ConfigPage.tsx`:

```tsx
import { useCallback, useEffect, useRef, useState } from 'react'
import { App, Button, Card, Form, Input, InputNumber, Typography } from 'antd'
import Editor, { type OnMount } from '@monaco-editor/react'
import {
  fetchConfig,
  fetchCookiesConfig,
  updateConfig,
  updateCookiesConfig,
  type AppConfig,
  type CookiesConfig,
} from '@/api/crawlerConfig'
import styles from './ConfigPage.module.less'

const DEFAULT_COOKIE_JSON = `[
  {
    "domain": "javdb.com",
    "name": "",
    "value": "",
    "path": "/"
  }
]`

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return '操作失败'
}

export default function ConfigPage() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [cookieSaving, setCookieSaving] = useState(false)
  const [cookieJson, setCookieJson] = useState('')
  const [cookieLoading, setCookieLoading] = useState(true)
  const [jsonError, setJsonError] = useState<string | null>(null)
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null)

  useEffect(() => {
    fetchConfig()
      .then((data: AppConfig) => {
        form.setFieldsValue(data)
      })
      .catch((error: unknown) => message.error(getErrorMessage(error)))
      .finally(() => setLoading(false))
  }, [form, message])

  useEffect(() => {
    fetchCookiesConfig()
      .then((data: CookiesConfig) => {
        setCookieJson(JSON.stringify(data.cookies, null, 2))
      })
      .catch(() => {
        setCookieJson(DEFAULT_COOKIE_JSON)
      })
      .finally(() => setCookieLoading(false))
  }, [])

  const handleEditorMount: OnMount = useCallback((editor) => {
    editorRef.current = editor
  }, [])

  const validateJson = (value: string): object | null => {
    try {
      const parsed = JSON.parse(value)
      if (!Array.isArray(parsed)) {
        setJsonError('Cookie 配置必须是 JSON 数组格式')
        return null
      }
      setJsonError(null)
      return parsed
    } catch (error: unknown) {
      const msg = error instanceof SyntaxError ? error.message : '无效的 JSON 格式'
      setJsonError(msg)
      return null
    }
  }

  const handleCookieChange = (value: string | undefined) => {
    const text = value ?? ''
    setCookieJson(text)
    if (text.trim()) {
      validateJson(text)
    } else {
      setJsonError(null)
    }
  }

  const handleSaveConfig = async (values: AppConfig) => {
    setSaving(true)
    try {
      await updateConfig(values)
      message.success('配置已保存')
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveCookies = async () => {
    const parsed = validateJson(cookieJson)
    if (!parsed) {
      message.error('请先修复 JSON 格式错误再保存')
      return
    }

    setCookieSaving(true)
    try {
      await updateCookiesConfig({ cookies: parsed as CookiesConfig['cookies'] })
      message.success('Cookie 配置已保存')
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setCookieSaving(false)
    }
  }

  const handleFormatJson = () => {
    try {
      const parsed = JSON.parse(cookieJson)
      const formatted = JSON.stringify(parsed, null, 2)
      setCookieJson(formatted)
      setJsonError(null)
    } catch {
      return
    }
  }

  if (loading) return null

  return (
    <div className={styles.configLayout}>
      <div className={styles.configLeft}>
        <Form form={form} layout="vertical" onFinish={handleSaveConfig}>
          <Card title="爬取参数" className={styles.formCard}>
            <Form.Item name="MAX_LIST_PAGES" label="最大翻页数">
              <InputNumber min={1} max={100} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="LIST_PAGE_DELAY_MIN" label="列表页最小延迟 (秒)">
              <InputNumber min={0} max={60} step={0.5} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="LIST_PAGE_DELAY_MAX" label="列表页最大延迟 (秒)">
              <InputNumber min={0} max={60} step={0.5} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="DETAIL_PAGE_DELAY_MIN" label="详情页最小延迟 (秒)">
              <InputNumber min={0} max={60} step={0.5} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="DETAIL_PAGE_DELAY_MAX" label="详情页最大延迟 (秒)">
              <InputNumber min={0} max={60} step={0.5} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="SECURITY_WAIT_SECONDS" label="安全验证等待 (秒)">
              <InputNumber min={10} max={600} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="REQUEST_TIMEOUT" label="请求超时 (秒)">
              <InputNumber min={5} max={120} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name="INCREMENTAL_EXIST_THRESHOLD"
              label="增量爬取阈值"
              tooltip="当某页已存在的条目数达到此阈值时，跳过后续页面。0 表示禁用（全量爬取）"
            >
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="USE_DYNAMIC_FETCHER" label="动态抓取器">
              <Input placeholder="false" />
            </Form.Item>
          </Card>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={saving}>
              保存配置
            </Button>
          </Form.Item>
        </Form>
      </div>

      <div className={styles.configRight}>
        <Card
          title="Cookie 配置"
          className={styles.formCard}
          extra={
            <div className={styles.cardExtra}>
              <Button onClick={handleFormatJson} disabled={!!jsonError && cookieJson.trim() !== ''}>
                格式化
              </Button>
              <Button type="primary" onClick={() => { void handleSaveCookies() }} loading={cookieSaving}>
                保存 Cookie
              </Button>
            </div>
          }
        >
          {cookieLoading ? null : (
            <>
              <div className={styles.editorFrame}>
                <Editor
                  height="400px"
                  defaultLanguage="json"
                  value={cookieJson}
                  onChange={handleCookieChange}
                  onMount={handleEditorMount}
                  options={{
                    minimap: { enabled: false },
                    lineNumbers: 'on',
                    scrollBeyondLastLine: false,
                    wordWrap: 'on',
                    tabSize: 2,
                    formatOnPaste: true,
                  }}
                />
              </div>
              {jsonError && (
                <Typography.Text type="danger" style={{ display: 'block', marginTop: 8 }}>
                  JSON 格式错误: {jsonError}
                </Typography.Text>
              )}
            </>
          )}
        </Card>
      </div>
    </div>
  )
}
```

- [ ] **Step 8: Run frontend page test**

Run:

```bash
cd frontend && npm test -- crawler-config.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 9: Commit Task 3**

Run:

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/api/crawlerConfig frontend/src/pages/crawler/config frontend/tests/crawler-config.ui.test.tsx
git commit -m "feat: add crawler config page"
```

Expected: Commit succeeds.

---

### Task 4: Register Route, Sidebar, And TagsView Title

**Files:**
- Modify: `frontend/src/routes/index.tsx`
- Modify: `frontend/src/layout/Sidebar/index.tsx`
- Modify: `frontend/src/routes/tags.ts`
- Modify: `frontend/tests/App.test.tsx`
- Modify: `frontend/tests/layout.ui.test.tsx`

- [ ] **Step 1: Add route and menu tests**

Modify the `vi.mock('@/api/crawlTask', ...)` section in `frontend/tests/App.test.tsx` by adding this mock below it:

```tsx
vi.mock('@/api/crawlerConfig', () => ({
  fetchConfig: vi.fn().mockResolvedValue({
    MAX_LIST_PAGES: 50,
    LIST_PAGE_DELAY_MIN: 1,
    LIST_PAGE_DELAY_MAX: 3,
    DETAIL_PAGE_DELAY_MIN: 2,
    DETAIL_PAGE_DELAY_MAX: 5,
    SECURITY_WAIT_SECONDS: 60,
    REQUEST_TIMEOUT: 30,
    INCREMENTAL_EXIST_THRESHOLD: 10,
    USE_DYNAMIC_FETCHER: false,
  }),
  fetchCookiesConfig: vi.fn().mockResolvedValue({ cookies: [] }),
  updateConfig: vi.fn(),
  updateCookiesConfig: vi.fn(),
}))
```

Add this test inside `describe('App auth routing', ...)`:

```tsx
it('shows crawler config page for authenticated user', async () => {
  setToken('test-token')
  useAuthStore.setState({ token: 'test-token', isAuthenticated: true })

  renderApp('/crawler/config')

  await waitFor(() => {
    expect(screen.getByText('爬取参数')).toBeInTheDocument()
    expect(screen.getAllByText('爬虫配置').length).toBeGreaterThanOrEqual(1)
  })
})
```

Modify `frontend/tests/layout.ui.test.tsx` in the first layout test by adding:

```tsx
expect(screen.getByText('爬虫配置')).toBeInTheDocument()
```

- [ ] **Step 2: Run route and layout tests to verify route/menu are missing**

Run:

```bash
cd frontend && npm test -- App.test.tsx layout.ui.test.tsx
```

Expected: FAIL because `/crawler/config` and the sidebar item are not registered.

- [ ] **Step 3: Register the route**

Modify `frontend/src/routes/index.tsx` imports:

```tsx
import ConfigPage from '@/pages/crawler/config/ConfigPage'
```

Add the route after `crawlerTasksRoute`:

```tsx
const crawlerConfigRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/config',
  component: ConfigPage,
})
```

Add it to `layoutRoute.addChildren([...])`:

```tsx
layoutRoute.addChildren([
  indexRoute,
  crawlerIndexRoute,
  crawlerTasksRoute,
  crawlerConfigRoute,
  crawlerTaskNewRoute,
  crawlerTaskEditRoute,
  legacyCrawlTasksRoute,
])
```

- [ ] **Step 4: Register the sidebar item**

Modify `frontend/src/layout/Sidebar/index.tsx` icon import:

```tsx
import { DashboardOutlined, SearchOutlined, SettingOutlined, UnorderedListOutlined } from '@ant-design/icons'
```

Add this child under the existing `爬虫` children:

```tsx
{
  key: '/crawler/config',
  icon: <SettingOutlined />,
  label: '爬虫配置',
},
```

Replace selected key logic:

```tsx
const selectedKey = pathname.startsWith('/crawler/tasks')
  ? '/crawler/tasks'
  : pathname.startsWith('/crawler/config')
    ? '/crawler/config'
    : pathname
```

- [ ] **Step 5: Register TagsView title**

Modify `frontend/src/routes/tags.ts` by adding:

```ts
{ pattern: /^\/crawler\/config$/, meta: { title: '爬虫配置' } },
```

- [ ] **Step 6: Run route and layout tests**

Run:

```bash
cd frontend && npm test -- App.test.tsx layout.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

Run:

```bash
git add frontend/src/routes/index.tsx frontend/src/layout/Sidebar/index.tsx frontend/src/routes/tags.ts frontend/tests/App.test.tsx frontend/tests/layout.ui.test.tsx
git commit -m "feat: register crawler config route"
```

Expected: Commit succeeds.

---

### Task 5: Verification

**Files:**
- No code changes.

- [ ] **Step 1: Run backend crawler config tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_config_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend focused tests**

Run:

```bash
cd frontend && npm test -- crawler-config.ui.test.tsx App.test.tsx layout.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend lint and build**

Run:

```bash
cd frontend && npm run lint && npm run build
```

Expected: PASS.

- [ ] **Step 4: Confirm cookie path**

Run:

```bash
source .venv/bin/activate
python - <<'PY'
from scraper.config.settings import COOKIE_DIR
print(COOKIE_DIR)
PY
```

Expected output ends with:

```text
/data/cookies
```

---

## Self-Review

**Spec coverage:** This plan ports the original `crawler/config` backend, original cookie backend behavior, original frontend config page workflow, route/menu/tags registration needed by Media Forge, and changes cookie storage to `data/cookies/`.

**Scope control:** The plan removes non-original UI substitutions and does not add fields, dashboard content, extra crawler actions, or alternate editor behavior.

**Consistency check:** Backend endpoints are `/api/crawler/config` and `/api/crawler/config/cookies`; frontend API calls those same paths through Media Forge `request`; response data uses existing `success(data=...)`; cookie file resolves to `data/cookies/javdb_cookies.json`.
