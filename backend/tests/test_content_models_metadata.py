from shared.database.models.base import Base


def test_crawler_run_and_content_tables_registered() -> None:
    expected = {
        "crawl_runs",
        "crawl_run_detail_tasks",
        "movies",
        "movie_magnets",
        "movie_filters",
    }
    assert expected.issubset(set(Base.metadata.tables))
