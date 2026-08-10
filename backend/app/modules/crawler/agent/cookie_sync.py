from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from scraper.config import settings as scraper_paths

JAVDB_COOKIE_FILE = "javdb_cookies.json"


class AgentCookie(BaseModel):
    name: str
    value: str
    domain: str
    path: str = "/"
    expirationDate: float | None = None
    hostOnly: bool = False
    httpOnly: bool = False
    sameSite: str | None = None
    secure: bool = True
    session: bool = False
    storeId: str | None = None


class CookieSyncResult(BaseModel):
    accepted: int
    rejected: int
    cookie_names: list[str] = Field(default_factory=list)


def _cookie_path() -> Path:
    return scraper_paths.COOKIE_DIR / JAVDB_COOKIE_FILE


def _is_javdb_domain(domain: str) -> bool:
    normalized = domain.strip().lower().lstrip(".")
    return normalized == "javdb.com" or normalized.endswith(".javdb.com")


def sync_javdb_cookies(cookies: list[AgentCookie]) -> CookieSyncResult:
    accepted_rows: list[dict] = []
    rejected = 0
    for cookie in cookies:
        if not cookie.name or not _is_javdb_domain(cookie.domain):
            rejected += 1
            continue
        accepted_rows.append(cookie.model_dump())

    path = _cookie_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(accepted_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return CookieSyncResult(
        accepted=len(accepted_rows),
        rejected=rejected,
        cookie_names=[row["name"] for row in accepted_rows],
    )
