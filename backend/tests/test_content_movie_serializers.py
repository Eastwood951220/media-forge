import uuid
from datetime import date
from decimal import Decimal

from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.content.movies.serializers import serialize_movie
from backend.tests.conftest import TestingSessionLocal
from shared.database.models.content import Movie, MovieMagnet


def test_serialize_movie_includes_magnets_and_storage_locations(admin_user) -> None:
    session = TestingSessionLocal()
    task_id = uuid.uuid4()
    movie = Movie(
        code="AAA-001",
        source_url="https://javdb.com/v/aaa",
        source_name="测试电影",
        release_date=date(2026, 1, 1),
        duration=120,
        director="导演A",
        maker="片商A",
        series="系列A",
        rating=Decimal("4.5"),
        actors=["演员A"],
        tags=["标签A"],
        source_task_ids=[task_id],
        storage_summary={"storage_status": "stored"},
    )
    session.add(movie)
    session.add(CrawlTask(id=task_id, name="任务A", owner_id=admin_user.id, storage_location="/target/A"))
    session.flush()
    session.add(
        MovieMagnet(
            movie_id=movie.id,
            magnet_url="magnet:?xt=urn:btih:abc",
            dedupe_key="abc",
            name="磁力A",
            selected=True,
        )
    )
    session.commit()

    payload = serialize_movie(movie, include_magnets=True, db=session)

    assert payload["id"] == str(movie.id)
    assert payload["code"] == "AAA-001"
    assert payload["storage_status"] == "stored"
    assert payload["storage_locations"] == ["/target/A"]
    assert payload["magnets"][0]["magnet_url"].startswith("magnet:")
    assert payload["selected_magnet_dedupe_key"] == "abc"

    session.close()
