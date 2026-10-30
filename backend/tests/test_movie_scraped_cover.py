from http import HTTPStatus

from shared.database.models.content import Movie


def test_scraped_cover_is_served_only_for_authenticated_scraped_movie(
    client, db_session, auth_headers, tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    scrape_root = tmp_path / "artwork"
    folder = scrape_root / "AAA-001"
    folder.mkdir(parents=True)
    image = b"\xff\xd8\xff\xd9"
    (folder / "folder.jpg").write_bytes(image)
    (tmp_path / "scraping.conf").write_text(
        f"scrape_root={scrape_root}\nmedia_root=/media\n", encoding="utf-8",
    )
    movie = Movie(
        code="AAA-001", source_url="https://example.test/movie",
        scraping_status="scraped", scraping_folder="/media/AAA-001",
    )
    db_session.add(movie)
    db_session.commit()
    url = f"/api/content/movies/{movie.id}/scraped-cover"

    assert client.get(url).status_code == HTTPStatus.UNAUTHORIZED
    response = client.get(url, headers=auth_headers)
    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.content == image

    (folder / "folder.jpg").unlink()
    assert client.get(url, headers=auth_headers).status_code == HTTPStatus.NOT_FOUND

    movie.scraping_status = "not_scraped"
    db_session.commit()
    assert client.get(url, headers=auth_headers).status_code == HTTPStatus.NOT_FOUND


def test_scraped_cover_cannot_escape_configured_root(
    client, db_session, auth_headers, tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    scrape_root = tmp_path / "artwork"
    scrape_root.mkdir()
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"secret")
    folder = scrape_root / "AAA-001"
    folder.mkdir()
    (folder / "folder.jpg").symlink_to(outside)
    (tmp_path / "scraping.conf").write_text(
        f"scrape_root={scrape_root}\nmedia_root=/media\n", encoding="utf-8",
    )
    movie = Movie(
        code="AAA-001", source_url="https://example.test/movie",
        scraping_status="scraped", scraping_folder="/media/AAA-001",
    )
    db_session.add(movie)
    db_session.commit()

    response = client.get(f"/api/content/movies/{movie.id}/scraped-cover", headers=auth_headers)
    assert response.status_code == HTTPStatus.NOT_FOUND
