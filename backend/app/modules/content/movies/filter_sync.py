from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from shared.database.models.content import Movie, MovieFilter


def sync_movie_filters(session: Session) -> dict[str, int]:
    actors: set[str] = set()
    tags: set[str] = set()
    directors: set[str] = set()
    makers: set[str] = set()
    series: set[str] = set()

    for movie in session.scalars(select(Movie)).all():
        for value in movie.actors or []:
            if isinstance(value, str) and value.strip():
                actors.add(value.strip())
        for value in movie.tags or []:
            if isinstance(value, str) and value.strip():
                tags.add(value.strip())
        if movie.director and movie.director.strip():
            directors.add(movie.director.strip())
        if movie.maker and movie.maker.strip():
            makers.add(movie.maker.strip())
        if movie.series and movie.series.strip():
            series.add(movie.series.strip())

    session.execute(delete(MovieFilter))
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
    session.flush()

    return {
        "actors": len(actors),
        "tags": len(tags),
        "directors": len(directors),
        "makers": len(makers),
        "series": len(series),
    }
