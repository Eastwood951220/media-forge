"""Repository for maintaining the unified movie_filters table."""

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from shared.database.models.content import Movie, MovieFilter
from shared.database.session import get_session_factory


def sync_movie_filters(session: Session | None = None) -> dict[str, int]:
    """Scan all movies, deduplicate filter values, and write to movie_filters.

    Args:
        session: Optional SQLAlchemy session. If None, creates a new one.

    Returns:
        Dict with counts per filter type: actors, tags, directors, makers, series.
    """
    close_session = session is None
    if session is None:
        session = get_session_factory()()

    try:
        # Collect unique values
        actors: set[str] = set()
        tags: set[str] = set()
        directors: set[str] = set()
        makers: set[str] = set()
        series: set[str] = set()

        # Query all movies
        movies = session.scalars(select(Movie)).all()

        for movie in movies:
            # Array fields
            for val in (movie.actors or []):
                if isinstance(val, str) and val.strip():
                    actors.add(val.strip())

            for val in (movie.tags or []):
                if isinstance(val, str) and val.strip():
                    tags.add(val.strip())

            # Scalar fields
            if movie.director and isinstance(movie.director, str) and movie.director.strip():
                directors.add(movie.director.strip())

            if movie.maker and isinstance(movie.maker, str) and movie.maker.strip():
                makers.add(movie.maker.strip())

            if movie.series and isinstance(movie.series, str) and movie.series.strip():
                series.add(movie.series.strip())

        # Delete existing filters
        session.execute(delete(MovieFilter))

        # Insert new filters
        for name in sorted(actors):
            session.add(MovieFilter(type="actor", name=name, count=0))

        for name in sorted(tags):
            session.add(MovieFilter(type="tag", name=name, count=0))

        for name in sorted(directors):
            session.add(MovieFilter(type="director", name=name, count=0))

        for name in sorted(makers):
            session.add(MovieFilter(type="maker", name=name, count=0))

        for name in sorted(series):
            session.add(MovieFilter(type="series", name=name, count=0))

        session.commit()

        return {
            "actors": len(actors),
            "tags": len(tags),
            "directors": len(directors),
            "makers": len(makers),
            "series": len(series),
        }
    except Exception:
        session.rollback()
        raise
    finally:
        if close_session:
            session.close()
