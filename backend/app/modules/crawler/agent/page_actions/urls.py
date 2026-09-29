from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from backend.app.modules.crawler.tasks.url_detection import detect_task_url_type


@dataclass(frozen=True)
class NormalizedJavdbListUrl:
    url: str
    url_type: str


def normalize_javdb_list_url(raw_url: str) -> NormalizedJavdbListUrl:
    parsed = urlsplit(raw_url.strip())
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("仅支持 HTTP 或 HTTPS URL")
    if hostname != "javdb.com" and not hostname.endswith(".javdb.com"):
        raise ValueError("仅支持 JavDB URL")
    if parsed.username or parsed.password:
        raise ValueError("URL 不能包含认证信息")
    path = parsed.path or "/"
    if path == "/" or re.match(r"^/v/[^/]+/?$", path):
        raise ValueError("当前页面不是 JavDB 列表页")
    default_port = (parsed.scheme == "http" and parsed.port == 80) or (
        parsed.scheme == "https" and parsed.port == 443
    )
    netloc = hostname if parsed.port is None or default_port else f"{hostname}:{parsed.port}"
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != "page"
    ]
    query.append(("page", "1"))
    query.sort(key=lambda pair: (pair[0], pair[1]))
    url = urlunsplit((parsed.scheme, netloc, path, urlencode(query, doseq=True), ""))
    return NormalizedJavdbListUrl(
        url=url,
        url_type=detect_task_url_type(url, "javdb") or "list",
    )
