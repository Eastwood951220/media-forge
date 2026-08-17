from typing import Literal

from pydantic import BaseModel, Field


class ConfigUpdate(BaseModel):
    MAX_LIST_PAGES: int | None = Field(None, ge=1, le=100)
    LIST_MAX_WORKERS: int | None = Field(None, ge=1, le=32)
    DETAIL_MAX_WORKERS: int | None = Field(None, ge=1, le=32)
    LIST_PAGE_DELAY_MIN: float | None = Field(None, ge=0)
    LIST_PAGE_DELAY_MAX: float | None = Field(None, ge=0)
    DETAIL_PAGE_DELAY_MIN: float | None = Field(None, ge=0)
    DETAIL_PAGE_DELAY_MAX: float | None = Field(None, ge=0)
    SECURITY_WAIT_SECONDS: float | None = Field(None, ge=0)
    INCREMENTAL_EXIST_THRESHOLD: int | None = Field(None, ge=0)
    REQUEST_TIMEOUT: int | None = Field(None, ge=1)
    JAVDB_FETCH_MODE: Literal["static", "agent"] | None = None
    JAVDB_AGENT_PARSE_MODE: Literal["backend", "extension"] | None = None
    AGENT_CLAIM_TIMEOUT_SECONDS: float | None = None


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


class CookieTestRequest(BaseModel):
    url: str | None = None


class CookieTestResponse(BaseModel):
    ok: bool
    status_code: int | None = None
    reason: str
    message: str
    url: str
    logged_in_detected: bool = False
    fetch_mode: str = "static"
