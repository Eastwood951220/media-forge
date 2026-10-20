from http import HTTPStatus

from backend.app.modules.scraping.strm import StrmRunResult


def _auth_headers(client, admin_user) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _write_config(tmp_path) -> None:
    (tmp_path / "scraping.conf").write_text(
        "base_url=https://example.com\n"
        "api_key=secret-key\n"
        "directory_id=4\n"
        "trigger_delay_seconds=30\n",
        encoding="utf-8",
    )


def test_get_and_put_scraping_config(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    headers = _auth_headers(client, admin_user)

    get_response = client.get("/api/scraping/config", headers=headers)

    assert get_response.status_code == HTTPStatus.OK
    assert get_response.json()["data"] == {
        "base_url": "",
        "api_key": "",
        "api_key_configured": False,
        "directory_id": None,
        "trigger_delay_seconds": 30,
    }

    put_response = client.put(
        "/api/scraping/config",
        headers=headers,
        json={
            "base_url": "https://example.com/",
            "api_key": "secret-key-1234",
            "directory_id": 4,
            "trigger_delay_seconds": 45,
        },
    )

    assert put_response.status_code == HTTPStatus.OK
    data = put_response.json()["data"]
    assert data["base_url"] == "https://example.com"
    assert data["api_key"] == "************1234"
    assert data["api_key_configured"] is True
    assert (tmp_path / "scraping.conf").exists()

    preserved = client.put(
        "/api/scraping/config",
        headers=headers,
        json={"api_key": "************1234", "base_url": "https://new.example.com"},
    )
    assert preserved.json()["data"]["api_key"] == "************1234"


def test_put_rejects_invalid_base_url(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    headers = _auth_headers(client, admin_user)

    response = client.put(
        "/api/scraping/config",
        headers=headers,
        json={"base_url": "ftp://example.com"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_put_rejects_out_of_range_values(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    headers = _auth_headers(client, admin_user)

    too_short = client.put(
        "/api/scraping/config",
        headers=headers,
        json={"trigger_delay_seconds": 5},
    )
    bad_directory = client.put(
        "/api/scraping/config",
        headers=headers,
        json={"directory_id": 0},
    )

    assert too_short.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert bad_directory.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_manual_run_rejects_unconfigured_service(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    headers = _auth_headers(client, admin_user)

    response = client.post("/api/scraping/strm/run", headers=headers)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    payload = response.json()
    assert payload["code"] == HTTPStatus.BAD_REQUEST
    assert "未配置外部服务地址" in payload["msg"]


def test_manual_run_returns_the_external_result(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    _write_config(tmp_path)
    headers = _auth_headers(client, admin_user)

    from backend.app.modules.scraping import router as scraping_router

    monkeypatch.setattr(
        scraping_router,
        "run_strm_generation",
        lambda config: StrmRunResult(success=True, status_code=200, message="HTTP 200"),
    )

    response = client.post("/api/scraping/strm/run", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"] == {
        "success": True,
        "status_code": 200,
        "message": "HTTP 200",
    }


def test_manual_run_reports_external_failure_with_200(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    _write_config(tmp_path)
    headers = _auth_headers(client, admin_user)

    from backend.app.modules.scraping import router as scraping_router

    monkeypatch.setattr(
        scraping_router,
        "run_strm_generation",
        lambda config: StrmRunResult(
            success=False,
            status_code=503,
            message="HTTP 503: unavailable",
        ),
    )

    response = client.post("/api/scraping/strm/run", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["success"] is False
    assert response.json()["data"]["status_code"] == 503
