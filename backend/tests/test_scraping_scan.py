from datetime import datetime
from pathlib import Path

from backend.app.modules.content.movies.storage_status import STORAGE_STATUS_STORED, STORAGE_STATUS_NOT_STORED
from backend.app.modules.scraping.scan import (
    judge_folder,
    refresh_movie_status,
    scan_directory,
)
from shared.database.models.content import Movie


def _make_movie(db, code: str, *, stored: bool, target_folder: str = "") -> Movie:
    summary = {
        "storage_status": STORAGE_STATUS_STORED if stored else STORAGE_STATUS_NOT_STORED,
        "locations": [{"target_folder": target_folder, "path": target_folder}] if target_folder else [],
    }
    movie = Movie(code=code, source_name=f"{code} title", storage_summary=summary)
    db.add(movie)
    db.commit()
    db.refresh(movie)
    return movie


def _make_folder(root: Path, relative: str, *, strm=True, nfo=True, images=1) -> Path:
    folder = root / relative
    folder.mkdir(parents=True, exist_ok=True)
    if strm:
        (folder / f"{folder.name}.strm").write_text("http://example.com/v.mkv", encoding="utf-8")
    if nfo:
        (folder / "movie.nfo").write_text("<movie/>", encoding="utf-8")
    for index in range(images):
        (folder / f"image{index}.jpg").write_bytes(b"img")
    return folder


def _config(scrape_root: Path) -> dict:
    return {"scrape_root": str(scrape_root), "media_root": "/media", "metadata_sources": ["javdb", "javbus"]}


def test_judge_folder_requires_strm_nfo_and_image(tmp_path: Path) -> None:
    good = _make_folder(tmp_path, "ADN-784")
    no_nfo = _make_folder(tmp_path, "BBB-001", nfo=False)
    no_image = _make_folder(tmp_path, "CCC-002", images=0)

    assert judge_folder(good) == (True, True, 1)
    assert judge_folder(no_nfo) == (True, False, 1)
    assert judge_folder(no_image) == (True, True, 0)


def test_scan_directory_updates_stored_movies(tmp_path: Path, db_session, monkeypatch) -> None:
    stored = _make_movie(db_session, "ADN-784", stored=True, target_folder="/media/演员/ADN-784")
    missing = _make_movie(db_session, "BBB-001", stored=True, target_folder="/media/演员/BBB-001")
    not_stored = _make_movie(db_session, "CCC-002", stored=False)
    _make_folder(tmp_path, "演员/ADN-784")

    summary = scan_directory(db_session, _config(tmp_path))

    db_session.refresh(stored)
    db_session.refresh(missing)
    db_session.refresh(not_stored)
    assert stored.scraping_status == "scraped"
    assert stored.scraping_folder == "/media/演员/ADN-784"
    assert missing.scraping_status == "not_scraped"
    assert missing.scraping_folder is None
    assert not_stored.scraping_status is None
    assert summary.scraped_folders == 1
    assert summary.updated_movies >= 2


def test_scan_directory_matches_by_folder_name_when_location_does_not_map(tmp_path: Path, db_session) -> None:
    movie = _make_movie(db_session, "ADN-784", stored=True, target_folder="/other/ADN-784")
    _make_folder(tmp_path, "ADN-784")

    scan_directory(db_session, _config(tmp_path))

    db_session.refresh(movie)
    assert movie.scraping_status == "scraped"
    assert movie.scraping_folder == "/media/ADN-784"


def test_refresh_movie_status_clears_when_not_stored(tmp_path: Path, db_session) -> None:
    movie = _make_movie(db_session, "ADN-784", stored=False, target_folder="/media/ADN-784")
    movie.scraping_status = "scraped"
    movie.scraping_folder = "/media/ADN-784"
    db_session.commit()

    status = refresh_movie_status(db_session, movie)

    db_session.refresh(movie)
    assert status == "not_stored"
    assert movie.scraping_status is None
