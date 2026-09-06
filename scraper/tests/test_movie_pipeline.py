from scraper.pipelines.movie_pipeline import MoviePipeline


def test_movie_pipeline_maps_javbus_cover_url_to_cover() -> None:
    item = {
        "source": "javbus",
        "source_url": "https://www.javbus.com/AAA-001",
        "source_name": "AAA 001",
        "code": "AAA-001",
        "cover_url": "https://www.javbus.com/pics/cover/aaa_b.jpg",
    }

    result = MoviePipeline().process_item(item)

    assert result is not None
    assert result["cover"] == "https://www.javbus.com/pics/cover/aaa_b.jpg"


def test_movie_pipeline_keeps_existing_cover_over_cover_url() -> None:
    item = {
        "source": "javbus",
        "source_url": "https://www.javbus.com/AAA-002",
        "source_name": "AAA 002",
        "code": "AAA-002",
        "cover": "https://cdn.example/cover.jpg",
        "cover_url": "https://www.javbus.com/pics/cover/aaa_b.jpg",
    }

    result = MoviePipeline().process_item(item)

    assert result is not None
    assert result["cover"] == "https://cdn.example/cover.jpg"
