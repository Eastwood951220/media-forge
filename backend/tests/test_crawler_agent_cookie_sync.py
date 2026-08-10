import json

from backend.app.modules.crawler.agent.cookie_sync import AgentCookie, sync_javdb_cookies


def test_sync_javdb_cookies_writes_only_javdb_domains(monkeypatch, tmp_path) -> None:
    cookie_dir = tmp_path / "cookies"
    monkeypatch.setattr("scraper.config.settings.COOKIE_DIR", cookie_dir)

    result = sync_javdb_cookies([
        AgentCookie(name="cf_clearance", value="ok", domain=".javdb.com", path="/"),
        AgentCookie(name="ignored", value="bad", domain="example.com", path="/"),
    ])

    assert result.accepted == 1
    assert result.rejected == 1
    saved = json.loads((cookie_dir / "javdb_cookies.json").read_text(encoding="utf-8"))
    assert saved[0]["name"] == "cf_clearance"
    assert saved[0]["value"] == "ok"


def test_sync_javdb_cookies_redacts_values_in_result(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("scraper.config.settings.COOKIE_DIR", tmp_path / "cookies")

    result = sync_javdb_cookies([
        AgentCookie(name="session", value="secret", domain="javdb.com", path="/"),
    ])

    assert "secret" not in result.model_dump_json()
