from shared.database.models.base import Base
from shared.database.models.content import Movie
from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem


def test_movie_has_scraping_columns() -> None:
    columns = Movie.__table__.columns
    assert "scraping_status" in columns
    assert "scraping_folder" in columns
    assert "scraping_checked_at" in columns
    assert columns["scraping_status"].nullable is True


def test_scraping_tables_are_registered() -> None:
    assert ScrapingTask.__tablename__ == "scraping_tasks"
    assert ScrapingTaskItem.__tablename__ == "scraping_task_items"
    assert "scraping_tasks" in Base.metadata.tables
    assert "scraping_task_items" in Base.metadata.tables

    item_columns = ScrapingTaskItem.__table__.columns
    for name in ("task_id", "movie_id", "movie_code", "movie_title", "status", "source", "folder", "duration_ms", "error_message"):
        assert name in item_columns

    task_columns = ScrapingTask.__table__.columns
    for name in ("status", "total_count", "success_count", "failed_count", "skipped_count", "cancel_requested", "config_snapshot", "created_by"):
        assert name in task_columns
