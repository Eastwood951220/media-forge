import json
from http import HTTPStatus

from fastapi.testclient import TestClient

from scraper.config import settings


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_cookie_dir_is_data_cookies() -> None:
    assert settings.COOKIE_DIR == settings.BASE_DIR / "data" / "cookies"


def test_get_crawler_config_returns_original_keys(
    client: TestClient,
    admin_user,
) -> None:
    response = client.get(
        "/api/crawler/config",
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["MAX_LIST_PAGES"] == settings.MAX_LIST_PAGES
    assert body["data"]["LIST_PAGE_DELAY_MIN"] == settings.LIST_PAGE_DELAY_MIN
    assert body["data"]["LIST_PAGE_DELAY_MAX"] == settings.LIST_PAGE_DELAY_MAX
    assert body["data"]["DETAIL_PAGE_DELAY_MIN"] == settings.DETAIL_PAGE_DELAY_MIN
    assert body["data"]["DETAIL_PAGE_DELAY_MAX"] == settings.DETAIL_PAGE_DELAY_MAX
    assert body["data"]["SECURITY_WAIT_SECONDS"] == settings.SECURITY_WAIT_SECONDS
    assert body["data"]["REQUEST_TIMEOUT"] == settings.REQUEST_TIMEOUT
    assert body["data"]["INCREMENTAL_EXIST_THRESHOLD"] == settings.INCREMENTAL_EXIST_THRESHOLD


def test_update_crawler_config_matches_original_env_update(
    client: TestClient,
    admin_user,
) -> None:
    response = client.put(
        "/api/crawler/config",
        json={
            "MAX_LIST_PAGES": 12,
            "REQUEST_TIMEOUT": 45,
        },
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert data["MAX_LIST_PAGES"] == 12
    assert data["REQUEST_TIMEOUT"] == 45


def test_cookies_config_reads_and_writes_browser_export_array(
    client: TestClient,
    admin_user,
    monkeypatch,
    tmp_path,
) -> None:
    cookie_dir = tmp_path / "data" / "cookies"
    monkeypatch.setattr(settings, "COOKIE_DIR", cookie_dir)
    payload = {
        "cookies": [
            {
                "domain": "javdb.com",
                "expirationDate": None,
                "hostOnly": True,
                "httpOnly": False,
                "name": "session",
                "path": "/",
                "sameSite": "lax",
                "secure": False,
                "session": False,
                "storeId": None,
                "value": "abc123",
            }
        ]
    }
    headers = auth_headers(client, admin_user)

    put_response = client.put(
        "/api/crawler/config/cookies",
        json=payload,
        headers=headers,
    )

    assert put_response.status_code == HTTPStatus.OK
    cookie_file = cookie_dir / "javdb_cookies.json"
    assert cookie_file.exists()
    assert json.loads(cookie_file.read_text(encoding="utf-8")) == payload["cookies"]

    get_response = client.get("/api/crawler/config/cookies", headers=headers)

    assert get_response.status_code == HTTPStatus.OK
    assert get_response.json()["data"] == payload


def test_cookies_config_converts_old_flat_dict(
    client: TestClient,
    admin_user,
    monkeypatch,
    tmp_path,
) -> None:
    cookie_dir = tmp_path / "data" / "cookies"
    cookie_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "COOKIE_DIR", cookie_dir)
    (cookie_dir / "javdb_cookies.json").write_text(
        json.dumps({"session": "abc123"}),
        encoding="utf-8",
    )

    response = client.get(
        "/api/crawler/config/cookies",
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.OK
    cookies = response.json()["data"]["cookies"]
    assert cookies == [
        {
            "domain": "javdb.com",
            "expirationDate": None,
            "hostOnly": True,
            "httpOnly": False,
            "name": "session",
            "path": "/",
            "sameSite": "lax",
            "secure": False,
            "session": False,
            "storeId": None,
            "value": "abc123",
        }
    ]


def test_update_crawler_config_persists_to_conf_file_after_restart(
    client: TestClient,
    admin_user,
    monkeypatch,
    tmp_path,
) -> None:
    from backend.app.modules.crawler.config import router as config_router

    conf_dir = tmp_path / "data" / "configs"
    conf_dir.mkdir(parents=True)
    conf_file = conf_dir / "crawler.conf"
    conf_file.write_text(
        "REQUEST_TIMEOUT=30\n"
        "UNCHANGED_VALUE=keep-me\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config_router.cfg, "BASE_DIR", tmp_path)
    monkeypatch.delenv("MAX_LIST_PAGES", raising=False)
    monkeypatch.delenv("REQUEST_TIMEOUT", raising=False)

    response = client.put(
        "/api/crawler/config",
        json={
            "MAX_LIST_PAGES": 17,
            "REQUEST_TIMEOUT": 46,
        },
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.OK
    persisted = conf_file.read_text(encoding="utf-8")
    assert "MAX_LIST_PAGES=17\n" in persisted
    assert "REQUEST_TIMEOUT=46\n" in persisted
    assert "UNCHANGED_VALUE=keep-me\n" in persisted

    monkeypatch.delenv("MAX_LIST_PAGES", raising=False)
    monkeypatch.delenv("REQUEST_TIMEOUT", raising=False)

    get_response = client.get(
        "/api/crawler/config",
        headers=auth_headers(client, admin_user),
    )

    assert get_response.status_code == HTTPStatus.OK
    data = get_response.json()["data"]
    assert data["MAX_LIST_PAGES"] == 17
    assert data["REQUEST_TIMEOUT"] == 46
