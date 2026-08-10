from backend.app.modules.crawler.agent.parser_bridge import (
    AgentPageSnapshot,
    AgentSnapshotParseError,
    parse_agent_detail_snapshot,
    parse_agent_list_snapshot,
)


def test_parse_agent_list_snapshot_uses_existing_javdb_selectors() -> None:
    snapshot = AgentPageSnapshot(
        page_kind="list",
        url="https://javdb.com/?page=1",
        source_page=1,
        fragments={
            "items": """
            <div class="item">
              <a class="box" href="/v/abc" title="ABC title">
                <img src="https://img.example/abc.jpg" />
                <div class="video-title"><strong>ABC-001</strong></div>
              </a>
            </div>
            """,
        },
    )

    tasks = parse_agent_list_snapshot(snapshot)

    assert tasks[0]["code"] == "ABC-001"
    assert tasks[0]["url"] == "https://javdb.com/v/abc"
    assert tasks[0]["source_page"] == 1


def test_parse_agent_detail_snapshot_rejects_invalid_page_kind() -> None:
    snapshot = AgentPageSnapshot(
        page_kind="list",
        url="https://javdb.com/v/abc",
        fragments={"movie_panel": ""},
    )

    try:
        parse_agent_detail_snapshot(snapshot)
    except AgentSnapshotParseError as exc:
        assert "detail_required" in str(exc)
    else:
        raise AssertionError("expected AgentSnapshotParseError")
