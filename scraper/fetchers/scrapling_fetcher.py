from __future__ import annotations

from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from scrapling.fetchers import Fetcher
from scrapling.parser import Adaptor

from scraper.core.exceptions import FetchError


def _normalize_same_site(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text == "lax":
        return "Lax"
    if text == "strict":
        return "Strict"
    if text in {"none", "no_restriction"}:
        return "None"
    return None


def normalize_browser_cookies(cookies: list[dict] | None) -> list[dict]:
    normalized: list[dict] = []
    for cookie in cookies or []:
        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None:
            continue

        item: dict[str, Any] = {
            "name": str(name),
            "value": str(value),
        }
        if cookie.get("domain"):
            item["domain"] = str(cookie["domain"])
        if cookie.get("path"):
            item["path"] = str(cookie["path"])
        if cookie.get("expirationDate") is not None:
            item["expires"] = float(cookie["expirationDate"])
        if cookie.get("httpOnly") is not None:
            item["httpOnly"] = bool(cookie["httpOnly"])
        if cookie.get("secure") is not None:
            item["secure"] = bool(cookie["secure"])
        same_site = _normalize_same_site(cookie.get("sameSite"))
        if same_site:
            item["sameSite"] = same_site
        elif item.get("domain") == "javdb.com":
            item["sameSite"] = "Lax"
        normalized.append(item)
    return normalized


class ScraplingFetcher:
    def __init__(
        self,
        headers: dict | None = None,
        cookies: dict | None = None,
        browser_cookies: list[dict] | None = None,
        timeout: int = 30,
        dynamic: bool = False,
    ):
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.browser_cookies = browser_cookies or []
        self.timeout = timeout
        self.dynamic = dynamic

    def get(
        self,
        url: str,
        *,
        headers: dict | None = None,
        cookies: dict | None = None,
    ):
        merged_headers = {**self.headers, **(headers or {})}
        merged_cookies = {**self.cookies, **(cookies or {})}

        if self.dynamic:
            return self._browser_get(url, headers=merged_headers)

        return Fetcher.get(
            url,
            headers=merged_headers,
            cookies=merged_cookies,
            timeout=self.timeout,
            impersonate="chrome",
        )

    def _browser_get(self, url: str, *, headers: dict):
        timeout_ms = int(self.timeout * 1000)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(locale="zh-CN")
                try:
                    normalized_cookies = normalize_browser_cookies(self.browser_cookies)
                    if normalized_cookies:
                        context.add_cookies(normalized_cookies)
                    page = context.new_page()
                    page.set_default_timeout(timeout_ms)
                    if headers:
                        page.set_extra_http_headers(headers)
                    response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    try:
                        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
                    except PlaywrightTimeoutError:
                        pass
                    html = page.content()
                    adaptor = Adaptor(html)
                    setattr(adaptor, "status_code", getattr(response, "status", None))
                    return adaptor
                finally:
                    context.close()
                    browser.close()
        except PlaywrightTimeoutError as exc:
            raise FetchError("JavDB 浏览器模式加载超时，请稍后重试或降低并发") from exc
        except PlaywrightError as exc:
            raise FetchError("浏览器模式不可用，Chromium/Playwright 未正确安装或启动失败") from exc
