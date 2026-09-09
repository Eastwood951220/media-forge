from shared.database.models.base import Base


def test_crawler_run_and_content_tables_registered() -> None:
    expected = {
        "crawl_runs",
        "crawl_run_detail_tasks",
        "movies",
        "movie_magnets",
        "movie_filters",
        "actress_profiles",
    }
    assert expected.issubset(set(Base.metadata.tables))


def test_movies_source_task_url_ids_column_registered() -> None:
    assert "source_task_url_ids" in Base.metadata.tables["movies"].columns
