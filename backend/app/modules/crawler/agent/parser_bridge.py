from __future__ import annotations

from pydantic import BaseModel, Field
from scrapling.parser import Adaptor

from scraper.spiders.javdb.javdb_parser import parse_detail_page, parse_search_page


class AgentPageSnapshot(BaseModel):
    page_kind: str
    url: str
    fragments: dict[str, str] = Field(default_factory=dict)
    source_page: int = 1


class AgentSnapshotParseError(ValueError):
    pass


def _html_from_fragments(snapshot: AgentPageSnapshot, required: tuple[str, ...]) -> str:
    missing = [key for key in required if not snapshot.fragments.get(key)]
    if missing:
        raise AgentSnapshotParseError(f"missing_required_fragments:{','.join(missing)}")
    body = "\n".join(snapshot.fragments.values())
    return f"<!doctype html><html><head><title></title></head><body>{body}</body></html>"


def _page(snapshot: AgentPageSnapshot, required: tuple[str, ...]) -> Adaptor:
    return Adaptor(_html_from_fragments(snapshot, required), url=snapshot.url)


def parse_agent_list_snapshot(snapshot: AgentPageSnapshot) -> list[dict]:
    if snapshot.page_kind != "list":
        raise AgentSnapshotParseError("invalid_page_kind:list_required")
    page = _page(snapshot, ("items",))
    return parse_search_page(page, source_page=snapshot.source_page)


def parse_agent_detail_snapshot(snapshot: AgentPageSnapshot) -> dict:
    if snapshot.page_kind != "detail":
        raise AgentSnapshotParseError("invalid_page_kind:detail_required")
    page = _page(snapshot, ("title", "movie_panel"))
    detail = parse_detail_page(page)
    if not detail.get("source_name") and not detail.get("code"):
        raise AgentSnapshotParseError("parser_empty_detail")
    return detail
