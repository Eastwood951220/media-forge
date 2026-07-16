from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.content.movies.storage_locations import build_movie_storage_target_folders
from shared.database.models.content import Movie


def test_build_movie_storage_target_folders_inserts_vr_directory_for_vr_movies(db_session, test_user) -> None:
    task = CrawlTask(name="vr-task", owner_id=test_user.id, storage_location="日本/巨乳")
    db_session.add(task)
    db_session.flush()
    movie = Movie(
        code="VR-001",
        source_name="VR Movie",
        tags=["VR"],
        source_task_ids=[task.id],
    )
    db_session.add(movie)
    db_session.flush()

    folders = build_movie_storage_target_folders(db_session, movie, {"target_folder": "/Movies"})

    assert [item["target_folder"] for item in folders] == [
        "/Movies/日本/巨乳/VR/VR-001",
        "/Movies/日本/巨乳/VR/VR-001-C",
        "/Movies/日本/巨乳/VR/VR-001-U",
        "/Movies/日本/巨乳/VR/VR-001-UC",
    ]
