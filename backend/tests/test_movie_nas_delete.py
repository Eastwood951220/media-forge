from pathlib import Path
from contextlib import contextmanager

import pytest

from backend.app.modules.content.movies.nas_delete import (
    UnsafeNasMovieFolder,
    delete_nas_movie_folders,
    resolve_nas_movie_folder,
)
from shared.database.models.content import Movie


def _movie(code: str, cloud_folder: str) -> Movie:
    return Movie(code=code, source_name=code, scraping_status="scraped", scraping_folder=cloud_folder)


def test_deletes_exact_strm_parent_folder_and_keeps_actor_folder(tmp_path: Path) -> None:
    root = tmp_path / "vol1" / "1000" / "Media" / "嘿嘿" / "日本"
    target = root / "愛那あい" / "CJOD-496-C"
    target.mkdir(parents=True)
    (target / "CJOD-496-C.strm").write_text("url", encoding="utf-8")
    (target / "poster.jpg").write_bytes(b"image")
    config = {"scrape_root": str(root), "media_root": "/media"}
    movie = _movie("CJOD-496-C", "/media/愛那あい/CJOD-496-C")
    assert resolve_nas_movie_folder(movie, config) == target
    result = delete_nas_movie_folders([movie], config)
    assert result.deleted_folders == [str(target)]
    assert not target.exists()
    assert target.parent.is_dir()


def test_rejects_symlink_or_root_escape_before_deleting(tmp_path: Path) -> None:
    root = tmp_path / "media"
    outside = tmp_path / "outside" / "CJOD-496-C"
    outside.mkdir(parents=True)
    root.mkdir()
    (root / "愛那あい").symlink_to(outside.parent, target_is_directory=True)
    config = {"scrape_root": str(root), "media_root": "/media"}
    with pytest.raises(UnsafeNasMovieFolder):
        resolve_nas_movie_folder(_movie("CJOD-496-C", "/media/愛那あい/CJOD-496-C"), config)
    with pytest.raises(UnsafeNasMovieFolder):
        resolve_nas_movie_folder(_movie("CJOD-496-C", "/media/.."), config)
    assert outside.exists()


def test_missing_nas_folder_is_reported_without_deleting_actor_folder(tmp_path: Path) -> None:
    root = tmp_path / "media"
    (root / "愛那あい").mkdir(parents=True)
    movie = _movie("CJOD-496-C", "/media/愛那あい/CJOD-496-C")
    result = delete_nas_movie_folders([movie], {"scrape_root": str(root), "media_root": "/media"})
    assert result.missing_folders == [str(root / "愛那あい" / "CJOD-496-C")]
    assert (root / "愛那あい").exists()


@pytest.mark.parametrize("mode,keeps_row", [("cloud_only", True), ("database_and_cloud", False)])
def test_movie_delete_api_removes_nas_folder_in_both_cloud_modes(
    tmp_path: Path, client, auth_headers, db_session, monkeypatch, mode, keeps_row,
) -> None:
    root = tmp_path / "日本"
    folder = root / "愛那あい" / "CJOD-496-C"
    folder.mkdir(parents=True)
    (folder / "CJOD-496-C.strm").write_text("url", encoding="utf-8")
    movie = _movie("CJOD-496-C", "/media/愛那あい/CJOD-496-C")
    movie.storage_summary = {"locations": [{"target_folder": "/Movies/CJOD-496-C"}]}
    db_session.add(movie)
    db_session.commit()
    deleted_cloud = []

    class Provider:
        def delete_file(self, path):
            deleted_cloud.append(path)

    class StorageConfig:
        @contextmanager
        def open_provider(self):
            yield {}, Provider()

    monkeypatch.setattr("backend.app.modules.storage.config.service.StorageConfigService", StorageConfig)
    monkeypatch.setattr(
        "backend.app.modules.scraping.config.ScrapingConfigService.get_raw_config",
        lambda _self: {"scrape_root": str(root), "media_root": "/media", "jellyfin_auto_refresh_enabled": False},
    )
    response = client.post("/api/content/movies/delete", json={"movie_ids": [str(movie.id)], "mode": mode}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["nas_deleted_folders"] == [str(folder)]
    assert deleted_cloud == ["/Movies/CJOD-496-C"]
    assert not folder.exists()
    assert folder.parent.is_dir()
    detail = client.get(f"/api/content/movies/{movie.id}", headers=auth_headers)
    assert (detail.status_code == 200) is keeps_row
    if keeps_row:
        assert detail.json()["data"]["scraping_status"] == "not_scraped"


def test_nested_nas_folders_abort_before_cloud_delete(tmp_path: Path, client, auth_headers, db_session, monkeypatch) -> None:
    root = tmp_path / "media"
    (root / "A-001" / "B-002").mkdir(parents=True)
    first = _movie("A-001", "/media/A-001")
    second = _movie("B-002", "/media/A-001/B-002")
    db_session.add_all([first, second])
    db_session.commit()
    called = []

    class Provider:
        def delete_file(self, path):
            called.append(path)

    class StorageConfig:
        @contextmanager
        def open_provider(self):
            yield {}, Provider()

    monkeypatch.setattr("backend.app.modules.storage.config.service.StorageConfigService", StorageConfig)
    monkeypatch.setattr(
        "backend.app.modules.scraping.config.ScrapingConfigService.get_raw_config",
        lambda _self: {"scrape_root": str(root), "media_root": "/media", "jellyfin_auto_refresh_enabled": False},
    )
    response = client.post(
        "/api/content/movies/delete",
        json={"movie_ids": [str(first.id), str(second.id)], "mode": "cloud_only"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert called == []
    assert (root / "A-001" / "B-002").is_dir()


def test_nas_failure_reports_partial_cleanup_and_keeps_movie(tmp_path: Path, client, auth_headers, db_session, monkeypatch) -> None:
    root = tmp_path / "media"
    folder = root / "CJOD-496-C"
    folder.mkdir(parents=True)
    (folder / "CJOD-496-C.strm").write_text("url", encoding="utf-8")
    movie = _movie("CJOD-496-C", "/media/CJOD-496-C")
    movie.storage_summary = {"locations": [{"target_folder": "/Movies/CJOD-496-C"}]}
    db_session.add(movie)
    db_session.commit()
    cloud_deleted = []

    class Provider:
        def delete_file(self, path):
            cloud_deleted.append(path)

    class StorageConfig:
        @contextmanager
        def open_provider(self):
            yield {}, Provider()

    monkeypatch.setattr("backend.app.modules.storage.config.service.StorageConfigService", StorageConfig)
    monkeypatch.setattr(
        "backend.app.modules.scraping.config.ScrapingConfigService.get_raw_config",
        lambda _self: {"scrape_root": str(root), "media_root": "/media", "jellyfin_auto_refresh_enabled": False},
    )
    monkeypatch.setattr("backend.app.modules.content.movies.nas_delete.shutil.rmtree", lambda _path: (_ for _ in ()).throw(OSError("NAS read-only")))
    response = client.post(
        "/api/content/movies/delete",
        json={"movie_ids": [str(movie.id)], "mode": "database_and_cloud"},
        headers=auth_headers,
    )
    assert response.status_code == 502
    assert response.json()["data"]["cloud_deleted_folders"] == ["/Movies/CJOD-496-C"]
    assert response.json()["data"]["nas_failed_folders"][0]["path"] == str(folder)
    assert cloud_deleted == ["/Movies/CJOD-496-C"]
    assert client.get(f"/api/content/movies/{movie.id}", headers=auth_headers).status_code == 200


def test_selected_parent_folder_cannot_delete_unselected_nested_movie(tmp_path: Path, client, auth_headers, db_session, monkeypatch) -> None:
    root = tmp_path / "media"
    (root / "A-001" / "B-002").mkdir(parents=True)
    selected = _movie("A-001", "/media/A-001")
    unselected = _movie("B-002", "/media/A-001/B-002")
    db_session.add_all([selected, unselected])
    db_session.commit()

    class StorageConfig:
        @contextmanager
        def open_provider(self):
            yield {}, object()

    monkeypatch.setattr("backend.app.modules.storage.config.service.StorageConfigService", StorageConfig)
    monkeypatch.setattr(
        "backend.app.modules.scraping.config.ScrapingConfigService.get_raw_config",
        lambda _self: {"scrape_root": str(root), "media_root": "/media", "jellyfin_auto_refresh_enabled": False},
    )
    response = client.post(
        "/api/content/movies/delete",
        json={"movie_ids": [str(selected.id)], "mode": "cloud_only"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert (root / "A-001" / "B-002").is_dir()
