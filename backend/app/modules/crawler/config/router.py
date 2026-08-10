import json
from pathlib import Path

from fastapi import APIRouter

from backend.app.core.dependencies import CurrentUser
from backend.app.modules.crawler.config.conf_reader import (
    read_crawler_config_dict,
    read_crawler_runtime_config,
    write_crawler_config,
)
from backend.app.modules.crawler.config.schemas import (
    ConfigUpdate,
    CookiesConfig,
    CookieTestRequest,
    CookieTestResponse,
    JavDBSessionCheckRequest,
    JavDBSessionExportResponse,
)
from scraper.config import settings as scraper_paths
from scraper.config.sites import JAVDB_SITE
from scraper.core.security import detect_access_state
from scraper.fetchers.javdb_browser_session import JavDBBrowserSession
from scraper.fetchers.site_fetcher import build_site_fetcher
from shared.schemas.common import success

router = APIRouter(prefix="/api/crawler/config", tags=["crawler-config"])

DEFAULT_COOKIE_FILE = "javdb_cookies.json"


def _cookie_path() -> Path:
    return scraper_paths.COOKIE_DIR / DEFAULT_COOKIE_FILE


@router.get("")
def get_config(_current_user: CurrentUser) -> dict:
    return success(data=read_crawler_config_dict())


@router.put("")
def update_config(body: ConfigUpdate, _current_user: CurrentUser) -> dict:
    updated = body.model_dump(exclude_none=True)
    write_crawler_config(updated)
    return success(data=read_crawler_config_dict())


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


def _page_text(page) -> str:
    text = getattr(page, "text", "") or ""
    if callable(text):
        text = text() or ""
    return str(text)


def _logged_in_detected(page) -> bool:
    text = _page_text(page)
    return "/users/profile" in text or "users/profile" in text


@router.post("/cookies/test")
def test_cookies_config(body: CookieTestRequest, _current_user: CurrentUser) -> dict:
    url = body.url or JAVDB_SITE["base_url"]
    runtime_config = read_crawler_runtime_config()
    fetch_mode = runtime_config.JAVDB_FETCH_MODE
    fetcher = build_site_fetcher("javdb", runtime_config)
    try:
        page = fetcher.get(url)
    except Exception:
        payload = CookieTestResponse(
            ok=False,
            status_code=None,
            reason="browser_unavailable" if fetch_mode == "browser" else "fetch_error",
            message="浏览器模式不可用，Chromium/Playwright 未正确安装或启动失败" if fetch_mode == "browser" else "请求 JavDB 失败，请检查网络连接和 Cookie 配置",
            url=url,
            logged_in_detected=False,
            fetch_mode=fetch_mode,
        )
        return success(data=payload.model_dump())

    access_state = detect_access_state(page)
    message = "JavDB Cookie 测试通过"
    if not access_state.ok:
        if fetch_mode == "static" and access_state.reason == "http_403":
            message = "JavDB static 模式返回 403，请切换浏览器模式后重试"
        elif fetch_mode == "browser":
            message = "JavDB 浏览器模式仍触发安全验证。普通 Chrome 可通过不代表 Playwright/后端浏览器会被接受；请优先用普通 Chrome 完成验证后导出 Cookie 并测试 static 模式，若仍失败则说明目标环境拒绝后端访问。"
        else:
            message = access_state.message

    payload = CookieTestResponse(
        ok=access_state.ok,
        status_code=access_state.status_code,
        reason=access_state.reason,
        message=message,
        url=url,
        logged_in_detected=access_state.ok and _logged_in_detected(page),
        fetch_mode=fetch_mode,
    )
    return success(data=payload.model_dump())


@router.get("/javdb-session")
def get_javdb_session(_current_user: CurrentUser) -> dict:
    return success(data=JavDBBrowserSession().status().model_dump())


@router.post("/javdb-session/open")
def open_javdb_session(body: JavDBSessionCheckRequest, _current_user: CurrentUser) -> dict:
    runtime_config = read_crawler_runtime_config()
    url = body.url or JAVDB_SITE["base_url"]
    status = JavDBBrowserSession().open_verification_browser(url=url, timeout=runtime_config.REQUEST_TIMEOUT)
    return success(data=status.model_dump())


@router.post("/javdb-session/close")
def close_javdb_session(_current_user: CurrentUser) -> dict:
    return success(data=JavDBBrowserSession().close_verification_browser().model_dump())


@router.post("/javdb-session/check")
def check_javdb_session(body: JavDBSessionCheckRequest, _current_user: CurrentUser) -> dict:
    runtime_config = read_crawler_runtime_config()
    url = body.url or JAVDB_SITE["base_url"]
    result = JavDBBrowserSession().check(
        url=url,
        timeout=runtime_config.REQUEST_TIMEOUT,
        headers=JAVDB_SITE["headers"],
    )
    return success(data=result.model_dump())


@router.post("/javdb-session/export")
def export_javdb_session(_current_user: CurrentUser) -> dict:
    path = JavDBBrowserSession().export_storage_state()
    return success(data=JavDBSessionExportResponse(path=str(path)).model_dump())


@router.delete("/javdb-session")
def reset_javdb_session(_current_user: CurrentUser) -> dict:
    return success(data=JavDBBrowserSession().reset().model_dump())
