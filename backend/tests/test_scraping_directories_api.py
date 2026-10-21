from http import HTTPStatus
from pathlib import Path

from backend.app.modules.scraping import browse


def _auth_headers(client) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_tree(root: Path) -> None:
    (root / "Alpha").mkdir()
    (root / "beta").mkdir()
    (root / ".hidden").mkdir()
    (root / "movie.mkv").write_text("", encoding="utf-8")


def test_directories_require_authentication(client) -> None:
    response = client.get("/api/scraping/directories", params={"path": "/"})

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_directories_list_subfolders(client, admin_user, tmp_path) -> None:
    _make_tree(tmp_path)
    headers = _auth_headers(client)
    resolved = str(tmp_path.resolve())

    response = client.get(
        "/api/scraping/directories",
        headers=headers,
        params={"path": str(tmp_path)},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert data["path"] == resolved
    assert data["parent"] == str(tmp_path.resolve().parent)
    assert [entry["name"] for entry in data["entries"]] == ["Alpha", "beta"]
    assert [entry["path"] for entry in data["entries"]] == [
        str(tmp_path / "Alpha"),
        str(tmp_path / "beta"),
    ]
    assert data["truncated"] is False
    assert data["roots"]
    assert all({"name", "path"} <= set(root) for root in data["roots"])


def test_directories_can_include_hidden_folders(client, admin_user, tmp_path) -> None:
    _make_tree(tmp_path)
    headers = _auth_headers(client)

    response = client.get(
        "/api/scraping/directories",
        headers=headers,
        params={"path": str(tmp_path), "include_hidden": "true"},
    )

    assert response.status_code == HTTPStatus.OK
    names = [entry["name"] for entry in response.json()["data"]["entries"]]
    assert names == [".hidden", "Alpha", "beta"]


def test_directories_default_to_configured_browse_root(
    client,
    admin_user,
    tmp_path,
    monkeypatch,
) -> None:
    (tmp_path / "library").mkdir()
    monkeypatch.setenv(browse.BROWSE_ROOT_ENV, str(tmp_path))
    headers = _auth_headers(client)

    response = client.get("/api/scraping/directories", headers=headers)

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert data["path"] == str(tmp_path.resolve())
    assert [entry["name"] for entry in data["entries"]] == ["library"]


def test_directories_reject_invalid_paths(client, admin_user, tmp_path) -> None:
    headers = _auth_headers(client)
    file_path = tmp_path / "movie.mkv"
    file_path.write_text("", encoding="utf-8")

    relative = client.get(
        "/api/scraping/directories",
        headers=headers,
        params={"path": "media/library"},
    )
    missing = client.get(
        "/api/scraping/directories",
        headers=headers,
        params={"path": str(tmp_path / "missing")},
    )
    not_a_folder = client.get(
        "/api/scraping/directories",
        headers=headers,
        params={"path": str(file_path)},
    )

    assert relative.status_code == HTTPStatus.BAD_REQUEST
    assert missing.status_code == HTTPStatus.BAD_REQUEST
    assert not_a_folder.status_code == HTTPStatus.BAD_REQUEST
    assert "绝对路径" in relative.json()["msg"]
    assert "不存在" in missing.json()["msg"]
    assert "文件夹" in not_a_folder.json()["msg"]


def test_directories_truncate_large_listings(client, admin_user, tmp_path, monkeypatch) -> None:
    for index in range(3):
        (tmp_path / f"folder-{index}").mkdir()
    monkeypatch.setattr(browse, "MAX_ENTRIES", 2)
    headers = _auth_headers(client)

    response = client.get(
        "/api/scraping/directories",
        headers=headers,
        params={"path": str(tmp_path)},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert data["truncated"] is True
    assert len(data["entries"]) == 2
