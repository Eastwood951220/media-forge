import uuid

from shared.database.models.content import Movie, MovieMagnet


def test_collect_cloud_delete_folders_deletes_number_folders_not_video_files() -> None:
    from backend.app.modules.content.movies.delete_service import collect_cloud_delete_folders

    movie = Movie(
        code="ABC-123",
        source_name="folder extraction",
        storage_summary={
            "locations": [
                {
                    "path": "/嘿嘿嘿/日本/巨乳/ABC-123/ABC-123.mp4",
                    "target_folder": "/嘿嘿嘿/日本/巨乳/ABC-123",
                    "storage_location": "巨乳",
                },
                {
                    "path": "/嘿嘿嘿/日本/巨乳/ABC-456/ABC-456.mp4",
                    "storage_location": "巨乳",
                },
            ],
            "tasks": [
                "/嘿嘿嘿/日本/巨乳/ABC-123/ABC-123.mp4",
                "/嘿嘿嘿/日本/巨乳/ABC-456/ABC-456.mp4",
            ],
        },
    )

    assert collect_cloud_delete_folders(movie) == [
        "/嘿嘿嘿/日本/巨乳/ABC-123",
        "/嘿嘿嘿/日本/巨乳/ABC-456",
    ]


def test_delete_movies_cloud_only_deletes_folders_and_keeps_database_rows(db_session):
    from backend.app.modules.content.movies.delete_service import delete_movies

    movie = Movie(
        code="ABC-123",
        source_name="cloud only",
        storage_summary={
            "storage_status": "stored",
            "last_status": "stored",
            "locations": [
                {
                    "path": "/Movies/A/ABC-123/ABC-123.mp4",
                    "target_folder": "/Movies/A/ABC-123",
                    "storage_location": "A",
                }
            ],
        },
    )
    db_session.add(movie)
    db_session.flush()
    movie_id = movie.id

    class Provider:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def delete_file(self, path: str):
            self.deleted.append(path)

    provider = Provider()

    result = delete_movies(
        db=db_session,
        movies=[movie],
        mode="cloud_only",
        provider=provider,
    )

    assert result.deleted_movies == 0
    assert result.deleted_magnets == 0
    assert result.updated_movies == 1
    assert result.cloud_deleted_folders == ["/Movies/A/ABC-123"]
    assert provider.deleted == ["/Movies/A/ABC-123"]
    assert db_session.get(Movie, movie_id) is not None
    assert db_session.get(Movie, movie_id).storage_summary["storage_status"] == "not_stored"
    assert db_session.get(Movie, movie_id).storage_summary["locations"] == []


def test_delete_movies_database_and_cloud_deletes_movie_after_cloud_cleanup(db_session):
    from backend.app.modules.content.movies.delete_service import delete_movies

    movie = Movie(
        code="ABC-456",
        source_name="database and cloud",
        storage_summary={
            "locations": [
                {
                    "path": "/Movies/A/ABC-456/ABC-456.mp4",
                    "target_folder": "/Movies/A/ABC-456",
                    "storage_location": "A",
                }
            ],
        },
    )
    db_session.add(movie)
    db_session.flush()
    magnet = MovieMagnet(
        movie_id=movie.id,
        magnet_url="magnet:?xt=urn:btih:abc456",
        dedupe_key=uuid.uuid4().hex,
        name="ABC-456",
    )
    db_session.add(magnet)
    db_session.flush()
    movie_id = movie.id

    class Provider:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def delete_file(self, path: str):
            self.deleted.append(path)

    provider = Provider()

    result = delete_movies(
        db=db_session,
        movies=[movie],
        mode="database_and_cloud",
        provider=provider,
    )

    assert result.deleted_movies == 1
    assert result.deleted_magnets == 1
    assert result.cloud_deleted_folders == ["/Movies/A/ABC-456"]
    assert db_session.get(Movie, movie_id) is None


def test_delete_movies_cloud_only_with_storage_location_filter_keeps_other_locations(db_session):
    from backend.app.modules.content.movies.delete_service import delete_movies

    movie = Movie(
        code="ABC-789",
        source_name="shared source",
        storage_summary={
            "storage_status": "stored",
            "last_status": "stored",
            "locations": [
                {
                    "path": "/Movies/A/ABC-789/ABC-789.mp4",
                    "target_folder": "/Movies/A/ABC-789",
                    "storage_location": "A",
                },
                {
                    "path": "/Movies/B/ABC-789/ABC-789.mp4",
                    "target_folder": "/Movies/B/ABC-789",
                    "storage_location": "B",
                },
            ],
        },
    )
    db_session.add(movie)
    db_session.flush()

    class Provider:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def delete_file(self, path: str):
            self.deleted.append(path)

    provider = Provider()

    result = delete_movies(
        db=db_session,
        movies=[movie],
        mode="cloud_only",
        provider=provider,
        storage_location_filter="A",
    )

    assert result.cloud_deleted_folders == ["/Movies/A/ABC-789"]
    assert provider.deleted == ["/Movies/A/ABC-789"]
    assert movie.storage_summary["storage_status"] == "stored"
    assert movie.storage_summary["locations"] == [
        {
            "path": "/Movies/B/ABC-789/ABC-789.mp4",
            "target_folder": "/Movies/B/ABC-789",
            "storage_location": "B",
        }
    ]
