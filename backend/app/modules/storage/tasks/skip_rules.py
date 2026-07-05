from __future__ import annotations

from shared.database.models.content import Movie


def classify_storage_skip(movie: Movie | None) -> str | None:
    if movie is None:
        return "movie_not_found"
    if movie.marked:
        return "movie_marked"
    if not movie.magnets:
        return "no_magnets"
    usable = [magnet for magnet in movie.magnets if magnet.magnet_url]
    if not usable:
        return "no_magnet_url"
    return None
