import json
from pathlib import Path

from scraper.config.settings import COOKIE_DIR
from shared.settings_cookies import read_cookies, read_legacy_cookies, write_cookies
from shared.settings_store import SettingsStore


class CookieManager:
    def __init__(self, filename: str, *, filepath: Path | None = None, store: SettingsStore | None = None):
        self.filename = filename
        # Explicit paths are legacy adapters for migration and tests, never a DB fallback.
        self.filepath: Path = filepath or COOKIE_DIR / filename
        self._legacy_path = filepath
        self._store = store

    def load(self) -> dict:
        return {row["name"]: row["value"] for row in self.load_browser_cookies()}

    def save(self, cookies: dict) -> None:
        if self._legacy_path is not None:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            self.filepath.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
            return
        write_cookies(cookies, self._store, filename=self.filename)

    def load_browser_cookies(self) -> list[dict]:
        if self._legacy_path is not None:
            try:
                return read_legacy_cookies(self.filepath)
            except (json.JSONDecodeError, OSError):
                return []
        return read_cookies(self._store, filename=self.filename)
