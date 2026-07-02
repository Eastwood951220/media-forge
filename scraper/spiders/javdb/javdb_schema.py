from typing import Any, TypedDict


class MovieSearchItem(TypedDict, total=False):
    title: str
    code: str
    href: str
    cover: str


class MagnetItem(TypedDict, total=False):
    magnet: str
    name: str
    size: float
    size_text: str
    file_count: int | None
    file_text: str
    tags: list[str]
    has_chinese_sub: bool
    date: str


class MovieDetailItem(TypedDict, total=False):
    source_name: str
    code: str
    cover: str
    magnets: list[MagnetItem]
    release_date: str
    duration: int
    director: str
    maker: str
    series: str
    rating: float
    tags: list[str]
    actors: list[str]


class JavdbDetailTask(TypedDict, total=False):
    url: str
    name: str
    code: str
    status: str
    source_page: int
    reason: str
    detail: dict[str, Any]
