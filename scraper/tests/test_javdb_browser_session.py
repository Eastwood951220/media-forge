from pathlib import Path

import pytest

from scraper.fetchers import javdb_browser_session as module
from scraper.fetchers.javdb_browser_session import JavDBBrowserSession


class FakeResponse:
    status = 200


class FakePage:
    def __init__(self, html: str = "<html><body>JavDB 成人影片數據庫 /users/profile</body></html>"):
        self.html = html
        self.default_timeout = None
        self.headers = None
        self.goto_calls = []

    def set_default_timeout(self, timeout):
        self.default_timeout = timeout

    def set_extra_http_headers(self, headers):
        self.headers = headers

    def goto(self, url, wait_until, timeout):
        self.goto_calls.append((url, wait_until, timeout))
        return FakeResponse()

    def wait_for_load_state(self, state, timeout):
        self.load_state = (state, timeout)

    def content(self):
        return self.html


class FakeContext:
    def __init__(self):
        self.page = FakePage()
        self.closed = False
        self.storage_state_path = None

    def new_page(self):
        return self.page

    def storage_state(self, path):
        self.storage_state_path = Path(path)
        self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_state_path.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")
        return {"cookies": [], "origins": []}

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, context):
        self.context = context
        self.launch_calls = []

    def launch_persistent_context(self, user_data_dir, **kwargs):
        self.launch_calls.append((Path(user_data_dir), kwargs))
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        return self.context


class FakePlaywright:
    def __init__(self, context):
        self.chromium = FakeChromium(context)

    def stop(self):
        pass


class FakeSyncPlaywright:
    def __init__(self, context):
        self.context = context
        self.closed = False
        self.playwright = FakePlaywright(context)

    def start(self):
        return self.playwright

    def stop(self):
        self.closed = True


def test_status_reports_profile_and_storage_state(tmp_path) -> None:
    profile_dir = tmp_path / "profile"
    storage_state = tmp_path / "cookies" / "state.json"
    profile_dir.mkdir()
    storage_state.parent.mkdir()
    storage_state.write_text("{}", encoding="utf-8")

    status = JavDBBrowserSession(profile_dir=profile_dir, storage_state_path=storage_state).status()

    assert status.profile_exists is True
    assert status.storage_state_exists is True
    assert status.verification_browser_open is False
    assert status.runtime_environment in {"local_gui", "headless", "unknown"}


def test_check_without_profile_returns_no_browser_profile(tmp_path) -> None:
    session = JavDBBrowserSession(
        profile_dir=tmp_path / "missing-profile",
        storage_state_path=tmp_path / "cookies" / "state.json",
    )

    result = session.check("https://javdb.com", timeout=30)

    assert result.ok is False
    assert result.reason == "no_browser_profile"
    assert result.status_code is None


def test_fetch_uses_persistent_context_and_returns_adaptor(monkeypatch, tmp_path) -> None:
    fake_context = FakeContext()
    fake_sync = FakeSyncPlaywright(fake_context)
    monkeypatch.setattr(module, "sync_playwright", lambda: fake_sync)
    session = JavDBBrowserSession(
        profile_dir=tmp_path / "profile",
        storage_state_path=tmp_path / "cookies" / "state.json",
    )

    page = session.fetch("https://javdb.com", headers={"Accept-Language": "zh-CN"}, timeout=30)

    assert page.status_code == 200
    assert fake_sync.playwright.chromium.launch_calls[0][0] == tmp_path / "profile"
    assert fake_context.page.headers == {"Accept-Language": "zh-CN"}
    assert fake_context.closed is True


def test_export_storage_state_writes_file(monkeypatch, tmp_path) -> None:
    fake_context = FakeContext()
    fake_sync = FakeSyncPlaywright(fake_context)
    monkeypatch.setattr(module, "sync_playwright", lambda: fake_sync)
    session = JavDBBrowserSession(
        profile_dir=tmp_path / "profile",
        storage_state_path=tmp_path / "cookies" / "state.json",
    )

    session.fetch("https://javdb.com", timeout=30)
    exported = session.export_storage_state()

    assert exported == tmp_path / "cookies" / "state.json"
    assert exported.exists()


def test_reset_removes_profile_and_storage_state(tmp_path) -> None:
    profile_dir = tmp_path / "profile"
    storage_state = tmp_path / "cookies" / "state.json"
    (profile_dir / "Default").mkdir(parents=True)
    (profile_dir / "Default" / "Cookies").write_text("cookie-db", encoding="utf-8")
    storage_state.parent.mkdir()
    storage_state.write_text("{}", encoding="utf-8")

    status = JavDBBrowserSession(profile_dir=profile_dir, storage_state_path=storage_state).reset()

    assert status.profile_exists is False
    assert status.storage_state_exists is False
    assert not profile_dir.exists()
    assert not storage_state.exists()
