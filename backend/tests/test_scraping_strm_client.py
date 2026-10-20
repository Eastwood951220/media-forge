import json

import httpx

from backend.app.modules.scraping.strm import run_strm_generation


def _config() -> dict:
    return {
        "base_url": "https://example.com/",
        "api_key": "secret-key",
        "directory_id": 4,
        "trigger_delay_seconds": 30,
    }


def test_run_posts_the_expected_request() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    result = run_strm_generation(_config(), transport=httpx.MockTransport(handler))

    assert result.success is True
    assert result.status_code == 200
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/sync/path/start"
    assert captured["query"] == {"api_key": "secret-key"}
    assert captured["body"] == {"id": 4}


def test_non_2xx_returns_a_failure_result() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    result = run_strm_generation(_config(), transport=httpx.MockTransport(handler))

    assert result.success is False
    assert result.status_code == 500
    assert "HTTP 500" in result.message
    assert "boom" in result.message


def test_connect_error_is_captured_and_the_key_is_redacted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed to connect to {request.url}")

    result = run_strm_generation(_config(), transport=httpx.MockTransport(handler))

    assert result.success is False
    assert result.status_code is None
    assert "secret-key" not in result.message
    assert "***" in result.message


def test_long_response_body_is_truncated() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="x" * 1000)

    result = run_strm_generation(_config(), transport=httpx.MockTransport(handler))

    assert "x" * 300 in result.message
    assert "x" * 301 not in result.message
    assert result.message.endswith("...")


def test_httpx_request_log_redacts_the_api_key(caplog) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    with caplog.at_level("INFO", logger="httpx"):
        run_strm_generation(_config(), transport=httpx.MockTransport(handler))

    assert "secret-key" not in caplog.text
    assert "api_key=***" in caplog.text
