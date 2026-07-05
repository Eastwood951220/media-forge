from datetime import date
from decimal import Decimal

from backend.app.modules.content.movies.queries import MovieListFilters, list_movies_page
from shared.database.models.content import Movie


def seed_query_movies(db_session) -> None:
    db_session.add_all([
        Movie(
            code="AAA-100",
            source_url="https://example.test/aaa",
            source_name="Alpha Movie",
            release_date=date(2026, 1, 10),
            rating=Decimal("4.8"),
            director="Director A",
            maker="Maker A",
            series="Series A",
            actors=["Actor A"],
            tags=["Tag A"],
        ),
        Movie(
            code="BBB-200",
            source_url="https://example.test/bbb",
            source_name="Beta Movie",
            release_date=date(2026, 2, 20),
            rating=Decimal("2.2"),
            director="Director B",
            maker="Maker B",
            series="Series B",
            actors=["Actor B"],
            tags=["Tag B"],
        ),
    ])
    db_session.commit()


def test_list_movies_page_pushes_scalar_filters_and_sorting(db_session) -> None:
    seed_query_movies(db_session)

    rows, total = list_movies_page(
        db_session,
        MovieListFilters(
            search="Movie",
            rating_min=4,
            release_date_from="2026-01-01",
            release_date_to="2026-01-31",
            director="Director A",
            maker="Maker A",
            series="Series A",
        ),
        sort_by="rating",
        sort_order=-1,
        page=1,
        limit=20,
        skip=None,
    )

    assert total == 1
    assert [movie.code for movie in rows] == ["AAA-100"]


def test_list_movies_page_uses_sql_offset_and_limit_for_scalar_filters(db_session) -> None:
    seed_query_movies(db_session)

    rows, total = list_movies_page(
        db_session,
        MovieListFilters(search="Movie"),
        sort_by="code",
        sort_order="asc",
        page=2,
        limit=1,
        skip=None,
    )

    assert total == 2
    assert [movie.code for movie in rows] == ["BBB-200"]


def test_list_movies_page_preserves_storage_status_fallback(db_session) -> None:
    db_session.add_all([
        Movie(code="STORE-1", source_url="https://example.test/store1", source_name="Stored", storage_summary={"storage_status": "stored", "last_status": "stored"}),
        Movie(code="STORE-2", source_url="https://example.test/store2", source_name="Missing", storage_summary={}),
    ])
    db_session.commit()

    rows, total = list_movies_page(
        db_session,
        MovieListFilters(storage_status="not_stored"),
        sort_by="code",
        sort_order="asc",
        page=1,
        limit=20,
        skip=None,
    )

    assert total == 1
    assert [movie.code for movie in rows] == ["STORE-2"]


def test_list_movies_page_preserves_sqlite_array_filter_fallback(db_session) -> None:
    seed_query_movies(db_session)

    rows, total = list_movies_page(
        db_session,
        MovieListFilters(actors="Actor A", tags_not="Tag B"),
        sort_by="code",
        sort_order="asc",
        page=1,
        limit=20,
        skip=None,
    )

    assert total == 1
    assert [movie.code for movie in rows] == ["AAA-100"]
