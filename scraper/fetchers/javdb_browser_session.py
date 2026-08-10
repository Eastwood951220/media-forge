from __future__ import annotations

import os
import shutil
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from scrapling.parser import Adaptor

from scraper.config import settings
from scraper.core.security import detect_access_state

JavDBReason = str

JAVDB_PROFILE_DIR = settings.BROWSER_PROFILE_DIR / "javdb"
JAVDB_STORAGE_STATE_PATH = settings.COOKIE_DIR / "javdb_storage_state.json"
_FETCH_LOCK = threading.Lock()


@dataclass(frozen=True)
class JavDBSessionStatus:
    profile_exists: bool
    storage_state_exists: bool
    verification_browser_open: bool
    last_check_at: str | None = None
    last_check_url: str | None = None
    last_status_code: int | None = None
    last_reason: str = "not_checked"
    last_message: str = "尚未检测 JavDB 浏览器会话"
    logged_in_detected: bool = False
    runtime_environment: str = "unknown"

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class JavDBSessionCheck:
    ok: bool
    status_code: int | None
    reason: str
    message: str
    url: str
    logged_in_detected: bool = False
    checked_at: str | None = None
    runtime_environment: str = "unknown"

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_environment() -> str:
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return "local_gui"
    if Path("/.dockerenv").exists() or os.environ.get("container"):
        return "headless"
    return "unknown"


def _logged_in_detected(page) -> bool:
    text = getattr(page, "text", "") or ""
    if callable(text):
        text = text() or ""
    return "/users/profile" in str(text) or "users/profile" in str(text)


class JavDBBrowserSession:
    def __init__(
        self,
        profile_dir: Path | None = None,
        storage_state_path: Path | None = None,
    ) -> None:
        self.profile_dir = profile_dir or JAVDB_PROFILE_DIR
        self.storage_state_path = storage_state_path or JAVDB_STORAGE_STATE_PATH
        self._verification_playwright = None
        self._verification_context = None
        self._last_check: JavDBSessionCheck | None = None

    def status(self) -> JavDBSessionStatus:
        last = self._last_check
        return JavDBSessionStatus(
            profile_exists=self.profile_dir.exists(),
            storage_state_exists=self.storage_state_path.exists(),
            verification_browser_open=self._verification_context is not None,
            last_check_at=last.checked_at if last else None,
            last_check_url=last.url if last else None,
            last_status_code=last.status_code if last else None,
            last_reason=last.reason if last else "not_checked",
            last_message=last.message if last else "尚未检测 JavDB 浏览器会话",
            logged_in_detected=last.logged_in_detected if last else False,
            runtime_environment=_runtime_environment(),
        )

    def open_verification_browser(self, url: str = "https://javdb.com", timeout: int = 30) -> JavDBSessionStatus:
        if self._verification_context is not None:
            return self.status()
        if _runtime_environment() == "headless":
            return JavDBSessionStatus(
                profile_exists=self.profile_dir.exists(),
                storage_state_exists=self.storage_state_path.exists(),
                verification_browser_open=False,
                last_reason="browser_unavailable",
                last_message="当前环境不支持本地弹窗诊断。请用普通 Chrome 完成 JavDB 验证后导出 Cookie，并在 Media Forge 的 Cookie 配置中保存。",
                runtime_environment="headless",
            )
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._verification_playwright = sync_playwright().start()
            self._verification_context = self._verification_playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=False,
                locale="zh-CN",
                timeout=timeout * 1000,
                args=["--disable-dev-shm-usage"],
            )
            page = self._verification_context.new_page()
            page.set_default_timeout(timeout * 1000)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            return self.status()
        except PlaywrightError:
            self.close_verification_browser()
            return JavDBSessionStatus(
                profile_exists=self.profile_dir.exists(),
                storage_state_exists=self.storage_state_path.exists(),
                verification_browser_open=False,
                last_reason="browser_unavailable",
                last_message="Playwright 辅助浏览器不可用，Chromium/Playwright 未正确安装或启动失败。请使用普通 Chrome 完成验证并导出 Cookie。",
                runtime_environment=_runtime_environment(),
            )

    def close_verification_browser(self) -> JavDBSessionStatus:
        if self._verification_context is not None:
            self._verification_context.close()
            self._verification_context = None
        if self._verification_playwright is not None:
            self._verification_playwright.stop()
            self._verification_playwright = None
        return self.status()

    def _fetch_unlocked(self, url: str, *, headers: dict | None = None, timeout: int = 30):
        timeout_ms = timeout * 1000
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        playwright = sync_playwright().start()
        context = None
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=True,
                locale="zh-CN",
                timeout=timeout_ms,
                args=["--disable-dev-shm-usage"],
            )
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
            if context is not None:
                context.close()
            playwright.stop()

    def fetch(self, url: str, *, headers: dict | None = None, timeout: int = 30):
        with _FETCH_LOCK:
            return self._fetch_unlocked(url, headers=headers, timeout=timeout)

    def check(self, url: str = "https://javdb.com", *, timeout: int = 30, headers: dict | None = None) -> JavDBSessionCheck:
        if not self.profile_dir.exists():
            result = JavDBSessionCheck(
                ok=False,
                status_code=None,
                reason="no_browser_profile",
                message="尚未建立 JavDB 浏览器会话。请先用普通 Chrome 完成 JavDB 验证并在 Cookie 配置中保存导出的 Cookie；Playwright 辅助验证浏览器仅用于诊断，可能被 JavDB 拒绝。",
                url=url,
                checked_at=_now_iso(),
                runtime_environment=_runtime_environment(),
            )
            self._last_check = result
            return result
        try:
            page = self.fetch(url, headers=headers, timeout=timeout)
        except PlaywrightTimeoutError:
            result = JavDBSessionCheck(
                ok=False,
                status_code=None,
                reason="browser_timeout",
                message="JavDB 浏览器会话检测超时，请稍后重试或延长请求超时",
                url=url,
                checked_at=_now_iso(),
                runtime_environment=_runtime_environment(),
            )
            self._last_check = result
            return result
        except PlaywrightError:
            result = JavDBSessionCheck(
                ok=False,
                status_code=None,
                reason="browser_unavailable",
                message="浏览器模式不可用，Chromium/Playwright 未正确安装或启动失败",
                url=url,
                checked_at=_now_iso(),
                runtime_environment=_runtime_environment(),
            )
            self._last_check = result
            return result

        access_state = detect_access_state(page)
        logged_in = _logged_in_detected(page)
        reason = access_state.reason
        message = access_state.message
        if access_state.status_code == 403:
            reason = "profile_expired_or_blocked"
            message = "JavDB 浏览器会话已存在但仍返回 403。普通 Chrome 可访问不代表 Playwright/后端浏览器也会被接受，请优先使用普通 Chrome 导出的 Cookie 做静态检测；若仍失败，说明目标环境的后端访问被拒。"
        elif access_state.reason == "security_keywords":
            reason = "verification_loop_or_rejected"
            message = "普通 Chrome 可以通过验证，但 Playwright 辅助浏览器仍停留在人机验证页面，说明自动化浏览器被 JavDB 拒绝。请不要在该浏览器中反复重试，改用普通 Chrome 完成验证后导出 Cookie。"
        elif access_state.ok and not logged_in:
            reason = "profile_not_verified"
            message = "JavDB 页面可访问，但未检测到登录或验证状态。请用普通 Chrome 完成验证后导出 Cookie，再回到 Media Forge 保存并检测。"
        elif access_state.ok:
            reason = "ok"
            message = "JavDB 浏览器会话检测通过"

        result = JavDBSessionCheck(
            ok=reason == "ok",
            status_code=access_state.status_code,
            reason=reason,
            message=message,
            url=url,
            logged_in_detected=logged_in,
            checked_at=_now_iso(),
            runtime_environment=_runtime_environment(),
        )
        self._last_check = result
        return result

    def export_storage_state(self) -> Path:
        self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        playwright = sync_playwright().start()
        context = None
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=True,
                locale="zh-CN",
                args=["--disable-dev-shm-usage"],
            )
            context.storage_state(path=str(self.storage_state_path))
            return self.storage_state_path
        finally:
            if context is not None:
                context.close()
            playwright.stop()

    def reset(self) -> JavDBSessionStatus:
        self.close_verification_browser()
        if self.profile_dir.exists():
            shutil.rmtree(self.profile_dir)
        if self.storage_state_path.exists():
            self.storage_state_path.unlink()
        self._last_check = None
        return self.status()
