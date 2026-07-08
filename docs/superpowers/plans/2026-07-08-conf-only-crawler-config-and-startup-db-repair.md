# Conf-Only Crawler Config And Startup Database Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make crawler runtime settings come only from `data/configs/crawler.conf`, remove crawler defaults from `.env`, and repair missing PostgreSQL databases or missing application tables automatically on backend restart.

**Architecture:** Introduce a small backend-owned crawler config reader with typed defaults and `.conf` parsing, then make the config API, crawler engine, spider, and URL-name extractor consume that reader instead of `scraper.config.settings` or environment-loaded values. Add a startup bootstrap helper that reconstructs an `InitConfigRequest` from persisted runtime config, reruns the existing database bootstrap path when connect/table checks fail, then reconnects PostgreSQL and proceeds with existing cleanup.

**Tech Stack:** Python 3.12+, FastAPI 0.115 lifespan, SQLAlchemy 2.0, Pytest, python-dotenv only for runtime `.conf` files, scraper JavDB spider.

## Global Constraints

- Remove crawler-related keys from `.env`; crawler settings must not be read from `.env`.
- Crawler runtime settings must be read from `data/configs/crawler.conf`.
- Keep runtime database/Redis config files (`database.conf`, `redis.conf`, `storage.conf`) unchanged.
- Reuse existing `bootstrap_application_database()` / `create_application_tables()` behavior for database and table repair.
- Do not add a new database migration for this task.
- Do not change frontend crawler config fields or API shape.
- Preserve existing crawler behavior except for the source of configuration values.

---

## File Structure

- Modify `.env`: remove crawler keys (`MAX_LIST_PAGES`, `REQUEST_TIMEOUT`, `LIST_PAGE_DELAY_MIN`, `LIST_PAGE_DELAY_MAX`, `DETAIL_PAGE_DELAY_MIN`, `DETAIL_PAGE_DELAY_MAX`, `SECURITY_WAIT_SECONDS`, `INCREMENTAL_EXIST_THRESHOLD`).
- Create `backend/app/modules/crawler/config/conf_reader.py`: typed defaults, `.conf` parser/writer helpers, and `read_crawler_runtime_config(base_dir: Path | None = None) -> CrawlerRuntimeConfig`.
- Modify `backend/app/modules/crawler/config/router.py`: use `conf_reader` instead of `scraper.config.settings` for defaults, path resolution, value coercion, and writes.
- Modify `backend/app/modules/crawler/runtime/config.py`: delegate `read_incremental_threshold_from_conf()` to `conf_reader`.
- Modify `scraper/spiders/javdb/javdb_spider.py`: remove module-level setting imports and load config values at runtime.
- Modify `backend/app/modules/crawler/runtime/engine.py`: read `REQUEST_TIMEOUT` through `conf_reader`.
- Modify `backend/app/modules/crawler/tasks/name_extractor.py`: read `REQUEST_TIMEOUT` through `conf_reader`.
- Modify `scraper/config/settings.py`: remove dotenv loading and crawler runtime configuration constants, keep only path constants such as `BASE_DIR`, `LOG_DIR`, `RUN_DATA_DIR`, `COOKIE_DIR`.
- Create `backend/app/startup_database.py`: startup database bootstrap/repair helper.
- Modify `backend/app/main.py`: call the startup repair helper before connecting and cleaning interrupted work.
- Modify `backend/tests/test_crawler_config_api.py`: cover conf-only defaults and `.env` ignoring.
- Modify `backend/tests/test_crawler_runtime_adapters.py`: keep incremental threshold coverage through the new reader.
- Modify or add `backend/tests/test_startup_database_repair.py`: cover startup bootstrap when database connect or table validation fails.
- Modify `backend/tests/test_init_database_bootstrap.py`: cover reconstructing bootstrap request from persisted runtime config if the helper lives there.

---

### Task 1: Add Conf-Only Crawler Runtime Config Reader

**Files:**
- Create: `backend/app/modules/crawler/config/conf_reader.py`
- Modify: `backend/app/modules/crawler/config/router.py`
- Modify: `backend/app/modules/crawler/runtime/config.py`
- Modify: `backend/tests/test_crawler_config_api.py`
- Modify: `backend/tests/test_crawler_runtime_adapters.py`

**Interfaces:**
- Produces `CrawlerRuntimeConfig` dataclass with fields:
  - `MAX_LIST_PAGES: int`
  - `LIST_PAGE_DELAY_MIN: float`
  - `LIST_PAGE_DELAY_MAX: float`
  - `DETAIL_PAGE_DELAY_MIN: float`
  - `DETAIL_PAGE_DELAY_MAX: float`
  - `SECURITY_WAIT_SECONDS: float`
  - `REQUEST_TIMEOUT: int`
  - `INCREMENTAL_EXIST_THRESHOLD: int`
- Produces `CONFIG_KEYS: tuple[str, ...]`.
- Produces `crawler_conf_path(base_dir: Path | None = None) -> Path`.
- Produces `read_crawler_conf_values(base_dir: Path | None = None) -> dict[str, str]`.
- Produces `read_crawler_config_dict(base_dir: Path | None = None) -> dict[str, int | float]`.
- Produces `read_crawler_runtime_config(base_dir: Path | None = None) -> CrawlerRuntimeConfig`.
- Produces `write_crawler_config(updated: dict[str, object], base_dir: Path | None = None) -> None`.
- `read_incremental_threshold_from_conf(base_dir: Path | None = None) -> int` continues to exist.

- [ ] **Step 1: Add failing conf-only tests**

Append these tests to `backend/tests/test_crawler_config_api.py`:

```python
def test_crawler_config_ignores_env_and_uses_conf_defaults(monkeypatch, tmp_path) -> None:
    from backend.app.modules.crawler.config.conf_reader import read_crawler_config_dict

    monkeypatch.setenv("MAX_LIST_PAGES", "99")
    monkeypatch.setenv("REQUEST_TIMEOUT", "88")

    data = read_crawler_config_dict(tmp_path)

    assert data["MAX_LIST_PAGES"] == 50
    assert data["REQUEST_TIMEOUT"] == 30


def test_crawler_config_reads_values_from_conf_file(monkeypatch, tmp_path) -> None:
    from backend.app.modules.crawler.config.conf_reader import read_crawler_config_dict

    conf_dir = tmp_path / "data" / "configs"
    conf_dir.mkdir(parents=True)
    (conf_dir / "crawler.conf").write_text(
        "MAX_LIST_PAGES=17\n"
        "REQUEST_TIMEOUT=46\n"
        "LIST_PAGE_DELAY_MIN=1.5\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MAX_LIST_PAGES", "99")
    monkeypatch.setenv("REQUEST_TIMEOUT", "88")

    data = read_crawler_config_dict(tmp_path)

    assert data["MAX_LIST_PAGES"] == 17
    assert data["REQUEST_TIMEOUT"] == 46
    assert data["LIST_PAGE_DELAY_MIN"] == 1.5
```

In `backend/tests/test_crawler_runtime_adapters.py`, replace the existing import:

```python
from backend.app.modules.crawler.runtime.config import read_incremental_threshold_from_conf
```

with the same import kept as-is, then add this test after `test_read_incremental_threshold_from_backend_runtime_config()`:

```python
def test_incremental_threshold_ignores_env_when_conf_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("INCREMENTAL_EXIST_THRESHOLD", "99")

    assert read_incremental_threshold_from_conf(tmp_path) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_config_api.py::test_crawler_config_ignores_env_and_uses_conf_defaults tests/test_crawler_config_api.py::test_crawler_config_reads_values_from_conf_file tests/test_crawler_runtime_adapters.py::test_incremental_threshold_ignores_env_when_conf_missing -v
```

Expected: FAIL because `backend.app.modules.crawler.config.conf_reader` does not exist.

- [ ] **Step 3: Create `conf_reader.py`**

Create `backend/app/modules/crawler/config/conf_reader.py`:

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from shared.runtime_config import PROJECT_ROOT

CONFIG_KEYS: tuple[str, ...] = (
    "MAX_LIST_PAGES",
    "LIST_PAGE_DELAY_MIN",
    "LIST_PAGE_DELAY_MAX",
    "DETAIL_PAGE_DELAY_MIN",
    "DETAIL_PAGE_DELAY_MAX",
    "SECURITY_WAIT_SECONDS",
    "REQUEST_TIMEOUT",
    "INCREMENTAL_EXIST_THRESHOLD",
)


@dataclass(frozen=True)
class CrawlerRuntimeConfig:
    MAX_LIST_PAGES: int = 50
    LIST_PAGE_DELAY_MIN: float = 4.0
    LIST_PAGE_DELAY_MAX: float = 5.0
    DETAIL_PAGE_DELAY_MIN: float = 2.0
    DETAIL_PAGE_DELAY_MAX: float = 3.0
    SECURITY_WAIT_SECONDS: float = 120.0
    REQUEST_TIMEOUT: int = 30
    INCREMENTAL_EXIST_THRESHOLD: int = 0


DEFAULT_CRAWLER_CONFIG = CrawlerRuntimeConfig()


def crawler_conf_path(base_dir: Path | None = None) -> Path:
    root = base_dir or PROJECT_ROOT
    return root / "data" / "configs" / "crawler.conf"


def _coerce_value(value: str) -> bool | int | float | str:
    text = value.strip().strip('"').strip("'")
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    if text.isdigit():
        return int(text)
    try:
        return float(text)
    except ValueError:
        return text


def read_crawler_conf_values(base_dir: Path | None = None) -> dict[str, str]:
    path = crawler_conf_path(base_dir)
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def read_crawler_config_dict(base_dir: Path | None = None) -> dict[str, int | float]:
    defaults = asdict(DEFAULT_CRAWLER_CONFIG)
    persisted = read_crawler_conf_values(base_dir)
    result: dict[str, int | float] = {}
    for key in CONFIG_KEYS:
        raw_value = persisted.get(key)
        if raw_value is None:
            result[key] = defaults[key]
            continue
        coerced = _coerce_value(raw_value)
        if key in {"MAX_LIST_PAGES", "REQUEST_TIMEOUT", "INCREMENTAL_EXIST_THRESHOLD"}:
            try:
                result[key] = int(coerced)
            except (TypeError, ValueError):
                result[key] = defaults[key]
        else:
            try:
                result[key] = float(coerced)
            except (TypeError, ValueError):
                result[key] = defaults[key]
    result["MAX_LIST_PAGES"] = min(int(result["MAX_LIST_PAGES"]), 50)
    return result


def read_crawler_runtime_config(base_dir: Path | None = None) -> CrawlerRuntimeConfig:
    data = read_crawler_config_dict(base_dir)
    return CrawlerRuntimeConfig(**data)


def _serialize_value(value: Any) -> str:
    text = str(value)
    if not text or any(char.isspace() for char in text) or "#" in text:
        return json.dumps(text, ensure_ascii=False)
    return text


def write_crawler_config(updated: dict[str, object], base_dir: Path | None = None) -> None:
    path = crawler_conf_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = {key: value for key, value in updated.items() if key in CONFIG_KEYS}
    next_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            next_lines.append(line)
            continue
        key, _value = line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key in remaining:
            next_lines.append(f"{normalized_key}={_serialize_value(remaining.pop(normalized_key))}")
        else:
            next_lines.append(line)

    for key, value in remaining.items():
        next_lines.append(f"{key}={_serialize_value(value)}")

    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")
    tmp_path.replace(path)
```

- [ ] **Step 4: Refactor crawler config router to use `conf_reader`**

In `backend/app/modules/crawler/config/router.py`, replace imports and helper usage.

Replace:

```python
import json
from pathlib import Path
from typing import Any
```

with:

```python
from pathlib import Path
```

Replace:

```python
from scraper.config import settings as cfg
```

with:

```python
from backend.app.modules.crawler.config.conf_reader import (
    read_crawler_config_dict,
    write_crawler_config,
)
from scraper.config import settings as scraper_paths
```

Delete local `CONFIG_KEYS`, `CONFIG_DIR_NAME`, `CONFIG_FILE_NAME`, `_defaults()`, `_config_file_path()`, `_coerce_value()`, `_read_conf_file()`, `_serialize_value()`, `_write_conf_file()`, and `_read_config()`.

Replace `_cookie_path()` with:

```python
def _cookie_path() -> Path:
    return scraper_paths.COOKIE_DIR / DEFAULT_COOKIE_FILE
```

Replace `get_config()`:

```python
@router.get("")
def get_config(_current_user: CurrentUser) -> dict:
    return success(data=read_crawler_config_dict())
```

Replace `update_config()`:

```python
@router.put("")
def update_config(body: ConfigUpdate, _current_user: CurrentUser) -> dict:
    updated = body.model_dump(exclude_none=True)
    write_crawler_config(updated)
    return success(data=read_crawler_config_dict())
```

- [ ] **Step 5: Refactor incremental threshold helper**

Replace `backend/app/modules/crawler/runtime/config.py` with:

```python
from __future__ import annotations

from pathlib import Path

from backend.app.modules.crawler.config.conf_reader import read_crawler_runtime_config


def read_incremental_threshold_from_conf(base_dir: Path | None = None) -> int:
    return read_crawler_runtime_config(base_dir).INCREMENTAL_EXIST_THRESHOLD
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_config_api.py tests/test_crawler_runtime_adapters.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/config/conf_reader.py backend/app/modules/crawler/config/router.py backend/app/modules/crawler/runtime/config.py backend/tests/test_crawler_config_api.py backend/tests/test_crawler_runtime_adapters.py
git commit -m "fix: read crawler config from conf"
```

---

### Task 2: Remove Scraper `.env` Runtime Settings From Crawler Execution

**Files:**
- Modify: `.env`
- Modify: `scraper/config/settings.py`
- Modify: `scraper/spiders/javdb/javdb_spider.py`
- Modify: `backend/app/modules/crawler/runtime/engine.py`
- Modify: `backend/app/modules/crawler/tasks/name_extractor.py`
- Test: `backend/tests/test_crawler_config_api.py`
- Test: `scraper/tests/test_javdb_spider_dedupe_callbacks.py`

**Interfaces:**
- Consumes `read_crawler_runtime_config(base_dir: Path | None = None) -> CrawlerRuntimeConfig` from Task 1.
- `scraper.config.settings` still exports `BASE_DIR`, `LOG_DIR`, `RUN_DATA_DIR`, and `COOKIE_DIR`.
- `JavdbSpider.collect_detail_tasks_for_url()` reads `MAX_LIST_PAGES`, list delays, and security wait from `read_crawler_runtime_config()` at call time.
- `JavdbSpider.run_detail_tasks()` reads detail delays and security wait from `read_crawler_runtime_config()` at call time.
- `JavdbCrawlerEngine._build_spider()` and `extract_url_name()` read `REQUEST_TIMEOUT` from conf.

- [ ] **Step 1: Add tests proving `.env` is ignored by crawler settings**

Append this test to `backend/tests/test_crawler_config_api.py`:

```python
def test_scraper_settings_no_longer_exposes_crawler_env_values(monkeypatch) -> None:
    monkeypatch.setenv("MAX_LIST_PAGES", "99")
    monkeypatch.setenv("REQUEST_TIMEOUT", "88")

    from scraper.config import settings

    assert not hasattr(settings, "MAX_LIST_PAGES")
    assert not hasattr(settings, "REQUEST_TIMEOUT")
    assert settings.COOKIE_DIR == settings.BASE_DIR / "data" / "cookies"
```

Append this test to `scraper/tests/test_javdb_spider_dedupe_callbacks.py`:

```python
def test_spider_reads_max_pages_from_conf_reader(monkeypatch) -> None:
    from backend.app.modules.crawler.config.conf_reader import CrawlerRuntimeConfig

    spider = JavdbSpider(fetcher=Fetcher())
    monkeypatch.setattr(
        spider_module,
        "read_crawler_runtime_config",
        lambda: CrawlerRuntimeConfig(MAX_LIST_PAGES=1),
    )
    monkeypatch.setattr(spider_module, "random_sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(spider_module, "is_security_check_page", lambda page: False)
    monkeypatch.setattr(
        spider_module,
        "parse_search_page",
        lambda page, source_page: [
            {"code": f"AAA-{source_page}", "url": f"https://javdb.com/v/{source_page}", "name": f"AAA {source_page}"}
        ],
    )

    result = spider.collect_detail_tasks_for_url(
        url_entry=CrawlTaskUrlEntry(url="https://javdb.com/actors/a", url_type="actors"),
        task_name="任务",
    )

    assert [item["code"] for item in result] == ["AAA-1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_config_api.py::test_scraper_settings_no_longer_exposes_crawler_env_values ../scraper/tests/test_javdb_spider_dedupe_callbacks.py::test_spider_reads_max_pages_from_conf_reader -v
```

Expected: FAIL because `scraper.config.settings` still exposes crawler constants and the spider module does not import `read_crawler_runtime_config`.

- [ ] **Step 3: Remove crawler keys from `.env`**

Edit `.env` so it no longer contains these lines:

```dotenv
MAX_LIST_PAGES=12
REQUEST_TIMEOUT=45
LIST_PAGE_DELAY_MIN=1.0
LIST_PAGE_DELAY_MAX=5.0
DETAIL_PAGE_DELAY_MIN=1.0
DETAIL_PAGE_DELAY_MAX=3.0
SECURITY_WAIT_SECONDS=120.0
INCREMENTAL_EXIST_THRESHOLD=0
```

The file may become empty. Keep it as an empty file only if the repo already tracks it.

- [ ] **Step 4: Simplify `scraper/config/settings.py`**

Replace `scraper/config/settings.py` with:

```python
from pathlib import Path

# BASE_DIR points to project root (one level up from scraper/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

LOG_DIR = BASE_DIR / "data" / "logs"
RUN_DATA_DIR = BASE_DIR / "data" / "run_data"
COOKIE_DIR = BASE_DIR / "data" / "cookies"
```

- [ ] **Step 5: Refactor spider to read runtime config**

In `scraper/spiders/javdb/javdb_spider.py`, replace the import block:

```python
from scraper.config.settings import (
    DETAIL_PAGE_DELAY_MAX,
    DETAIL_PAGE_DELAY_MIN,
    LIST_PAGE_DELAY_MAX,
    LIST_PAGE_DELAY_MIN,
    MAX_LIST_PAGES,
    SECURITY_WAIT_SECONDS,
)
```

with:

```python
from backend.app.modules.crawler.config.conf_reader import read_crawler_runtime_config
```

Inside `collect_detail_tasks_for_url()`, replace:

```python
        max_pages = MAX_LIST_PAGES
```

with:

```python
        runtime_config = read_crawler_runtime_config()
        max_pages = runtime_config.MAX_LIST_PAGES
```

Replace list security waits:

```python
                    f"等待 {SECURITY_WAIT_SECONDS}s 后重试"
...
                fixed_sleep(SECURITY_WAIT_SECONDS, reason="列表页触发人工验证")
```

with:

```python
                    f"等待 {runtime_config.SECURITY_WAIT_SECONDS}s 后重试"
...
                fixed_sleep(runtime_config.SECURITY_WAIT_SECONDS, reason="列表页触发人工验证")
```

Replace list delay:

```python
                random_sleep(LIST_PAGE_DELAY_MIN, LIST_PAGE_DELAY_MAX)
```

with:

```python
                random_sleep(runtime_config.LIST_PAGE_DELAY_MIN, runtime_config.LIST_PAGE_DELAY_MAX)
```

Inside `run_detail_tasks()`, add after `verification_count = 0`:

```python
        runtime_config = read_crawler_runtime_config()
```

Replace detail security waits and detail delays with:

```python
runtime_config.SECURITY_WAIT_SECONDS
runtime_config.DETAIL_PAGE_DELAY_MIN
runtime_config.DETAIL_PAGE_DELAY_MAX
```

- [ ] **Step 6: Refactor request timeout usage**

In `backend/app/modules/crawler/runtime/engine.py`, replace:

```python
from scraper.config.settings import REQUEST_TIMEOUT
```

with:

```python
from backend.app.modules.crawler.config.conf_reader import read_crawler_runtime_config
```

Inside `_build_spider()`, add:

```python
        runtime_config = read_crawler_runtime_config()
```

and replace:

```python
            timeout=REQUEST_TIMEOUT,
```

with:

```python
            timeout=runtime_config.REQUEST_TIMEOUT,
```

In `backend/app/modules/crawler/tasks/name_extractor.py`, replace:

```python
from scraper.config.settings import REQUEST_TIMEOUT
```

with:

```python
from backend.app.modules.crawler.config.conf_reader import read_crawler_runtime_config
```

Before constructing `ScraplingFetcher`, add:

```python
    runtime_config = read_crawler_runtime_config()
```

and replace `timeout=REQUEST_TIMEOUT` with:

```python
        timeout=runtime_config.REQUEST_TIMEOUT,
```

- [ ] **Step 7: Update tests that monkeypatch old module constants**

In `scraper/tests/test_javdb_spider_dedupe_callbacks.py`, replace each `monkeypatch.setattr(spider_module, "MAX_LIST_PAGES", value)` with monkeypatching `read_crawler_runtime_config`:

```python
    from backend.app.modules.crawler.config.conf_reader import CrawlerRuntimeConfig

    monkeypatch.setattr(
        spider_module,
        "read_crawler_runtime_config",
        lambda: CrawlerRuntimeConfig(MAX_LIST_PAGES=1),
    )
```

For the threshold test that needs `MAX_LIST_PAGES=5`, use:

```python
    monkeypatch.setattr(
        spider_module,
        "read_crawler_runtime_config",
        lambda: CrawlerRuntimeConfig(MAX_LIST_PAGES=5),
    )
```

- [ ] **Step 8: Run tests to verify they pass**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_config_api.py ../scraper/tests/test_javdb_spider_dedupe_callbacks.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add .env scraper/config/settings.py scraper/spiders/javdb/javdb_spider.py backend/app/modules/crawler/runtime/engine.py backend/app/modules/crawler/tasks/name_extractor.py backend/tests/test_crawler_config_api.py scraper/tests/test_javdb_spider_dedupe_callbacks.py
git commit -m "fix: remove crawler env settings"
```

---

### Task 3: Add Startup Database And Table Repair

**Files:**
- Create: `backend/app/startup_database.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_init_database_bootstrap.py`
- Create: `backend/tests/test_startup_database_repair.py`

**Interfaces:**
- Produces `build_init_request_from_runtime_config(values: dict[str, str]) -> InitConfigRequest`.
- Produces `ensure_database_ready_from_runtime_config() -> bool`.
- Produces `connect_or_repair_postgres() -> bool`.
- `connect_or_repair_postgres()` returns `False` when runtime config is missing.
- `connect_or_repair_postgres()` returns `True` after either direct connect or successful bootstrap+reconnect.

- [ ] **Step 1: Add runtime config reconstruction tests**

Append these tests to `backend/tests/test_init_database_bootstrap.py`:

```python
def test_build_init_request_from_runtime_config_parses_database_and_redis_urls() -> None:
    from backend.app.startup_database import build_init_request_from_runtime_config

    request = build_init_request_from_runtime_config({
        "DATABASE_URL": "postgresql+asyncpg://admin:secret@db.example:5433/mediaforge",
        "POSTGRES_CONNECT_TIMEOUT": "7",
        "POSTGRES_POOL_SIZE": "8",
        "POSTGRES_MAX_OVERFLOW": "9",
        "POSTGRES_MAX_RETRIES": "4",
        "POSTGRES_RETRY_DELAY": "2",
        "REDIS_URL": "redis://:redispass@redis.example:6380/0",
        "REDIS_SOCKET_TIMEOUT": "11",
        "REDIS_SOCKET_CONNECT_TIMEOUT": "12",
        "REDIS_MAX_CONNECTIONS": "13",
    })

    assert request.databaseHost == "db.example"
    assert request.databasePort == 5433
    assert request.databaseName == "mediaforge"
    assert request.databaseUser == "admin"
    assert request.databasePassword == "secret"
    assert request.postgresConnectTimeout == 7
    assert request.postgresPoolSize == 8
    assert request.postgresMaxOverflow == 9
    assert request.postgresMaxRetries == 4
    assert request.postgresRetryDelay == 2
    assert request.redisHost == "redis.example"
    assert request.redisPort == 6380
    assert request.redisPassword == "redispass"
    assert request.redisSocketTimeout == 11
    assert request.redisConnectTimeout == 12
    assert request.redisMaxConnections == 13


def test_build_init_request_from_runtime_config_supports_passwordless_redis() -> None:
    from backend.app.startup_database import build_init_request_from_runtime_config

    request = build_init_request_from_runtime_config({
        "DATABASE_URL": "postgresql+asyncpg://admin:secret@localhost:54329/mediaforge",
        "REDIS_URL": "redis://localhost:6379/0",
    })

    assert request.redisHost == "localhost"
    assert request.redisPort == 6379
    assert request.redisPassword == ""
```

- [ ] **Step 2: Add startup repair tests**

Create `backend/tests/test_startup_database_repair.py`:

```python
from __future__ import annotations

from unittest.mock import Mock


class SessionContext:
    def __init__(self) -> None:
        self.statements: list[object] = []

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None

    def execute(self, statement):
        self.statements.append(statement)
        return None


def test_connect_or_repair_postgres_returns_false_without_runtime_config(monkeypatch) -> None:
    from backend.app import startup_database

    monkeypatch.setattr(startup_database, "runtime_config_exists", lambda: False)

    assert startup_database.connect_or_repair_postgres() is False


def test_connect_or_repair_postgres_connects_without_repair(monkeypatch) -> None:
    from backend.app import startup_database

    connect = Mock()
    bootstrap = Mock()
    monkeypatch.setattr(startup_database, "runtime_config_exists", lambda: True)
    monkeypatch.setattr(startup_database, "connect_postgres", connect)
    monkeypatch.setattr(startup_database, "get_session_factory", lambda: SessionContext)
    monkeypatch.setattr(startup_database, "bootstrap_application_database", bootstrap)

    assert startup_database.connect_or_repair_postgres() is True
    assert connect.call_count == 1
    assert bootstrap.call_count == 0


def test_connect_or_repair_postgres_bootstraps_after_connect_failure(monkeypatch) -> None:
    from backend.app import startup_database

    connect = Mock(side_effect=[RuntimeError("database does not exist"), None])
    bootstrap = Mock()
    monkeypatch.setattr(startup_database, "runtime_config_exists", lambda: True)
    monkeypatch.setattr(startup_database, "connect_postgres", connect)
    monkeypatch.setattr(startup_database, "close_postgres", Mock())
    monkeypatch.setattr(startup_database, "get_session_factory", lambda: SessionContext)
    monkeypatch.setattr(startup_database, "read_runtime_config", lambda: {
        "DATABASE_URL": "postgresql+asyncpg://admin:secret@localhost:54329/mediaforge",
        "REDIS_URL": "redis://localhost:6379/0",
    })
    monkeypatch.setattr(startup_database, "bootstrap_application_database", bootstrap)

    assert startup_database.connect_or_repair_postgres() is True
    assert connect.call_count == 2
    assert bootstrap.call_count == 1
    assert bootstrap.call_args.args[0].databaseName == "mediaforge"


def test_connect_or_repair_postgres_bootstraps_after_table_check_failure(monkeypatch) -> None:
    from backend.app import startup_database

    connect = Mock()
    bootstrap = Mock()

    def broken_session_factory():
        raise RuntimeError("relation users does not exist")

    monkeypatch.setattr(startup_database, "runtime_config_exists", lambda: True)
    monkeypatch.setattr(startup_database, "connect_postgres", connect)
    monkeypatch.setattr(startup_database, "close_postgres", Mock())
    monkeypatch.setattr(startup_database, "get_session_factory", broken_session_factory)
    monkeypatch.setattr(startup_database, "read_runtime_config", lambda: {
        "DATABASE_URL": "postgresql+asyncpg://admin:secret@localhost:54329/mediaforge",
        "REDIS_URL": "redis://localhost:6379/0",
    })
    monkeypatch.setattr(startup_database, "bootstrap_application_database", bootstrap)

    assert startup_database.connect_or_repair_postgres() is True
    assert bootstrap.call_count == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_init_database_bootstrap.py::test_build_init_request_from_runtime_config_parses_database_and_redis_urls tests/test_init_database_bootstrap.py::test_build_init_request_from_runtime_config_supports_passwordless_redis tests/test_startup_database_repair.py -v
```

Expected: FAIL because `backend.app.startup_database` does not exist.

- [ ] **Step 4: Create startup database helper**

Create `backend/app/startup_database.py`:

```python
from __future__ import annotations

import logging
from urllib.parse import urlparse, unquote

from sqlalchemy import text

from backend.app.modules.init.database_bootstrap import bootstrap_application_database
from backend.app.modules.init.schemas import InitConfigRequest
from shared.database.session import close_postgres, connect_postgres, get_session_factory
from shared.runtime_config import read_runtime_config, runtime_config_exists

logger = logging.getLogger(__name__)


def _int_value(values: dict[str, str], key: str, default: int) -> int:
    try:
        return int(values.get(key, default))
    except (TypeError, ValueError):
        return default


def build_init_request_from_runtime_config(values: dict[str, str]) -> InitConfigRequest:
    database_url = values.get("DATABASE_URL", "")
    redis_url = values.get("REDIS_URL", "redis://localhost:6379/0")
    parsed_db = urlparse(database_url)
    parsed_redis = urlparse(redis_url)
    return InitConfigRequest(
        databaseHost=parsed_db.hostname or "localhost",
        databasePort=parsed_db.port or 5432,
        databaseName=(parsed_db.path or "/mediaforge").lstrip("/") or "mediaforge",
        databaseUser=unquote(parsed_db.username or "admin"),
        databasePassword=unquote(parsed_db.password or "admin123"),
        postgresConnectTimeout=_int_value(values, "POSTGRES_CONNECT_TIMEOUT", 5),
        postgresPoolSize=_int_value(values, "POSTGRES_POOL_SIZE", 5),
        postgresMaxOverflow=_int_value(values, "POSTGRES_MAX_OVERFLOW", 10),
        postgresMaxRetries=_int_value(values, "POSTGRES_MAX_RETRIES", 10),
        postgresRetryDelay=_int_value(values, "POSTGRES_RETRY_DELAY", 3),
        redisHost=parsed_redis.hostname or "localhost",
        redisPort=parsed_redis.port or 6379,
        redisPassword=unquote(parsed_redis.password or ""),
        redisSocketTimeout=_int_value(values, "REDIS_SOCKET_TIMEOUT", 5),
        redisConnectTimeout=_int_value(values, "REDIS_SOCKET_CONNECT_TIMEOUT", 5),
        redisMaxConnections=_int_value(values, "REDIS_MAX_CONNECTIONS", 10),
    )


def _verify_application_tables() -> None:
    factory = get_session_factory()
    with factory() as session:
        session.execute(text("SELECT 1 FROM users LIMIT 1"))
        session.execute(text("SELECT 1 FROM crawl_tasks LIMIT 1"))


def ensure_database_ready_from_runtime_config() -> bool:
    request = build_init_request_from_runtime_config(read_runtime_config())
    bootstrap_application_database(request)
    return True


def connect_or_repair_postgres() -> bool:
    if not runtime_config_exists():
        return False

    try:
        connect_postgres()
        _verify_application_tables()
        return True
    except Exception as exc:
        logger.warning("PostgreSQL startup check failed, attempting bootstrap repair: %s", exc)
        close_postgres()

    ensure_database_ready_from_runtime_config()
    connect_postgres()
    _verify_application_tables()
    return True
```

- [ ] **Step 5: Confirm startup table verification checks real tables**

Confirm `backend/app/startup_database.py` imports SQLAlchemy `text`:

```python
from sqlalchemy import text
```

Confirm `_verify_application_tables()` executes both application table checks:

```python
        session.execute(text("SELECT 1 FROM users LIMIT 1"))
        session.execute(text("SELECT 1 FROM crawl_tasks LIMIT 1"))
```

- [ ] **Step 6: Wire helper into lifespan**

In `backend/app/main.py`, add:

```python
from backend.app.startup_database import connect_or_repair_postgres
```

Replace this startup block:

```python
    if runtime_config_exists():
        connect_postgres()
        logger.info("PostgreSQL connected.")
```

with:

```python
    if connect_or_repair_postgres():
        logger.info("PostgreSQL connected.")
```

Remove unused `connect_postgres` import from:

```python
from shared.database.session import close_postgres, connect_postgres, get_session_factory
```

so it becomes:

```python
from shared.database.session import close_postgres, get_session_factory
```

Keep `runtime_config_exists()` import for shutdown unless the implementer also changes shutdown to use another state flag.

- [ ] **Step 7: Run startup tests to verify they pass**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_init_database_bootstrap.py tests/test_startup_database_repair.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/startup_database.py backend/app/main.py backend/tests/test_init_database_bootstrap.py backend/tests/test_startup_database_repair.py
git commit -m "fix: repair database on startup"
```

---

### Task 4: Focused Regression Verification

**Files:**
- No new files.
- Verify files changed in Tasks 1-3.

**Interfaces:**
- Consumes conf-only crawler config reader and startup database repair helper.
- Produces verified behavior for crawler config persistence, scraper runtime config, and startup database repair.

- [ ] **Step 1: Search for crawler `.env` reads**

Run:

```bash
rg -n "REQUEST_TIMEOUT|MAX_LIST_PAGES|LIST_PAGE_DELAY|DETAIL_PAGE_DELAY|SECURITY_WAIT_SECONDS|INCREMENTAL_EXIST_THRESHOLD|load_dotenv|APP_ENV" scraper backend shared .env
```

Expected: crawler setting names appear in `conf_reader.py`, API schemas/tests, frontend types, and docs/tests only. They do not appear as `os.getenv(...)` reads or `.env` entries.

- [ ] **Step 2: Run focused backend tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_config_api.py tests/test_crawler_runtime_adapters.py tests/test_init_database_bootstrap.py tests/test_startup_database_repair.py -v
```

Expected: PASS.

- [ ] **Step 3: Run focused scraper tests**

Run:

```bash
source .venv/bin/activate
python -m pytest scraper/tests/test_javdb_spider_dedupe_callbacks.py backend/tests/test_javdb_spider_multi_url.py -v
```

Expected: PASS.

- [ ] **Step 4: Run broader backend tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/ -v
```

Expected: PASS. If unrelated pre-existing failures appear, record exact test names and failure messages before continuing.

- [ ] **Step 5: Inspect final diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: only intended implementation files remain modified, or the working tree is clean after task commits.

- [ ] **Step 6: Commit verification fixes if needed**

If verification required small corrections, commit them:

```bash
git add .env scraper/config/settings.py scraper/spiders/javdb/javdb_spider.py backend/app/modules/crawler backend/app/startup_database.py backend/app/main.py backend/tests shared
git commit -m "test: verify conf config and startup repair"
```

If no corrections were needed, do not create an empty commit.
