import pytest

from backend.app.modules.jellyfin.sync import sync_jellyfin_watch_state
from backend.app.models.jellyfin_sync import JellyfinSyncState
from shared.database.models.content import Movie


class FakeJellyfin:
    def __init__(self, pages):
        self.pages = pages
        self.starts = []

    def get_root_user_id(self):
        return "root-id"

    def get_items(self, user_id, start, limit):
        assert user_id == "root-id"
        self.starts.append(start)
        return self.pages[start]


def _movie(db_session, code, folder):
    movie = Movie(code=code, source_name=code, scraping_folder=folder)
    db_session.add(movie)
    db_session.commit()
    return movie


def _item(item_id, path, *, played=False, position=0):
    return {"Id": item_id, "Path": path, "UserData": {"Played": played, "PlaybackPositionTicks": position}}


def test_sync_maps_four_states_by_path_and_pages(db_session) -> None:
    movies = [
        _movie(db_session, "A-001", "/media/A-001"),
        _movie(db_session, "B-002", "/media/B-002"),
        _movie(db_session, "C-003", "/media/C-003"),
        _movie(db_session, "D-004", "/media/D-004"),
    ]
    client = FakeJellyfin({
        0: {"Items": [_item("a", "/media/A-001/A-001.strm", played=True), _item("b", "/media/B-002/B-002.strm", position=500)], "TotalRecordCount": 3},
        2: {"Items": [_item("c", "/media/C-003/C-003.strm")], "TotalRecordCount": 3},
    })
    result = sync_jellyfin_watch_state(db_session, client, page_size=2)
    db_session.expire_all()
    assert [db_session.get(Movie, movie.id).jellyfin_watch_status for movie in movies] == [
        "played", "in_progress", "unplayed", "not_in_library",
    ]
    assert db_session.get(Movie, movies[1].id).jellyfin_playback_position_ticks == 500
    assert client.starts == [0, 2]
    assert result.matched_count == 3


def test_sync_matches_same_movie_across_different_mount_roots(db_session) -> None:
    movie = _movie(db_session, "A-001", "/vol1/media/actor/A-001")
    client = FakeJellyfin({0: {"Items": [
        _item("jf-a", "/media/actor/A-001/A-001.strm", played=True),
    ], "TotalRecordCount": 1}})

    result = sync_jellyfin_watch_state(db_session, client)

    db_session.refresh(movie)
    assert movie.jellyfin_item_id == "jf-a"
    assert movie.jellyfin_watch_status == "played"
    assert result.matched_count == 1


def test_sync_matches_unique_code_without_scraping_folder(db_session) -> None:
    movie = _movie(db_session, "A-001", None)
    client = FakeJellyfin({0: {"Items": [
        _item("jf-a", "/media/actor/A-001/A-001.strm", position=500),
    ], "TotalRecordCount": 1}})

    sync_jellyfin_watch_state(db_session, client)

    db_session.refresh(movie)
    assert movie.jellyfin_item_id == "jf-a"
    assert movie.jellyfin_watch_status == "in_progress"


def test_sync_keeps_duplicate_code_matches_unknown(db_session) -> None:
    movie = _movie(db_session, "A-001", "/vol1/media/actor/A-001")
    client = FakeJellyfin({0: {"Items": [
        _item("first", "/media/other/A-001/one.strm", played=True),
        _item("second", "/media/another/A-001/two.strm"),
    ], "TotalRecordCount": 2}})

    result = sync_jellyfin_watch_state(db_session, client)

    db_session.refresh(movie)
    assert movie.jellyfin_item_id is None
    assert movie.jellyfin_watch_status is None
    assert result.ambiguous_count == 1


def test_sync_leaves_ambiguous_movie_unknown(db_session) -> None:
    movie = _movie(db_session, "A-001", "/media/A-001")
    client = FakeJellyfin({0: {"Items": [
        _item("first", "/media/A-001/one.strm", played=True),
        _item("second", "/media/A-001/two.strm"),
    ], "TotalRecordCount": 2}})
    sync_jellyfin_watch_state(db_session, client)
    db_session.refresh(movie)
    assert movie.jellyfin_watch_status is None
    assert movie.jellyfin_item_id is None


def test_failed_sync_preserves_last_snapshot(db_session) -> None:
    movie = _movie(db_session, "A-001", "/media/A-001")
    movie.jellyfin_watch_status = "played"
    db_session.commit()

    class BrokenJellyfin:
        def get_root_user_id(self):
            raise RuntimeError("offline")

    with pytest.raises(RuntimeError, match="offline"):
        sync_jellyfin_watch_state(db_session, BrokenJellyfin())
    db_session.refresh(movie)
    assert movie.jellyfin_watch_status == "played"


def test_movie_list_filters_jellyfin_status(client, auth_headers, db_session) -> None:
    played = _movie(db_session, "A-001", "/media/A-001")
    other = _movie(db_session, "B-002", "/media/B-002")
    played.jellyfin_watch_status = "played"
    other.jellyfin_watch_status = "unplayed"
    db_session.commit()
    response = client.get("/api/content/movies", params={"jellyfin_watch_status": "played"}, headers=auth_headers)
    assert response.status_code == 200
    assert [row["code"] for row in response.json()["rows"]] == ["A-001"]
    assert response.json()["rows"][0]["jellyfin_watch_status"] == "played"


def test_storage_sync_selection_respects_jellyfin_filter(db_session) -> None:
    from backend.app.modules.content.movies.storage_sync_service import select_movies_for_storage_sync

    played = _movie(db_session, "A-001", "/media/A-001")
    other = _movie(db_session, "B-002", "/media/B-002")
    played.jellyfin_watch_status = "played"
    other.jellyfin_watch_status = "unplayed"
    db_session.commit()
    selected = select_movies_for_storage_sync(
        db_session, movie_ids=None, filters={"jellyfin_watch_status": "played"},
    )
    assert [movie.id for movie in selected] == [played.id]


def test_duplicate_local_folder_does_not_assign_watch_state(db_session) -> None:
    first = _movie(db_session, "A-001", "/media/shared")
    second = _movie(db_session, "B-002", "/media/shared")
    client = FakeJellyfin({0: {"Items": [_item("jf", "/media/shared/movie.strm", played=True)], "TotalRecordCount": 1}})
    sync_jellyfin_watch_state(db_session, client)
    db_session.refresh(first)
    db_session.refresh(second)
    assert first.jellyfin_watch_status is None
    assert second.jellyfin_watch_status is None


def test_config_change_hides_old_watch_status_and_filter(client, auth_headers, db_session) -> None:
    movie = _movie(db_session, "A-001", "/media/A-001")
    movie.jellyfin_watch_status = "played"
    db_session.add(JellyfinSyncState(id=1, status="success", config_fingerprint="old-fingerprint"))
    db_session.commit()
    plain = client.get("/api/content/movies", headers=auth_headers)
    assert plain.json()["rows"][0]["jellyfin_watch_status"] is None
    filtered = client.get("/api/content/movies", params={"jellyfin_watch_status": "played"}, headers=auth_headers)
    assert filtered.json()["total"] == 0
