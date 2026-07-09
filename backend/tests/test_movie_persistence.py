import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from backend.app.modules.content.movies.persistence import (
    append_source_task_id,
    append_source_task_ids_for_codes,
    compute_magnet_weight,
    extract_info_hash,
    sync_movie_filters,
    upsert_magnets,
    upsert_movie,
    upsert_movie_with_magnets,
)
from backend.tests.conftest import TestingSessionLocal
from shared.database.models.content import Movie, MovieFilter, MovieMagnet


def test_extract_info_hash_from_magnet_url() -> None:
    assert extract_info_hash("magnet:?xt=urn:btih:ABCDEF&dn=name") == "abcdef"
    assert extract_info_hash("") == ""
    assert extract_info_hash(None) == ""


def test_upsert_movie_inserts_and_reuses_by_code() -> None:
    session = TestingSessionLocal()
    first_id = upsert_movie(session, {
        "code": "AAA-001",
        "source_url": "https://javdb.com/v/aaa001",
        "source_name": "AAA 001",
        "release_date": date(2026, 1, 1),
        "duration": 120,
        "rating": Decimal("4.5"),
        "actors": ["演员A"],
        "tags": ["标签A"],
    })
    second_id = upsert_movie(session, {
        "code": "AAA-001",
        "source_url": "https://javdb.com/v/aaa001-copy",
        "source_name": "AAA 001 copy",
    })

    assert second_id == first_id
    assert session.scalar(select(Movie).where(Movie.code == "AAA-001")).id == first_id

    session.close()


def test_append_source_task_id_adds_unique_id() -> None:
    session = TestingSessionLocal()
    movie_id = upsert_movie(session, {"code": "SRC-001", "source_url": "https://javdb.com/v/src001"})
    task_id = uuid.uuid4()

    assert append_source_task_id(session, "SRC-001", task_id) is True
    assert append_source_task_id(session, "SRC-001", task_id) is False

    movie = session.get(Movie, movie_id)
    assert [str(value) for value in movie.source_task_ids] == [str(task_id)]

    session.close()


def test_upsert_magnets_dedupes_updates_and_selects_best() -> None:
    session = TestingSessionLocal()
    movie_id = upsert_movie(session, {"code": "MAG-001", "source_url": "https://javdb.com/v/mag001"})

    saved_count = upsert_magnets(session, movie_id, {"code": "MAG-001"}, [
        {
            "magnet": "magnet:?xt=urn:btih:1111111111111111111111111111111111111111",
            "name": "small",
            "size_text": "100MB",
            "tags": [],
        },
        {
            "magnet": "magnet:?xt=urn:btih:2222222222222222222222222222222222222222",
            "name": "large subtitles",
            "size_text": "3GB",
            "tags": ["中字"],
        },
    ])

    assert saved_count == 2
    upsert_magnets(session, movie_id, {"code": "MAG-001"}, [
        {
            "magnet": "magnet:?xt=urn:btih:1111111111111111111111111111111111111111",
            "name": "small updated",
            "size_text": "200MB",
            "tags": [],
        }
    ])

    magnets = session.scalars(select(MovieMagnet).where(MovieMagnet.movie_id == movie_id)).all()
    assert len(magnets) == 2
    assert any(magnet.name == "small updated" for magnet in magnets)
    selected = [magnet for magnet in magnets if magnet.selected]
    assert len(selected) == 1
    assert selected[0].name == "large subtitles"
    assert compute_magnet_weight({"name": "中字", "size_text": "3GB", "tags": ["中字"]}) > compute_magnet_weight({"name": "plain", "size_text": "100MB"})

    session.close()


def test_upsert_movie_with_magnets_persists_movie_and_magnets() -> None:
    session = TestingSessionLocal()

    movie_id = upsert_movie_with_magnets(session, {
        "code": "FULL-001",
        "source_url": "https://javdb.com/v/full001",
        "source_name": "FULL 001",
        "magnets": [
            {
                "magnet": "magnet:?xt=urn:btih:3333333333333333333333333333333333333333",
                "name": "FULL 001",
                "size_text": "1.2GB",
            }
        ],
    })

    assert session.get(Movie, movie_id).code == "FULL-001"
    assert len(session.scalars(select(MovieMagnet).where(MovieMagnet.movie_id == movie_id)).all()) == 1

    session.close()


def test_sync_movie_filters_rebuilds_filter_cache() -> None:
    session = TestingSessionLocal()
    session.add(Movie(
        code="FILTER-001",
        source_url="https://javdb.com/v/filter001",
        source_name="Filter 001",
        actors=["演员A", "演员B"],
        tags=["标签A"],
        director="导演A",
        maker="片商A",
        series="系列A",
    ))
    session.commit()

    result = sync_movie_filters(session)

    assert result == {"actors": 2, "tags": 1, "directors": 1, "makers": 1, "series": 1}
    assert session.scalar(select(MovieFilter).where(MovieFilter.type == "actor", MovieFilter.name == "演员A")) is not None

    session.close()


def test_magnet_identity_and_scoring_helpers() -> None:
    from backend.app.modules.content.movies.magnet_identity import build_magnet_dedupe_key, extract_info_hash
    from backend.app.modules.content.movies.magnet_scoring import compute_magnet_weight, parse_size_mb

    assert extract_info_hash("magnet:?xt=urn:btih:ABCDEF") == "abcdef"
    assert parse_size_mb("1.5 GB") == 1536
    assert parse_size_mb("1024 KB") == 1
    assert parse_size_mb("1 TB") == 1024 * 1024
    assert build_magnet_dedupe_key("movie-1", {"name": "a", "size_text": "1 GB"})
    assert compute_magnet_weight({"name": "ABC 中文字幕", "size_text": "3 GB", "file_count": 1}) > compute_magnet_weight({"name": "ABC", "size_text": "500 MB", "file_count": 10})


def test_movie_persistence_facade_exports_existing_public_functions() -> None:
    from backend.app.modules.content.movies import persistence
    from backend.app.modules.content.movies import magnet_identity, magnet_persistence, magnet_scoring, movie_persistence, filter_sync

    assert persistence.extract_info_hash is magnet_identity.extract_info_hash
    assert persistence.compute_magnet_weight is magnet_scoring.compute_magnet_weight
    assert persistence.upsert_magnets is magnet_persistence.upsert_magnets
    assert persistence.upsert_movie is movie_persistence.upsert_movie
    assert persistence.append_source_task_id is movie_persistence.append_source_task_id
    assert persistence.append_source_task_ids_for_codes is movie_persistence.append_source_task_ids_for_codes
    assert persistence.sync_movie_filters is filter_sync.sync_movie_filters


def test_append_source_task_ids_for_codes_adds_unique_ids_to_existing_movies() -> None:
    session = TestingSessionLocal()
    task_id = uuid.uuid4()
    existing_task_id = uuid.uuid4()
    first_id = upsert_movie(session, {"code": "BULK-001", "source_url": "https://javdb.com/v/bulk001"})
    second_id = upsert_movie(session, {
        "code": "BULK-002",
        "source_url": "https://javdb.com/v/bulk002",
        "source_task_ids": [existing_task_id],
    })
    session.commit()

    changed = append_source_task_ids_for_codes(
        session,
        ["BULK-001", "BULK-002", "BULK-001", "MISSING-001", None, ""],
        task_id,
    )
    session.commit()

    first = session.get(Movie, first_id)
    second = session.get(Movie, second_id)

    assert changed == {"BULK-001", "BULK-002"}
    assert [str(value) for value in first.source_task_ids] == [str(task_id)]
    assert [str(value) for value in second.source_task_ids] == [str(existing_task_id), str(task_id)]

    changed_again = append_source_task_ids_for_codes(session, ["BULK-001", "BULK-002"], task_id)
    session.commit()

    assert changed_again == set()
    assert [str(value) for value in first.source_task_ids] == [str(task_id)]
    assert [str(value) for value in second.source_task_ids] == [str(existing_task_id), str(task_id)]

    session.close()
